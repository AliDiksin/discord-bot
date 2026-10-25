#!/usr/bin/env python3
"""Refresh local SF6 hitbox GIFs from Ultimate Frame Data without deleting fallbacks."""

from __future__ import annotations

import argparse
import difflib
import os
import pprint
import re
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


BASE_URL = "https://ultimateframedata.com/sf6/"
DEFAULT_ROOT = Path("sf6frames/files")
DEFAULT_URL_CACHE = Path("bubbot/data/sf6_ufd_gif_urls.py")
USER_AGENT = "FrameBub-UFD-SF6-GIF-Sync/1.0"
MEDIA_EXTENSIONS = {".gif", ".webp", ".png", ".jpg", ".jpeg"}
STEM_OVERRIDES = {
    ("deejay", "forward jump, down + light kick"): "2LK_Knee_Shot",
    ("ehonda", "forward jump, down + medium kick"): "2MK_Flying_Sumo_Press",
    ("ken", "quick dash > forward step kick"): "5KK_HK_Forward_Step_Kick",
    ("ken", "quick dash > thunder kick"): "5KK_MK_Thunder_Kick",
    ("ken", "shoryuken (quick dash)"): "5KK_623P_Quick_Dash_Shoryuken",
    ("kimberly", "jump, down + medium punch"): "2MP_Elbow_Drop",
    ("marisa", "caelum arc (neutral jump > down + heavy punch)"): "2HP_Caelum_Arc",
    ("zangief", "double lariat (overdrive)"): "5LPMPHP_OD_Double_Lariat",
}

DIRECTION_TOKENS = {
    "neutral jump": "8",
    "forward jump": "9",
    "backward jump": "7",
    "back jump": "7",
    "down-forward": "3",
    "down-back": "1",
    "up-forward": "9",
    "up-back": "7",
    "forward": "6",
    "back": "4",
    "down": "2",
    "up": "8",
    "jump": "9",
}
BUTTON_TOKENS = {
    "light punch": "LP",
    "medium punch": "MP",
    "heavy punch": "HP",
    "light kick": "LK",
    "medium kick": "MK",
    "heavy kick": "HK",
    "two punches": "PP",
    "two kicks": "KK",
    "any punch": "P",
    "any kick": "K",
    "punches": "PP",
    "kicks": "KK",
    "punch": "P",
    "kick": "K",
    "pp": "PP",
    "kk": "KK",
    "lp": "LP",
    "mp": "MP",
    "hp": "HP",
    "lk": "LK",
    "mk": "MK",
    "hk": "HK",
}
INPUT_TOKEN_RE = re.compile(
    "|".join(
        rf"\b{re.escape(token)}\b"
        for token in sorted(
            {*DIRECTION_TOKENS, *BUTTON_TOKENS},
            key=len,
            reverse=True,
        )
    ),
    re.IGNORECASE,
)
GENERIC_NAME_WORDS = {
    "air",
    "aerial",
    "back",
    "crouching",
    "down",
    "forward",
    "heavy",
    "jump",
    "jumping",
    "kick",
    "h",
    "k",
    "l",
    "light",
    "m",
    "medium",
    "normal",
    "od",
    "overdrive",
    "p",
    "punch",
    "sa",
    "standing",
}


def fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def compact_input(value: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", str(value or "").lower())
    text = text.replace("forward/back", "back, forward")
    tokens = []
    for match in INPUT_TOKEN_RE.finditer(text):
        token = match.group(0).lower()
        tokens.append(DIRECTION_TOKENS.get(token) or BUTTON_TOKENS[token])
    return "".join(tokens)


def infer_num_cmd(move_name: str, input_sequence: str, category: str) -> str:
    command = compact_input(input_sequence)
    if command:
        return command

    command = compact_input(move_name)
    lowered_name = move_name.lower()
    if category == "normalattacks":
        if "crouching" in lowered_name:
            return f"2{command}"
        return f"5{command}"
    if category == "jumpattacks":
        if command and command[0].isdigit():
            return command
        return f"9{command}"
    if category == "targetcombos" and command and not command[0].isdigit():
        return f"5{command}"
    return command


def normalize_command(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\bfull\s+charge\b", "hold", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcharge\b", "hold", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcharged\b", "hold", text, flags=re.IGNORECASE)
    words = re.findall(r"[a-z0-9]+", text.lower())
    meaningful = [word for word in words if word not in GENERIC_NAME_WORDS]
    return "".join(meaningful or words)


def move_name_variants(move_name: str) -> list[str]:
    variants = [move_name, re.sub(r"\([^)]*\)", " ", move_name)]
    parentheticals = re.findall(r"\(([^)]*)\)", move_name)
    variants.extend(parentheticals)
    base_name = move_name.split("(", 1)[0].strip()
    if any(re.search(r"\b(?:charged?|full\s+charge|hold)\b", value, re.IGNORECASE) for value in parentheticals):
        variants.append(f"{base_name} hold")
    normalized = []
    for value in variants:
        candidate = normalize_name(value)
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def drink_level_from_label(label: str) -> int | None:
    """Return the minimum drink level represented by a UFD hitbox label."""
    match = re.search(r"\b(\d+)\s*(?:[-+]\s*\d*)?\s*drinks?\b", str(label or ""), re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_existing_asset(path: Path) -> dict[str, str | Path] | None:
    parts = [part for part in path.stem.split("_") if part]
    if not parts:
        return None
    command_parts = [parts[0]]
    name_index = 1
    if len(parts) > 1 and re.match(r"^\d", parts[1]):
        command_parts.append(parts[1])
        name_index = 2
    return {
        "command": normalize_command("".join(command_parts)),
        "name": normalize_name(" ".join(parts[name_index:])),
        "path": path,
    }


def load_existing_assets(directory: Path) -> list[dict[str, str | Path]]:
    if not directory.is_dir():
        return []
    assets = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        parsed = parse_existing_asset(path)
        if parsed:
            assets.append(parsed)
    legacy_assets = [asset for asset in assets if Path(asset["path"]).suffix.lower() != ".gif"]
    return legacy_assets or assets


def name_score(move_name: str, existing_name: str) -> float:
    if not existing_name:
        return 0.0
    scores = []
    for variant in move_name_variants(move_name):
        if variant == existing_name:
            return 1.0
        if variant in existing_name or existing_name in variant:
            scores.append(0.9)
        scores.append(difflib.SequenceMatcher(None, variant, existing_name).ratio())
    return max(scores, default=0.0)


def choose_existing_stem(
    assets: list[dict[str, str | Path]],
    num_cmd: str,
    move_name: str,
) -> str | None:
    command = normalize_command(num_cmd)
    command_matches = [asset for asset in assets if command and asset["command"] == command]
    candidates = command_matches or assets
    ranked = sorted(
        ((name_score(move_name, str(asset["name"])), asset) for asset in candidates),
        key=lambda item: (item[0], str(item[1]["path"])),
        reverse=True,
    )
    if not ranked:
        return None
    score, asset = ranked[0]
    if command_matches and (len(command_matches) == 1 or score >= 0.35):
        return Path(asset["path"]).stem
    if not command_matches and score >= 0.78:
        return Path(asset["path"]).stem
    return None


def infer_followup_num_cmd(
    move_name: str,
    assets: list[dict[str, str | Path]],
) -> str | None:
    name_before_parenthetical = move_name.split("(", 1)[0]
    if ">" not in name_before_parenthetical:
        return None
    parent_name, followup_name = (part.strip() for part in move_name.split(">", 1))
    if "+" not in followup_name and not re.match(
        r"^(?:light|medium|heavy|punch|kick|lp|mp|hp|lk|mk|hk|pp|kk)\b",
        followup_name,
        re.IGNORECASE,
    ):
        return None
    parent_candidates = sorted(
        (
            (name_score(parent_name, str(asset["name"])), asset)
            for asset in assets
        ),
        key=lambda item: (item[0], str(item[1]["path"])),
        reverse=True,
    )
    if not parent_candidates or parent_candidates[0][0] < 0.78:
        return None
    parent_command = str(parent_candidates[0][1]["command"]).upper()
    followup_command = compact_input(followup_name)
    if followup_command and not followup_command[0].isdigit():
        followup_command = f"5{followup_command}"
    if not parent_command or not followup_command:
        return None
    return f"{parent_command}>{followup_command}"


def safe_filename_part(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9-]+", "_", text).strip("_")
    return text or "move"


def character_directory(root: Path, slug: str) -> Path:
    if root.is_dir():
        for entry in root.iterdir():
            if entry.is_dir() and normalize_command(entry.name) == normalize_command(slug):
                return entry
    return root / slug


def discover_characters(timeout: int) -> list[tuple[str, str]]:
    soup = BeautifulSoup(fetch(BASE_URL, timeout), "html.parser")
    characters = []
    seen = set()
    for anchor in soup.select("#charList .charactericon > a[href]"):
        url = urljoin(BASE_URL, anchor["href"])
        slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1].lower()
        if slug == "stats" or slug in seen:
            continue
        seen.add(slug)
        characters.append((slug, url.rstrip("/")))
    return characters


def extract_moves(page_url: str, timeout: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(fetch(page_url, timeout), "html.parser")
    moves = []
    for container in soup.select(".movecontainer"):
        name_node = container.select_one(".movename")
        image_nodes = container.select("a.hitboximg[data-featherlight]")
        if not name_node or not image_nodes:
            continue
        category_node = container.find_previous("h2", class_="movecategory")
        input_node = container.select_one(".inputsequence")
        notes_node = container.select_one(".notes")
        move_name = name_node.get_text(" ", strip=True)
        input_sequence = input_node.get_text(" ", strip=True) if input_node else ""
        notes = notes_node.get_text(" ", strip=True) if notes_node else ""
        category = str(category_node.get("id") or "") if category_node else ""
        num_cmd = infer_num_cmd(move_name, input_sequence, category)
        for image_node in image_nodes:
            media_url = urljoin(page_url, str(image_node.get("data-featherlight") or ""))
            if media_url:
                label_node = image_node.previous_sibling
                label = str(label_node).strip() if label_node else ""
                drink_level = drink_level_from_label(label)
                asset_move_name = move_name
                if label.lower() == "charged":
                    asset_move_name = f"{move_name} (Hold)"
                media_hint = Path(urlparse(media_url).path).stem
                page_slug = urlparse(page_url).path.rstrip("/").rsplit("/", 1)[-1]
                media_hint = re.sub(rf"^{re.escape(page_slug)}[-_]", "", media_hint, flags=re.IGNORECASE)
                moves.append(
                    {
                        "category": category,
                        "move_name": asset_move_name,
                        "match_name": f"{asset_move_name} ({media_hint.replace('-', ' ')})",
                        "num_cmd": num_cmd,
                        "media_url": media_url,
                        "drink_level": drink_level,
                        "august_2026": "august 2026" in notes.lower(),
                    }
                )
    return moves


def write_gif(path: Path, content: bytes) -> str:
    if not content.startswith((b"GIF87a", b"GIF89a")):
        raise ValueError("download was not a GIF")
    if path.is_file() and path.read_bytes() == content:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(content)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return "updated"


def write_url_cache(path: Path, urls: dict[tuple[str, str], str]) -> None:
    content = (
        '"""Generated UFD SF6 hitbox GIF URLs. Do not edit manually."""\n\n'
        f"SF6_UFD_GIF_URLS = {pprint.pformat(dict(sorted(urls.items())), width=140, sort_dicts=False)}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def sync(args: argparse.Namespace) -> int:
    selected = {value.lower() for value in args.character}
    characters = discover_characters(args.timeout)
    if selected:
        characters = [item for item in characters if item[0] in selected]
        missing = selected.difference(slug for slug, _url in characters)
        if missing:
            raise RuntimeError(f"Unknown UFD SF6 characters: {', '.join(sorted(missing))}")

    totals = {"moves": 0, "updated": 0, "unchanged": 0, "skipped": 0, "errors": 0}
    url_cache = {}
    for character_index, (slug, page_url) in enumerate(characters):
        if character_index:
            time.sleep(args.delay)
        directory = character_directory(args.root, slug)
        assets = load_existing_assets(directory)
        moves = extract_moves(page_url, args.timeout)
        totals["moves"] += len(moves)
        assigned_paths = set()
        character_counts = {"updated": 0, "unchanged": 0, "skipped": 0, "errors": 0}

        for move in moves:
            followup_num_cmd = infer_followup_num_cmd(move["move_name"], assets)
            num_cmd = followup_num_cmd or move["num_cmd"]
            drink_level = move.get("drink_level")
            if drink_level is not None and num_cmd:
                stem = (
                    f"{safe_filename_part(num_cmd)}_"
                    f"{safe_filename_part(move['move_name'])}_Drink_Level_{drink_level}"
                )
            else:
                stem = STEM_OVERRIDES.get((slug, move["move_name"].lower()))
                if stem is None:
                    stem = None if followup_num_cmd else choose_existing_stem(assets, num_cmd, move["match_name"])
                if stem is None and num_cmd:
                    stem = f"{safe_filename_part(num_cmd)}_{safe_filename_part(move['move_name'])}"
            if stem is None:
                character_counts["skipped"] += 1
                continue

            target = directory / f"{stem}.gif"
            suffix = 2
            while target in assigned_paths:
                target = directory / f"{stem}_{suffix}.gif"
                suffix += 1
            assigned_paths.add(target)
            url_cache[(normalize_command(directory.name), target.name)] = move["media_url"]

            if args.urls_only:
                character_counts["unchanged"] += 1
                continue
            if args.dry_run:
                character_counts["updated"] += 1
                if args.verbose:
                    print(f"[dry-run] {slug}: {move['move_name']} -> {target.name}")
                continue

            try:
                time.sleep(args.delay)
                result = write_gif(target, fetch(move["media_url"], args.timeout))
                character_counts[result] += 1
            except (OSError, ValueError, urllib.error.URLError) as error:
                if not move["august_2026"]:
                    character_counts["skipped"] += 1
                    print(f"[ufd-sf6] {slug}: kept fallback for unavailable non-August asset: {move['media_url']}")
                else:
                    character_counts["errors"] += 1
                    print(f"[ufd-sf6] {slug}: failed August 2026 asset {move['media_url']}: {error}")

        for key in character_counts:
            totals[key] += character_counts[key]
        print(
            f"[ufd-sf6] {slug}: moves={len(moves)} "
            f"updated={character_counts['updated']} unchanged={character_counts['unchanged']} "
            f"skipped={character_counts['skipped']} errors={character_counts['errors']}",
            flush=True,
        )

    if not args.dry_run:
        write_url_cache(args.url_cache, url_cache)
        print(f"[ufd-sf6] wrote {len(url_cache)} remote URLs to {args.url_cache}", flush=True)

    print(
        "UFD SF6 GIF sync complete: "
        f"characters={len(characters)} moves={totals['moves']} updated={totals['updated']} "
        f"unchanged={totals['unchanged']} skipped={totals['skipped']} errors={totals['errors']}",
        flush=True,
    )
    return 1 if totals["errors"] else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--url-cache", type=Path, default=DEFAULT_URL_CACHE)
    parser.add_argument("--character", action="append", default=[], help="UFD character slug; repeatable")
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--urls-only", action="store_true", help="refresh the remote URL cache without downloading GIF files")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    raise SystemExit(sync(args))


if __name__ == "__main__":
    main()
