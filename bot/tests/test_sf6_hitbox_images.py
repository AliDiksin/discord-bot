"""SF6 frame cards show SuperCombo's hitbox images: FAT inputs matched to SuperCombo's SF6_FrameData rows."""

import unittest

from scripts.build_move_image_caches import pick_sf6_supercombo_row, sf6_fat_input_keys, sf6_hitbox_files, sf6_input_key


def _row(move_input, name, hitboxes="SF6_X_hitbox.png"):
    return {"input": move_input, "name": name, "hitboxes": hitboxes}


class FatToSuperComboInputTests(unittest.TestCase):
    def assertMatches(self, fat, supercombo):
        self.assertIn(sf6_input_key(supercombo), sf6_fat_input_keys(fat), f"{fat!r} should match {supercombo!r}")

    def assertNoMatch(self, fat, supercombo):
        self.assertNotIn(sf6_input_key(supercombo), sf6_fat_input_keys(fat), f"{fat!r} must not match {supercombo!r}")

    def test_notation_differences(self):
        self.assertMatches("5HP", "5HP")
        self.assertMatches("8LP", "j.LP")
        self.assertMatches("5HP (hold)", "5[HP]")
        self.assertMatches("8HP (hold)", "j.[HP]")
        self.assertMatches("LPLK (air)", "j.LPLK")
        self.assertMatches("5MP > 5MK", "5MP~MK")
        self.assertMatches("8MP > 8HP", "j.MP~j.HP")
        self.assertMatches("8 > 8HK", "j.8HK")
        self.assertMatches("9 > 2HP", "j.2HP")
        self.assertMatches("46MP", "[4]6MP")
        self.assertMatches("28HK", "[2]8HK")
        self.assertMatches("7 or 9HK", "7HK or 9HK")
        self.assertMatches("MPMK / 66 (cancel)", "MPMK or 66")
        self.assertMatches("236236K (CA)", "236236K")

    def test_different_moves_stay_apart(self):
        self.assertNoMatch("214K > K", "214KK")  # Marisa's Procella is not OD Scutum
        self.assertNoMatch("236KK", "236K~K")
        self.assertNoMatch("5HK", "5[HK]")
        self.assertNoMatch("8 > 8HK", "j.HK")  # Rashid's Aerial Shot is not a jumping HK
        self.assertNoMatch("8HP", "j.8HP")

    def test_hitbox_files_skip_template_placeholders(self):
        self.assertEqual(["a_hitbox.png", "b_hitbox.png"], sf6_hitbox_files("a_hitbox.png, b_hitbox.png"))
        self.assertEqual([], sf6_hitbox_files("{{{hitboxes}}}"))


class PickSuperComboRowTests(unittest.TestCase):
    def test_same_name_wins(self):
        rows = [_row("236236P", "Shinryu Reppa", "a.png"), _row("236236P", "Shinryu Reppa (CA)", "b.png")]
        self.assertEqual("b.png", pick_sf6_supercombo_row(rows, "Shinryu Reppa (Critical Art)")["hitboxes"])
        self.assertEqual("a.png", pick_sf6_supercombo_row(rows, "Shinryu Reppa")["hitboxes"])

    def test_versions_of_one_move_use_the_base_version(self):
        rows = [_row("5LP", "Standing Light Punch (DL0)", "dl0.png"), _row("5LP", "Standing Light Punch (DL1)", "dl1.png")]
        self.assertEqual("dl0.png", pick_sf6_supercombo_row(rows, "Stand LP")["hitboxes"])

    def test_unrelated_moves_sharing_an_input_give_no_image(self):
        rows = [_row("214214P", "Denjin Hashogeki Lv.1", "a.png"), _row("214214P", "Shin Hashogeki Lv.1", "b.png")]
        self.assertEqual("b.png", pick_sf6_supercombo_row(rows, "Shin Hashogeki")["hitboxes"])
        self.assertIsNone(pick_sf6_supercombo_row(rows, "Something Else"))


if __name__ == "__main__":
    unittest.main()
