"""Layer 2 for frame data: when Bub's parser can't read a request, the Decisions API picks the game,
character and move from Bub's own tables, and Bub answers the rewritten request ("ggst sol 5H") as if
it had been typed, with its usual cards, buttons and images, plus a "Read as" line.

Called from Bub's last step, just before the invalid-query notice. One to three small requests (the
game is skipped when the message names it); anything unsure, slow or failing leaves the notice as it was.
"""

import contextvars
import difflib
import time
from dataclasses import dataclass

from bubbot.runtime import decisions
from bubbot.utils.choice_utils import character_choices, move_choices


@dataclass(frozen=True)
class Game:
    key: str
    label: str
    tag: str
    frame_data: dict


@dataclass(frozen=True)
class Resolution:
    game: Game
    character: str
    move: str
    query: str


_GAMES = {}
# Set while a rewritten request runs, so it neither reaches SF Stats again nor asks again.
_RESOLVING = contextvars.ContextVar("bub_frame_resolving", default=False)
_recent = {}
THROTTLE_SECONDS = 5.0


def configure(games):
    """Bub's games, in its parser order: [(key, label, tag, frame_data)]. Tables are read at call time."""
    _GAMES.clear()
    for key, label, tag, frame_data in games:
        _GAMES[key] = Game(key, label, tag, frame_data)


def resolving():
    return _RESOLVING.get()


def games():
    return list(_GAMES.values())


def throttled(user_id, now=None):
    """One Decisions fallback per user every few seconds."""
    return _throttled(user_id, now)


def _throttled(user_id, now=None):
    now = time.monotonic() if now is None else now
    if len(_recent) > 5_000:
        _recent.clear()
    if now - _recent.get(user_id, float("-inf")) < THROTTLE_SECONDS:
        return True
    _recent[user_id] = now
    return False


def _closest(values, text, limit):
    """The options closest to the text, when a table has more than one question can list."""
    if len(values) <= limit:
        return list(values)
    words = text.lower()
    scored = sorted(values, key=lambda value: difflib.SequenceMatcher(None, words, value.lower()).ratio(), reverse=True)
    return scored[:limit]


def move_label(row):
    name, command = str(row.get("moveName", "")).strip(), str(row.get("numCmd", "")).strip()
    return f"{name} ({command})" if name and command and command.lower() != name.lower() else (name or command)


def _move_query(row):
    """What Bub's parser reads best: the numpad input when there is a short one, else the move's name."""
    command = str(row.get("numCmd", "")).strip()
    return command if command and len(command) <= 12 else str(row.get("moveName", "")).strip() or command


async def resolve(text, *, session, tagged=(), config=None):
    """A Resolution, or None when any layer is unsure, off or failing."""
    if not decisions.enabled(config) or not _GAMES:
        return None
    games = [_GAMES[key] for key in tagged if key in _GAMES]
    if len(games) != 1:
        questions = {"game": decisions.choice(
            decisions.options([game.label for game in _GAMES.values()], "No fighting game, or one Bub doesn't have."),
            "Which fighting game is this frame data request about? Street Fighter 6 when a Street Fighter 6 character is "
            "named and no other game is.")}
        answers = await decisions.decide(text, questions, session=session, config=config, label="frame-game")
        label = decisions.sure(answers, "game")
        games = [game for game in _GAMES.values() if game.label == label]
        if not games:
            return None
    game = games[0]

    characters = {display: key for key, display in character_choices({k: v for k, v in game.frame_data.items() if v})}
    if not characters:
        return None
    questions = {"character": decisions.choice(
        decisions.options(_closest(sorted(characters), text, decisions.MAX_CHOICES - 1), "No character is named."),
        f"Which {game.label} character is the request about? Nicknames, short names and typos count.")}
    answers = await decisions.decide(text, questions, session=session, config=config, label="frame-character")
    character = decisions.sure(answers, "character")
    if character not in characters:
        return None

    rows = {}
    for row, label in move_choices(game.frame_data.get(characters[character], []), label_fn=move_label,
                                   key_fields=("moveName", "numCmd", "moveType")):
        rows.setdefault(label, row)
    if not rows:
        return None
    questions = {"move": decisions.choice(
        decisions.options(_closest(list(rows), text, decisions.MAX_CHOICES - 1), "No move of this character is asked about."),
        f"Which of {character}'s moves in {game.label} does the request ask about? Plain words count: \"standing medium "
        "punch\" is 5MP, \"crouching heavy kick\" or \"sweep\" is 2HK, \"fireball\" is the projectile special, \"DP\" the "
        "uppercut special. Light, medium and heavy versions are different moves.")}
    answers = await decisions.decide(text, questions, session=session, config=config, label="frame-move")
    move = decisions.sure(answers, "move")
    if move not in rows:
        return None
    query = " ".join(part for part in (game.tag, character, _move_query(rows[move])) if part)
    return Resolution(game=game, character=character, move=move, query=query)


class _NotedChannel:
    """The real channel, with the "Read as" line added to the first message sent."""

    def __init__(self, channel, state):
        self._channel = channel
        self._state = state

    def __getattr__(self, name):
        return getattr(self._channel, name)

    async def send(self, content=None, **kwargs):
        return await self._channel.send(self._state.noted(content), **kwargs)


class _NoteState:
    def __init__(self, note):
        self.note = note
        self.sent = False

    def noted(self, content):
        first, self.sent = not self.sent, True
        if not first:
            return content
        return self.note if not content else f"{self.note}\n{content}"[:2000]


class Rephrased:
    """The original message with the rewritten request as its content; replies still go to the original."""

    def __init__(self, message, content, note):
        self._message = message
        self._state = _NoteState(note)
        self.content = content
        self.channel = _NotedChannel(message.channel, self._state)

    def __getattr__(self, name):
        return getattr(self._message, name)

    @property
    def replied(self):
        return self._state.sent

    async def reply(self, content=None, **kwargs):
        return await self._message.reply(self._state.noted(content), **kwargs)


async def resolve_and_rerun(message, text, *, rerun, bot_user_id, session, tagged=(), config=None, throttle=True):
    """True when the rewritten request was answered; False leaves the message to Bub's notice."""
    if resolving() or not decisions.enabled(config) or not bot_user_id:
        return False
    if throttle and _throttled(str(getattr(getattr(message, "author", None), "id", ""))):
        return False
    resolution = await resolve(text, session=session, tagged=tagged, config=config)
    if resolution is None:
        print("[frame-resolve] unresolved", flush=True)
        return False
    note = f"-# Read as **{resolution.character}** · {resolution.move} ({resolution.game.label})"
    proxy = Rephrased(message, f"<@{bot_user_id}> {resolution.query}", note)
    token = _RESOLVING.set(True)
    try:
        await rerun(proxy)
    finally:
        _RESOLVING.reset(token)
    print(f"[frame-resolve] game={resolution.game.key} answered={proxy.replied}", flush=True)
    return proxy.replied


def tags_in(text, detect):
    """The game keys a message names, via Bub's own tag detection."""
    try:
        return tuple(sorted(detect(str(text or "").lower())))
    except Exception:
        return ()

