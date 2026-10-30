"""Rankings over Bub's frame data: what a table offers, the ranking itself, and the Decisions questions.

``cd bot && PYTHONPATH=. python -m unittest discover -s tests -t tests -p test_frame_rankings.py``.
"""

import math
import unittest
from unittest.mock import AsyncMock, patch

from bubbot.runtime import decisions, frame_rankings
from bubbot.runtime.decisions import Config
from bubbot.runtime.frame_resolver import Game, move_label


ON = Config(key="k" * 20)


def row(char, name, cmd, kind, **values):
    return {"char_name": char, "moveName": name, "numCmd": cmd, "moveType": kind, **values}


TABLE = {
    "ken": [row("Ken", "Stand MP", "5MP", "normal", startup="5", onBlock="+1", dmg="600", range="1.20"),
            row("Ken", "Stand HK", "5HK", "normal", startup="12", onBlock="-4", dmg="900", range="2.10"),
            row("Ken", "Shoryuken", "623HP", "special", startup="5", onBlock="-26", dmg="1400", range="0.9", antiAirMove="1"),
            row("Ken", "Throw", "LPLK", "throw", startup="5", onBlock="-", dmg="1200", range="0.8"),
            row("Ken", "Shinryuken", "236236K", "super", startup="7", onBlock="KD +5", dmg="4000", range=float("nan"))],
    "jp": [row("JP", "Stand HK", "5HK", "normal", startup="13", onBlock="-6", dmg="900", range="3.10"),
           row("JP", "Torbalan", "236P", "special", startup="20", onBlock="+2", dmg="800", range="5.0", projectile="1")],
}
SF6 = Game("sf6", "Street Fighter 6", "sf6", TABLE)
GGST = Game("ggst", "Guilty Gear Strive", "ggst", {"sol": [row("Sol", f"Move {n}", f"{n}K", "normal", startup=str(n), dmg="300") for n in range(3, 9)]})


def scripted(**answers):
    async def decide(text, questions, *, session, config=None, label="decide", timeout_seconds=None):
        if label == "rank-game":
            return {"game": answers["game"]}
        return {name: answers[name] for name in questions if name in answers}
    return AsyncMock(side_effect=decide)


class ParsingTests(unittest.TestCase):
    def test_numbers_are_the_leading_number_of_a_cell(self):
        cases = {"+3": 3, "-2": -2, "800 (1000)": 800, "1.22": 1.22, 12: 12, "KD +30": None, "-": None, "": None, None: None}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(expected, frame_rankings.number(value))
        self.assertIsNone(frame_rankings.number(float("nan")))

    def test_ranking_wording(self):
        for text in ("give me the move with the most range", "fastest normal", "kens most plus move on block", "top 3 jp moves by damage"):
            self.assertTrue(frame_rankings.is_ranking(text), text)
        for text in ("ken 5mp", "define safejump", "ryus medium punch"):
            self.assertFalse(frame_rankings.is_ranking(text), text)
        self.assertEqual("framedata", decisions.local_route("give me the move with the most range"))


class OfferTests(unittest.TestCase):
    def test_a_table_offers_what_it_fills(self):
        offer = frame_rankings.offer(TABLE)
        self.assertEqual({"Ken": "ken", "JP": "jp"}, offer.characters)
        self.assertEqual(["startup", "onBlock", "dmg", "range"], offer.metrics)
        self.assertEqual(["normal", "special"], offer.kinds)   # one throw and one super: too few to offer
        self.assertEqual(["antiAirMove", "projectile"], offer.traits)


