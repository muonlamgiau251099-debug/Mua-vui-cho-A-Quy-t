import json
import logging

import httpx
import pytest

from app.config import Settings
from app.hardening import InsecureConfigError, RedactFilter, check_production_settings, redact
from app.main import create_app


def test_redact_hides_tokens_cookies_and_cards_including_nested_arrays() -> None:
    message = json.dumps(
        {
            "type": "game.state",
            "payload": {
                "state": {"yourHand": [1, 5, 9], "hands": [[1, 2], [3, [4]]], "current": 2},
                "token": 'abc"def',
                "deck": [1, 2],
            },
        }
    )
    cleaned = redact(f"{message} Authorization: Bearer xyz.123 cookie tlmn_admin_session=s3cr3t; x=1")
    assert "xyz.123" not in cleaned and "s3cr3t" not in cleaned
    for leaked in ("[1, 5, 9]", "[3, [4]]", "abc", "[1, 2]"):
        assert leaked not in cleaned
    assert '"current": 2' in cleaned  # dữ liệu không nhạy cảm vẫn giữ để chẩn đoán
    assert json.loads(cleaned.split(" Authorization")[0])["payload"]["state"]["hands"] == "***"


def test_log_filter_rewrites_records(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("tlmn.test")
    logger.addFilter(RedactFilter())
    with caplog.at_level(logging.INFO, logger="tlmn.test"):
        logger.info("login token=%s", "abc123")
    assert "abc123" not in caplog.text and "token=***" in caplog.text


async def test_security_headers_and_body_limit(no_db_settings: Settings) -> None:
    app = create_app(no_db_settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/api/rules/schema")
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert response.headers["Cache-Control"] == "no-store"
        assert "Strict-Transport-Security" not in response.headers  # chỉ bật khi có HTTPS
        big = await client.post(
            "/api/guests", content=b"x" * (65 * 1024), headers={"Content-Type": "application/json"}
        )
        assert (big.status_code, big.json()["code"]) == (413, "PAYLOAD_TOO_LARGE")
    await app.state.engine.dispose()


def test_production_refuses_insecure_settings() -> None:
    with pytest.raises(InsecureConfigError, match="COOKIE_SECURE"):
        check_production_settings(Settings(environment="production"))
    check_production_settings(
        Settings(
            environment="production",
            cookie_secure=True,
            allowed_origins=["https://tlmn.example"],
            database_url="postgresql+asyncpg://tlmn:mat-khau-manh@db:5432/tlmn",
        )
    )
