"""The SF Stats frame-data helper: what /render runs, returns and refuses.

Imports only ``render_server`` and ``frame_only`` (no discord.py), so it runs anywhere aiohttp is
installed: ``cd bot && PYTHONPATH=. python -m unittest tests.test_render_server``.
"""

import asyncio
import base64
import io
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer

from bubbot.runtime import frame_only, render_server


SECRET = "s" * 40
ME = SimpleNamespace(id=100000000000000001)
USER = "323456789012345678"
ROUTER = Path(__file__).resolve().parents[1] / "bubbot" / "runtime" / "message_router.py"


class Embed:
    def __init__(self, title):
        self.title = title

    def to_dict(self):
        return {"title": self.title}


class View:
    def to_components(self):
        return [{"type": 1, "components": [
            {"type": 2, "style": 1, "custom_id": "compare", "label": "Compare"},
            {"type": 2, "style": 5, "url": "https://wiki.supercombo.gg/w/Street_Fighter_6/JP", "label": "SuperCombo"},
        ]}]


def run(handler, body, *, secret=SECRET, ready=lambda: True):
    async def go():
        app = render_server.make_app(client=SimpleNamespace(user=ME), handle_message=handler, secret=SECRET, ready=ready)
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/render", json=body, headers={"x-sfstats-internal-secret": secret})
            json_body = response.content_type == "application/json"
            return response.status, await response.json() if json_body else await response.text()
    return asyncio.run(go())


class RenderTests(unittest.TestCase):
    def test_bubs_answer_comes_back_instead_of_being_sent(self):
        seen = {}

        async def handler(message):
            seen.update(content=message.content, author=message.author.id, rendering=render_server.rendering(),
                        mentions=[m.id for m in message.mentions])
            sent = await message.reply(embed=Embed("JP 2MP"), view=View(), files=[SimpleNamespace(fp=io.BytesIO(b"GIF89a"), filename="jp-2mp.gif")])
            await sent.edit(view=None)
            await message.channel.send("Second card", embeds=[Embed("JP 2MP (notes)")])

        status, body = run(handler, {"content": "jp crmp", "user_id": USER, "channel_id": "823456789012345678"})
        self.assertEqual(status, 200)
        self.assertEqual(seen, {"content": f"<@{ME.id}> jp crmp", "author": int(USER), "rendering": True, "mentions": [ME.id]},
                         "Bub sees a request addressed to it")
        first, second = body["messages"]
        self.assertEqual(first["embeds"], [{"title": "JP 2MP"}])
        self.assertEqual(first["components"], [{"type": 1, "components": [View().to_components()[0]["components"][1]]}],
                         "only link buttons: the others would need this process to answer their clicks")
        self.assertEqual(first["files"], [{"name": "jp-2mp.gif", "data": base64.b64encode(b"GIF89a").decode()}])
        self.assertEqual((second["content"], second["embeds"], second["files"]), ("Second card", [{"title": "JP 2MP (notes)"}], []))
        self.assertFalse(render_server.rendering(), "the flag never leaks past the request")

    def test_refusals(self):
        async def handler(_message):
            raise AssertionError("never runs")

        self.assertEqual(run(handler, {"content": "jp crmp", "user_id": USER}, secret="wrong")[0], 401)
        self.assertEqual(run(handler, {"content": "", "user_id": USER})[0], 400)
        self.assertEqual(run(handler, {"content": "jp crmp", "user_id": "nope"})[0], 400)
        self.assertEqual(run(handler, ["jp crmp"])[0], 400)
        self.assertEqual(run(handler, {"content": "jp crmp", "user_id": USER}, ready=lambda: False),
                         (503, {"messages": [], "reason": "loading"}))

    def test_failures_and_big_files_never_break_the_answer(self):
        async def handler(message):
            await message.reply("Partial answer", files=[SimpleNamespace(fp=io.BytesIO(b"x" * (render_server.MAX_FILE_BYTES + 1)), filename="huge.gif")])
            raise RuntimeError("lookup crashed")

        status, body = run(handler, {"content": "jp crmp", "user_id": USER})
        self.assertEqual(status, 200)
        self.assertEqual(body["reason"], "RuntimeError")
        self.assertEqual(body["messages"], [{"content": "Partial answer", "embeds": [], "components": [], "files": []}])


class FrameOnlyTests(unittest.TestCase):
    def test_every_extension_hook_bub_calls_exists(self):
        called = set(re.findall(r"buenavista_extension\.(\w+)", ROUTER.read_text(encoding="utf-8")))
        self.assertTrue(called)
        self.assertEqual({name for name in called if not hasattr(frame_only.buenavista_extension, name)}, set())

    def test_nothing_but_frame_data_answers(self):
        ext = frame_only.buenavista_extension
        self.assertFalse(asyncio.run(ext.maybe_handle_chat()))
        self.assertIsNone(asyncio.run(ext.rewrite_sf_lookup_query("jp crmp", str)))
        self.assertTrue(ext.should_send_public_invalid_query_notice(None), "an addressed request nothing matched still gets Bub's notice")
        self.assertFalse(asyncio.run(frame_only.FrameOnlyReminders(None).handle_message(None, "", "")))


if __name__ == "__main__":
    unittest.main()
