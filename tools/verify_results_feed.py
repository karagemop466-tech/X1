#!/usr/bin/env python3
"""Re-verify the committed results feed against its official evidence.

Session `arena-1d3600f8-x1` (T16). Offline checker for CI. Re-parses the
evidence snapshots in data/results/raw/, compares every cell against the
committed CSV, re-runs the standings double-entry checks, and asserts the
provenance contract (every row has an official source URL). Exits 1 on any
failure. Never writes.
"""

from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_results_feed as b  # noqa: E402

ROOT = b.ROOT


def main() -> int:
    failures: list[str] = []

    committed_path = os.path.join(b.OUT_DIR, "verified_results_2026.csv")
    committed = list(csv.DictReader(open(committed_path, encoding="utf-8")))
    rep = json.load(open(os.path.join(b.OUT_DIR, "verification_report.json"), encoding="utf-8"))

    # 1. re-parse the evidence and compare cell by cell
    rebuilt = []
    for week in range(1, 11):
        rows = b.parse_week(week)
        if len(rows) != b.EXPECTED[week]:
            failures.append(f"week {week}: {len(rows)} rows, expected {b.EXPECTED[week]}")
        rebuilt.extend(rows)
    rebuilt.sort(key=lambda r: (int(r["week"]), r["date_iso"], r["game_id"]))

    if len(rebuilt) != len(committed):
        failures.append(f"row count {len(rebuilt)} != committed {len(committed)}")
    keys = ["game_id", "date_iso", "away_team", "away_score", "home_team",
            "home_score", "game_url", "status"]
    for a, c in zip(rebuilt, committed):
        for k in keys:
            if a[k] != c[k]:
                failures.append(f"{a['game_id']}: {k} evidence={a[k]!r} committed={c[k]!r}")

    # 2. provenance contract
    for c in committed:
        if not c["source_url"].startswith("https://www.nfl.com/games/"):
            failures.append(f"{c['game_id']}: source_url is not an official game page")
        if c["verification"] != "verified-official":
            failures.append(f"{c['game_id']}: not marked verified-official")

    # 3. standings double-entry (recomputed from the committed CSV itself)
    from collections import defaultdict
    pf: dict[str, int] = defaultdict(int)
    pa: dict[str, int] = defaultdict(int)
    wlt: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in committed:
        a, h = b.norm(r["away_team"]), b.norm(r["home_team"])
        as_, hs = int(r["away_score"]), int(r["home_score"])
        pf[a] += as_; pa[a] += hs
        pf[h] += hs; pa[h] += as_
        if as_ > hs:
            wlt[a][0] += 1; wlt[h][1] += 1
        elif as_ < hs:
            wlt[h][0] += 1; wlt[a][1] += 1
        else:
            wlt[a][2] += 1; wlt[h][2] += 1

    standings = {}
    with open(os.path.join(ROOT, "data", "standings_2026.csv"), encoding="utf-8") as fh:
        for s in csv.DictReader(fh):
            standings[b.norm(s["team_abbr"])] = s
    if len(standings) != 32:
        failures.append(f"standings has {len(standings)} teams, expected 32")

    for code, s in standings.items():
        if pf[code] != int(s["PF"]) or pa[code] != int(s["PA"]):
            failures.append(f"{code}: PF/PA {pf[code]}/{pa[code]} != standings {s['PF']}/{s['PA']}")
        if wlt[code] != [int(s["W"]), int(s["L"]), int(s["T"])]:
            failures.append(f"{code}: W-L-T {wlt[code]} != standings {[s['W'], s['L'], s['T']]}")

    if sum(pf.values()) != sum(int(s["PF"]) for s in standings.values()):
        failures.append("league total points mismatch vs standings")

    # 4. the stored verification report must itself say all_green
    if not rep.get("checks", {}).get("all_green"):
        failures.append("verification_report.json does not report all_green")

    print(f"rows re-checked : {len(committed)}")
    print(f"teams cross-checked : {len(standings)} (PF/PA + W-L-T)")
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures[:40]:
            print("  FAIL", f)
        return 1
    print("results feed verification passed: evidence matches, provenance complete, standings agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
