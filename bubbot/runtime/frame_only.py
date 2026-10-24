"""Stand-ins for Bub's local-only modules, so a checkout of ``bot/`` runs frame data on its own.

The Buenavista extension (LLM chat, voice, Streetfighterdle) and reminders live only in Bub's
own deployment and are gitignored here (see AGENTS.md). Without them the bot, and the SF Stats
frame-data helper (``bubbot.render_service``), answers frame data only: every hook below says
"not mine", except the notice for an addressed request nothing matched.
"""


class FrameOnlyExtension:
    def log_status(self):
        print("[frame-only] Buenavista extension not installed: frame data only.", flush=True)

    async def start_background_tasks(self, **_kwargs):
        return None

    def build_reminder_ack_text(self, *_args, **_kwargs):
        return ""

    def build_reminder_fire_text(self, *_args, **_kwargs):
        return ""

    async def maybe_handle_voice_command(self, **_kwargs):
        return False

    async def maybe_handle_streetfighterdle_message(self, **_kwargs):
        return False

    async def maybe_ack_streetfighterdle_score(self, *_args, **_kwargs):
        return None

    async def maybe_handle_private_message(self, **_kwargs):
        return False

    async def rewrite_ggst_lookup_query(self, *_args, **_kwargs):
        return None

    async def rewrite_sf_lookup_query(self, *_args, **_kwargs):
        return None

    def should_suppress_public_implied_frame_lookup(self, *_args, **_kwargs):
        return False

    def should_handle_frame_context_request(self, **_kwargs):
        return False

    async def maybe_handle_frame_context(self, **_kwargs):
        return False

    def should_handle_chat_trigger(self, **_kwargs):
        return False

    async def maybe_handle_chat(self, **_kwargs):
        return False

    def should_send_public_invalid_query_notice(self, *_args, **_kwargs):
        return True


class FrameOnlyReminders:
    def __init__(self, *_args, **_kwargs):
        pass

    async def handle_message(self, *_args, **_kwargs):
        return False

    async def reminder_loop(self):
        return None


buenavista_extension = FrameOnlyExtension()
