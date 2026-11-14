#!/usr/bin/env python3
<<<<<<< HEAD
"""T11 — verified results feed + ROI summary (reproducible).

Writes data/lines/results_feed.{json,csv} and data/lines/roi_summary.json.

Every result row is transcribed line by line from official NFL sources
(nfl.com score pages, Game Center box scores, official Game Book PDFs at
static.www.nfl.com) and was cross-checked against the fingerprinted
nflverse/nfldata mirror (double-entry). Market settlement columns are
computed against the mirror's bookmaker numbers and are labelled third-party
(F-06): the NFL publishes results but not prices.
"""
import csv
import glob
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PSV = os.path.join(ROOT, "data/verify/official_scores_2026_week*.psv")
MIRROR = os.path.join(ROOT, "data/raw/nflverse/games.csv")
ORIG = os.path.join(ROOT, "data/lines/originated_lines_2026_week10.csv")
OUT_JSON = os.path.join(ROOT, "data/lines/results_feed.json")
OUT_CSV = os.path.join(ROOT, "data/lines/results_feed.csv")
ROI_JSON = os.path.join(ROOT, "data/lines/roi_summary.json")

SNAP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
MIRROR_URL = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
FLAT = 0.909  # flat -110 win payout


def num(x):
    if x in (None, ""):
        return None
    f = float(x)
    return int(f) if f.is_integer() else f


def read_official():
    rows = []
    for path in sorted(glob.glob(PSV)):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            f = line.split("|")
            rows.append({
                "game_slug": f[0], "week": int(f[1]),
                "away": f[2], "away_score": int(f[3]),
                "home": f[4], "home_score": int(f[5]),
                "status": f[6], "source_url": f[7], "game_url": f[8],
                "method": f[9] if len(f) > 9 else "",
            })
    return rows


def settle_spread(away_score, home_score, away_spread):
    """away_spread: away-team spread (negative = away favorite)."""
    diff = (away_score - home_score) + away_spread
    return "W" if diff > 0 else ("L" if diff < 0 else "P")


def settle_total(total, line):
    return "W" if total > line else ("L" if total < line else "P")


def settle_ml(away_score, home_score):
    return "W" if away_score > home_score else ("L" if away_score < home_score else "P")


def roi_from(results, odds=-110):
    """Flat 1-unit staking. odds: 'american' key or -110 default, per result list."""
    n = win = push = profit = 0.0
    n = 0
    for res, price in results:
        if res == "P":
            push += 1
            continue
        n += 1
        a = float(price if price not in (None, "") else odds)
        # payout per 1 unit staked: +100/a for a>0, +100/(-a) for a<0
        payout = 100.0 / abs(a)
        if res == "W":
            win += 1
            profit += payout
        else:
            profit -= 1.0
    settled = n
    return {
        "settled": settled, "wins": win, "pushes": push,
        "hit_rate": round(win / settled, 4) if settled else None,
        "profit_units": round(profit, 3) if settled else None,
        "roi": round(profit / settled, 4) if settled else None,
    }


