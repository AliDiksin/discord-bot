import re
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

import bot

from bubbot.data.aliases import SF6_STAT_PHRASE_ALIASES
from bubbot.features import bub_llm
from bubbot.frame_data import avtl_frame_data
from bubbot.frame_data import bbcf_frame_data
from bubbot.frame_data import cotw_frame_data
from bubbot.frame_data import gif_lookup
from bubbot.frame_data import ggacr_frame_data
from bubbot.frame_data import ggst_frame_data
from bubbot.frame_data import mk1_frame_data
from bubbot.frame_data import sfv_frame_data
from bubbot.frame_data import third_strike_frame_data
from bubbot.frame_data import tuco_frame_data
from bubbot.frame_data import usfiv_frame_data
from bubbot.frame_data.sf6_loader import jamie_drink_level_from_sheet_name
from bubbot.frame_data.sf6_character_aliases import jamie_drink_level_from_text
from bubbot.frame_data.sf6_character_stats import match_stat_keys_in_text
from bubbot.runtime import message_router
from bubbot.utils import text_utils
from bubbot.utils.frame_match_utils import prefer_grounded_rows, row_is_air_move, row_strengths
from bubbot.utils.text_utils import QUERY_TERM_ALIASES, compact_key, normalize_query_terms
from scripts.sync_ufd_sf6_gifs import drink_level_from_label


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_WORKBOOKS = (
    "GGST Frame Data.ods",
    "GGACR Frame Data.ods",
    "BBCF Frame Data.ods",
    "COTW Frame Data.ods",
    "2XKO Frame Data.ods",
    "SF5 Frame Data - FAT .ods",
    "USFIV Frame Data.ods",
    "Third Strike Frame Data.ods",
    "FAT - SF6 Frame Data.ods",
    "AVTL Frame Data.ods",
)


class RoutingPerformanceRegressions(unittest.TestCase):
    def test_ground_preference_preserves_air_only_moves_and_explicit_air(self):
        ground = {"moveName": "Air Slasher", "numCmd": "46LP", "extraInfo": "Anti-air", "guard": "Air"}
        air = {"moveName": "Strike", "numCmd": "j.236A"}
        self.assertFalse(row_is_air_move(ground))
        self.assertEqual([ground], prefer_grounded_rows([air, ground], "strike"))
        self.assertEqual([air], prefer_grounded_rows([air], "strike"))
        for query in ("air strike", "jump 236a", "j.236a", "j236a", "jA", "8LP"):
            self.assertEqual([air, ground], prefer_grounded_rows([air, ground], query))

    def test_mimo_is_the_only_llm_provider(self):
        self.assertEqual(bub_llm.MIMO_ENABLED, bub_llm.LLM_ENABLED)
        self.assertFalse(hasattr(bub_llm, "GEMINI_ENABLED"))
        self.assertFalse(hasattr(bub_llm, "OPENROUTER_ENABLED"))
        self.assertFalse(hasattr(bub_llm, "get_gemini_response"))
        self.assertFalse(hasattr(bub_llm, "get_openrouter_response"))

    def test_explicit_game_tags_select_only_relevant_parsers(self):
        cases = {
            "sf6 ryu 5lp": {"sf6"},
            "sfv ryu 5lp": {"sfv"},
            "2xko ahri 5l": {"tuco"},
            "bbcf ragna 5b": {"bbcf"},
            "cotw terry 5a": {"cotw"},
            "3s akuma 5hp": {"third_strike"},
            "usf4 adon 5lp": {"usfiv"},
            "mk1 baraka 1": {"mk1"},
            "ggst sol 5k": {"ggst", "ggacr"},
            "ggacr sol 5k": {"ggst", "ggacr"},
        }
        no_exact_matches = (False,) * 11
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(
                    expected,
                    message_router._selected_frame_parser_subset(query, no_exact_matches),
                )

    def test_exact_character_selection_preserves_fuzzy_fallback(self):
        exact_matches = (False, False, False, False, True, False, False, False, False, False, False)
        self.assertEqual(
            {"bbcf"},
            message_router._selected_frame_parser_subset("ragna 5b", exact_matches),
        )
        self.assertIsNone(
            message_router._selected_frame_parser_subset("unknown 5b", (False,) * 11),
        )

    def test_typo_correction_reuses_completed_result(self):
        aliases = {"startup": "startup"}
        text_utils._TYPO_CORRECTION_CACHE.clear()
        with patch.object(
            text_utils.difflib,
            "get_close_matches",
            wraps=text_utils.difflib.get_close_matches,
        ) as close_matches:
            first = text_utils.correct_alias_typos("startpu", aliases)
            second = text_utils.correct_alias_typos("startpu", aliases)
        self.assertEqual("startup", first)
        self.assertEqual(first, second)
        self.assertEqual(1, close_matches.call_count)


requires_local_sf6_gifs = unittest.skipUnless(
    (ROOT / "sf6frames" / "files").is_dir(), "local SF6 GIF media (sf6frames/files) required"
)


