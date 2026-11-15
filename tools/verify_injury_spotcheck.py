#!/usr/bin/env python3
"""Diff the published Week 10 injury CSV against an independent read of nfl.com/injuries/.

Inputs
  data/readiness/official_spotcheck_w10.tsv   every row of the official page, transcribed
                                               from the page as read on READ_DATE (see the
                                               provenance block below; 28 clubs)
  data/injuries/injuries_2026_week10.csv       the published table (345 rows, 2026-11-14 capture)

Outputs
  data/readiness/spotcheck_result.json         per-team counts, every mismatch, the verdict
  data/readiness/spotcheck_diffs.csv           one line per mismatch (for a reviewer)

Exit code 1 only when the TSV itself is malformed. Mismatches are data, not build failures:
the official page is a moving target, so a difference is reported with its reason category.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSV = os.path.join(ROOT, "data", "readiness", "official_spotcheck_w10.tsv")
PUBLISHED = os.path.join(ROOT, "data", "injuries", "injuries_2026_week10.csv")
OUT_JSON = os.path.join(ROOT, "data", "readiness", "spotcheck_result.json")
OUT_CSV = os.path.join(ROOT, "data", "readiness", "spotcheck_diffs.csv")

PROVENANCE = {
    "official_url": "https://www.nfl.com/injuries/",
    "read_via": "fetch_page tool, 8 chunks (chunkIndex 0-7); chunks 0-6 cover all 28 clubs",
    "read_on": "2026-11-15 (UTC, session arena-8c67ec75-x1)",
    "published_capture": "snapshot 2026-11-14 (data/injuries/injuries_2026_week10.csv)",
}

PRACTICE_OK = {"", "Full Participation in Practice", "Limited Participation in Practice",
               "Did Not Participate In Practice"}
GAME_OK = {"", "Out", "Doubtful", "Questionable"}


def norm(value: str) -> str:
    return (value or "").strip()


def load_official():
    with open(TSV, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    bad = []
    for number, r in enumerate(rows, 2):
        if not r.get("team") or not r.get("player"):
            bad.append(f"line {number}: missing team or player")
        if norm(r.get("practice_status")) not in PRACTICE_OK:
            bad.append(f"line {number}: unknown practice status {r.get('practice_status')!r}")
        if norm(r.get("game_status")) not in GAME_OK:
            bad.append(f"line {number}: unknown game status {r.get('game_status')!r}")
    return rows, bad


def load_published():
    with open(PUBLISHED, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    official, bad = load_official()
    if bad:
        print("official TSV malformed:"); [print(" -", b) for b in bad]
        return 1
    published = load_published()

    off_by_team = defaultdict(dict)
    for r in official:
        key = norm(r["player"])
        if key in off_by_team[r["team"]]:
            bad.append(f"duplicate official row {r['team']} {key}")
        off_by_team[r["team"]][key] = r
    pub_by_team = defaultdict(dict)
    pub_dupes = []
    for r in published:
        key = norm(r["player"])
        team = norm(r["team"])
        if key in pub_by_team[team]:
            pub_dupes.append(f"{team} {key}")
        pub_by_team[team][key] = r

    diffs = []
    teams = sorted(set(off_by_team) | set(pub_by_team))
    per_team = {}
    for team in teams:
        off = off_by_team.get(team, {})
        pub = pub_by_team.get(team, {})
        matched = 0
        for player in sorted(set(off) | set(pub)):
            if player not in pub:
                diffs.append({"team": team, "player": player, "field": "row",
                              "official": "present", "published": "absent",
                              "category": "missing from published table"})
                continue
            if player not in off:
                diffs.append({"team": team, "player": player, "field": "row",
                              "official": "absent", "published": "present",
                              "category": "not on the official page as read"})
                continue
            matched += 1
            o, p = off[player], pub[player]
            pairs = [
                ("injuries", norm(o["injuries"]), norm(p.get("injuries"))),
                ("practice_status", norm(o["practice_status"]), norm(p.get("practice_status"))),
                ("game_status", norm(o["game_status"]), norm(p.get("game_status"))),
            ]
            for field, ov, pv in pairs:
                if ov != pv:
                    if field == "game_status" and ov and not pv:
                        category = "designation blank in published table"
                    elif field == "game_status" and pv and not ov:
                        category = "designation removed since 2026-11-14 capture (timing)"
                    elif field == "game_status":
                        category = "designation changed since 2026-11-14 capture (timing)"
                    else:
                        category = f"{field} differs (timing or transcription; see row)"
                    diffs.append({"team": team, "player": player, "field": field,
                                  "official": ov, "published": pv, "category": category})
        per_team[team] = {
            "official_rows": len(off),
            "published_rows": len(pub),
            "matched_rows": matched,
            "row_mismatches": sum(1 for d in diffs if d["team"] == team),
        }

    totals = Counter(d["category"] for d in diffs)
    result = {
        "provenance": PROVENANCE,
        "official_rows": len(official),
        "published_rows": len(published),
        "teams_compared": len(teams),
        "teams_with_zero_mismatch": sorted(t for t, v in per_team.items() if v["row_mismatches"] == 0),
        "teams_with_mismatch": sorted(t for t, v in per_team.items() if v["row_mismatches"]),
        "mismatch_count": len(diffs),
        "mismatch_categories": dict(totals),
        "published_duplicate_keys": pub_dupes,
        "per_team": per_team,
        "mismatches": diffs,
        "verdict": ("every row matches" if not diffs else
                    f"{len(diffs)} differences; see mismatches. Category tells whether the "
                    "published value is stale (timing) or wrong (defect)."),
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["team", "player", "field", "official", "published", "category"])
        writer.writeheader()
        for d in diffs:
            writer.writerow(d)
    print(f"official rows {len(official)} | published rows {len(published)} | teams {len(teams)}")
    print(f"row-level mismatches: {len(diffs)} | categories: {dict(totals)}")
    print(f"teams with zero mismatch: {len(result['teams_with_zero_mismatch'])} of {len(teams)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
