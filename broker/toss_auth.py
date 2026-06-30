"""OAuth2 token cache for Toss Open API."""

import json
import threading
import datetime
from pathlib import Path

import requests

from broker.rate_limiter import RateLimiter

BASE_URL = "https://openapi.tossinvest.com"


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
        if not self.cache_path.exists():
            return
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            exp = datetime.datetime.fromisoformat(data["expires_at"])
            if exp > datetime.datetime.now().astimezone() + datetime.timedelta(minutes=5):
                self._token = data["access_token"]
                self._expires_at = exp
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            pass

    def _save_cache(self, token: str, expires_at: datetime.datetime) -> None:
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump({
                "access_token": token,
                "expires_at": expires_at.isoformat(),
            }, f, indent=2)

    def get_token(self) -> str:
        with self._lock:
            now = datetime.datetime.now().astimezone()
            if self._token and self._expires_at and self._expires_at > now + datetime.timedelta(minutes=5):
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
