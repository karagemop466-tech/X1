#!/usr/bin/env python3
"""Unit and mutation tests for `tools/origination_desk` math and verification gates."""
from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.origination_desk.build_roster_audit import _norm_name, _parse_inactive_entry
from tools.origination_desk.build_skill_desk import (
    _american_to_implied,
    _norm_cdf,
    _norm_ppf,
    _pearson_with_ci,
    _solve_power_vig,
)
from tools.origination_desk.verify_desk import _TableSourceParser, _is_official_https, verify_all


class OriginationDeskTests(unittest.TestCase):
    def test_vig_free_power_method_sums_to_one_and_penalizes_longshot_more(self) -> None:
        # Heavy favorite -400 vs underdog +310
        q_fav = _american_to_implied(-400)  # 0.8000
        q_dog = _american_to_implied(310)   # 0.2439
        k, p_fav, p_dog = _solve_power_vig(q_fav, q_dog)
        self.assertGreater(k, 1.0)
        self.assertAlmostEqual(p_fav + p_dog, 1.0, places=7)
        # Power vig removal reduces the longshot proportionally more than multiplicative
        p_dog_mult = q_dog / (q_fav + q_dog)
        self.assertLess(p_dog, p_dog_mult)

    def test_normal_cdf_and_ppf_roundtrip(self) -> None:
        for p in (0.001653, 0.025, 0.05, 0.50, 0.95, 0.975):
            z = _norm_ppf(p)
            self.assertAlmostEqual(_norm_cdf(z), p, places=6)

    def test_pearson_with_ci_bounds(self) -> None:
        xs = [float(i) for i in range(30)]
        ys = [2.0 * i + 1.0 for i in range(30)]
        r, lo, hi, _, pval = _pearson_with_ci(xs, ys)
        self.assertAlmostEqual(r, 1.0, places=5)
        self.assertLess(lo, hi)
        self.assertLess(pval, 1e-6)

    def test_name_normalization_strips_packers_jersey_and_suffixes(self) -> None:
        self.assertEqual(_norm_name("9 Christian Watson"), "christianwatson")
        self.assertEqual(_norm_name("Charvarius Ward Sr."), "charvariusward")
        self.assertEqual(_norm_name("Ar'maj Reed- Adams"), _norm_name("Ar'maj Reed-Adams"))

    def test_parse_inactive_entry_preserves_emergency_qb_note(self) -> None:
        pos, player, note = _parse_inactive_entry("QB Kedon Slovis (emergency third QB)")
        self.assertEqual(pos, "QB")
        self.assertEqual(player, "Kedon Slovis")
        self.assertEqual(note, "emergency third QB")

    def test_source_cell_mutation_rejected_by_parser(self) -> None:
        bad_html = '<table data-table><tr><th>Club</th><th>Source</th></tr><tr><td>BUF</td><td>no link here</td></tr></table>'
        p = _TableSourceParser()
        p.feed(bad_html)
        self.assertEqual(p.data_rows, 1)
        self.assertEqual(p.unsourced_rows, [1])

        spoof_html = '<table data-table><tr><td>BUF</td><td><a href="https://evil-nfl.com.example.org/x">spoof</a></td></tr></table>'
        p2 = _TableSourceParser()
        p2.feed(spoof_html)
        self.assertEqual(p2.unsourced_rows, [1])
        self.assertFalse(_is_official_https("http://www.nfl.com/standings"))
        self.assertTrue(_is_official_https("https://api.weather.gov/gridpoints/LOT/76,72/forecast"))

    def test_full_desk_verification_passes(self) -> None:
        checks, errors = verify_all()
        self.assertEqual(errors, [])
        self.assertGreater(checks, 700)


if __name__ == "__main__":
    unittest.main()
