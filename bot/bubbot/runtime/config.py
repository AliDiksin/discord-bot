"""Runtime constants: paths, Discord copy strings, and local hitbox GIF settings.
Env-backed values like TOKEN live here; game data workbooks are loaded elsewhere."""

import os


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOKEN = os.getenv("DISCORD_TOKEN")

# Failures read like SF Stats' own notices: one plain line, a small hint, no buttons (bubbot.features.failure_card).
# Every failed prompt still reaches the report channel on its own (notify_owner).
FRAME_DATA_ERROR_CONTACT_TEXT = ""
MISSING_HITBOX_GIF_TEXT = "I have that move's frame data, but no hitbox gif for it yet."
MISSING_SCROLLS_TEXT = "I couldn't find that move."
MISSING_SCROLLS_HINT = "Try a character and a move, like `ryu 5hp` or `ken crouching medium kick`. Type `/` for the frame data menu."
PUBLIC_INVALID_QUERY_TEXT = MISSING_SCROLLS_TEXT
RANGE_SCROLLS_MISSING_TEXT = "the range of that move is not on the supercombo scrolls"
RANGE_MISSING_PLACEHOLDERS = {"{{{atkrange}}}"}

LOCAL_HITBOX_GIF_ROOT = os.path.join(BASE_DIR, "sf6frames", "files")
LOCAL_HITBOX_GIF_EXTENSIONS = {".webp", ".gif", ".png", ".jpg", ".jpeg"}
