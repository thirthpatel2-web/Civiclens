"""The proof-of-filing slip: a real PDF, owner-only, carrying the reference and the tracking link."""

from __future__ import annotations

import unittest

from app.core.exceptions import NotFound
from tests.support_env import CIT, CIT2, Env


class AcknowledgementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = Env()
        self.c = self.env.create()

    def test_the_owner_gets_a_pdf_with_the_reference_and_tracking_link(self) -> None:
        pdf = self.env.complaints.acknowledgement(CIT, self.c.id, public_base_url="https://civiclens.example/")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(self.c.reference.encode(), pdf)
        self.assertIn(f"https://civiclens.example/grievances/{self.c.id}".encode(), pdf)

    def test_nobody_else_can_download_it(self) -> None:
        with self.assertRaises(NotFound):
            self.env.complaints.acknowledgement(CIT2, self.c.id, public_base_url="https://civiclens.example")

    def test_a_non_latin_title_without_a_unicode_font_is_replaced_not_garbled(self) -> None:
        c = self.env.create(title="सड़क पर बड़ा गड्ढा", description="सड़क पर बड़ा गड्ढा है और दुर्घटना हो रही है")
        pdf = self.env.complaints.acknowledgement(CIT, c.id, public_base_url="https://civiclens.example")
        self.assertIn(b"title in the language you filed it", pdf)


if __name__ == "__main__":
    unittest.main()
