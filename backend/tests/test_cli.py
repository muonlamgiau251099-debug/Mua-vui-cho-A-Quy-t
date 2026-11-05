import io

import pytest

from app import cli


@pytest.mark.parametrize("raw", ["mat-khau-dai-123\n", "mat-khau-dai-123\r\n", "﻿mat-khau-dai-123\r\n"])
def test_create_admin_reads_password_from_stdin_without_line_ending_or_bom(
    raw: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    async def fake_create(username: str, password: str) -> None:
        captured.update(username=username, password=password)

    monkeypatch.setattr(cli, "_create_admin", fake_create)
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))
    assert cli.main(["create-admin", "--username", "quantri", "--password-stdin"]) == 0
    assert captured == {"username": "quantri", "password": "mat-khau-dai-123"}