@unittest.skipUnless(all((ROOT / name).exists() for name in REQUIRED_WORKBOOKS), "local frame-data workbooks required")
class FrameQueryRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for module in (
            ggst_frame_data,
            ggacr_frame_data,
            bbcf_frame_data,
            cotw_frame_data,
            tuco_frame_data,
            sfv_frame_data,
            usfiv_frame_data,
            third_strike_frame_data,
            mk1_frame_data,
            avtl_frame_data,
        ):
            if not module.load_frame_data():
                raise RuntimeError(f"Failed to load frame data for {module.__name__}")
        bot.load_frame_data()
        if not bot.FRAME_DATA:
            raise RuntimeError("Failed to load SF6 frame data")

    def assert_comparison(self, module, query, expected_commands):
        payload = module.find_moves_in_text(query)
        self.assertTrue(payload.get("wants_comparison"), query)
        self.assertEqual(expected_commands, [row.get("numCmd") for row in payload.get("rows", [])], query)

    def test_same_character_comparisons_across_games(self):
        cases = (
            (ggst_frame_data, "ky 2s vs 5k gatling", ["2S", "5K"]),
            (ggacr_frame_data, "ggacr ky 2s vs 2h framedata", ["2S", "2H"]),
            (bbcf_frame_data, "bbcf ragna 2b vs 5c framedata", ["2B", "5C"]),
            (cotw_frame_data, "cotw terry 2c vs 2d framedata", ["2C", "2D"]),
            (tuco_frame_data, "2xko ahri 2h vs 5l framedata", ["2H", "5L"]),
            (sfv_frame_data, "sfv ryu 2mk vs 5hp framedata", ["2MK", "5HP"]),
            (usfiv_frame_data, "usf4 ryu 2mk vs 2hk framedata", ["D MK", "D HK"]),
            (third_strike_frame_data, "3s ryu 2mk vs 2hk framedata", ["2MK", "2HK"]),
            (mk1_frame_data, "mk1 scorpion b2 vs b3 framedata", ["B+2", "B+3"]),
        )
        for module, query, expected_commands in cases:
            with self.subTest(query=query):
                self.assert_comparison(module, query, expected_commands)

    def test_avtl_notation_names_and_fuzzy_typos_resolve(self):
        cases = (
            ("avtl zuko 5a", "zuko", "5A"),
            ("zuko 5a", "zuko", "5A"),
            ("aang air scooter", None, "236A"),
            ("avtl aang 236a", "aang", "236A"),
            ("zuko igniting blast", "zuko", "4B"),
            ("zukko 5a", "zuko", "5A"),
            ("nightmare korra 236abc", "nightmare_korra", "236ABC"),
        )
        for query, char_key, command in cases:
            with self.subTest(query=query):
                payload = avtl_frame_data.find_moves_in_text(query)
                self.assertTrue(payload.get("rows"), query)
                row = payload["rows"][0]
                if char_key:
                    self.assertEqual(char_key, row.get("char_key"), query)
                self.assertEqual(command, row.get("numCmd"), query)

    def test_avtl_embeds_first_media_and_keeps_source_thumbnail_urls(self):
        from bubbot.features.menu_system import FrameResultView

        row = avtl_frame_data.find_moves_in_text("avtl zuko 5c")["rows"][0]
        media = avtl_frame_data.get_media_links(row, limit=None)
        view = FrameResultView("avtl", "zuko", row, owner_id=1)

        self.assertTrue(media)
        self.assertIn("/300px-", media[0])
        self.assertEqual(media[0], view.build_embed().image.url)
        self.assertNotIn(media[0], view.all_hitbox_images_button.hitbox_links)

    def test_avtl_plain_notation_defaults_to_base_grounded_move(self):
        for command in ("214A", "214B", "214C", "j214A", "j214B", "j214C"):
            with self.subTest(command=command):
                payload = avtl_frame_data.find_moves_in_text(f"avtl zaheer {command}")
                self.assertFalse(payload.get("needs_disambiguation"))
                self.assertEqual([f"Zaheer_{command}"], [row["moveId"] for row in payload["rows"]])
        for query in ("j.214a", "jump 214a", "air 214a"):
            self.assertEqual("Zaheer_j214A", avtl_frame_data.find_matching_rows("zaheer", query)[0]["moveId"])
        self.assertEqual(
            "Zaheer_214A_Ming_Hua",
            avtl_frame_data.find_matching_rows("zaheer", "214a ming hua")[0]["moveId"],
        )

    def test_avtl_scraper_restores_air_input_before_media_keying(self):
        from scripts.scrape_avtl_supercombo import parse_character

        rows, media, _ = parse_character("Zaheer", "Avatar Legends/Zaheer/Data", """
{{FrameData-AL
| moveId = Zaheer_j214A
| input = 214A
| name = Air Call
| startup = 37
| images = AL Zaheer j214A.png
}}
""")
        self.assertEqual("j214A", rows[0]["numCmd"])
        self.assertEqual("j214a", media[0][1])

    def test_fuzzy_comparison_terms_across_games(self):
        cases = (
            (ggst_frame_data, "ggst ky 2s verssu 5k", ["2S", "5K"]),
            (bbcf_frame_data, "bbcf ragna 2b verssu 5c", ["2B", "5C"]),
            (third_strike_frame_data, "3s ryu 2mk verssu 2hk", ["2MK", "2HK"]),
        )
        for module, query, expected_commands in cases:
            with self.subTest(query=query):
                self.assert_comparison(module, query, expected_commands)

    def test_existing_two_character_comparison_still_works(self):
        payload = ggst_frame_data.find_moves_in_text("ggst ky 5k vs sol 5k gatling")
        self.assertTrue(payload.get("wants_comparison"))
        self.assertEqual(["ky", "sol"], [row.get("char_key") for row in payload.get("rows", [])])

    def test_sf6_target_combo_comma_and_tilde_shorthand(self):
        for query in ("manon 2hp,hp", "manon 2hp~hp"):
            with self.subTest(query=query):
                payload = bot.find_moves_in_text(query)
                self.assertTrue(payload.get("target_combo_query"))
                self.assertEqual(["2HP > HP"], [row.get("numCmd") for row in payload.get("rows")])

    def test_street_fighter_strength_words_select_one_row(self):
        cases = (
            (sfv_frame_data, "sf5 dan light dankukyaku", "214LK", ""),
            (sfv_frame_data, "sf5 dan medium dankukyaku", "214MK", ""),
            (sfv_frame_data, "sf5 dan heavy dankukyaku", "214HK", ""),
            (usfiv_frame_data, "sf4 dan light dankyaku", "214 LK ARMORBREAK", "LK"),
            (usfiv_frame_data, "sf4 dan medium dankyaku", "214 MK ARMORBREAK", "MK"),
            (usfiv_frame_data, "sf4 dan heavy dankyaku", "214 HK ARMORBREAK", "HK"),
            (third_strike_frame_data, "3s ken light tatsu", "214K", "LK"),
            (third_strike_frame_data, "3s ken medium tatsu", "214K", "MK"),
            (third_strike_frame_data, "3s ken heavy tatsu", "214K", "HK"),
        )
        for module, query, command, version in cases:
            with self.subTest(query=query):
                payload = module.find_moves_in_text(query)
                self.assertEqual(1, len(payload.get("rows", [])), query)
                row = payload["rows"][0]
                self.assertEqual(command, row.get("numCmd"), query)
                if version:
                    self.assertTrue(str(row.get("version", "")).endswith(version), query)

    def test_oni_motion_strength_does_not_fall_back_to_stand_hk(self):
        for query in ("sf4 oni 623hk", "oni heavy 623k"):
            with self.subTest(query=query):
                payload = usfiv_frame_data.find_moves_in_text(query)
                self.assertEqual(1, len(payload.get("rows", [])), query)
                row = payload["rows"][0]
                self.assertEqual("Sekisei Jiraiken", row.get("moveName"), query)
                self.assertEqual("Ground Pound HK", row.get("version"), query)

    def test_unqualified_oni_623k_preserves_three_normal_strengths(self):
        payload = usfiv_frame_data.find_moves_in_text("oni 623k")
        self.assertTrue(payload.get("needs_disambiguation"))
        self.assertEqual(
            ["Ground Pound LK", "Ground Pound MK", "Ground Pound HK"],
            [row.get("version") for row in payload.get("rows", [])],
        )

    def test_strength_extraction_covers_workbook_edge_encodings(self):
        self.assertEqual(frozenset({"HP"}), row_strengths({"moveName": "Angle Jump HP", "numCmd": "9 LK"}))
        self.assertEqual(frozenset({"EX"}), row_strengths({"moveName": "Airborne EX Soul Spark", "numCmd": "236PP"}))
        self.assertEqual(frozenset({"LP", "MP"}), row_strengths({"moveName": "LPMP Thunder Clap", "numCmd": "214LPMP"}))

    def test_sf6_named_moves_outrank_hp_health_shorthand(self):
        cases = (
            ("ryu hp hadouken", "HP Hadoken", "236HP"),
            ("ryu hadouken hp", "HP Hadoken", "236HP"),
            ("ken hp dp", "HP Shoryuken", "623HP"),
            ("guile hp boom", "HP Sonic Boom", "46HP"),
            ("c.viper hp tracer combination", "HP Tracer Combination", "214HP > 6PP"),
            ("ken hk jinrai kick", "HK Jinrai Kick", "236HK"),
            ("yasmine alon", "LP Alon", "236LP > 6P"),
            ("yasmine lp alon", "LP Alon", "236LP > 6P"),
            ("yasmine mp alon", "MP Alon", "236MP > 6P"),
            ("yasmine hp alon", "HP Alon", "236HP > 6P"),
            ("yasmine heavy daloy ng tubig", "HP Daloy ng Tubig", "236HP"),
        )
        for query, move_name, command in cases:
            with self.subTest(query=query):
                payload = bot.find_moves_in_text(query)
                self.assertEqual("frame", payload.get("mode"), query)
                self.assertEqual([move_name], [row.get("moveName") for row in payload.get("rows", [])], query)
                self.assertEqual([command], [row.get("numCmd") for row in payload.get("rows", [])], query)

        stats_payload = bot.find_moves_in_text("yasmine hp")
        self.assertEqual("stats", stats_payload.get("mode"))
        self.assertEqual(["health"], stats_payload.get("stats_keys"))

        explicit_stats_payload = bot.find_moves_in_text("yasmine hp alon health")
        self.assertEqual(["health"], explicit_stats_payload.get("stats_keys"))
        self.assertEqual("HP Alon", explicit_stats_payload["rows"][0].get("moveName"))

        broad_stats_payload = bot.find_moves_in_text("ryu hp stats")
        self.assertEqual("stats", broad_stats_payload.get("mode"))
        self.assertEqual(["health"], broad_stats_payload.get("stats_keys"))
        self.assertEqual([], broad_stats_payload.get("rows"))

    def test_sf6_broad_stats_yields_to_identified_move(self):
        for query, command in (("cammy level 2 stats", "214214P"), ("cammy 5lp stats", "5LP")):
            with self.subTest(query=query):
                payload = bot.find_moves_in_text(query)
                self.assertFalse(payload.get("stats_only"), query)
                self.assertEqual("frame", payload.get("mode"), query)
                self.assertEqual([command], [row.get("numCmd") for row in payload.get("rows", [])], query)
        stats_only_payload = bot.find_moves_in_text("cammy stats")
        self.assertTrue(stats_only_payload.get("stats_only"))
        self.assertEqual([], stats_only_payload.get("rows"))
        specific_stats_payload = bot.find_moves_in_text("cammy throw range")
        self.assertTrue(specific_stats_payload.get("stats_only"))
        self.assertEqual(["throwHurt", "throwRange"], specific_stats_payload.get("stats_keys"))

    def test_sf6_stat_terms_support_compact_and_typo_variants(self):
        for phrases, expected_keys in SF6_STAT_PHRASE_ALIASES:
            for phrase in phrases:
                compact_phrase = compact_key(phrase)
                if compact_phrase == phrase:
                    continue
                with self.subTest(compact_phrase=compact_phrase):
                    self.assertTrue(
                        set(expected_keys).issubset(match_stat_keys_in_text(compact_phrase))
                    )

        cases = (
            ("ryu walkspeed", ["bWalk", "fWalk"]),
            ("ryu walkspeeed", ["bWalk", "fWalk"]),
            ("ryu waalk speed", ["bWalk", "fWalk"]),
            ("ryu dashspeed", ["bDash", "bDashDist", "fDash", "fDashDist"]),
            ("ryu dashspeeed", ["bDash", "bDashDist", "fDash", "fDashDist"]),
            ("ryu helth", ["health"]),
            ("ryu throwrnage", ["throwRange"]),
            ("ryu driverush", ["dRushDist", "dRushDistBlock", "dRushDistMax", "dRushDistMin"]),
        )
        for query, expected_keys in cases:
            with self.subTest(query=query):
                payload = bot.find_moves_in_text(query)
                self.assertEqual("stats", payload.get("mode"), query)
                self.assertEqual(expected_keys, payload.get("stats_keys"), query)

    def test_shared_query_terms_support_compact_forms(self):
        for canonical, aliases in QUERY_TERM_ALIASES:
            for alias in aliases:
                with self.subTest(alias=alias):
                    self.assertEqual(canonical, normalize_query_terms(compact_key(alias)))

        self.assertEqual("flame date", normalize_query_terms("flame date"))

    def test_fuzzy_shared_query_terms_across_all_games(self):
        games = (
            (bot, "ryu 2mk", "2MK"),
            (sfv_frame_data, "sfv ryu 2mk", "2MK"),
            (usfiv_frame_data, "usf4 ryu 2mk", "D MK"),
            (third_strike_frame_data, "3s ryu 2mk", "2MK"),
            (ggst_frame_data, "ggst ky 2s", "2S"),
            (ggacr_frame_data, "ggacr ky 2s", "2S"),
            (bbcf_frame_data, "bbcf jin 3c", "3C"),
            (cotw_frame_data, "cotw terry 2c", "2C"),
            (tuco_frame_data, "2xko ahri 2h", "2H"),
            (mk1_frame_data, "mk1 scorpion b2", "B+2"),
        )
        for module, base_query, expected_command in games:
            for term in ("stratup", "blockadvantage", "block advantge", "framedta", "imgae"):
                query = f"{base_query} {term}"
                with self.subTest(module=module.__name__, term=term):
                    payload = module.find_moves_in_text(query)
                    self.assertEqual([expected_command], [row.get("numCmd") for row in payload.get("rows", [])], query)
                    if term == "imgae":
                        self.assertTrue(payload.get("gif_query"), query)

    def test_fuzzy_property_terms_preserve_compound_precedence(self):
        cases = {
            "blockadvantage": "on_block",
            "block advantge": "on_block",
            "frameadvantage": "frame_advantage",
            "chipdamge": "chip_damage",
            "guarddamge": "guard_damage",
            "supermetergain": "super_gain",
        }
        for query, expected_key in cases.items():
            with self.subTest(query=query):
                self.assertEqual(expected_key, message_router._requested_property_key(query))

    def test_resolved_move_identity_outranks_property_terms(self):
        rows = ggst_frame_data.find_moves_in_text("ky stun dipper").get("rows", [])
        self.assertEqual(["Stun Dipper"], [row.get("moveName") for row in rows])
        self.assertIsNone(
            message_router._requested_property_key_after_move_resolution("ky stun dipper", rows)
        )
        self.assertEqual(
            "stun",
            message_router._requested_property_key_after_move_resolution("ky stun dipper stun", rows),
        )
        self.assertEqual(
            "stun",
            message_router._requested_property_key_after_move_resolution("ky 236k stun", rows),
        )

    def test_all_sf6_strength_prefixed_move_names_resolve_from_loaded_data(self):
        checked_queries = set()
        for char, rows in bot.FRAME_DATA.items():
            for row in rows:
                move_name = str(row.get("moveName", "")).strip()
                match = re.match(
                    r"^(LP|MP|HP|LK|MK|HK)\s+(.+?)(?:\s+\([^)]*\))?$",
                    move_name,
                    re.IGNORECASE,
                )
                if not match:
                    continue
                strength, base_name = match.groups()
                query = f"{char} {strength.lower()} {base_name.lower()}"
                if query in checked_queries:
                    continue
                checked_queries.add(query)
                with self.subTest(query=query):
                    payload = bot.find_moves_in_text(query)
                    result_names = [str(result.get("moveName", "")) for result in payload.get("rows", [])]
                    self.assertTrue(
                        any(
                            candidate.lower().startswith(f"{strength.lower()} ")
                            and base_name.lower() in candidate.lower()
                            for candidate in result_names
                        ),
                        f"{query}: {result_names}",
                    )
        self.assertGreater(len(checked_queries), 300)

    def test_jamie_drink_sheets_and_query_forms_select_correct_level(self):
        self.assertEqual(
            [1, 2, 3, 4],
            [jamie_drink_level_from_sheet_name(f"JamieD{level}") for level in range(1, 5)],
        )
        self.assertEqual(2, jamie_drink_level_from_sheet_name("jamied 2"))
        self.assertIsNone(jamie_drink_level_from_sheet_name("JamieD5"))

        for level in range(1, 5):
            with self.subTest(level=level):
                query_forms = (
                    f"jamie 5lp drink level {level}",
                    f"jamie d{level} 5lp",
                    f"jamie dl{level} 5lp",
                    f"jamie 5lp drinks {level}",
                )
                expected_damage = 270 + (15 * level)
                for query in query_forms:
                    payload = bot.find_moves_in_text(query)
                    self.assertEqual("frame", payload.get("mode"), query)
                    self.assertEqual(1, len(payload.get("rows", [])), query)
                    row = payload["rows"][0]
                    self.assertEqual(level, row.get("_jamie_drink_level"), query)
                    self.assertEqual(expected_damage, row.get("dmg"), query)

        for text, level in (("d0", 0), ("dl1", 1), ("dl2", 2), ("drink level 3", 3), ("drinks 4", 4)):
            self.assertEqual(level, jamie_drink_level_from_text(text))

        base_payload = bot.find_moves_in_text("jamie 5lp")
        self.assertIsNone(base_payload["rows"][0].get("_jamie_drink_level"))
        self.assertEqual(270, base_payload["rows"][0].get("dmg"))

    def test_jamie_drink_gifs_and_embed_header_follow_selected_level(self):
        self.assertEqual(0, drink_level_from_label("0 Drinks"))
        self.assertEqual(1, drink_level_from_label("1+ Drinks"))
        self.assertEqual(0, drink_level_from_label("0-3 Drinks"))
        self.assertEqual(1, gif_lookup.parse_local_hitbox_gif_filename(
            "5LP_Standing_Light_Punch_Drink_Level_1.gif"
        ).get("drink_level"))

        gif_rows = [
            {"moveName": "Standing Light Punch", "numCmd": "5LP", "moveLink": "base.gif"},
            {
                "moveName": "Standing Light Punch Drink Level 0",
                "numCmd": "5LP",
                "moveLink": "level0.gif",
                "drink_level": 0,
            },
            {
                "moveName": "Standing Light Punch Drink Level 1",
                "numCmd": "5LP",
                "moveLink": "level1.gif",
                "drink_level": 1,
            },
        ]
        with patch.dict(bot.HITBOX_GIF_DATA, {"jamie": gif_rows}):
            for level, expected_link in ((0, "level0.gif"), (1, "level1.gif"), (4, "level1.gif")):
                with self.subTest(level=level):
                    row = bot.find_moves_in_text(f"jamie dl{level} 5lp")["rows"][0]
                    self.assertEqual(expected_link, bot.lookup_hitbox_gif_link(row))

            self.assertEqual(
                ["level1.gif"],
                bot.lookup_hitbox_gif_links_from_query("jamie", "dl1 5lp"),
            )

        level_one_row = bot.find_moves_in_text("jamie dl1 5lp")["rows"][0]
        self.assertIn("(drink level 1)", bot.build_frame_embed(level_one_row).description)

    def test_jamie_drink_progression_applies_to_all_simple_commands(self):
        commands = {}
        for row in bot.FRAME_DATA["jamie"]:
            command = str(row.get("numCmd", "")).strip()
            if re.fullmatch(r"[1-9][0-9]*(?:LP|MP|HP|LK|MK|HK|PP|KK)(?: \(air\))?", command, re.IGNORECASE):
                commands.setdefault(command, []).append(row)

        checked_queries = 0
        for command, variants in commands.items():
            if not any(row.get("_jamie_drink_level") is not None for row in variants):
                continue
            for level in range(1, 5):
                with self.subTest(command=command, level=level):
                    eligible = [
                        row
                        for row in variants
                        if int(row.get("_jamie_drink_level", 0) or 0) <= level
                    ]
                    if not eligible:
                        continue
                    expected = max(
                        eligible,
                        key=lambda row: int(row.get("_jamie_drink_level", 0) or 0),
                    )
                    payload = bot.find_moves_in_text(f"jamie {command} d{level}")
                    matching_rows = [
                        row for row in payload.get("rows", [])
                        if row.get("numCmd") == command
                    ]
                    self.assertEqual(1, len(matching_rows), command)
                    self.assertEqual(
                        expected.get("_jamie_drink_level"),
                        matching_rows[0].get("_jamie_drink_level"),
                    )
                    checked_queries += 1
        self.assertGreater(checked_queries, 100)

    def test_word_based_motion_notation_for_repeated_down(self):
        from bubbot.frame_data.sf6_parser_helpers import normalize_direction_word_motion_notation

        self.assertEqual("22mk", normalize_direction_word_motion_notation("down down mk"))
        self.assertEqual("22mk", normalize_direction_word_motion_notation("down, down mk"))
        self.assertEqual("22mk", normalize_direction_word_motion_notation("down + down mk"))
        self.assertEqual("236hp", normalize_direction_word_motion_notation("quarter circle forward hp"))
        self.assertEqual("236hp", normalize_direction_word_motion_notation("qcf hp"))

        cases = (
            ("zangief down down medium kick", "22MK"),
            ("zangief down down mk", "22MK"),
            ("zangief down, down mk", "22MK"),
            ("zangief down down hk", "22HK"),
            ("ryu qcf hp", "236HP"),
            ("ryu quarter circle forward hp", "236HP"),
            ("ryu qcf light punch", "236LP"),
        )
        for query, expected_cmd in cases:
            with self.subTest(query=query):
                payload = bot.find_moves_in_text(query)
                self.assertEqual("frame", payload.get("mode"), query)
                self.assertEqual([expected_cmd], [row.get("numCmd") for row in payload.get("rows", [])], query)

        # Direct lookup also handles word notation
        row = bot.lookup_frame_data("zangief", "down down mk")
        self.assertIsNotNone(row)
        self.assertEqual("22MK", row.get("numCmd"))

    def test_images_keyword_resolves_moves_across_games(self):
        cases = (
            (ggst_frame_data, "ggst ky 2s images", "2S"),
            (ggacr_frame_data, "ggacr ky 2s images", "2S"),
            (bbcf_frame_data, "bbcf jin 3c images", "3C"),
            (cotw_frame_data, "cotw terry 2c images", "2C"),
            (tuco_frame_data, "2xko ahri 2h images", "2H"),
            (sfv_frame_data, "sfv ryu 2mk images", "2MK"),
            (usfiv_frame_data, "usf4 ryu 2mk images", "D MK"),
            (third_strike_frame_data, "3s ryu 2mk images", "2MK"),
            (mk1_frame_data, "mk1 scorpion b2 images", "B+2"),
        )
        for module, query, expected_command in cases:
            with self.subTest(query=query):
                payload = module.find_moves_in_text(query)
                self.assertEqual([expected_command], [row.get("numCmd") for row in payload.get("rows", [])])

        sf6_payload = bot.find_moves_in_text("sf6 ryu 2mk images")
        self.assertTrue(sf6_payload.get("gif_query"))
        self.assertEqual(["2MK"], [row.get("numCmd") for row in sf6_payload.get("rows", [])])

    def test_exact_character_alias_outranks_another_games_fuzzy_match(self):
        query = "jin 3c images"
        modules = (
            ggacr_frame_data,
            ggst_frame_data,
            sfv_frame_data,
            tuco_frame_data,
            bbcf_frame_data,
            cotw_frame_data,
            third_strike_frame_data,
            usfiv_frame_data,
            mk1_frame_data,
        )
        payloads = [module.find_moves_in_text(query) for module in modules]
        ggst_payload = payloads[1]
        bbcf_payload = payloads[4]

        self.assertEqual("sin", ggst_payload.get("char_key"))
        self.assertEqual(["3C"], [row.get("numCmd") for row in bbcf_payload.get("rows", [])])
        self.assertEqual(
            (False, True),
            message_router._preferred_character_game_matches(
                query,
                (
                    (ggst_frame_data.GGST_CHARACTER_ALIASES, ggst_frame_data.GGST_FRAME_DATA.keys()),
                    (bbcf_frame_data.BBCF_CHARACTER_ALIASES, bbcf_frame_data.BBCF_FRAME_DATA.keys()),
                ),
            ),
        )

    @requires_local_sf6_gifs
    def test_alex_stance_lariat_resolves_stance_row(self):
        payload = bot.find_moves_in_text("alex stance lariat")
        self.assertEqual("frame", payload.get("mode"))
        self.assertEqual(["2PP > 5HP"], [row.get("numCmd") for row in payload.get("rows", [])])
        row = payload["rows"][0]
        links = gif_lookup.get_frame_row_gif_links(row)
        self.assertTrue(links[0].startswith("https://ultimateframedata.com/"))

        from bubbot.features import menu_system

        view = menu_system.build_frame_result_view("sf6", row, owner_id=1, char_key="alex")
        self.assertEqual(links[0], view.default_gif_url)
        self.assertIsNone(view.default_gif_asset_path)

    def test_cammy_hooligan_hold_rejects_unrelated_charged_kick_gif(self):
        payload = bot.find_moves_in_text("cammy 236hp")
        self.assertEqual(["HP Hooligan Combination (hold)"], [row.get("moveName") for row in payload.get("rows", [])])
        row = payload["rows"][0]
        self.assertIsNone(gif_lookup.lookup_hitbox_gif_link(row))
        self.assertEqual([], gif_lookup.get_frame_row_gif_links(row))

    def test_viper_double_burn_rejects_unrelated_double_kick_gif(self):
        payload = bot.find_moves_in_text("viper double burn")
        self.assertEqual(["Double Burn"], [row.get("moveName") for row in payload.get("rows", [])])
        row = payload["rows"][0]
        self.assertIsNone(gif_lookup.lookup_hitbox_gif_link(row))
        self.assertEqual([], gif_lookup.get_frame_row_gif_links(row))

    @requires_local_sf6_gifs
    def test_cammy_jump_motion_resolves_cannon_strike_and_its_gif(self):
        payload = bot.find_moves_in_text("cammy j.214k")
        self.assertEqual("frame", payload.get("mode"))
        self.assertEqual(
            [("Cannon Strike", "214K (air)")],
            [(row.get("moveName"), row.get("numCmd")) for row in payload.get("rows", [])],
        )

        gif_links = gif_lookup.get_frame_row_gif_links(payload["rows"][0])
        self.assertTrue(gif_links)
        self.assertIn("cammy-cannon-strike", gif_links[0])

        gif_payload = bot.find_moves_in_text("cammy j.214k gif")
        self.assertTrue(gif_payload.get("gif_query"))
        self.assertEqual(["Cannon Strike"], [row.get("moveName") for row in gif_payload.get("rows", [])])
        self.assertIn(
            "cammy-cannon-strike",
            gif_lookup.collect_hitbox_gif_links_from_text(
                "cammy j.214k gif",
                frame_rows=gif_payload.get("rows", []),
            )[0],
        )

        shared_command_payload = bot.find_moves_in_text("kimberly j.214kk")
        self.assertEqual(
            [("OD Aerial Bushin Senpukyaku", "214KK (air)")],
            [
                (row.get("moveName"), row.get("numCmd"))
                for row in shared_command_payload.get("rows", [])
            ],
        )

    def test_jump_motion_notation_resolves_air_rows_across_games(self):
        cases = (
            (bot, "cammy", "214k", "Cannon Strike", "214K (air)"),
            (sfv_frame_data, "akira", "236lp", "LP Kiko Kai (air)", "236LP"),
            (usfiv_frame_data, "adon", "214lk", "Air Jaguar Kick", "(j.) 214 LK"),
            (third_strike_frame_data, "akuma", "236p", "Zankuu Hadouken", "236P (air)"),
            (ggst_frame_data, "axl", "214h", "Snail (air)", "j.214H"),
            (ggacr_frame_data, "anji", "214p", "Shin: Nishiki", "j.214P"),
            (bbcf_frame_data, "amane", "236c", "Tensou Rakugeki: Gosei", "j.236C"),
            (cotw_frame_data, "andy", "214a", "Kuu Hishou Ken A A", "j.214A/C/AC"),
            (tuco_frame_data, "ahri", "41236s2", "Spirit Rush (Air)", "j.(4/1/2/3/6)S2"),
            (mk1_frame_data, "baraka", "db1", "(Air) Blade Sparks", "DB1"),
            (avtl_frame_data, "zaheer", "214a", "j214A", "j214A"),
        )
        for module, prefix, command, expected_name, expected_command in cases:
            for notation in (f"j.{command}", f"j{command}", f"jump {command}"):
                query = f"{prefix} {notation}"
                with self.subTest(query=query):
                    payload = module.find_moves_in_text(query)
                    self.assertTrue(payload.get("explicit_move_attempt"))
                    self.assertEqual(
                        [(expected_name, expected_command)],
                        [
                            (row.get("moveName"), row.get("numCmd"))
                            for row in payload.get("rows", [])
                        ],
                    )

        enhanced_air = mk1_frame_data.find_moves_in_text("mk1 baraka j.db1 enhanced")
        self.assertEqual(
            [("(Air) Enhanced Blade Sparks", "DB1+EX")],
            [(row.get("moveName"), row.get("numCmd")) for row in enhanced_air.get("rows", [])],
        )

    def test_all_game_matchers_prefer_ground_regardless_of_row_order(self):
        cases = (
            (bot, "FRAME_DATA", "ryu"),
            (sfv_frame_data, "SFV_FRAME_DATA", "akira"),
            (usfiv_frame_data, "USFIV_FRAME_DATA", "adon"),
            (third_strike_frame_data, "THIRD_STRIKE_FRAME_DATA", "akuma"),
            (ggst_frame_data, "GGST_FRAME_DATA", "axl"),
            (ggacr_frame_data, "GGACR_FRAME_DATA", "sol"),
            (bbcf_frame_data, "BBCF_FRAME_DATA", "jin"),
            (cotw_frame_data, "COTW_FRAME_DATA", "mai"),
            (tuco_frame_data, "TUCO_FRAME_DATA", "ahri"),
            (mk1_frame_data, "MK1_FRAME_DATA", "baraka"),
            (avtl_frame_data, "AVTL_FRAME_DATA", "korra"),
        )
        for module, store_name, character in cases:
            char_key = module.resolve_character_key(character)
            ground = {"char_key": char_key, "char_name": character, "moveName": "Probe Strike", "numCmd": "236A"}
            air = {**ground, "numCmd": "j.236A"}
            with self.subTest(game=store_name), patch.dict(getattr(module, store_name), {char_key: [air, ground]}):
                if module is bot:
                    self.assertEqual(ground, bot.lookup_frame_data(char_key, "probe strike"))
                else:
                    self.assertEqual([ground], module.find_matching_rows(char_key, "probe strike"))

    def test_ground_defaults_through_natural_language_queries(self):
        cases = (
            (bot, "kimberly 214kk"),
            (sfv_frame_data, "akira 236lp"),
            (usfiv_frame_data, "adon light jaguar kick"),
            (third_strike_frame_data, "akuma 236p"),
            (ggst_frame_data, "axl snail"),
            (ggacr_frame_data, "ggacr sol volcanic viper"),
            (bbcf_frame_data, "jin hishouken"),
            (cotw_frame_data, "mai 214a"),
            (tuco_frame_data, "ahri spirit rush"),
            (mk1_frame_data, "baraka db1"),
            (avtl_frame_data, "korra 214a"),
        )
        for module, query in cases:
            with self.subTest(query=query):
                rows = module.find_moves_in_text(query).get("rows", [])
                self.assertTrue(rows)
                self.assertFalse(any(row_is_air_move(row) for row in rows))

    def test_generic_p_motion_uses_existing_strength_prompt(self):
        payload = bot.find_moves_in_text("ed 623p")
        self.assertEqual("frame", payload.get("mode"))
        self.assertEqual([], payload.get("rows"))
        self.assertIn("Special Strength Options (Ed)", payload.get("data", ""))
        for command in ("623LP", "623MP", "623HP", "623PP"):
            self.assertIn(f"`{command}`", payload.get("data", ""))

        explicit_payload = bot.find_moves_in_text("ed 623hp")
        self.assertEqual(["623HP"], [row.get("numCmd") for row in explicit_payload.get("rows", [])])


class CrossGameImageResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_images_keyword_sends_only_media_response(self):
        module = type(
            "Module",
            (),
            {
                "send_frame_response": AsyncMock(return_value=[1]),
                "send_hitbox_response": AsyncMock(return_value=[2]),
            },
        )()

        with patch("bubbot.runtime.message_router._record_frame_data_ids"):
            await message_router._send_cross_game_lookup_response(
                object(),
                module,
                [{"numCmd": "3C"}],
                {"gif_query": False, "frame_query": False},
                "bbcf jin 3c images",
            )

        module.send_hitbox_response.assert_awaited_once()
        module.send_frame_response.assert_not_awaited()

    async def test_property_word_inside_move_name_sends_full_frame_response(self):
        module = type(
            "Module",
            (),
            {
                "send_frame_response": AsyncMock(return_value=[1]),
                "send_hitbox_response": AsyncMock(return_value=[2]),
            },
        )()
        rows = [{"char_name": "Ky", "moveName": "Stun Dipper", "numCmd": "236K", "stun": "10"}]

        with (
            patch("bubbot.runtime.message_router._record_frame_data_ids"),
            patch("bubbot.runtime.message_router._send_property_value_reply", AsyncMock()) as send_property,
        ):
            await message_router._send_cross_game_lookup_response(
                object(),
                module,
                rows,
                {"gif_query": False, "frame_query": False},
                "ky stun dipper",
            )

        module.send_frame_response.assert_awaited_once()
        send_property.assert_not_awaited()

    async def test_property_after_move_name_sends_property_response(self):
        module = type(
            "Module",
            (),
            {
                "send_frame_response": AsyncMock(return_value=[1]),
                "send_hitbox_response": AsyncMock(return_value=[2]),
            },
        )()
        rows = [{"char_name": "Ky", "moveName": "Stun Dipper", "numCmd": "236K", "stun": "10"}]

        with (
            patch("bubbot.runtime.message_router._record_frame_data_ids"),
            patch("bubbot.runtime.message_router._send_property_value_reply", AsyncMock()) as send_property,
        ):
            await message_router._send_cross_game_lookup_response(
                object(),
                module,
                rows,
                {"gif_query": False, "frame_query": False},
                "ky stun dipper stun",
            )

        send_property.assert_awaited_once()
        module.send_frame_response.assert_not_awaited()


