"""Toss token error parsing — OAuth2 표준 / BFF envelope 두 형태 (no network)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

from broker.toss_auth import _extract_token_error, _format_token_error


def _res(status: int, body, headers: dict | None = None) -> requests.Response:
    res = requests.Response()
    res.status_code = status
    res._content = json.dumps(body, ensure_ascii=False).encode()
    res.headers["Content-Type"] = "application/json"
    for k, v in (headers or {}).items():
        res.headers[k] = v
    return res


def test_oauth2_flat_error() -> None:
    res = _res(401, {"error": "invalid_client", "error_description": "Bad credentials"})
    info = _extract_token_error(res)
    assert info["code"] == "invalid_client"
    assert info["message"] == "Bad credentials"
    text = _format_token_error(res)
    assert "invalid_client" in text
    assert "재발급" in text


def test_bff_envelope_error() -> None:
    res = _res(
        401,
        {"error": {"requestId": "01HXYZ", "code": "edge-blocked", "message": "허용되지 않은 요청입니다."}},
    )
    info = _extract_token_error(res)
    assert info["code"] == "edge-blocked"
    assert info["message"] == "허용되지 않은 요청입니다."
    assert info["request_id"] == "01HXYZ"
    text = _format_token_error(res)
    assert "edge-blocked" in text
    assert "허용 IP" in text


def test_non_json_body() -> None:
    res = requests.Response()
    res.status_code = 502
    res._content = b"<html>Bad Gateway</html>"
    info = _extract_token_error(res)
    assert info["code"] == ""
    assert "Bad Gateway" in info["snippet"]
    assert "502" in _format_token_error(res)


def test_no_fabricated_credential_blame() -> None:
    """401 이라도 토스가 IP 차단이라고 하면 키 오류로 단정하지 않는다."""
    res = _res(401, {"error": {"code": "edge-blocked", "message": "허용되지 않은 요청입니다."}})
    text = _format_token_error(res)
    assert "client_id/secret" not in text


def main() -> int:
    test_oauth2_flat_error()
    test_bff_envelope_error()
    test_non_json_body()
    test_no_fabricated_credential_blame()
    print("test_toss_token_error: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
