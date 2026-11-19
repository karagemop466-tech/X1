#!/usr/bin/env python3
"""Verify data/models/ splits, opponent-aware ratings, dual totals, and personnel ablations."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_DIR = os.path.join(ROOT, "data", "models")


def main() -> int:
    sp = json.load(open(os.path.join(MOD_DIR, "season_splits.json"), encoding="utf-8"))
    rt = json.load(open(os.path.join(MOD_DIR, "opponent_aware_ratings.json"), encoding="utf-8"))
    dt = json.load(open(os.path.join(MOD_DIR, "dual_totals_walkforward.json"), encoding="utf-8"))
    ab = json.load(open(os.path.join(MOD_DIR, "personnel_ablations.json"), encoding="utf-8"))

    assert sp["meta"]["overlap_games_across_splits"] == 0, "split leakage detected"
    assert len(sp["rows"]) == 4
    # Chronological monotonicity
    for i in range(len(sp["rows"]) - 1):
        assert sp["rows"][i]["max_gameday"] < sp["rows"][i + 1]["min_gameday"]

    assert len(rt["rows"]) == 32, f"expected 32 club ratings, got {len(rt['rows'])}"
    for r in rt["rows"]:
        assert abs((r["unadjusted_rating"] + r["sos_adjustment"]) - r["opponent_aware_srs"]) <= 0.005
        assert str(r["source_url"]).startswith("https://")

    assert len(dt["summary"]) == 3
    assert len(dt["rows"]) == 118, f"expected 118 2026 W3-W10 rows, got {len(dt['rows'])}"
    for r in dt["rows"]:
        assert round(r["total_model_b"] - r["total_model_a"], 2) == r["gap_b_minus_a"]
        assert str(r["source_url"]).startswith("https://")

    assert len(ab["rows"]) == 3
    blocked = [r for r in ab["rows"] if r["status"] == "BLOCKED_PENDING_MULTI_WEEK_INACTIVES"]
    assert len(blocked) == 1 and blocked[0]["delta_mae_with_minus_without"] == ""

    print(
        f"verify_modeling_lab PASS: 4 disjoint splits (0 overlap), 32 SRS ratings, "
        f"{len(dt['rows'])} dual-total games, {len(ab['rows'])} ablation rows"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