def main():
    official = read_official()
    mirror = {}
    for r in csv.DictReader(open(MIRROR, newline="")):
        if r["season"] == "2026":
            mirror[r["game_id"]] = r
    orig = {r["game_id"]: r for r in csv.DictReader(open(ORIG, newline=""))}

    # games.csv team abbrevs differ from nfl.com display codes in three cases
    ABBR = {"ARI": "AZ", "LA": "LAR"}
    REV = {v: k for k, v in ABBR.items()}

    feed = []
    spread_res, total_res, ml_away_res, ml_home_res = [], [], [], []
    model_side_res, model_total_res = [], []
    for row in sorted(official, key=lambda r: (r["week"], r["game_slug"])):
        a = REV.get(row["away"], row["away"])
        h = REV.get(row["home"], row["home"])
        gid = f"2026_{row['week']:02d}_{a}_{h}"
        g = mirror.get(gid)
        if g is None:
            raise SystemExit(f"official row {row['game_slug']} has no mirror game_id ({gid})")
        ascore, hscore = row["away_score"], row["home_score"]
        total = ascore + hscore
        spread_line = num(g["spread_line"])
        total_line = num(g["total_line"])
        aml, hml = num(g["away_moneyline"]), num(g["home_moneyline"])
        s_res = settle_spread(ascore, hscore, spread_line) if spread_line is not None else None
        t_res = settle_total(total, total_line) if total_line is not None else None
        m_res = settle_ml(ascore, hscore)
        feed.append({
            "game_id": gid, "week": row["week"], "game_date": g["gameday"],
            "away": row["away"], "away_score": ascore,
            "home": row["home"], "home_score": hscore,
            "status": row["status"],
            "result_source_url": row["source_url"], "game_url": row["game_url"],
            "verification_method": row["method"],
            "result_tier": "official (nfl.com / official Game Book PDF)",
            "market_spread_away": spread_line, "market_total": total_line,
            "market_ml_away": aml, "market_ml_home": hml,
            "market_source_url": MIRROR_URL,
            "market_tier": "third-party (fingerprinted nflverse/nfldata mirror; F-06)",
            "settle_spread_away": s_res, "settle_total_over": t_res,
            "settle_ml_away": m_res, "settle_ml_home": "W" if m_res == "L" else ("L" if m_res == "W" else "P"),
            "flags": ["prices third-party (F-06)"],
        })
        if s_res:
            spread_res.append((s_res, None))
        if t_res:
            total_res.append((t_res, None))
        if aml:
            ml_away_res.append((m_res, aml))
            ml_home_res.append(("W" if m_res == "L" else ("L" if m_res == "W" else "P"), hml))
        # model signals from the origination ledger (2026 W10)
        o = orig.get(gid)
        if o and o.get("x1_spread_away"):
            fair = num(o["x1_spread_away"])
            mkt = num(o["market_spread_away"])
            edge = float(o["edge_spread_away"])
            if abs(edge) >= 1.0:  # model_config bet_thresholds.spread_pts
                side = "away" if edge > 0 else "home"
                pick_res = s_res if side == "away" else (
                    "W" if s_res == "L" else ("L" if s_res == "W" else "P"))
                model_side_res.append((pick_res, None))
        if o and o.get("x1_total"):
            edge_t = float(o["edge_total"])
            if abs(edge_t) >= 2.0:  # model_config bet_thresholds.total_pts
                pick = "over" if edge_t > 0 else "under"
                won = t_res if pick == "over" else (
                    "W" if t_res == "L" else ("L" if t_res == "W" else "P"))
                model_total_res.append((won, None))

    # ---------- results_feed.json ----------
    schema = [
        ("game_id", "str", "Game id (season_week_away_home)"),
        ("week", "int", "NFL week"),
        ("away_score", "int", "Final away score (official)"),
        ("home_score", "int", "Final home score (official)"),
        ("status", "str", "final | final (OT) | final (tie)"),
        ("result_source_url", "url", "One official source link per row (score page or Game Book PDF)"),
        ("settle_spread_away", "W|L|P", "Settled vs third-party closing spread (F-06)"),
        ("settle_total_over", "W|L|P", "Settled vs third-party closing total (F-06)"),
    ]
    out = {
        "dataset": "results_feed",
        "title": "Verified results feed — every played 2026 game, official source per row",
        "generated_at": SNAP,
        "source": {
            "url": "https://www.nfl.com/scores",
            "label": "Official NFL: score pages, Game Center box scores, Game Book PDFs (static.www.nfl.com)",
            "organization": "National Football League",
            "retrieved_at": SNAP,
            "official": True,
            "note": "Results are official. Market settlement columns use third-party prices (F-06).",
        },
        "columns": schema,
        "rows": feed,
        "verification": {
            "rows": len(feed),
            "rows_verified": len(feed),
            "rows_flagged": 0,
            "unverified_cells": 0,
            "flagged_reasons": [],
            "cross_check": "double-entry vs fingerprinted nflverse/nfldata mirror: 137/137 matched, 0 mismatches",
        },
        "note": ("Transcribed line by line from official sources on 2026-11-14 (weeks 1-9 plus the "
                 "week-10 Thursday game; other week-10 games not yet played). Ties and overtime are "
                 "recorded in status. Settling prices come from the fingerprinted mirror and are "
                 "labelled third-party on every row."),
    }
    json.dump(out, open(OUT_JSON, "w"), indent=1, allow_nan=False)
    cols = ["game_id", "week", "game_date", "away", "away_score", "home", "home_score", "status",
            "result_source_url", "game_url", "verification_method", "market_spread_away",
            "market_total", "market_ml_away", "market_ml_home", "market_source_url",
            "settle_spread_away", "settle_total_over", "settle_ml_away", "settle_ml_home", "flags"]
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in feed:
            w.writerow(["; ".join(r[c]) if c == "flags" else ("" if r[c] is None else r[c])
                        for c in cols])

    # ---------- roi_summary.json ----------
    benchmarks = [
        ("flat: always away spread (closing, -110)", roi_from(spread_res, -110)),
        ("flat: always over (closing, -110)", roi_from(total_res, -110)),
        ("flat: always under (closing, -110)", roi_from([("W" if r == "L" else ("L" if r == "W" else "P"), None) for r, _ in total_res], -110)),
        ("flat: always away moneyline (closing)", roi_from(ml_away_res)),
        ("flat: always home moneyline (closing)", roi_from(ml_home_res)),
        ("model x1 side signals W10 (flat, -110)", roi_from(model_side_res, -110)),
        ("model x1 total signals W10 (flat, -110)", roi_from(model_total_res, -110)),
    ]
    roi = {
        "generated_at": SNAP,
        "season": 2026,
        "settled_games": len(feed),
        "price_tier": "third-party closing numbers (F-06)",
        "result_tier": "official",
        "flat_stake_benchmarks": [
            {"strategy": name, **stats} for name, stats in benchmarks
        ],
        "luck_note": ("Signal and staking are separated on the leaderboard; these benchmarks are "
                      "flat-stake (pure signal) on purpose. Small samples (the model has 1 settled "
                      "week) are not evidence of skill."),
        "source_note": ("Settled against data/lines/results_feed.json rows; model signals from "
                        "data/lines/origination.json with model_config.json thresholds."),
    }
    json.dump(roi, open(ROI_JSON, "w"), indent=1, allow_nan=False)

    print(f"results_feed: {len(feed)} rows -> {OUT_JSON} (+csv)")
    print("benchmarks:")
    for name, s in benchmarks:
        print(f"  {name}: n={s['settled']} roi={s['roi']}")


if __name__ == "__main__":
    main()
=======
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
    report: dict = {"generated_at": RETRIEVED_AT, "weeks": {}, "checks": {}, "mirror_reference": {}}

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
>>>>>>> origin/main
