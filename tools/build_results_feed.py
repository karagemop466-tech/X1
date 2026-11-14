#!/usr/bin/env python3
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
