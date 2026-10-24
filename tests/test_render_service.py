"""End to end: the frame-data helper loads every game and answers as Bub does, without Discord.

Needs Bub's packages (discord.py, pandas, odfpy) and the workbooks, so it runs on the hosted
runner, never on the SF Stats server; it skips where they are missing.
``cd bot && PYTHONPATH=. python -m unittest tests.test_render_service``.
"""

import asyncio
import importlib.util
import json
import os
import unittest
from pathlib import Path


BOT = Path(__file__).resolve().parents[1]
HAVE_PACKAGES = all(importlib.util.find_spec(name) for name in ("discord", "pandas", "odf"))
SECRET = "s" * 40
USER = "323456789012345678"
# Each of Bub's games, as people ask SF Stats: the card's text must name what was asked for.
QUESTIONS = {
    "jp crmp": "jp",
    "ryu 5hp on block": "ryu",
    "ken fireball gif": "ken",
    "ggst ky 5h": "ky",
    "sfv ryu 5mp": "ryu",
    "usf4 cammy cannon spike lk framedata": "cammy",
    "3s urien 5hp": "urien",
    "ragna 5b": "ragna",
    "ahri 5l": "ahri",
    "terry far c": "terry",
    "mk1 sub 1 framedata": "sub",
    "ryu corner combo": "ryu",
}


@unittest.skipUnless(HAVE_PACKAGES, "needs Bub's packages: runs on the hosted runner")
class RenderServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(BOT)
        os.environ.pop("BUB_RENDER_PORT", None)
        from bubbot import render_service
        from bubbot.runtime import message_router, render_server

        cls.router, cls.server = message_router, render_server
        message_router.FRAME_ONLY = True
        message_router.client._connection.user = render_service.helper_user()
        asyncio.run(message_router.on_ready())

    def ask(self, content):
        from aiohttp.test_utils import TestClient, TestServer

        async def go():
            app = self.server.make_app(client=self.router.client, handle_message=self.router._handle_message,
                                       secret=SECRET, ready=lambda: self.router._DATA_LOADED)
            async with TestClient(TestServer(app)) as client:
                response = await client.post("/render", json={"content": content, "user_id": USER},
                                             headers={"x-sfstats-internal-secret": SECRET})
                self.assertEqual(response.status, 200)
                return await response.json()
        return asyncio.run(go())

    def test_every_game_answers(self):
        self.assertTrue(self.router._DATA_LOADED)
        failures = []
        for question, expected in QUESTIONS.items():
            body = self.ask(question)
            text = json.dumps(body["messages"]).lower()
            if body.get("reason") or not body["messages"] or expected not in text:
                failures.append(f"{question!r} → {body.get('reason')} {text[:200]}")
        self.assertEqual(failures, [])

    def test_never_logs_in_or_schedules(self):
        self.assertFalse(self.router.client.is_ready(), "no gateway connection")
        self.assertIsNone(self.router.reminder_task_handle)


if __name__ == "__main__":
    unittest.main()
