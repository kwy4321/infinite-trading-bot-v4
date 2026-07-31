"""Server public IP — WTS 허용 IP 등록용."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_IP_ENDPOINTS = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
)


def fetch_public_ip(*, timeout: float = 5.0) -> str:
    for url in _IP_ENDPOINTS:
        try:
            res = requests.get(url, timeout=timeout)
            if res.ok:
                text = (res.text or "").strip()
                if text:
                    return text
        except requests.RequestException as exc:
            logger.debug("public IP fetch failed (%s): %s", url, exc)
    return ""
