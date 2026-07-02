"""OAuth2 token cache for Toss Open API."""

import json
import threading
import datetime
from pathlib import Path

import requests

from broker.rate_limiter import RateLimiter

BASE_URL = "https://openapi.tossinvest.com"
REFRESH_BUFFER = datetime.timedelta(minutes=5)


class TossAuth:
    def __init__(self, client_id: str, client_secret: str, cache_path: Path, limiter: RateLimiter):
        self.client_id = client_id
        self.client_secret = client_secret
        self.cache_path = cache_path
        self.limiter = limiter
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at: datetime.datetime | None = None
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_cache()

    def _load_cache(self) -> None:
        token, exp = self._read_cache_file()
        if token and exp and exp > datetime.datetime.now().astimezone() + REFRESH_BUFFER:
            self._token = token
            self._expires_at = exp

    def _read_cache_file(self) -> tuple[str | None, datetime.datetime | None]:
        if not self.cache_path.exists():
            return None, None
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            exp = datetime.datetime.fromisoformat(data["expires_at"])
            token = data.get("access_token")
            if not token:
                return None, None
            if exp.tzinfo is None:
                exp = exp.astimezone()
            return token, exp
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
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
            now = datetime.datetime.now().astimezone()
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
        status = self.get_status()
        if status["ok"]:
            return status
        if status["reason"] in ("expired", "missing", "expiring_soon"):
            try:
                self.get_token()
            except Exception as exc:
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
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump({
                "access_token": token,
                "expires_at": expires_at.isoformat(),
            }, f, indent=2)

    def get_token(self) -> str:
        with self._lock:
            now = datetime.datetime.now().astimezone()
            if self._token and self._expires_at and self._expires_at > now + REFRESH_BUFFER:
                return self._token
            return self._refresh()

    def _refresh(self) -> str:
        self.limiter.acquire("AUTH")
        res = requests.post(
            f"{BASE_URL}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        if not res.ok:
            raise requests.HTTPError(
                f"Toss token failed ({res.status_code}): {res.text[:500]}",
                response=res,
            )
        body = res.json()
        token = body["access_token"]
        expires_in = int(body.get("expires_in", 3600))
        expires_at = datetime.datetime.now().astimezone() + datetime.timedelta(seconds=expires_in - 60)
        self._token = token
        self._expires_at = expires_at
        self._save_cache(token, expires_at)
        return token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
            self._expires_at = None
