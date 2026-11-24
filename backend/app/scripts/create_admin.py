"""Create an admin account.

    python -m app.scripts.create_admin \
        --email owner@example.uz --name "Ism Familiya" --role super_admin

The password is read from the ADMIN_PASSWORD environment variable if set, otherwise
asked interactively (never pass it as a command-line argument: it would end up in
shell history and process lists).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from app.core.exceptions import AppError
from app.database.session import dispose_engine, get_sessionmaker
from app.models.enums import AdminRoleName
from app.services.admin_config import MIN_PASSWORD_LENGTH, StaffService


def _password() -> str:
    from_env = os.environ.get("ADMIN_PASSWORD")
    if from_env:
        return from_env
    first = getpass.getpass(f"Parol (kamida {MIN_PASSWORD_LENGTH} belgi): ")
    if first != getpass.getpass("Parolni takrorlang: "):
        sys.exit("Parollar mos kelmadi.")
    return first


async def _create(args: argparse.Namespace, password: str) -> None:
    async with get_sessionmaker()() as session:
        admin = await StaffService(session).create(
            email=args.email,
            full_name=args.name,
            password=password,
            role=AdminRoleName(args.role),
            created_by=None,
        )
        print(f"Yaratildi: {admin.email} ({admin.role.name})")
    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an admin account")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--role", choices=[r.value for r in AdminRoleName], default=AdminRoleName.SUPER_ADMIN.value
    )
    args = parser.parse_args()
    try:
        asyncio.run(_create(args, _password()))
    except AppError as exc:
        sys.exit(f"Xato: {exc.message}")


if __name__ == "__main__":
    main()
