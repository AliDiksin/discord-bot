"""The SF Stats frame-data helper: SF Stats posts Bub's frame data under its own name.

``POST /render`` with ``{"content": "jp crmp", "user_id": "...", "guild_id": "...", "channel_id": "..."}``
runs Bub's own message handler on a stand-in message addressed to Bub and returns what Bub would
have sent, instead of sending it:
``{"messages": [{"content", "embeds", "components", "files": [{"name", "data" (base64)}]}]}``.
Only link buttons are kept: Bub's other buttons call back into this process, and their clicks
would reach SF Stats, not Bub. Quizzes, reminders, voice and the Buenavista extras never run here.

``GET /health`` says whether the game data has loaded (the deploy waits for it).

Runs in ``bubbot.render_service`` on the SF Stats server, beside the web app; dormant unless
``BUB_RENDER_PORT`` is set. Listens on ``BUB_RENDER_HOST`` (127.0.0.1 by default) and requires
``SFSTATS_INTERNAL_SECRET`` in ``x-sfstats-internal-secret``, the web app's internal secret.
"""

import asyncio
import base64
import contextvars
import hmac
import itertools
import os
from types import SimpleNamespace

from aiohttp import web


RENDERING = contextvars.ContextVar("bub_rendering", default=False)
MAX_CONTENT = 600
TIMEOUT_SECONDS = 8.0
# Discord's upload limit for bots; bigger GIFs are dropped from the answer rather than failing it.
MAX_FILE_BYTES = 10 * 1024 * 1024
_ids = itertools.count(1)
_runner = None


def rendering():
    """True while Bub answers for SF Stats: side effects (quizzes, reminders, voice) must not run."""
    return RENDERING.get()


def _embed_dict(embed):
    return embed.to_dict() if hasattr(embed, "to_dict") else dict(embed)


def _file_dict(file):
    fp = getattr(file, "fp", None)
    if fp is None:
        return None
    try:
        fp.seek(0)
    except Exception:
        pass
    data = fp.read()
    if not data or len(data) > MAX_FILE_BYTES:
        return None
    return {"name": str(getattr(file, "filename", None) or "file"), "data": base64.b64encode(data).decode("ascii")}


def _link_rows(view):
    """Only link buttons survive: every other control needs this process to answer its click."""
    if view is None or not hasattr(view, "to_components"):
        return []
    rows = []
    for row in view.to_components():
        links = [c for c in row.get("components", []) if c.get("type") == 2 and c.get("style") == 5 and c.get("url")]
        if links:
            rows.append({"type": 1, "components": links})
    return rows


def _menu_card_embeds(view):
    """A menu is a Components V2 card, which SF Stats posts only as embeds: its text as one, controls left out."""
    from bubbot.utils.sfstats_style import BRAND, DIVIDER, CardView

    if not isinstance(view, CardView):
        return []
    text = "\n\n".join(str(block) for block in view._blocks if block is not DIVIDER).strip()
    title, _, body = text.partition("\n") if text.startswith("## ") else ("", "", text)
    if not (title or body):
        return []
    return [{"title": title[3:][:256], "description": body.strip()[:4096], "color": BRAND.value}]


def capture(sink, content=None, *, embed=None, embeds=None, file=None, files=None, view=None, **_ignored):
    message = {
        "content": "" if content is None else str(content),
        "embeds": [_embed_dict(e) for e in ([embed] if embed is not None else []) + list(embeds or [])] or _menu_card_embeds(view),
        "components": _link_rows(view),
        "files": [f for f in (_file_dict(x) for x in ([file] if file is not None else []) + list(files or [])) if f],
    }
    if message["content"] or message["embeds"] or message["files"]:
        sink.append(message)


class _Sent:
    """What Bub gets back from a send: enough for the follow-ups it records or edits."""

    def __init__(self, channel, content=None, embeds=()):
        self.id = next(_ids)
        self.channel = channel
        self.content = content or ""
        self.embeds = list(embeds)
        self.author = channel.me
        self.reference = None
        self.attachments = []

    async def edit(self, **_kwargs):
        return self

    async def delete(self, **_kwargs):
        return None

    async def add_reaction(self, *_args, **_kwargs):
        return None


