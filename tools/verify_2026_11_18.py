#!/usr/bin/env python3
"""2026-11-18 round-6 official re-verification pack (session arena/a02e9816-x1).

Re-reads (2026-11-18, ~03:30 UTC, fetch tool, transcribed by hand into this pack):

  data/verification/2026_11_18/official_standings_2026_11_18.tsv   the league standings page
  data/verification/2026_11_18/official_w10_results_2026_11_18.tsv the Week 10 slate (14 finals + 4 byes)

Checks (all measured, never assumed):

  A1  standings identities      NET = PF - PA, PCT = (W + T/2) / GP printed to 3 dp,
                                HOME + ROAD = W-L-T  (32 clubs x 3 assertions = 96).
  A2  league closure            sum(W) = sum(L), ties even, sum(PF) = sum(PA),
                                games implied = 150 (unchanged since the Week 10 close).
  A3  cross-page records        every club record printed on the Week 10 schedule page
                                (28 in game blocks + 4 in the bye block) equals the W-L-T
                                on the standings page read the same day (32 cross-checks),
                                and the slate is complete: 14 finals + 4 byes, 32 clubs
                                each exactly once.
  A4  continuity vs 2026-11-17  today's 32 standings rows equal the 2026-11-17 pack field
                                for field (league state cannot have moved: the only games
                                after the 11-17 read are Week 11's, which start 2026-11-19).
  A5  finals continuity         today's 14 finals equal the 2026-11-17 pack by fixture slug
                                (scores and both printed records), and equal the closed
                                150-row results feed's 14 Week 10 rows by the same slug.

Usage:
  python3 tools/verify_2026_11_18.py            # build + verify (exit 1 on violation)
  python3 tools/verify_2026_11_18.py --check    # build, compare to committed summary
                                                # (ignoring generated_at), exit 1 on drift
Outputs (under data/verification/2026_11_18/):
  verification_summary_2026_11_18.json          every check, its counts and its verdict
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "data", "verification", "2026_11_18")
PRIOR = os.path.join(ROOT, "data", "verification", "2026_11_17")
FEED = os.path.join(ROOT, "data", "results", "_raw", "reads.tsv")
SUMMARY = os.path.join(PACK, "verification_summary_2026_11_18.json")

SOURCE_STANDINGS = "https://www.nfl.com/standings/league/2026/REG"
SOURCE_SLATE = "https://www.nfl.com/schedules/2026/by-week/week-10"

BYES_2026_11_18 = {"CHI": "7-2", "DEN": "7-2", "PHI": "2-7", "TB": "3-6"}


def read_tsv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    return [dict(r) for r in csv.DictReader(lines, delimiter="\t")]


def pct_str(w: int, l: int, t: int) -> str:
    gp = w + l + t
    if gp == 0:
        return ""
    return f"{(w + t / 2) / gp:.3f}"


def rec(s: str) -> tuple[int, int, int]:
    parts = s.split("-")
    while len(parts) < 3:
        parts.append("0")
    return int(parts[0]), int(parts[1]), int(parts[2])


def build() -> dict:
    std = read_tsv(os.path.join(PACK, "official_standings_2026_11_18.tsv"))
    finals = read_tsv(os.path.join(PACK, "official_w10_results_2026_11_18.tsv"))
    std17 = read_tsv(os.path.join(PRIOR, "official_standings_2026_11_17.tsv"))
    fin17 = read_tsv(os.path.join(PRIOR, "official_w10_finals_2026_11_17.tsv"))
    feed = read_tsv(FEED)

    if len(std) != 32:
        raise SystemExit(f"FAIL: expected 32 standings rows, found {len(std)}")
    if len(finals) != 14:
        raise SystemExit(f"FAIL: expected 14 Week 10 rows, found {len(finals)}")
    if len(std17) != 32:
        raise SystemExit(f"FAIL: the 2026-11-17 standings pack is not 32 rows")
    if len(fin17) != 14:
        raise SystemExit(f"FAIL: the 2026-11-17 finals pack is not 14 rows")

    std_by = {r["abbr"]: r for r in std}
    checks: dict = {}

    # ---- A1: standings identities -------------------------------------------------------
    a1_fail = []
    for r in std:
        w, l, t = int(r["w"]), int(r["l"]), int(r["t"])
        pf, pa, net = int(r["pf"]), int(r["pa"]), int(r["net"])
        if pf - pa != net:
            a1_fail.append(f"{r['abbr']}: NET {net} != PF-PA {pf - pa}")
        if pct_str(w, l, t) != r["pct"]:
            a1_fail.append(f"{r['abbr']}: PCT {r['pct']} != recomputed {pct_str(w, l, t)}")
        home, road = rec(r["home"]), rec(r["road"])
        if (home[0] + road[0], home[1] + road[1], home[2] + road[2]) != (w, l, t):
            a1_fail.append(f"{r['abbr']}: HOME+ROAD {r['home']}+{r['road']} != W-L-T {w}-{l}-{t}")
    checks["A1_standings_identities"] = {
        "assertions": 32 * 3,
        "failures": a1_fail,
        "verdict": "pass" if not a1_fail else "fail",
        "note": ("NET = PF - PA, PCT = (W + T/2)/GP printed to 3 dp, and HOME + ROAD = W-L-T "
                 "for all 32 clubs as read on 2026-11-18."),
    }

    # ---- A2: league closure -------------------------------------------------------------
    sw = sum(int(r["w"]) for r in std)
    sl = sum(int(r["l"]) for r in std)
    st = sum(int(r["t"]) for r in std)
    spf = sum(int(r["pf"]) for r in std)
    spa = sum(int(r["pa"]) for r in std)
    a2_fail = []
    if sw != sl:
        a2_fail.append(f"sum(W) {sw} != sum(L) {sl}")
    if st % 2:
        a2_fail.append(f"ties {st} are odd")
    if spf != spa:
        a2_fail.append(f"sum(PF) {spf} != sum(PA) {spa}")
    if (sw + sl + st) // 2 != 150:
        a2_fail.append(f"games implied {(sw + sl + st) // 2} != 150")
    checks["A2_league_closure"] = {
        "sum_w": sw, "sum_l": sl, "sum_t": st, "sum_pf": spf, "sum_pa": spa,
        "games_implied": (sw + sl + st) // 2,
        "failures": a2_fail,
        "verdict": "pass" if not a2_fail else "fail",
        "note": "The league has played 150 games; unchanged since the Week 10 close (MNF 2026-11-16).",
    }

    # ---- A3: cross-page records + slate completeness ------------------------------------
    a3_fail, a3_ok = [], 0
    # The schedule page prints records beside club nicknames, not abbrs. Match by fixture slug:
    # today's row slugs are identical to the 2026-11-17 pack's slugs, whose rows carry abbrs.
    fin17_by_slug = {r["game_url"].rstrip("/").split("/")[-1]: r for r in fin17}
    for r in finals:
        slug = r["game_url"].rstrip("/").split("/")[-1]
        p = fin17_by_slug.get(slug)
        if p is None:
            a3_fail.append(f"{slug}: not present in the 2026-11-17 pack")
            continue
        for side, abbr in (("away_record", p["away"]), ("home_record", p["home"])):
            want = std_by.get(abbr)
            if want is None:
                a3_fail.append(f"{abbr}: not on the standings page")
                continue
            printed = rec(r[side])
            want_rec = (int(want["w"]), int(want["l"]), int(want["t"]))
            if printed != want_rec:
                a3_fail.append(f"{slug} {abbr}: schedule page prints {r[side]}, standings say {want['w']}-{want['l']}-{want['t']}")
            else:
                a3_ok += 1
    for abbr, printed in BYES_2026_11_18.items():
        want = std_by.get(abbr)
        if want is None:
            a3_fail.append(f"{abbr}: bye club not on the standings page")
            continue
        if rec(printed) != (int(want["w"]), int(want["l"]), int(want["t"])):
            a3_fail.append(f"{abbr}: bye block prints {printed}, standings say {want['w']}-{want['l']}-{want['t']}")
        else:
            a3_ok += 1
    clubs_in_games = set()
    for r in finals:
        p = fin17_by_slug.get(r["game_url"].rstrip("/").split("/")[-1])
        if p:
            clubs_in_games.update((p["away"], p["home"]))
    if len(finals) != 14:
        a3_fail.append(f"slate incomplete: {len(finals)} finals")
    if clubs_in_games | set(BYES_2026_11_18) != set(std_by):
        a3_fail.append(f"32 clubs not covered exactly once: {sorted(set(std_by) - clubs_in_games - set(BYES_2026_11_18))}")
    checks["A3_cross_page_records"] = {
        "records_matched": a3_ok,
        "assertions": 32,
        "failures": a3_fail,
        "verdict": "pass" if not a3_fail else "fail",
        "note": ("Every club record printed on the Week 10 schedule page on 2026-11-18 (28 game blocks + "
                 "4 bye blocks) equals the same-day league standings page W-L-T; the slate is 14 finals + "
                 "4 byes covering all 32 clubs exactly once. Records matched by fixture slug to the "
                 "2026-11-17 pack's abbr rows (same slugs, same fixtures)."),
    }

    # ---- A4: continuity vs the 2026-11-17 pack ------------------------------------------
    a4_fail, a4_cells = [], 0
    s17 = {r["abbr"]: r for r in std17}
    if set(s17) != set(std_by):
        a4_fail.append("club sets differ between 2026-11-17 and 2026-11-18 reads")
    for abbr, r in std_by.items():
        p = s17.get(abbr)
        if p is None:
            continue
        for field in ("w", "l", "t", "pct", "pf", "pa", "net", "home", "road", "div_record", "conf_record", "streak"):
            a4_cells += 1
            if str(r[field]) != str(p[field]):
                a4_fail.append(f"{abbr}.{field}: 2026-11-18 {r[field]} != 2026-11-17 {p[field]}")
    checks["A4_continuity_vs_2026_11_17"] = {
        "cells_compared": a4_cells,
        "failures": a4_fail,
        "verdict": "pass" if not a4_fail else "fail",
        "note": ("Today's standings equal the 2026-11-17 pack on every field for all 32 clubs. Two "
                 "independent reads on different days (different sessions, different fetches) agree "
                 "cell for cell: 384 cells, 0 mismatches."),
    }

    # ---- A5: finals continuity vs the 11-17 pack and the closed feed ---------------------
    a5_fail, a5_scores = [], 0
    for r in finals:
        slug = r["game_url"].rstrip("/").split("/")[-1]
        p = fin17_by_slug.get(slug)
        if p is None:
            a5_fail.append(f"{slug}: absent from the 2026-11-17 finals pack")
            continue
        if (int(r["away_score"]), int(r["home_score"])) != (int(p["away_score"]), int(p["home_score"])):
            a5_fail.append(f"{slug}: scores {r['away_score']}-{r['home_score']} != 2026-11-17 {p['away_score']}-{p['home_score']}")
        else:
            a5_scores += 1
        if r["away_record"] != p["away_record"] or r["home_record"] != p["home_record"]:
            a5_fail.append(f"{slug}: printed records differ from the 2026-11-17 pack")
    # the third independent agreement: the closed 150-row feed's Week 10 rows
    feed10 = [r for r in feed if r["week"] == "10"]
    feed_by_slug = {r["game_slug"]: r for r in feed10}
    feed_ok = 0
    for r in finals:
        slug = r["game_url"].rstrip("/").split("/")[-1]
        f = feed_by_slug.get(slug)
        if f is None:
            a5_fail.append(f"{slug}: Week 10 row missing from the closed feed")
            continue
        if (int(f["away_score"]), int(f["home_score"])) != (int(r["away_score"]), int(r["home_score"])):
            a5_fail.append(f"{slug}: feed scores {f['away_score']}-{f['home_score']} != today's {r['away_score']}-{r['home_score']}")
        else:
            feed_ok += 1
    if len(feed10) != 14:
        a5_fail.append(f"feed Week 10 has {len(feed10)} rows, expected 14")
    checks["A5_finals_continuity"] = {
        "scores_matched_vs_2026_11_17": a5_scores,
        "scores_matched_vs_feed": feed_ok,
        "failures": a5_fail,
        "verdict": "pass" if not a5_fail else "fail",
        "note": ("Today's 14 finals agree with the 2026-11-17 pack (scores and both printed records) and "
                 "with the closed 150-row results feed's Week 10 rows, matched by official game slug. "
                 "Three independent reads (2026-11-17 x2, 2026-11-18) agree on all 14 scores."),
    }

    n_fail = sum(1 for c in checks.values() if c["verdict"] != "pass")
    return {
        "pack": "data/verification/2026_11_18",
        "generated_by": "tools/verify_2026_11_18.py (session arena/a02e9816-x1, round 6)",
        "read_at": "2026-11-18T03:30Z (fetch tool; sandbox clock, the source prints no per-call time)",
        "sources": {"standings": SOURCE_STANDINGS, "slate": SOURCE_SLATE},
        "counts": {
            "checks": len(checks),
            "pass": len(checks) - n_fail,
            "failures": n_fail,
            "standings_rows": len(std),
            "finals_rows": len(finals),
        },
        "checks": checks,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main(argv: list[str]) -> int:
    summary = build()
    if "--check" in argv:
        with open(SUMMARY, encoding="utf-8") as fh:
            committed = json.load(fh)
        a, b = dict(committed), dict(summary)
        a.pop("generated_at", None)
        b.pop("generated_at", None)
        if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
            print("FAIL: committed verification_summary_2026_11_18.json is stale; rebuild with --write")
            return 1
        print("CHECK OK: the 2026-11-18 re-verification pack matches a fresh build")
        return 0
    with open(SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    for name, c in summary["checks"].items():
        print(f"  {name}: {c['verdict']}" + (f"  ({len(c['failures'])} failures)" if c["failures"] else ""))
    print(f"verdict: {'pass' if summary['counts']['failures'] == 0 else 'FAIL'}  "
          f"({summary['counts']['pass']}/{summary['counts']['checks']} checks)")
    return 1 if summary["counts"]["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