class RankTests(unittest.TestCase):
    def setUp(self):
        self.offer = frame_rankings.offer(TABLE)

    def test_all_characters_highest_first_skipping_blanks(self):
        ranking = frame_rankings.rank(SF6, self.offer, metric="range", sort="desc", count=3, label=move_label)
        self.assertEqual([("JP", "Torbalan (236P)", 5.0), ("JP", "Stand HK (5HK)", 3.1), ("Ken", "Stand HK (5HK)", 2.1)],
                         [entry[:3] for entry in ranking.entries])

    def test_one_character_lowest_first_with_filters(self):
        fastest = frame_rankings.rank(SF6, self.offer, character="Ken", metric="startup", sort="asc", kind="normal", count=1)
        self.assertEqual([("Ken", "Stand MP", 5.0)], [entry[:3] for entry in fastest.entries])
        punishable = frame_rankings.rank(SF6, self.offer, metric="onBlock", sort="asc", trait="antiAirMove")
        self.assertEqual([("Ken", "Shoryuken", -26.0)], [entry[:3] for entry in punishable.entries])

    def test_embed(self):
        ranking = frame_rankings.rank(SF6, self.offer, metric="onBlock", sort="desc", count=2, label=move_label)
        embed = frame_rankings.embed(ranking)
        self.assertEqual("Highest On block · all characters (Street Fighter 6)", embed.title)
        self.assertEqual("**1.** JP · Torbalan (236P) — **+2** · startup 20\n**2.** Ken · Stand MP (5MP) — **+1** · startup 5",
                         embed.description)
        fastest = frame_rankings.embed(frame_rankings.rank(SF6, self.offer, character="Ken", metric="startup", sort="asc", count=1))
        self.assertEqual("Fastest startup · Ken (Street Fighter 6)", fastest.title)


class AnswerTests(unittest.IsolatedAsyncioTestCase):
    async def test_street_fighter_6_by_default_in_one_request(self):
        decide = scripted(metric=("range", 0.9), sort=("desc", 0.9), count=("1 move", 0.8),
                          character=("none", 0.95), kind=("none", 0.9), trait=("none", 0.9))
        with patch.object(decisions, "decide", decide):
            ranking = await frame_rankings.answer("give me the move with the most range", games=[SF6, GGST], session=None, config=ON)
        self.assertEqual([("JP", "Torbalan", 5.0)], [entry[:3] for entry in ranking.entries])
        self.assertEqual(["rank"], [call.kwargs["label"] for call in decide.await_args_list])
        asked = decide.await_args_list[0].args[1]
        self.assertEqual(["none", "startup", "onBlock", "dmg", "range"], list(asked["metric"]["criteria"]))
        self.assertEqual("none", next(iter(asked["character"]["criteria"])))

    async def test_a_character_named_in_the_message_wins_over_an_unsure_or_none_answer(self):
        # "marisa longest button range" ranked every character: the model answered none for the character.
        for character in (("none", 0.95), ("Ken", 0.2)):
            decide = scripted(metric=("range", 0.9), sort=("desc", 0.9), character=character)
            with self.subTest(character=character), patch.object(decisions, "decide", decide):
                ranking = await frame_rankings.answer("jp longest button range", games=[SF6], session=None, config=ON)
            self.assertEqual("JP", ranking.character)
            self.assertEqual({"JP"}, {entry[0] for entry in ranking.entries})
        # A sure answer still stands, and naming two characters names neither.
        with patch.object(decisions, "decide", scripted(metric=("range", 0.9), sort=("desc", 0.9), character=("Ken", 0.9))):
            self.assertEqual("Ken", (await frame_rankings.answer("jp longest range", games=[SF6], session=None, config=ON)).character)
        with patch.object(decisions, "decide", scripted(metric=("range", 0.9), sort=("desc", 0.9), character=("none", 0.9))):
            self.assertIsNone((await frame_rankings.answer("ken or jp longest range", games=[SF6], session=None, config=ON)).character)

    async def test_a_named_game_skips_its_question_and_unsure_answers_give_up(self):
        decide = scripted(metric=("startup", 0.9), sort=("asc", 0.9), character=("Sol", 0.9))
        with patch.object(decisions, "decide", decide):
            ranking = await frame_rankings.answer("ggst sol fastest move", games=[SF6, GGST], session=None, tagged=("ggst",), config=ON)
        self.assertEqual(3.0, ranking.entries[0][2])
        self.assertEqual(5, len(ranking.entries))
        self.assertEqual(1, decide.await_count)
        for answers in ({"metric": ("startup", 0.3), "sort": ("asc", 0.9)}, {"metric": ("startup", 0.9), "sort": ("none", 0.9)},
                        {"metric": ("hitstun", 0.9), "sort": ("asc", 0.9)}):
            with self.subTest(answers=answers), patch.object(decisions, "decide", scripted(**answers)):
                self.assertIsNone(await frame_rankings.answer("x", games=[SF6], session=None, tagged=("sf6",), config=ON))
        self.assertIsNone(await frame_rankings.answer("x", games=[SF6], session=None, config=Config()))


if __name__ == "__main__":
    unittest.main()
