#!/usr/bin/env python3
"""Depth-of-replacement aggregates (T19).

Session `arena-1d3600f8-x1`. Owner requirement:

> Track the depth of the replacement, not just the fact of a replacement.

The deficiency register (data/verify/deficiency_recomputed.json) already carries
`replacement_depth` per slot. This tool publishes the DEPTH dimension: how deep
each replacement sits on the official club depth chart (2nd string, 3rd string,
4th string), for starters on the official injury report, split by game status
and unit, with per-team summaries. Rows whose depth cannot be read from the
official depth chart are counted as `unknown` and flagged — never inferred.

Output: data/analysis/replacement_depth.json
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "verify", "deficiency_recomputed.json")
OUT = os.path.join(ROOT, "data", "analysis", "replacement_depth.json")


def main() -> int:
    d = json.load(open(SRC, encoding="utf-8"))
    rows = d["rows"]

    on_report = [r for r in rows if r["starter_on_report"]]
    by_status: dict[str, list] = defaultdict(list)
    for r in on_report:
        by_status[r["starter_game_status"] or "unknown"].append(r)

    def depth_dist(rs: list) -> dict:
        c = Counter()
        for r in rs:
            dp = r["replacement_depth"]
            c["unknown (not readable on official depth chart)" if dp is None else f"string {dp}"] += 1
        return dict(sorted(c.items()))

    def unit_split(rs: list) -> dict:
        out = {}
        for unit in ("Offense", "Defense", "Special Teams"):
            sub = [r for r in rs if r["unit"] == unit]
            out[unit] = {"slots": len(sub), "depth_distribution": depth_dist(sub)}
        return out

    deep = [
        {
            "team": r["team_abbrev"], "unit": r["unit"], "position": r["position"],
            "slot": r["slot"], "starter": r["starter_display"],
            "starter_game_status": r["starter_game_status"],
            "replacement": r["replacement_display"], "replacement_depth": r["replacement_depth"],
            "source_depth_chart": r["source_depth_chart"],
            "source_injury": r["source_injury"],
        }
        for r in on_report if (r["replacement_depth"] or 0) >= 3
    ]

    unknown = [
        {
            "team": r["team_abbrev"], "unit": r["unit"], "position": r["position"],
            "slot": r["slot"], "starter": r["starter_display"],
            "starter_game_status": r["starter_game_status"],
            "replacement": r["replacement_display"],
            "flag": "replacement_depth not readable on the official depth chart — left blank, not inferred",
            "source_depth_chart": r["source_depth_chart"],
            "source_injury": r["source_injury"],
        }
        for r in on_report if r["replacement_depth"] is None
    ]

    per_team = []
    teams = sorted({r["team_abbrev"] for r in rows})
    for t in teams:
        trs = [r for r in rows if r["team_abbrev"] == t]
        tor = [r for r in trs if r["starter_on_report"]]
        depths = [r["replacement_depth"] for r in tor if r["replacement_depth"] is not None]
        per_team.append({
            "team": t,
            "slots_tracked": len(trs),
            "starters_on_report": len(tor),
            "out": sum(1 for r in tor if r["starter_game_status"] == "Out"),
            "doubtful": sum(1 for r in tor if r["starter_game_status"] == "Doubtful"),
            "questionable": sum(1 for r in tor if r["starter_game_status"] == "Questionable"),
            "mean_replacement_depth": round(sum(depths) / len(depths), 3) if depths else None,
            "max_replacement_depth": max(depths) if depths else None,
            "deep_replacements_3rd_or_worse": sum(1 for d in depths if d >= 3),
            "depth_unknown": sum(1 for r in tor if r["replacement_depth"] is None),
            "source_injury": "https://www.nfl.com/injuries/",
            "source_depth_chart": next((r["source_depth_chart"] for r in trs if r["source_depth_chart"]), ""),
        })

    doc = {
        "dataset": "replacement_depth",
        "title": "Depth of replacement — how deep the backup sits, not just that there is one",
        "generated_at": "2026-11-14",
        "built_from": d["summary"].get("built_from", []),
        "definition": {
            "replacement_depth": "position of the replacement on the club's official depth chart at the slot in question: 2 = second string, 3 = third string, 4 = fourth string",
            "severity": "game status of the starter on the official injury report: 3 = Out, 2 = Doubtful, 1 = Questionable, 0 = not on report",
            "unknown": "depth could not be read from the official depth chart (continuation rows, jersey-number rows, missing chart) — counted and flagged, never inferred",
        },
        "totals": {
            "slots_tracked": len(rows),
            "teams_covered": len(teams),
            "teams_missing": d["summary"].get("teams_missing", []),
            "starters_on_report": len(on_report),
            "by_game_status": {k: len(v) for k, v in sorted(by_status.items())},
        },
        "depth_of_replacement_on_report": {
            "all": depth_dist(on_report),
            "by_game_status": {k: depth_dist(v) for k, v in sorted(by_status.items())},
            "by_unit": unit_split(on_report),
        },
        "deep_replacements_3rd_string_or_worse": deep,
        "unknown_depth_on_report": unknown,
        "per_team": per_team,
        "provenance": {
            "injury_status": "https://www.nfl.com/injuries/ (official)",
            "depth_charts": "official club depth chart sites (one per club, link on every row)",
            "note": "Club depth charts are club publications, not league facts (flag F-04); the injury status is league-official.",
        },
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)

    print(f"slots tracked        : {len(rows)} ({len(teams)} teams; missing {doc['totals']['teams_missing']})")
    print(f"starters on report   : {len(on_report)}")
    print(f"depth distribution   : {depth_dist(on_report)}")
    print(f"3rd string or deeper : {len(deep)}")
    print(f"depth unknown        : {len(unknown)} (flagged, not inferred)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