class _Channel:
    def __init__(self, channel_id, guild, me, sink):
        self.id = channel_id
        self.guild = guild
        self.me = me
        self._sink = sink

    async def send(self, content=None, **kwargs):
        capture(self._sink, content, **kwargs)
        embeds = [kwargs["embed"]] if kwargs.get("embed") is not None else list(kwargs.get("embeds") or [])
        return _Sent(self, content, embeds)

    async def fetch_message(self, _message_id):
        raise LookupError("no message history while rendering")

    def typing(self):
        return _NoTyping()


class _NoTyping:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _Message:
    def __init__(self, content, *, me, user_id, guild_id, channel_id, sink):
        guild = SimpleNamespace(id=guild_id, me=me) if guild_id else None
        self.id = next(_ids)
        self.content = f"<@{me.id}> {content}"
        self.author = SimpleNamespace(id=user_id, bot=False, name="sfstats", display_name="SF Stats user", mention=f"<@{user_id}>")
        self.guild = guild
        self.channel = _Channel(channel_id, guild, me, sink)
        self.mentions = [me]
        self.raw_mentions = [me.id]
        self.raw_role_mentions = []
        self.role_mentions = []
        self.reference = None
        self.webhook_id = None
        self.embeds = []
        self.attachments = []
        self.type = SimpleNamespace(value=0)
        self.jump_url = ""

    async def reply(self, content=None, **kwargs):
        kwargs.pop("mention_author", None)
        return await self.channel.send(content, **kwargs)

    async def add_reaction(self, *_args, **_kwargs):
        return None


def _authorized(request, secret):
    supplied = request.headers.get("x-sfstats-internal-secret", "")
    return bool(secret) and hmac.compare_digest(supplied.encode(), secret.encode())


def _snowflake(value):
    text = str(value or "")
    return int(text) if text.isdigit() and 17 <= len(text) <= 20 else None


def make_app(*, client, handle_message, secret, ready=lambda: True, version="dev"):
    async def health(_request):
        return web.json_response({"ready": bool(ready()), "version": version}, status=200 if ready() else 503)

    async def render(request):
        if not _authorized(request, secret):
            return web.Response(status=401, text="Unauthorized")
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")
        if not isinstance(body, dict):
            return web.Response(status=400, text="Invalid JSON")
        if not ready():
            return web.json_response({"messages": [], "reason": "loading"}, status=503)
        content = str(body.get("content") or "").strip()[:MAX_CONTENT]
        user_id = _snowflake(body.get("user_id"))
        channel_id = _snowflake(body.get("channel_id")) or 0
        me = getattr(client, "user", None)
        if not content or not user_id or me is None:
            return web.json_response({"messages": [], "reason": "unsupported"}, status=400)
        sink = []
        message = _Message(content, me=me, user_id=user_id, guild_id=_snowflake(body.get("guild_id")),
                           channel_id=channel_id, sink=sink)
        token = RENDERING.set(True)
        try:
            await asyncio.wait_for(handle_message(message), TIMEOUT_SECONDS)
            reason = None
        except asyncio.TimeoutError:
            reason = "timeout"
        except Exception as error:
            reason = type(error).__name__
            print(f"[bub-render] Failed: {reason}: {error}", flush=True)
        finally:
            RENDERING.reset(token)
        # Never log the question itself: only how the answer went.
        print(f"[bub-render] messages={len(sink)} files={sum(len(m['files']) for m in sink)} {reason or 'ok'}", flush=True)
        return web.json_response({"messages": sink, **({"reason": reason} if reason else {})})

    app = web.Application(client_max_size=64 * 1024)
    app.router.add_post("/render", render)
    app.router.add_get("/health", health)
    return app


async def start(*, client, handle_message, ready=lambda: True, version="dev"):
    """Start once (on_ready runs again after reconnects); dormant without BUB_RENDER_PORT."""
    global _runner
    port = os.getenv("BUB_RENDER_PORT", "").strip()
    secret = os.getenv("SFSTATS_INTERNAL_SECRET", "").strip()
    if _runner is not None or not port.isdigit():
        return None
    if len(secret) < 32:
        print("[bub-render] Not started: SFSTATS_INTERNAL_SECRET is missing or short", flush=True)
        return None
    host = os.getenv("BUB_RENDER_HOST", "127.0.0.1").strip() or "127.0.0.1"
    runner = web.AppRunner(make_app(client=client, handle_message=handle_message, secret=secret, ready=ready, version=version), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, int(port)).start()
    _runner = runner
    print(f"[bub-render] Listening on {host}:{port}", flush=True)
    return runner

