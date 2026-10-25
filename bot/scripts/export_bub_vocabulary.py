"""Write the words that make a plain-language request Bub's to ``src/lib/discord/nl/bub-vocabulary.json``.

The web app's parser (``src/lib/discord/nl/parse.ts``) hands requests back to Bub when they name a
character from one of Bub's other games ("ggst ky 5h", "potemkin buster") or ask about a glossary
term ("what is a meaty"). SF6 characters are already in the web app's roster. Run from ``bot/``
after editing an alias map or the glossary: ``python scripts/export_bub_vocabulary.py``.
Reads the files as data (no imports), so it needs nothing installed.
"""

import ast
import json
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
DATA = BOT / "bubbot" / "data"
OUT = BOT.parent / "src" / "lib" / "discord" / "nl" / "bub-vocabulary.json"
OTHER_GAMES = ("avtl", "bbcf", "cotw", "ggacr", "ggst", "mk1", "sfv", "third_strike", "tuco", "usfiv")
# Aliases that are everyday words or numbers: too loose to claim a request on their own.
TOO_COMMON = {"12", "big", "es", "guy", "nine", "pot", "ram", "rock", "sin", "test", "ww", "claw", "bang", "mu", "nu", "vi"}


def literal(path, name):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(f"{name} not in {path.name}")


def main():
    nicknames = literal(DATA / "aliases.py", "CHARACTER_ALIASES")
    sf6 = {name.lower() for name in [*nicknames, *nicknames.values(), *literal(DATA / "aliases.py", "CHARACTER_INPUT_ALIASES")]}
    characters = set()
    for game in OTHER_GAMES:
        aliases = literal(DATA / f"{game}_aliases.py", f"{game.upper()}_CHARACTER_ALIASES")
        characters |= {key.strip().lower() for key in aliases if len(key.strip()) >= 2}
    glossary = json.loads((DATA / "fg_glossary.json").read_text(encoding="utf-8"))
    terms = {str(name or "").strip().lower() for entry in glossary for name in [entry.get("term"), *(entry.get("altterm") or [])]}
    vocabulary = {
        "characters": sorted(characters - sf6 - TOO_COMMON),
        "glossary": sorted(term for term in terms if len(term) >= 3),
    }
    OUT.write_text(json.dumps(vocabulary, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(BOT.parent)}: {len(vocabulary['characters'])} characters, {len(vocabulary['glossary'])} glossary terms")


if __name__ == "__main__":
    main()
