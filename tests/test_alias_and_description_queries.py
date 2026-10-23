import unittest
from pathlib import Path

import bot

from bubbot.frame_data import ggst_frame_data
from bubbot.utils.text_utils import normalize_query_terms


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_WORKBOOKS = ("GGST Frame Data.ods", "FAT - SF6 Frame Data.ods")


@unittest.skipUnless(all((ROOT / name).exists() for name in REQUIRED_WORKBOOKS), "local frame-data workbooks required")
class AliasAndDescriptionQueries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ggst_frame_data.load_frame_data():
            raise RuntimeError("Failed to load GGST frame data")
        bot.load_frame_data()
        if not bot.FRAME_DATA:
            raise RuntimeError("Failed to load SF6 frame data")

    def test_sf6_character_alias_resolves_bare_move_name_like_canonical_name(self):
        for alias_query, canonical_query, character, move in (
            ("Gief lariat", "zangief lariat", "Zangief", "Double Lariat"),
            ("gief hellstab", "zangief hellstab", "Zangief", "Hellstab"),
            ("gief stomp", "zangief stomp", "Zangief", "Stomp"),
        ):
            with self.subTest(query=alias_query):
                alias_payload = bot.find_moves_in_text(alias_query)
                canonical_payload = bot.find_moves_in_text(canonical_query)
                self.assertEqual("frame", alias_payload.get("mode"))
                self.assertFalse(alias_payload.get("missing_scrolls_query"))
                rows = [(row.get("char_name"), row.get("moveName")) for row in alias_payload.get("rows", [])]
                self.assertEqual([(character, move)], rows)
                self.assertEqual(
                    rows,
                    [(row.get("char_name"), row.get("moveName")) for row in canonical_payload.get("rows", [])],
                )

    def test_sf6_alias_query_with_bot_mention_and_extra_words(self):
        payload = bot.find_moves_in_text("<@123456789> Gief lariat")
        self.assertEqual("frame", payload.get("mode"))
        self.assertEqual(["Double Lariat"], [row.get("moveName") for row in payload.get("rows", [])])

    def test_sf6_alias_does_not_strip_move_words_that_were_not_typed_as_the_alias(self):
        payload = bot.find_moves_in_text("gief double lariat")
        self.assertEqual(["Double Lariat"], [row.get("moveName") for row in payload.get("rows", [])])

    def test_description_is_a_frame_data_request(self):
        for query in (
            "johnny joker trick description",
            "@bub johnny joker trick description",
            "johnny joker trick desc",
            "johnny 236236s description",
        ):
            with self.subTest(query=query):
                payload = ggst_frame_data.find_moves_in_text(query)
                self.assertEqual("frame", payload.get("mode"))
                self.assertTrue(payload.get("frame_query"))
                self.assertEqual(["Joker Trick"], [row.get("moveName") for row in payload.get("rows", [])])
                self.assertIn("Startup", payload.get("data", ""))

    def test_millia_hair_car_alias_resolves_iron_savior_only_for_millia(self):
        for query in ("millia hair car", "<@123> millia hair car", "hair car millia", "millia hair car frame data"):
            with self.subTest(query=query):
                payload = ggst_frame_data.find_moves_in_text(query)
                self.assertEqual(
                    [("Millia", "Iron Savior", "214P")],
                    [(row.get("char_name"), row.get("moveName"), row.get("numCmd")) for row in payload.get("rows", [])],
                )
        self.assertEqual([], ggst_frame_data.find_moves_in_text("ky hair car").get("rows"))

    def test_character_move_aliases_ignore_spaces_and_punctuation(self):
        # Only "hair car" is registered; spacing variants must not need their own aliases.
        for query in ("millia haircar", "millia Hair-Car", "millia hair  car", "millia hairc ar", "haircar millia"):
            with self.subTest(query=query):
                rows = ggst_frame_data.find_moves_in_text(query).get("rows", [])
                self.assertEqual([("Millia", "Iron Savior")], [(row.get("char_name"), row.get("moveName")) for row in rows])
        self.assertNotIn("haircar", ggst_frame_data.GGST_CHARACTER_MOVE_ALIASES["millia"])
        lookup = ggst_frame_data.lookup_character_move_alias
        self.assertEqual("623S", lookup("sol", "s vv"))
        self.assertEqual("623S", lookup("sol", "SVV"))
        self.assertIsNone(lookup("sol", "haircar"))
        self.assertIsNone(lookup("unknown", "svv"))
        self.assertIsNone(lookup("sol", ""))

    def test_description_synonym_is_exact_only(self):
        self.assertIn("framedata", normalize_query_terms("ky stun dipper description"))
        for word in ("deception", "descriptoin", "describe"):
            with self.subTest(word=word):
                self.assertEqual(word, normalize_query_terms(word))


if __name__ == "__main__":
    unittest.main()
