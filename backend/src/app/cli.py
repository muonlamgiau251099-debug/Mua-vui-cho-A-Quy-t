"""Lệnh quản trị. Không có trang đăng ký Admin công khai (docs/gd2/06 §1).

uv run python -m app.cli create-admin --username admin      # hỏi mật khẩu (không hiện trên màn hình)
uv run python -m app.cli seed-rules                          # tạo luật v1 nếu chưa có
"""

import argparse
import asyncio
import getpass
import sys

from app.config import get_settings
from app.db import make_engine, make_sessionmaker
from app.services.admin_auth import create_admin
from app.services.rules import ensure_seeded


async def _create_admin(username: str, password: str) -> None:
    engine = make_engine(get_settings().database_url)
    try:
        async with make_sessionmaker(engine)() as session:
            await create_admin(session, username, password)
            await session.commit()
    finally:
        await engine.dispose()


async def _seed_rules() -> bool:
    engine = make_engine(get_settings().database_url)
    try:
        async with make_sessionmaker(engine)() as session:
            return await ensure_seeded(session) is not None
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin", help="tạo tài khoản Admin hệ thống")
    create.add_argument("--username", required=True)
    create.add_argument(
        "--password-stdin", action="store_true", help="đọc mật khẩu từ stdin (dùng cho script)"
    )
    sub.add_parser("seed-rules", help="tạo bộ luật v1 từ cấu hình mặc định nếu chưa có")
    args = parser.parse_args(argv)

    if args.command == "create-admin":
        if args.password_stdin:
            # Windows gửi "\r\n" và PowerShell có thể thêm BOM; không được để lọt vào mật khẩu.
            password = sys.stdin.readline().lstrip("﻿").rstrip("\r\n")
        else:
            password = getpass.getpass("Mật khẩu: ")
            if password != getpass.getpass("Nhập lại mật khẩu: "):
                print("Hai lần nhập không khớp", file=sys.stderr)
                return 1
        try:
            asyncio.run(_create_admin(args.username, password))
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"Đã tạo Admin '{args.username}'")
    elif args.command == "seed-rules":
        print("Đã tạo luật v1" if asyncio.run(_seed_rules()) else "Đã có luật đang áp dụng, không làm gì")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
