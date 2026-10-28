"""Menus are SF Stats cards (Components V2) and results stay embeds; a result's buttons open menus as new cards."""

import asyncio
import unittest

import discord

from bubbot.features import menu_system
from bubbot.runtime import render_server
from bubbot.utils.sfstats_style import ACTION, BRAND, DIVIDER, CardView, card_text


class _Response:
    def __init__(self):
        self.calls = []

    async def send_message(self, *args, **kwargs):
        self.calls.append(("send_message", kwargs))

    async def edit_message(self, *args, **kwargs):
        self.calls.append(("edit_message", kwargs))


class _Interaction:
    def __init__(self, user_id=1):
        self.user = type("User", (), {"id": user_id})()
        self.response = _Response()


class CardViewTests(unittest.TestCase):
    def test_text_in_one_branded_container_with_controls_below(self):
        class Menu(CardView):
            @discord.ui.button(label="Back", style=ACTION, row=1)
            async def back_button(self, interaction, button):
                return ("back", button.label)

        menu = Menu().set_card(card_text("Title", "Line.", footer=["Page 1 of 2", None]), DIVIDER, "**More**")
        menu.add_item(discord.ui.Select(placeholder="Pick", options=[discord.SelectOption(label="a", value="a")]))
        container, *rows = menu.to_components()
        self.assertEqual(17, container["type"])
        self.assertEqual(BRAND.value, container["accent_color"])
        self.assertEqual("## Title\nLine.\n-# Page 1 of 2", container["components"][0]["content"])
        self.assertEqual([[3], [2]], [[item["type"] for item in row["components"]] for row in rows])
        # @discord.ui.button controls are kept (LayoutView alone drops them), bound and iconed by label.
        self.assertIs(menu.back_button.view, menu)
        self.assertIsNotNone(menu.back_button.emoji)
        self.assertEqual(("back", "Back"), asyncio.run(menu.back_button.callback(_Interaction())))

    def test_text_stays_within_discords_limit(self):
        card = CardView().set_card("a" * 3000, "b" * 3000)
        texts = [part["content"] for part in card.to_components()[0]["components"] if part["type"] == 10]
        self.assertEqual(4000, sum(len(text) for text in texts))


class MenuFlowTests(unittest.TestCase):
    def test_main_menu_is_a_card(self):
        menu = menu_system.MainMenuView(5)
        container = menu.to_components()[0]
        self.assertTrue(container["components"][0]["content"].startswith("## SF Stats"))
        labels = [item.label for item in menu._controls if isinstance(item, discord.ui.Button)]
        self.assertEqual(["Readme", "Glossary"], labels)

    def test_return_to_menu_on_a_result_opens_a_private_menu(self):
        result = menu_system.OwnedView(owner_id=None)
        button = menu_system.FrameReturnMenuButton()
        result.add_item(button)
        interaction = _Interaction(user_id=9)
        asyncio.run(button.callback(interaction))
        [(method, kwargs)] = interaction.response.calls
        self.assertEqual("send_message", method)
        self.assertTrue(kwargs["ephemeral"])
        self.assertIsInstance(kwargs["view"], menu_system.MainMenuView)
        self.assertEqual(9, kwargs["view"].owner_id)

    def test_frame_data_helper_still_gets_menus_as_embeds(self):
        sink = []
        render_server.capture(sink, view=menu_system.MainMenuView(5))
        [message] = sink
        self.assertEqual("SF Stats", message["embeds"][0]["title"])
        self.assertEqual([], message["components"])


if __name__ == "__main__":
    unittest.main()
