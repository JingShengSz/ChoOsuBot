"""Long titles stay inside the beatmap column without touching the artist."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import heading


class HeadingTest(unittest.TestCase):
    def test_wraps_the_reported_title_with_separate_artist_row(self):
        title = "We Could Get More Machinegun Psystyle! (And More Genre Switches)"
        overlay = heading.render_wrapped_heading(title, "かめりあ")
        self.assertIsNotNone(overlay)
        alpha = overlay.getchannel("A")
        self.assertIsNotNone(alpha.crop((104, 74, 661, 110)).getbbox())
        self.assertIsNotNone(alpha.crop((104, 110, 661, 147)).getbbox())
        self.assertIsNone(alpha.crop((661, 60, 960, 178)).getbbox())
        self.assertIsNone(alpha.crop((60, 149, 661, 153)).getbbox())

    def test_short_title_keeps_template_text_layers(self):
        self.assertIsNone(heading.render_wrapped_heading("FREEDOM DiVE", "xi"))


if __name__ == "__main__":
    unittest.main()
