"""Bub's failure replies as the same plain card SF Stats uses for its notices: a dark accent, one line, a small hint."""

import discord

# SF Stats' brand accent (src/lib/discord/ui.ts BRAND), so both bots' notices look alike.
ACCENT = discord.Colour(0x0B0B0B)


class FailureCard(discord.ui.LayoutView):
    def __init__(self, text, hint=None):
        super().__init__(timeout=None)
        body = str(text or "").strip() + (f"\n-# {hint}" if hint else "")
        self.add_item(discord.ui.Container(discord.ui.TextDisplay(body[:4000]), accent_colour=ACCENT))
