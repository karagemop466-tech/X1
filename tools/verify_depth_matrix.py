#!/usr/bin/env python3
"""Verify data/depth/ group model, 32-club deficiency summary, and W11 matchup matrix."""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPTH_DIR = os.path.join(ROOT, "data", "depth")


def main() -> int:
    dg = json.load(open(os.path.join(DEPTH_DIR, "depth_groups_32.json"), encoding="utf-8"))
    ts = json.load(open(os.path.join(DEPTH_DIR, "team_deficiency_summary.json"), encoding="utf-8"))
    mx = json.load(open(os.path.join(DEPTH_DIR, "matchup_deficiency_matrix_w11.json"), encoding="utf-8"))

    # 1. 32 clubs in summary, HOU explicitly unavailable_image_only and depth fields blank
    assert len(ts["rows"]) == 32, f"expected 32 clubs, got {len(ts['rows'])}"
    hou = [r for r in ts["rows"] if r["team_abbrev"] == "HOU"]
    assert len(hou) == 1 and hou[0]["depth_status"] == "unavailable_image_only"
    assert hou[0]["depth1_slots"] == "" and hou[0]["w11_offense_replacements"] == ""
    verified_clubs = [r for r in ts["rows"] if r["depth_status"] == "verified_club_chart"]
    assert len(verified_clubs) == 31

    # 2. Packers jersey stripping recovers joins and keeps raw_player
    gb_rows = [r for r in dg["rows"] if r["team_abbrev"] == "GB" and r["slot_kind"] != "empty_depth_gap"]
    assert len(gb_rows) == 55
    for r in gb_rows:
        assert re.match(r"^\d+\s+", r["raw_player"]), f"expected raw jersey prefix on GB: {r['raw_player']}"
        assert not re.match(r"^\d+\s+", r["player_clean"]), f"jersey prefix not stripped: {r['player_clean']}"
        assert r["jersey_stripped"] == "true"
    c = dg["meta"]["counts"]
    assert c["gb_w10_injury_joins_stripped"] > c["gb_w10_injury_joins_raw"]

    # 3. Shared & empty slots explicitly modelled
    kinds = {r["slot_kind"] for r in dg["rows"]}
    assert "shared_position_group" in kinds
    assert "shared_concatenated_cell" in kinds
    assert "empty_depth_gap" in kinds
    assert "unavailable_image_only" in kinds

    # 4. Every row carries an official https source_url
    for label, rows in (("depth_groups_32", dg["rows"]), ("team_deficiency_summary", ts["rows"])):
        for r in rows:
            assert str(r.get("source_url", "")).startswith("https://"), f"{label} row missing source_url: {r}"
    for r in mx["rows"]:
        assert str(r.get("game_url", "")).startswith("https://www.nfl.com/games/")
        assert str(r.get("off_source_url", "")).startswith("https://")
        assert str(r.get("def_source_url", "")).startswith("https://")

    # 5. Week 11 matrix covers all 13 games x 2 directions x 3 lanes = 78 rows
    assert len(mx["rows"]) == 78, f"expected 78 matrix rows, got {len(mx['rows'])}"
    hou_mx = [r for r in mx["rows"] if "HOU" in (r["offense_team"], r["defense_team"])]
    assert len(hou_mx) == 6 and all(r["mismatch_flag"] == "HOU_DEPTH_UNAVAILABLE" for r in hou_mx)

    print(
        f"verify_depth_matrix PASS: 32 clubs ({len(verified_clubs)} verified + 1 HOU image-only), "
        f"GB joins {c['gb_w10_injury_joins_raw']}->{c['gb_w10_injury_joins_stripped']}, "
        f"{len(mx['rows'])} W11 matchup rows ({c['w11_matrix_mismatch_alerts']} alerts)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
