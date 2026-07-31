"""OAuth2 token cache for Toss Open API."""

from __future__ import annotations

import datetime
import json
import logging
import threading
import time
from pathlib import Path

import requests

from broker.rate_limiter import RateLimiter
from config.json_io import load_json, save_json
from config.toss_credentials import normalize_toss_credentials

logger = logging.getLogger(__name__)

BASE_URL = "https://openapi.tossinvest.com"
REFRESH_BUFFER = datetime.timedelta(minutes=5)
EARLY_REFRESH_SECS = 60


def _parse_iso_datetime(raw: str) -> datetime.datetime:
    """Parse cache expires_at — Py3.10 Z suffix and naive values included."""
    text = str(raw).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    dt = datetime.datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone()


def _expires_at_from_ttl(expires_in: int) -> datetime.datetime:
    """Map OAuth expires_in to local cache expiry (early refresh margin, min 1s)."""
    ttl = max(int(expires_in), 0)
    cache_secs = max(ttl - EARLY_REFRESH_SECS, 1)
    return datetime.datetime.now().astimezone() + datetime.timedelta(seconds=cache_secs)


def _format_token_error(res: requests.Response) -> str:
    status = res.status_code
    try:
        body = res.json()
    except ValueError:
        body = None

    if isinstance(body, dict):
        err = str(body.get("error") or "")
        desc = str(body.get("error_description") or body.get("message") or "")
        if status == 403 or err == "access_denied":
            if "ip" in desc.lower():
                return "403 허용 IP 아님 — WTS Open API > 허용 IP 관리 확인"
            return f"403 접근 거부{': ' + desc if desc else ''}"
        if status == 401 or err == "invalid_client":
            return (
                "401 client_id/secret 오류 — WTS Open API 키 재확인 "
                "(ID=c_/tsck_, SECRET=s_, 뒤바뀜·재발급 여부)"
            )
        if err or desc:
            return f"{status} {err or 'error'}{': ' + desc if desc else ''}"

    snippet = (res.text or "").strip().replace("\n", " ")[:160]
    return f"Toss token failed ({status}){': ' + snippet if snippet else ''}"


