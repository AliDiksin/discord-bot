"""The SF Stats frame-data helper: Bub's frame data, served to the SF Stats web app on this machine.

    cd bot && BUB_RENDER_PORT=3015 SFSTATS_INTERNAL_SECRET=... python -m bubbot.render_service

Loads every game's data exactly as Bub does, then answers ``POST /render`` (see
``runtime/render_server.py``). It never connects to Discord: SF Stats receives the messages and
posts the answers itself. Quizzes, reminders, voice and chat never run here.
"""

import asyncio
import os
from types import SimpleNamespace


# The identity Bub's handler sees as "the bot"; the stand-in message always mentions it.
HELPER_USER_ID = 100000000000000001


def helper_user():
    return SimpleNamespace(id=HELPER_USER_ID, name="SF Stats", display_name="SF Stats", bot=True,
                           mention=f"<@{HELPER_USER_ID}>")


async def serve():
    from bubbot.runtime import message_router

    message_router.FRAME_ONLY = True
    # discord.Client.user reads the connection state; without a login there is none.
    message_router.client._connection.user = helper_user()
    if not os.getenv("BUB_RENDER_PORT", "").strip():
        os.environ["BUB_RENDER_PORT"] = "3015"
    await message_router.on_ready()
    if render_server_running():
        await asyncio.Event().wait()
    raise SystemExit("[bub-render] Not started: see the log above")


def render_server_running():
    from bubbot.runtime import render_server

    return render_server._runner is not None


def main():
    asyncio.run(serve())


if __name__ == "__main__":
    main()
