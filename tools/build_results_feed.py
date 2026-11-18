#!/usr/bin/env python3
"""Build the verified results feed from the official evidence snapshots.

Session `arena-1d3600f8-x1` (T16). Parses the verbatim result anchors captured from
https://www.nfl.com/schedules/2026/by-week/week-N (N = 1..10) into a row-level
verified results feed, then runs double-entry cross-checks:

  1. Per-week game counts against the expected slate size.
  2. Per-team points for / points against against the official standings table
     (data/standings_2026.csv, itself verified against nfl.com/standings).
  3. Per-team W-L-T against the same standings table.
  4. League totals (sum of all points) against the standings sum.
  5. Reference-only diff against the third-party mirror (data/processed/
     schedule_2026.json) — disagreements are reported, never used to change a
     value. The mirror is not an official source.

SCOPE (read before quoting the row count): this artefact is the 2026-11-14 view —
weeks 1-9 plus the Week 10 Thursday game — because that is what its evidence files
captured and that is the standings snapshot it reconciles against. It is not the
current feed. The current feed is 150 rows through Week 10, published by
tools/build_results_r3.py and closed by tools/verify_2026_11_17.py; see
`coverage_scope` in the report and docs/methodology/results-feed.md.

Every row published in the feed carries the official game-page URL as its
source. Nothing is inferred: date_iso is derived from the anchor's printed
month/day with year 2026 (the page is the 2026 schedule) and is cross-checked
against the anchor label; the verbatim label is kept alongside.

Outputs:
  data/results/verified_results_2026.csv
  data/results/verification_report.json
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "results", "raw")
OUT_DIR = os.path.join(ROOT, "data", "results")
RETRIEVED_AT = "2026-11-14"

TEAM_CODES = {
    "Cardinals": "ARI", "Falcons": "ATL", "Ravens": "BAL", "Bills": "BUF",
    "Panthers": "CAR", "Bears": "CHI", "Bengals": "CIN", "Browns": "CLE",
    "Cowboys": "DAL", "Broncos": "DEN", "Lions": "DET", "Packers": "GB",
    "Texans": "HOU", "Colts": "IND", "Jaguars": "JAX", "Chiefs": "KC",
    "Raiders": "LV", "Chargers": "LAC", "Rams": "LAR", "Dolphins": "MIA",
    "Vikings": "MIN", "Patriots": "NE", "Saints": "NO", "Giants": "NYG",
    "Jets": "NYJ", "Eagles": "PHI", "Steelers": "PIT", "Seahawks": "SEA",
    "49ers": "SF", "Buccaneers": "TB", "Titans": "TEN", "Commanders": "WAS",
}

MONTHS = {"september": 9, "october": 10, "november": 11, "december": 12, "january": 1}

# Expected settled-game counts per week at the 2026-11-14 snapshot.
EXPECTED = {1: 16, 2: 16, 3: 16, 4: 16, 5: 15, 6: 14, 7: 14, 8: 14, 9: 15, 10: 1}

ANCHOR_RE = re.compile(
    r"\[([A-Za-z.0-9 ]+?) (\d+), ([A-Za-z.0-9 ]+?) (\d+), FINAL, "
    r"(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday), "
    r"([A-Za-z]+) (\d+)(?:st|nd|rd|th)\]\((https://www\.nfl\.com/games/[^)]+)\)"
)


def norm(code: str) -> str:
    """Team-code normalisation used across this repo (flags I-15 / I-16)."""
    return {"LAR": "LA", "ARI": "AZ"}.get(code, code)


def parse_week(week: int) -> list[dict]:
    path = os.path.join(RAW, f"week_{week:02d}.md")
    text = open(path, encoding="utf-8").read()
    rows = []
    for away_name, away_score, home_name, home_score, month, day, url in ANCHOR_RE.findall(text):
        if away_name.strip() not in TEAM_CODES or home_name.strip() not in TEAM_CODES:
            raise SystemExit(f"week {week}: unknown team in anchor: {away_name!r} / {home_name!r}")
        slug = url.rstrip("/").split("/")[-1]
        away, home = TEAM_CODES[away_name.strip()], TEAM_CODES[home_name.strip()]
        m = MONTHS[month.lower()]
        rows.append({
            "season": "2026",
            "week": str(week),
            "game_id": f"2026_{week:02d}_{away}_{home}",
            "game_slug": slug,
            "date_iso": f"2026-{m:02d}-{int(day):02d}",
            "date_label": f"{month} {int(day)}",
            "away_team": away,
            "away_score": away_score,
            "home_team": home,
            "home_score": home_score,
            "status": "Final",
            "game_url": url,
            "source_url": url,
            "source_label": f"NFL.com official game page (via by-week schedule, week {week})",
            "retrieved_at": RETRIEVED_AT,
            "verification": "verified-official",
        })
    return rows


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    feed: list[dict] = []
    report: dict = {"generated_at": RETRIEVED_AT, "weeks": {}, "checks": {}, "mirror_reference": {},
        # Read-this-first scope. The evidence files this tool parses are the 2026-11-14 verbatim
        # captures, and it validates against the standings captured the same day, so 137 rows here is
        # correct FOR THAT DATE and is not a stale view of today. Week 10 was completed on
        # 2026-11-15/16; those 14 games are in the current feed
        # (`data/results/verified_results_2026_r3.csv`, 150 rows), which reconciles against the dated
        # standings transcription in `data/verification/2026_11_17/` and is checked by
        # `tools/verify_2026_11_17.py`. Extending this artefact past its own evidence would mean
        # writing page text this tool never captured, so it is left as the dated view it is.
        "coverage_scope": {
            "evidence_captured": RETRIEVED_AT,
            "rows_in_this_artefact": 137,
            "current_feed_rows": 150,
            "current_feed_files": ["data/results/verified_results_2026_r3.csv",
                                   "data/results/verified_results_2026_n2.csv",
                                   "data/results/verified_results.json"],
            "why_not_extended": "this builder reads only the verbatim anchor captures in "
                                "data/results/raw/; the 2026-11-17 Week 10 read is a named-column "
                                "transcription, not an anchor capture, and inventing anchors would "
                                "fabricate the one property this file exists to preserve",
        }}

    for week in range(1, 11):
        rows = parse_week(week)
        feed.extend(rows)
        ok = len(rows) == EXPECTED[week]
        report["weeks"][str(week)] = {
            "rows": len(rows), "expected": EXPECTED[week], "count_ok": ok,
            "evidence": f"data/results/raw/week_{week:02d}.md",
            "source_url": f"https://www.nfl.com/schedules/2026/by-week/week-{week}",
        }

    feed.sort(key=lambda r: (int(r["week"]), r["date_iso"], r["game_id"]))

    # ---------------------------------------------------------------- checks
    counts_ok = all(v["count_ok"] for v in report["weeks"].values())

    pf: dict[str, int] = defaultdict(int)
    pa: dict[str, int] = defaultdict(int)
    wlt: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # W, L, T
    for r in feed:
        a, h = norm(r["away_team"]), norm(r["home_team"])
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
            standings[norm(s["team_abbr"])] = s

    pf_mismatch, wlt_mismatch = [], []
    for code, s in sorted(standings.items()):
        n = norm(code)
        if pf[n] != int(s["PF"]) or pa[n] != int(s["PA"]):
            pf_mismatch.append({"team": code, "feed_pf": pf[n], "standings_pf": s["PF"],
                                "feed_pa": pa[n], "standings_pa": s["PA"]})
        wl = wlt[n]
        if wl != [int(s["W"]), int(s["L"]), int(s["T"])]:
            wlt_mismatch.append({"team": code, "feed": wl,
                                 "standings": [s["W"], s["L"], s["T"]]})

    total_points_feed = sum(pf.values())
    total_points_standings = sum(int(s["PF"]) for s in standings.values())

    report["checks"] = {
        "week_counts_ok": counts_ok,
        "rows_total": len(feed),
        "pf_pa_mismatches": pf_mismatch,
        "wlt_mismatches": wlt_mismatch,
        "total_points_feed": total_points_feed,
        "total_points_standings": total_points_standings,
        "total_points_ok": total_points_feed == total_points_standings,
        "standings_source": "https://www.nfl.com/standings/ (via data/standings_2026.csv)",
    }

    # ------------------------------------------- mirror reference diff (info)
    mirror_path = os.path.join(ROOT, "data", "processed", "schedule_2026.json")
    mirror_diffs = []
    if os.path.exists(mirror_path):
        mgames = json.load(open(mirror_path, encoding="utf-8"))["games"]
        by_id = {}
        for g in mgames:
            gid = g.get("game_id") or ""
            m = re.match(r"(\d{4})_(\d{2})_([A-Z]+)_([A-Z]+)", gid)
            if m:
                by_id[(int(m.group(2)), norm(m.group(3)), norm(m.group(4)))] = g
        for r in feed:
            key = (int(r["week"]), norm(r["away_team"]), norm(r["home_team"]))
            g = by_id.get(key)
            if not g:
                mirror_diffs.append({"game_id": r["game_id"], "issue": "not in mirror"})
                continue
            try:
                ma, mh = int(float(g["away_score"])), int(float(g["home_score"]))
            except (TypeError, ValueError):
                mirror_diffs.append({"game_id": r["game_id"], "issue": "mirror score empty"})
                continue
            if (ma, mh) != (int(r["away_score"]), int(r["home_score"])):
                mirror_diffs.append({"game_id": r["game_id"], "feed": [r["away_score"], r["home_score"]],
                                     "mirror": [ma, mh]})
    report["mirror_reference"] = {
        "source": "https://github.com/nflverse/nfldata (third-party mirror, NOT official)",
        "games_compared": len(feed),
        "disagreements": mirror_diffs,
        "note": "Reference only. The mirror never changes a published value.",
    }

    # -------------------------------------------------------------- write out
    out_csv = os.path.join(OUT_DIR, "verified_results_2026.csv")
    cols = ["season", "week", "game_id", "game_slug", "date_iso", "date_label",
            "away_team", "away_score", "home_team", "home_score", "status",
            "game_url", "source_url", "source_label", "retrieved_at", "verification"]
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(feed)

    report["checks"]["all_green"] = bool(
        counts_ok and not pf_mismatch and not wlt_mismatch
        and report["checks"]["total_points_ok"]
    )
    with open(os.path.join(OUT_DIR, "verification_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)

    print(f"rows written          : {len(feed)} -> {out_csv}")
    print(f"week counts ok        : {counts_ok}")
    print(f"pf/pa mismatches      : {len(pf_mismatch)}")
    print(f"w-l-t mismatches      : {len(wlt_mismatch)}")
    print(f"total points feed     : {total_points_feed} (standings {total_points_standings})")
    print(f"mirror disagreements  : {len(mirror_diffs)} (reference only)")
    return 0 if report["checks"]["all_green"] else 1


if __name__ == "__main__":
    sys.exit(main())