class TossAuth:
    def __init__(self, client_id: str, client_secret: str, cache_path: Path, limiter: RateLimiter):
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.cache_path = cache_path
        self.limiter = limiter
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at: datetime.datetime | None = None
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_cache()

    def _now(self) -> datetime.datetime:
        return datetime.datetime.now().astimezone()

    def _valid_cached(self) -> bool:
        return bool(
            self._token
            and self._expires_at
            and self._expires_at > self._now() + REFRESH_BUFFER
        )

    def _load_cache(self) -> None:
        token, exp = self._read_cache_file()
        if token and exp and exp > self._now() + REFRESH_BUFFER:
            self._token = token
            self._expires_at = exp

    def _read_cache_file(self) -> tuple[str | None, datetime.datetime | None]:
        if not self.cache_path.exists():
            return None, None
        data = load_json(self.cache_path, None)
        if not isinstance(data, dict):
            return None, None
        try:
            token = data.get("access_token")
            exp_raw = data.get("expires_at")
            if not token or not exp_raw:
                return None, None
            exp = _parse_iso_datetime(exp_raw)
            return str(token), exp
        except (TypeError, ValueError):
            return None, None

    def _cached_token(self) -> tuple[str | None, datetime.datetime | None]:
        """메모리·파일 캐시에서 토큰·만료 시각 (재발급 없음)."""
        if self._token and self._expires_at:
            return self._token, self._expires_at
        return self._read_cache_file()

    def get_status(self) -> dict:
        """토큰 사용 가능 여부·남은 시간 (네트워크 호출 없음)."""
        with self._lock:
            if not self.client_id or not self.client_secret:
                return {
                    "ok": False,
                    "reason": "no_credentials",
                    "remaining_seconds": 0,
                    "expires_at": None,
                }

            token, expires_at = self._cached_token()
            now = self._now()
            if not token or not expires_at:
                return {
                    "ok": False,
                    "reason": "missing",
                    "remaining_seconds": 0,
                    "expires_at": None,
                }

            remaining = int((expires_at - now).total_seconds())
            if remaining <= 0:
                return {
                    "ok": False,
                    "reason": "expired",
                    "remaining_seconds": 0,
                    "expires_at": expires_at,
                }

            buffer_secs = int(REFRESH_BUFFER.total_seconds())
            ok = remaining > buffer_secs
            return {
                "ok": ok,
                "reason": "valid" if ok else "expiring_soon",
                "remaining_seconds": remaining,
                "expires_at": expires_at,
            }

    def ensure_token_status(self) -> dict:
        """만료·없음이면 재발급 시도 후 최종 상태."""
        self._drop_expired_memory()
        status = self.get_status()
        if status["ok"] or status.get("reason") == "expiring_soon":
            return status
        if not self.client_id or not self.client_secret:
            return status
        if status["reason"] in ("expired", "missing"):
            try:
                self.get_token()
            except Exception as exc:
                logger.warning("Toss token refresh failed: %s", exc)
                return {
                    "ok": False,
                    "reason": "refresh_failed",
                    "remaining_seconds": 0,
                    "expires_at": None,
                    "error": str(exc),
                }
            return self.get_status()
        return status

    def _save_cache(self, token: str, expires_at: datetime.datetime) -> None:
        save_json(
            self.cache_path,
            {
                "access_token": token,
                "expires_at": expires_at.isoformat(),
            },
            compact=False,
        )

    def _delete_cache_file(self) -> None:
        try:
            self.cache_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("failed to delete token cache %s", self.cache_path)

    def sync_credentials(self, client_id: str, client_secret: str) -> None:
        """Settings 재로드 후 client_id/secret 반영 (형식·뒤바뀜 자동 교정)."""
        cid, sec, notes = normalize_toss_credentials(client_id, client_secret)
        for note in notes:
            logger.warning("Toss credentials: %s", note)
        with self._lock:
            changed = cid != self.client_id or sec != self.client_secret
            self.client_id = cid
            self.client_secret = sec
        if changed and cid and sec:
            self.invalidate()
            self._delete_cache_file()
            logger.info("Toss credentials changed — token cache cleared")

    def _drop_expired_memory(self) -> None:
        with self._lock:
            if self._token and self._expires_at and self._expires_at <= self._now():
                self._token = None
                self._expires_at = None

    def _parse_token_response(self, res: requests.Response) -> tuple[str, datetime.datetime]:
        try:
            body = res.json()
        except ValueError as exc:
            snippet = (res.text or "").strip().replace("\n", " ")[:160]
            raise requests.HTTPError(
                f"Toss token response is not JSON ({res.status_code}): {snippet}",
            ) from exc

        if not isinstance(body, dict):
            raise requests.HTTPError(f"Toss token response invalid: {body!r}")

        token = body.get("access_token")
        if not token and isinstance(body.get("result"), dict):
            nested = body["result"]
            token = nested.get("access_token")
            expires_raw = nested.get("expires_in", body.get("expires_in", 3600))
        else:
            expires_raw = body.get("expires_in", 3600)

        if not token:
            raise requests.HTTPError(
                f"Toss token response missing access_token: {json.dumps(body)[:200]}",
            )
        expires_at = _expires_at_from_ttl(int(expires_raw))
        return str(token), expires_at

    def _post_token_request(self, *, use_basic: bool) -> requests.Response:
        payload = {"grant_type": "client_credentials"}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        kwargs: dict = {
            "url": f"{BASE_URL}/oauth2/token",
            "data": payload,
            "headers": headers,
            "timeout": 15,
        }
        if use_basic:
            kwargs["auth"] = (self.client_id, self.client_secret)
        else:
            payload["client_id"] = self.client_id
            payload["client_secret"] = self.client_secret
        return requests.post(**kwargs)

    def _request_token(self) -> tuple[str, datetime.datetime]:
        if not self.client_id or not self.client_secret:
            raise ValueError("TOSS_CLIENT_ID/SECRET 없음 — .env 확인")

        last_err: Exception | None = None
        for attempt in range(3):
            self.limiter.acquire("AUTH")
            try:
                res = self._post_token_request(use_basic=False)
            except requests.RequestException as exc:
                last_err = exc
                if attempt >= 2:
                    raise
                time.sleep(1 + attempt)
                continue

            if res.status_code == 401:
                logger.info("Toss token form auth 401 — retry with HTTP Basic")
                try:
                    res = self._post_token_request(use_basic=True)
                except requests.RequestException as exc:
                    last_err = exc
                    if attempt >= 2:
                        raise
                    time.sleep(1 + attempt)
                    continue

            if res.status_code == 429:
                retry = max(int(res.headers.get("Retry-After", "2") or 2), 1)
                logger.warning("Toss AUTH rate limited — retry in %ss", retry)
                if attempt >= 2:
                    raise requests.HTTPError(_format_token_error(res), response=res)
                time.sleep(retry)
                continue

            if not res.ok:
                raise requests.HTTPError(_format_token_error(res), response=res)

            return self._parse_token_response(res)

        if last_err:
            raise last_err
        raise RuntimeError("Toss token request failed")

    def _apply_token(self, token: str, expires_at: datetime.datetime) -> None:
        with self._lock:
            self._token = token
            self._expires_at = expires_at
            self._save_cache(token, expires_at)
        logger.info(
            "Toss access token refreshed (expires %s KST)",
            expires_at.strftime("%Y-%m-%d %H:%M"),
        )

    def get_token(self) -> str:
        self._drop_expired_memory()
        with self._lock:
            if self._valid_cached():
                return self._token  # type: ignore[return-value]

        token, expires_at = self._request_token()
        self._apply_token(token, expires_at)
        return token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
            self._expires_at = None

    def force_refresh(self) -> dict:
        """새 토큰 발급 — 실패 시 기존 캐시 유지."""
        if not self.client_id or not self.client_secret:
            return {
                "ok": False,
                "reason": "no_credentials",
                "remaining_seconds": 0,
                "expires_at": None,
                "error": "TOSS_CLIENT_ID/SECRET 없음",
            }
        try:
            token, expires_at = self._request_token()
        except Exception as exc:
            logger.warning("Toss force_refresh failed: %s", exc)
            stale = self.get_status()
            return {
                "ok": False,
                "reason": "refresh_failed",
                "remaining_seconds": int(stale.get("remaining_seconds") or 0),
                "expires_at": stale.get("expires_at"),
                "error": str(exc),
            }
        self._apply_token(token, expires_at)
        return self.get_status()

    def probe_refresh(self) -> dict:
        """진단 — 발급 시도만 (캐시 교체 없음)."""
        if not self.client_id or not self.client_secret:
            return {"ok": False, "step": "credentials", "error": "TOSS_CLIENT_ID/SECRET 없음"}
        try:
            token, expires_at = self._request_token()
        except Exception as exc:
            return {"ok": False, "step": "oauth2/token", "error": str(exc)}
        return {
            "ok": True,
            "step": "oauth2/token",
            "expires_at": expires_at.isoformat(),
            "token_len": len(token),
        }
