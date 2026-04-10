"""Command line entry points for vault administration.

Most users do not need this CLI. The dashboard auto-generates its master key
on first run and you set the admin password through the web UI. These
commands exist for two situations:

1. set-admin-password: recovery if you forget the admin login. Resets it
   from the command line so you can get back into the Settings page.

2. generate-kek / rotate-kek: ADVANCED. Only needed if you choose to move
   the master key off disk and into an environment variable for stricter
   compliance posture. The default file-based bootstrap does not require
   either command.

Usage:
  python -m app.vault.cli set-admin-password [username]
  python -m app.vault.cli generate-kek           # advanced
  python -m app.vault.cli rotate-kek             # advanced
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from datetime import datetime, timezone

from app.config import get_settings
from app.database import get_database
from app.vault import crypto
from app.vault.manager import SecretsManager


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cmd_generate_kek(_args: argparse.Namespace) -> int:
    kek = crypto.generate_kek()
    encoded = crypto.encode_kek(kek)
    sys.stdout.write(encoded + "\n")
    sys.stderr.write(
        "\n[advanced] A new master key has been generated.\n"
        "Most users do NOT need this command. The dashboard auto-generates\n"
        "its key file on first run.\n\n"
        "If you are intentionally moving to env-var key storage:\n"
        "  1. Store this value in your password manager NOW.\n"
        "  2. Set PSA_DASHBOARD_MASTER_KEY=<value> in your service environment.\n"
        "  3. Delete the existing data/.vault_master_key file (if any).\n"
        "Losing this key means losing access to every stored secret.\n"
    )
    return 0


async def _rotate_kek_async() -> int:
    try:
        old_kek = crypto.load_kek_from_env("PSA_DASHBOARD_MASTER_KEY")
    except crypto.CryptoError as exc:
        sys.stderr.write(f"ERROR: cannot load current KEK: {exc}\n")
        return 2
    new_encoded = os.environ.get("PSA_DASHBOARD_MASTER_KEY_NEW", "").strip()
    if not new_encoded:
        sys.stderr.write(
            "ERROR: PSA_DASHBOARD_MASTER_KEY_NEW is not set. Generate a new key "
            "with `python -m app.vault.cli generate-kek` and export it before "
            "running rotate-kek.\n"
        )
        return 2
    try:
        new_kek = crypto.decode_kek(new_encoded)
    except crypto.CryptoError as exc:
        sys.stderr.write(f"ERROR: new KEK is invalid: {exc}\n")
        return 2
    if old_kek == new_kek:
        sys.stderr.write("ERROR: new KEK matches the current KEK. Aborting.\n")
        return 2

    settings = get_settings()
    db = get_database(settings.db_path)
    await db.initialize()
    try:
        manager = SecretsManager(db, old_kek)
        await manager.rotate_kek(new_kek)
    finally:
        await db.close()
    sys.stdout.write(
        "KEK rotated successfully.\n"
        "Now: update PSA_DASHBOARD_MASTER_KEY in your environment to the new "
        "value, unset PSA_DASHBOARD_MASTER_KEY_NEW, and restart the service.\n"
    )
    return 0


def cmd_rotate_kek(_args: argparse.Namespace) -> int:
    return asyncio.run(_rotate_kek_async())


async def _set_admin_password_async(username: str, password: str) -> int:
    try:
        import bcrypt
    except ImportError:
        sys.stderr.write(
            "ERROR: bcrypt is not installed. Run "
            "`pip install -r requirements.txt` first.\n"
        )
        return 2
    pw_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("ascii")

    settings = get_settings()
    db = get_database(settings.db_path)
    await db.initialize()
    try:
        conn = await db.get_connection()
        await conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) "
            "VALUES (?, ?, 'admin', ?) "
            "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash",
            (username, pw_hash, _iso_now()),
        )
        await conn.commit()
    finally:
        await db.close()
    sys.stdout.write(f"Admin password set for user '{username}'.\n")
    return 0


def cmd_set_admin_password(args: argparse.Namespace) -> int:
    username = args.username or "admin"
    pw1 = getpass.getpass(f"New password for {username}: ")
    if len(pw1) < 12:
        sys.stderr.write("ERROR: password must be at least 12 characters.\n")
        return 2
    pw2 = getpass.getpass("Confirm: ")
    if pw1 != pw2:
        sys.stderr.write("ERROR: passwords do not match.\n")
        return 2
    return asyncio.run(_set_admin_password_async(username, pw1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.vault.cli",
        description="PSA Dashboard vault administration",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "generate-kek",
        help="Print a fresh base64-encoded KEK to stdout",
    ).set_defaults(func=cmd_generate_kek)

    sub.add_parser(
        "rotate-kek",
        help="Re-wrap the DEK under PSA_DASHBOARD_MASTER_KEY_NEW",
    ).set_defaults(func=cmd_rotate_kek)

    set_pw = sub.add_parser(
        "set-admin-password",
        help="Set or reset the admin login password",
    )
    set_pw.add_argument("username", nargs="?", default="admin")
    set_pw.set_defaults(func=cmd_set_admin_password)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
