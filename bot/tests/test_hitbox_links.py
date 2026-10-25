"""Without the sf6frames/ folder, SF6 hitbox gifs come from the generated Ultimate Frame Data links.

``cd bot && PYTHONPATH=. python -m unittest discover -s tests -t tests -p test_hitbox_links.py``.
"""

import unittest
from unittest.mock import patch

from bubbot.data.sf6_ufd_gif_urls import SF6_UFD_GIF_URLS
from bubbot.frame_data import gif_lookup
from bubbot.runtime.config import LOCAL_HITBOX_GIF_EXTENSIONS
from bubbot.utils.text_utils import compact_key


class HitboxLinkTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.multiple(gif_lookup, normalize_char_name=compact_key, LOCAL_HITBOX_GIF_EXTENSIONS=LOCAL_HITBOX_GIF_EXTENSIONS,
                                 LOCAL_HITBOX_GIF_ROOT="/nonexistent/sf6frames/files")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.lookup = {compact_key(char): char for char, _file in SF6_UFD_GIF_URLS}

    def test_every_generated_link_becomes_a_hitbox_row(self):
        data = gif_lookup.load_local_hitbox_gif_data(self.lookup)
        self.assertEqual(len(SF6_UFD_GIF_URLS), sum(len(rows) for rows in data.values()))
        self.assertEqual(31, len(data))
        row = next(r for r in data["aki"] if r["sourceFile"] == "2HK_Crouching_Heavy_Kick.gif")
        self.assertEqual({"moveName": "Crouching Heavy Kick", "numCmd": "2HK", "localPath": "",
                          "moveLink": "https://ultimateframedata.com/sf6/hitboxes/aki/aki-cr-hk-june2025.gif"},
                         {k: row[k] for k in ("moveName", "numCmd", "localPath", "moveLink")})

    def test_unknown_characters_and_files_are_skipped(self):
        urls = {("aki", "2HK_Crouching_Heavy_Kick.gif"): "https://x/a.gif", ("nobody", "5LP_Stand_LP.gif"): "https://x/b.gif",
                ("aki", "notes.txt"): "https://x/c", ("aki", "5LP_Stand_LP.gif"): ""}
        data = gif_lookup.hitbox_gif_data_from_urls({"aki": "aki"}, urls)
        self.assertEqual(["2HK_Crouching_Heavy_Kick.gif"], [row["sourceFile"] for row in data["aki"]])


if __name__ == "__main__":
    unittest.main()
