#!/usr/bin/env python3
"""Lists every Discord server Bub is in, with member counts.

Read-only: calls Discord's REST API with the bot token from .env (never printed), so it does
not log in to the gateway, sync slash commands, or disturb the running bot.

Run from the project root:
    .venv/bin/python scripts/list_guilds.py [--details] [--json] [--sort members|name|created]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://discord.com/api/v10"
USER_AGENT = "DiscordBot (https://github.com/AliDiksin/FrameBub, 1.0) list_guilds"
DISCORD_EPOCH_MS = 1420070400000


def load_token() -> str:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    token = (os.getenv("DISCORD_TOKEN") or "").strip()
    if not token:
        sys.exit("DISCORD_TOKEN is not set (looked in the environment and .env).")
    return token


def api_get(path: str, token: str, params: dict | None = None):
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"Authorization": f"Bot {token}", "User-Agent": USER_AGENT})
    for _attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                retry_after = float(json.load(error).get("retry_after", 1))
                time.sleep(retry_after + 0.2)
                continue
            if error.code == 401:
                sys.exit("Discord rejected the bot token (401).")
            raise
    sys.exit(f"Rate limited too many times on {path}.")


def fetch_guilds(token: str) -> list[dict]:
    guilds: list[dict] = []
    after = None
    while True:
        params = {"limit": 200, "with_counts": "true"}
        if after:
            params["after"] = after
        page = api_get("/users/@me/guilds", token, params)
        guilds.extend(page)
        if len(page) < 200:
            return guilds
        after = page[-1]["id"]


def created_at(snowflake: str) -> datetime:
    return datetime.fromtimestamp(((int(snowflake) >> 22) + DISCORD_EPOCH_MS) / 1000, tz=timezone.utc)


def buenavista_guild_ids() -> set[str]:
    """Guilds Bub treats as private Buenavista servers (env override or built-in defaults)."""
    try:
        sys.path.insert(0, str(ROOT))
        with contextlib.redirect_stdout(io.StringIO()):
            from bubbot.runtime import buenavista_extension
        return {str(guild_id) for guild_id in buenavista_extension._BUENAVISTA_GUILD_IDS}
    except Exception:
        return set()


def build_rows(token: str, details: bool) -> list[dict]:
    private = buenavista_guild_ids()
    rows = []
    for guild in fetch_guilds(token):
        row = {
            "name": guild.get("name", "?"),
            "id": guild["id"],
            "members": guild.get("approximate_member_count"),
            "online": guild.get("approximate_presence_count"),
            "bot_is_owner": bool(guild.get("owner")),
            "buenavista": guild["id"] in private,
            "created": created_at(guild["id"]).date().isoformat(),
        }
        if details:
            full = api_get(f"/guilds/{guild['id']}", token, {"with_counts": "true"})
            row.update(
                owner_id=full.get("owner_id"),
                boost_tier=full.get("premium_tier"),
                boosts=full.get("premium_subscription_count"),
                verification_level=full.get("verification_level"),
                locale=full.get("preferred_locale"),
                features=full.get("features", []),
                description=full.get("description"),
            )
        rows.append(row)
    return rows


def sort_rows(rows: list[dict], key: str) -> list[dict]:
    if key == "name":
        return sorted(rows, key=lambda row: row["name"].lower())
    if key == "created":
        return sorted(rows, key=lambda row: row["created"])
    return sorted(rows, key=lambda row: row["members"] or 0, reverse=True)


def print_table(rows: list[dict], details: bool) -> None:
    total_members = sum(row["members"] or 0 for row in rows)
    print(f"Bub is in {len(rows)} server{'s' if len(rows) != 1 else ''} "
          f"({sum(1 for row in rows if row['buenavista'])} Buenavista).")
    print(f"Total members across servers: {total_members:,} "
          "(approximate; people in several servers are counted once per server)\n")

    headers = ["#", "Server", "ID", "Members", "Online", "BV", "Created"]
    if details:
        headers += ["Owner ID", "Boost", "Verif.", "Locale"]
    table = []
    for index, row in enumerate(rows, start=1):
        line = [
            str(index),
            row["name"][:38],
            row["id"],
            f"{row['members']:,}" if row["members"] is not None else "?",
            f"{row['online']:,}" if row["online"] is not None else "?",
            "yes" if row["buenavista"] else "",
            row["created"],
        ]
        if details:
            line += [
                str(row.get("owner_id") or ""),
                f"T{row.get('boost_tier', 0)} ({row.get('boosts', 0)})",
                str(row.get("verification_level", "")),
                str(row.get("locale") or ""),
            ]
        table.append(line)
    widths = [max(len(headers[i]), *(len(line[i]) for line in table)) if table else len(headers[i]) for i in range(len(headers))]
    numeric = {0, 3, 4}
    fmt = lambda cells: "  ".join(cell.rjust(widths[i]) if i in numeric else cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()
    print(fmt(headers))
    print("  ".join("-" * width for width in widths))
    for line in table:
        print(fmt(line))
    if details:
        print()
        for row in rows:
            extras = ", ".join(row.get("features") or [])
            if extras or row.get("description"):
                print(f"{row['name']}: {row.get('description') or ''} {('[' + extras + ']') if extras else ''}".strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="List the Discord servers Bub is in.")
    parser.add_argument("--details", action="store_true", help="also fetch owner, boosts, verification level, locale, and features per server")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON instead of a table")
    parser.add_argument("--sort", choices=("members", "name", "created"), default="members")
    args = parser.parse_args()

    rows = sort_rows(build_rows(load_token(), args.details), args.sort)
    if args.json:
        print(json.dumps({"server_count": len(rows), "total_members": sum(row["members"] or 0 for row in rows), "servers": rows}, indent=2))
    else:
        print_table(rows, args.details)


if __name__ == "__main__":
    main()
