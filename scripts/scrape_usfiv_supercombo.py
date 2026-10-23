"""Build Ultra Street Fighter IV frame data and media caches from SuperCombo."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import scraper_utils  # noqa: E402
from scripts.generation_utils import normal_sheet_name, write_ods_sheets, write_python_constants  # noqa: E402
from scripts.scraper_utils import (  # noqa: E402
    extract_headings,
    extract_templates,
    file_url_for_name,
    resolve_file_urls,
)


API_URL = "https://wiki.supercombo.gg/api.php"
PAGE_PREFIX = "Ultra Street Fighter IV"
IMAGE_THUMB_WIDTH = 300

CHARACTERS = (
    "Abel", "Adon", "Akuma", "Balrog", "Blanka", "C. Viper", "Cammy", "Chun-Li", "Cody", "Dan",
    "Decapre", "Dee Jay", "Dhalsim", "Dudley", "E. Honda", "El Fuerte", "Elena", "Evil Ryu", "Fei Long",
    "Gen", "Gouken", "Guile", "Guy", "Hakan", "Hugo", "Ibuki", "Juri", "Ken", "M. Bison", "Makoto",
    "Oni", "Poison", "Rolento", "Rose", "Rufus", "Ryu", "Sagat", "Sakura", "Seth", "T. Hawk", "Vega",
    "Yang", "Yun", "Zangief",
)

MOVE_COLUMNS = (
    "char_key", "char_name", "source_page_title", "source_page_url", "section", "subsection", "moveId",
    "moveType", "moveName", "nickname", "numCmd", "version", "startup", "active", "recovery", "total",
    "onBlock", "onHit", "blockstun", "hitstun", "dmg", "stun", "meterGain", "guardLevel", "cancel",
    "armor", "fullInvuln", "strikeInvuln", "projInvuln", "throwInvuln", "airborne", "juggleInfo", "extraInfo",
)

SIMPLE_TEMPLATE_REPLACEMENTS = {
    "lp": "LP", "mp": "MP", "hp": "HP", "lk": "LK", "mk": "MK", "hk": "HK", "p": "P", "k": "K",
    "pp": "PP", "kk": "KK", "ppp": "PPP", "kkk": "KKK", "ex": "EX", "n": "5", "qcf": "236",
    "qcb": "214", "dp": "623", "rdp": "421", "hcf": "41236", "hcb": "63214", "360": "360",
    "720": "720", "u": "8", "d": "2", "f": "6", "b": "4", "uf": "9", "ub": "7", "df": "3", "db": "1",
}


def char_key(display_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(display_name).lower()).strip("_")


def page_url(page_title: str) -> str:
    encoded = urllib.parse.quote(page_title.replace(" ", "_"), safe="/:()-'.,[]")
    return f"https://wiki.supercombo.gg/w/{encoded}"


def fetch_raw_page(page_title: str, sleep_seconds: float, cache_dir: Path | None, refresh: bool) -> str:
    return scraper_utils.fetch_text(
        page_title,
        sleep_seconds=sleep_seconds,
        cache_dir=cache_dir,
        refresh=refresh,
        api_url=API_URL,
    )


def expand_simple_templates(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = re.sub(r"[_\s]+", " ", match.group(1).strip().lower())
        return SIMPLE_TEMPLATE_REPLACEMENTS.get(name, "")

    return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", replace, str(text or ""))


def clean_text(value: object) -> str:
    text = expand_simple_templates(str(value or ""))
    text = scraper_utils.clean_wiki_text(text)
    text = re.sub(r"\[\]\s*refers? to\s+", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def positional_params(span: str) -> dict[str, str]:
    """Parse positional template fields without losing intentionally blank cells."""
    body = str(span or "").strip()[2:-2]
    parts = []
    current = []
    template_depth = 0
    link_depth = 0
    index = 0
    while index < len(body):
        pair = body[index : index + 2]
        if pair == "{{":
            template_depth += 1
            current.extend(pair)
            index += 2
            continue
        if pair == "}}":
            template_depth -= 1
            current.extend(pair)
            index += 2
            continue
        if pair == "[[":
            link_depth += 1
            current.extend(pair)
            index += 2
            continue
        if pair == "]]":
            link_depth -= 1
            current.extend(pair)
            index += 2
            continue
        if body[index] == "|" and template_depth == 0 and link_depth == 0:
            parts.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(body[index])
        index += 1
    parts.append("".join(current).strip())
    return {str(index): value for index, value in enumerate(parts[1:])}


def normalize_input(value: object) -> str:
    text = clean_text(value)
    motion_tokens = {
        "qcf": "236", "qcb": "214", "dp": "623", "rdp": "421", "hcf": "41236", "hcb": "63214",
    }
    for token, notation in motion_tokens.items():
        text = re.sub(rf"\b{token}\b", notation, text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\bclose\s+", "cl. ", text)
    text = re.sub(r"(?i)\bfar\s+", "far. ", text)
    text = re.sub(r"(?i)\bcrouch(?:ing)?\s+", "2", text)
    text = re.sub(r"(?i)\b(?:neutral\s+)?jump(?:ing)?\s+", "j. ", text)
    text = re.sub(r"(?i)\b(?:angled|diagonal)\s+jump(?:ing)?\s+", "j. ", text)
    text = re.sub(r"(?i)\bin\s+air\s*", "j. ", text)
    text = re.sub(r"\s*\+\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.upper().replace("CL. ", "cl.").replace("FAR. ", "far.").replace("J. ", "j.")


def split_media(value: object) -> list[str]:
    files = []
    for item in re.split(r"[,;\n]", str(value or "")):
        filename = clean_text(item)
        filename = re.sub(r"^(?:File|Image):", "", filename, flags=re.IGNORECASE).strip()
        if filename and filename.lower() != "no_image.png" and re.search(r"\.(?:png|webp|gif|jpe?g)$", filename, re.IGNORECASE):
            files.append(filename)
    return list(dict.fromkeys(files))


def heading_context(raw_text: str, position: int) -> tuple[str, str]:
    section = ""
    subsection = ""
    for level, heading_position, title in extract_headings(raw_text):
        if heading_position >= position:
            break
        if level == 2:
            section = title
            subsection = ""
        elif level == 3:
            subsection = title
    return section, subsection


def infer_move_type(move_name: str, num_cmd: str, variant_label: str) -> str:
    name = f"{move_name or ''} {variant_label or ''}".lower()
    command = str(num_cmd or "").lower()
    if any(term in name for term in ("super combo", "ultra combo", "ultra i", "ultra ii")):
        return "super"
    if any(term in name for term in ("focus attack", "red focus", "throw", "taunt")):
        return "system"
    if re.search(r"(?:236|214|623|421|41236|63214|360|720)", command):
        return "special"
    if re.search(r"\b(?:cl\.|far\.|j\.|[1-9]?\s*(?:lp|mp|hp|lk|mk|hk))\b", command):
        return "normal"
    if any(term in name for term in ("close ", "far ", "crouch ", "jump ", "neutral jump", "angled jump")):
        return "normal"
    return "special"


def row_from_template(display_name: str, page_title: str, raw_text: str, record, identity: dict[str, str]) -> dict[str, str] | None:
    params = positional_params(record.raw)
    for index in range(4):
        value = clean_text(params.get(str(index), ""))
        if value:
            identity[str(index)] = value
    move_name = identity.get("0", "")
    if not move_name:
        return None
    variant_label = clean_text(params.get("4", ""))
    version = variant_label
    if variant_label.lower().startswith(move_name.lower()):
        version = variant_label[len(move_name) :].strip(" -()")
    raw_input = identity.get("2", "")
    num_cmd = normalize_input(raw_input) or variant_label or move_name
    if move_name.upper().startswith("EX ") and variant_label.lower() == f"{move_name[3:]} ex".lower():
        version = "EX"
    if version.upper() in {"LP", "MP", "HP", "LK", "MK", "HK"}:
        num_cmd = re.sub(r"\b[PK]\b", version.upper(), num_cmd, count=1)
        num_cmd = re.sub(r"\s*\bEX\b", "", num_cmd, flags=re.IGNORECASE).strip()
    section, subsection = heading_context(raw_text, record.start)
    extra = clean_text(params.get("18", ""))
    return {
        "char_key": char_key(display_name),
        "char_name": display_name,
        "source_page_title": page_title,
        "source_page_url": page_url(page_title),
        "section": section or "Frame Data",
        "subsection": subsection,
        "moveId": clean_text(identity.get("0", "")),
        "moveType": infer_move_type(move_name, num_cmd, variant_label),
        "moveName": move_name,
        "nickname": identity.get("1", ""),
        "numCmd": num_cmd,
        "version": version,
        "startup": clean_text(params.get("10", "")),
        "active": clean_text(params.get("11", "")),
        "recovery": clean_text(params.get("12", "")),
        "total": clean_text(params.get("13", "")),
        "onBlock": clean_text(params.get("16", "")),
        "onHit": clean_text(params.get("17", "")),
        "blockstun": clean_text(params.get("14", "")),
        "hitstun": clean_text(params.get("15", "")),
        "dmg": clean_text(params.get("5", "")),
        "stun": clean_text(params.get("6", "")),
        "meterGain": clean_text(params.get("7", "")),
        "guardLevel": clean_text(params.get("8", "")),
        "cancel": clean_text(params.get("9", "")),
        "armor": clean_text(params.get("26", "")),
        "fullInvuln": clean_text(params.get("27", "")),
        "strikeInvuln": clean_text(params.get("28", "")),
        "projInvuln": clean_text(params.get("29", "")),
        "throwInvuln": clean_text(params.get("30", "")),
        "airborne": clean_text(params.get("31", "")),
        "juggleInfo": clean_text(params.get("32", "")),
        "extraInfo": extra,
    }


def description_data(raw_text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    notes: dict[str, str] = {}
    images: dict[str, list[str]] = {}
    for record in extract_templates(raw_text, {"usfivmovelistrow"}):
        params = positional_params(record.raw)
        move_name = clean_text(params.get("2", ""))
        if not move_name:
            continue
        description = clean_text(params.get("5", ""))
        strategy = clean_text(params.get("6", ""))
        parts = [part for part in (description, strategy) if part and part.lower() != "(no uses/strategies)"]
        if parts:
            notes[move_name.lower()] = "\n".join(dict.fromkeys(parts))
        filenames = split_media(params.get("7", ""))
        if filenames:
            images[move_name.lower()] = filenames
    return notes, images


def parse_character(display_name: str, raw_text: str) -> tuple[list[dict[str, str]], list[tuple[str, str, str]], dict[str, dict[str, str]]]:
    page_title = f"{PAGE_PREFIX}/{display_name}"
    full_section = re.search(r"^==\s*Frame Data\s*==\s*$", raw_text, flags=re.IGNORECASE | re.MULTILINE)
    if not full_section:
        return [], [], {}
    descriptions, images_by_name = description_data(raw_text)
    rows = []
    media = []
    notes_cache: dict[str, dict[str, str]] = {}
    identity: dict[str, str] = {}
    key = char_key(display_name)
    for record in extract_templates(raw_text[full_section.end() :], {"usfivframedatarow"}):
        record.start += full_section.end()
        row = row_from_template(display_name, page_title, raw_text, record, identity)
        if row is None:
            continue
        move_name_key = str(row["moveName"]).lower()
        description = descriptions.get(move_name_key, "")
        if description:
            row["extraInfo"] = "\n".join(dict.fromkeys(part for part in (row["extraInfo"], description) if part))
        rows.append(row)
        move_key = re.sub(r"[^a-z0-9]+", "", f"{row['numCmd']} {row['version']}".lower())
        if row["extraInfo"]:
            notes_cache.setdefault(key, {})[move_key] = row["extraInfo"]
        for filename in images_by_name.get(move_name_key, []):
            media.append((key, move_key, filename))
    return rows, media, notes_cache


def write_cache(path: Path, media: list[tuple[str, str, str]], notes: dict[str, dict[str, str]], urls: dict[str, str]) -> tuple[int, int]:
    image_cache: dict[str, dict[str, str]] = {}
    for char, move_key, filename in media:
        url = file_url_for_name(urls, filename)
        if url:
            image_cache.setdefault(char, {}).setdefault(move_key, url)
    write_python_constants(
        path,
        {
            "USFIV_MOVE_IMAGE_URLS": image_cache,
            "USFIV_HITBOX_DATA": {},
            "USFIV_MOVE_NOTES": notes,
        },
        "scrape_usfiv_supercombo.py",
    )
    return sum(len(items) for items in image_cache.values()), sum(len(items) for items in notes.values())


def build(output_workbook: Path, output_cache: Path, sleep_seconds: float, cache_dir: Path | None, refresh: bool, allow_incomplete: bool) -> None:
    all_rows: list[dict[str, str]] = []
    all_media: list[tuple[str, str, str]] = []
    all_notes: dict[str, dict[str, str]] = {}
    sheets: dict[str, list[dict[str, str]]] = {}
    missing = []
    for display_name in CHARACTERS:
        page_title = f"{PAGE_PREFIX}/{display_name}"
        raw_text = fetch_raw_page(page_title, sleep_seconds, cache_dir, refresh)
        rows, media, notes = parse_character(display_name, raw_text)
        if not rows:
            missing.append(display_name)
        else:
            sheets[normal_sheet_name(display_name)] = rows
            all_rows.extend(rows)
            all_media.extend(media)
            for key, values in notes.items():
                all_notes.setdefault(key, {}).update(values)
        print(f"[usf4-scrape] {display_name}: {len(rows)} rows, {len(media)} media refs", flush=True)
    if missing and not allow_incomplete:
        raise RuntimeError(f"No USF4 frame rows found for: {', '.join(missing)}")
    if not all_rows:
        raise RuntimeError("No USF4 frame rows scraped")
    write_ods_sheets(output_workbook, sheets, MOVE_COLUMNS)
    urls = resolve_file_urls(API_URL, [filename for _char, _move, filename in all_media], IMAGE_THUMB_WIDTH, sleep_seconds)
    image_count, notes_count = write_cache(output_cache, all_media, all_notes, urls)
    print(f"[usf4-scrape] wrote {len(all_rows)} rows to {output_workbook}; cache images={image_count} notes={notes_count}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Ultra Street Fighter IV frame data from SuperCombo raw wikitext.")
    parser.add_argument("--output", default="USFIV Frame Data.ods")
    parser.add_argument("--output-cache", default="bubbot/data/usfiv_move_images.py")
    parser.add_argument("--cache-dir", default=".cache/usfiv_supercombo")
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    build(Path(args.output), Path(args.output_cache), args.sleep, Path(args.cache_dir) if args.cache_dir else None, args.refresh, args.allow_incomplete)


if __name__ == "__main__":
    main()