class Sf6MessageRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_addressed_generic_motion_replies_with_strength_prompt(self):
        prompt = "Special Strength Options (Ed)\n1. `623LP`\n2. `623MP`\n3. `623HP`\n4. `623PP`"
        payload = {
            "mode": "frame",
            "rows": [],
            "data": prompt,
            "explicit_move_attempt": True,
        }
        sent_message = type("SentMessage", (), {"id": 123})()
        message = type(
            "Message",
            (),
            {
                "author": type("Author", (), {"id": 1})(),
                "content": "<@999> Ed 623P",
                "mentions": [],
                "raw_mentions": [],
                "reference": None,
                "channel": object(),
                "reply": AsyncMock(return_value=sent_message),
            },
        )()
        empty_payload = {"mode": "none", "rows": [], "data": ""}

        with ExitStack() as stack:
            stack.enter_context(patch.object(message_router, "_DATA_LOADED", True))
            stack.enter_context(patch.object(message_router, "is_plain_bot_mention_only", return_value=False))
            stack.enter_context(patch.object(message_router, "message_directly_mentions_bot", return_value=True))
            stack.enter_context(patch.object(message_router.quiz_module, "route_message", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router, "_handle_cross_game_disambiguation_reply", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router, "_handle_sf6_prompt_disambiguation_reply", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router.buenavista_extension, "maybe_handle_voice_command", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router.buenavista_extension, "maybe_handle_streetfighterdle_message", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router, "maybe_handle_glossary_lookup", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router.buenavista_extension, "maybe_ack_streetfighterdle_score", AsyncMock()))
            stack.enter_context(patch.object(message_router, "_is_reply_to_suppressed_bub_message", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router.reminder_manager, "handle_message", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router.buenavista_extension, "maybe_handle_private_message", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router, "_is_reply_to_frame_data", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router, "_try_route_combo_query", AsyncMock(return_value=False)))
            stack.enter_context(patch.object(message_router, "_preferred_character_game_matches", return_value=(True,) + (False,) * 10))
            stack.enter_context(patch.object(message_router, "find_moves_in_text", return_value=payload))
            for module in (
                message_router.ggacr_module,
                message_router.ggst_module,
                message_router.sfv_module,
                message_router.tuco_module,
                message_router.bbcf_module,
                message_router.cotw_module,
                message_router.third_strike_module,
                message_router.usfiv_module,
                message_router.mk1_module,
            ):
                stack.enter_context(patch.object(module, "find_moves_in_text", return_value=empty_payload))
            stack.enter_context(
                patch.object(
                    message_router.buenavista_extension,
                    "should_suppress_public_implied_frame_lookup",
                    return_value=False,
                )
            )
            remember_prompt = stack.enter_context(
                patch.object(message_router.sf6_prompt_replies, "remember_special_strength_prompt_mode")
            )
            send_frame_table = stack.enter_context(
                patch.object(message_router, "send_frame_table_response", AsyncMock())
            )
            await message_router._handle_message(message)

        message.reply.assert_awaited_once_with(prompt)
        remember_prompt.assert_called_once_with(123, "frame")
        send_frame_table.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
