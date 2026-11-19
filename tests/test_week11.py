"""Regression tests for tools/week11/build_week11.py (session arena-2d1ba329-x1).

They pin the parser to the stored Week 11 capture at 2026-11-19T13:16:57Z (the ledger line
whose raw bytes are committed), so a change in the parser or the stored bytes fails loudly.
"""

import gzip
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "week11"))

import build_week11 as bw  # noqa: E402

PINNED = "raw/20261119T131657Z_f678e9a08fe4.html.gz"


class Week11Parse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        entries = bw.read_ledger()
        cls.entry = next(e for e in entries if e["file"] == PINNED)
        cls.page, cls.checks = bw.load_raw(cls.entry)
        cls.parsed = bw.parse_page(cls.page)
        cls.shape = bw.shape_checks(cls.parsed)

    def test_stored_bytes_match_ledger(self):
        self.assertTrue(all(self.checks.values()), self.checks)
        self.assertEqual(hashlib.sha256(self.page).hexdigest(), self.entry["sha256"])

    def test_structure_counts(self):
        self.assertEqual(self.shape["matchup_strips"], 26)
        self.assertEqual(self.shape["games"], 13)
        self.assertEqual(self.shape["clubs_with_table"], 24)
        self.assertEqual(self.shape["player_rows"], 253)

    def test_missing_tables_are_gaps_not_healthy(self):
        self.assertEqual(sorted(self.shape["clubs_without_table"]), ["CIN", "WAS"])

    def test_unknown_values_none(self):
        self.assertTrue(self.shape["unknown_values_pass"], self.shape)

    def test_known_row_values(self):
        ind = {c["abbr"]: c for c in self.parsed["clubs"]}["IND"]
        heck = next(r for r in ind["rows"] if r["player"] == "Charlie Heck")
        self.assertEqual(heck["injury"], "Not injury related - personal matter")
        self.assertEqual(heck["game_status"], "Questionable")
        tucker = next(r for r in ind["rows"] if r["player"] == "Dalton Tucker")
        self.assertEqual((tucker["injury"], tucker["game_status"]), ("", ""))

    def test_full_build_is_deterministic(self):
        a = bw.outputs(bw.build())
        b = bw.outputs(bw.build())
        self.assertEqual(a, b)
        self.assertIn("latest_read.tsv", a)
        self.assertTrue(json.loads(a["parse_checks.json"])["all_hash_checks_pass"])


if __name__ == "__main__":
    unittest.main()
