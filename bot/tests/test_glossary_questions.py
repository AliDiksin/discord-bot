"""Plain questions about fighting game terms reach the glossary, and nothing else does.

``cd bot && PYTHONPATH=. python -m unittest discover -s tests -t tests -p test_glossary_questions.py``.
"""

import unittest

from bubbot.features.fg_glossary import find_glossary_term, glossary_question_term
from bubbot.runtime import decisions


class GlossaryQuestionTests(unittest.TestCase):
    def test_questions_about_terms_find_the_term(self):
        cases = {
            "what is a safe jump": "Safe Jump",
            "what does oki mean": "Okizeme",
            "whats a dp": "Dragon Punch",
            "what is okizeme?": "Okizeme",
            "meaning of frame trap": "Frame Trap",
            "what are footsies": "Footsies",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(expected, find_glossary_term(glossary_question_term(text))["term"])

    def test_other_questions_are_left_alone(self):
        for text in ("what is ken 5mp", "what is my rank", "whats the best ryu", "what is jp 2mp on block",
                     "whats up", "what is ryu", "what is sf stats", "what is marisa good at"):
            with self.subTest(text=text):
                self.assertIsNone(glossary_question_term(text))

    def test_glossary_wording_routes_to_frame_data_without_a_request(self):
        for text in ("<@1556366213784010792> define safejump", "glossary oki", "what does oki mean"):
            with self.subTest(text=text):
                self.assertEqual("framedata", decisions.local_route(text))


if __name__ == "__main__":
    unittest.main()
