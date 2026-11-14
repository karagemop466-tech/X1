#!/usr/bin/env python3
"""Build the verified results feed — data/results_feed.json.

Session arena/907c5baf-x1 (task N1). The feed settles every market we originate
from official final scores only.

Inputs (all read-only):
  data/verify/raw/nfl_scores_2026_official.psv  — game-by-game transcription of
      the official NFL.com weekly schedule pages (retrieved 2026-11-14).
  data/nfl/standings.tsv                        — official standings (verified
      by earlier sessions) used for an arithmetic cross-check of the whole feed.
  data/raw/nflverse/games.csv                   — community-mirror results used
      only for a labelled cross-check; never as a source of truth.
  data/lines/originated_lines_2026_week10.csv   — our originated markets (model
      lines + our moneyline prices) to settle.

Output:
  data/results_feed.json

Verification rules enforced here:
  * A score enters the feed only if the official page printed it (the PSV).
  * Per-team W-L-T, PF and PA recomputed from the feed must equal the official
    standings for every club; any mismatch fails the build.
  * A mirror value is reported as a cross-check only, under an explicit
    "community mirror — not an official source" label.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = "2026-11-14"
GEN = "2026-11-14"

PSV = os.path.join(ROOT, "data", "verify", "raw", "nfl_scores_2026_official.psv")
STANDINGS = os.path.join(ROOT, "data", "nfl", "standings.tsv")
GAMES_MIRROR = os.path.join(ROOT, "data", "raw", "nflverse", "games.csv")
ORIGINATED = os.path.join(ROOT, "data", "lines", "originated_lines_2026_week10.csv")
OUT = os.path.join(ROOT, "data", "results_feed.json")

WEEK_URL = "https://www.nfl.com/schedules/2026/by-week/week-%d"
STANDINGS_URL = "https://www.nfl.com/standings/"


def canon(code: str) -> str:
    """Normalise club codes across sources (official page prints LA and AZ;
    several repo files use LAR and ARI). Applied for joins only — the published
    tables keep the code each source prints (flags I-15/I-16)."""
    return {"ARI": "AZ", "LA": "LAR"}.get(code, code)


def read_psv() -> list[dict]:
    rows = []
    with open(PSV, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            assert len(parts) == 10, f"bad PSV row: {line[:80]}"
            week, game_id, away, ascore, home, hscore, gameday, status, gurl, wurl = parts
            rows.append({
                "week": int(week),
                "game_id": game_id,
                "away": away,
                "home": home,
                "away_score": int(ascore) if ascore else None,
                "home_score": int(hscore) if hscore else None,
                "gameday": gameday,
                "status": status,
                "game_url": gurl,
                "week_url": wurl,
            })
    return rows


def read_standings() -> dict:
    out = {}
    with open(STANDINGS, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 18 or p[0] == "abbr":
                continue
            try:
                out[canon(p[0])] = {"W": int(p[5]), "L": int(p[6]), "T": int(p[7]),
                                    "PF": int(p[9]), "PA": int(p[10])}
            except ValueError:
                continue
    return out


def read_mirror() -> dict:
    out = {}
    with open(GAMES_MIRROR, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("season") == "2026" and r.get("away_score") and r.get("home_score"):
                gid = r["game_id"]
                # normalise 2026_WW_AWAY_HOME (mirror pads the week, prints LA/ARI)
                p = gid.split("_")
                gid = "2026_%d_%s_%s" % (int(p[1]), canon(p[2]), canon(p[3]))
                out[gid] = (int(r["away_score"]), int(r["home_score"]))
    return out


def read_originated() -> list[dict]:
    with open(ORIGINATED, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    games = read_psv()
    standings = read_standings()
    mirror = read_mirror()
    originated = read_originated()

    finals = [g for g in games if g["status"] == "FINAL"]
    scheduled = [g for g in games if g["status"] != "FINAL"]
    assert len(finals) == 137, f"expected 137 finals, got {len(finals)}"
    assert len(scheduled) == 13, f"expected 13 scheduled, got {len(scheduled)}"

    # ------------------------------------------------ integrity: standings
    rec = defaultdict(lambda: {"W": 0, "L": 0, "T": 0, "PF": 0, "PA": 0})
    for g in finals:
        a, h = rec[canon(g["away"])], rec[canon(g["home"])]
        a["PF"] += g["away_score"]; a["PA"] += g["home_score"]
        h["PF"] += g["home_score"]; h["PA"] += g["away_score"]
        if g["away_score"] > g["home_score"]:
            a["W"] += 1; h["L"] += 1
        elif g["away_score"] < g["home_score"]:
            a["L"] += 1; h["W"] += 1
        else:
            a["T"] += 1; h["T"] += 1

    check_rows, n_ok, n_bad = [], 0, 0
    for team in sorted(standings):
        s, r = standings[team], rec[team]
        ok = (s["W"], s["L"], s["T"], s["PF"], s["PA"]) == \
             (r["W"], r["L"], r["T"], r["PF"], r["PA"])
        check_rows.append({
            "team": team,
            "feed_wlt": f"{r['W']}-{r['L']}-{r['T']}",
            "official_wlt": f"{s['W']}-{s['L']}-{s['T']}",
            "feed_pf_pa": f"{r['PF']}-{r['PA']}",
            "official_pf_pa": f"{s['PF']}-{s['PA']}",
            "result": "match" if ok else "MISMATCH",
            "_source_url": STANDINGS_URL,
            "_source_label": "NFL.com standings (2026 REG)",
            "_source_org": "NFL",
            "_retrieved_at": SNAPSHOT,
            "_flags": [] if ok else ["feed recomputation disagrees with the official standings"],
        })
        n_ok += ok
        n_bad += (not ok)

    # ------------------------------------------------ integrity: mirror
    m_ok = m_bad = 0
    m_rows = []
    for g in finals:
        p = g["game_id"].split("_")
        gid = "2026_%d_%s_%s" % (int(p[1]), canon(p[2]), canon(p[3]))
        if gid in mirror:
            ma, mh = mirror[gid]
            agree = (ma, mh) == (g["away_score"], g["home_score"])
            m_ok += agree
            m_bad += (not agree)
            if not agree:
                m_rows.append({
                    "game_id": g["game_id"],
                    "official": f"{g['away_score']}-{g['home_score']}",
                    "mirror": f"{ma}-{mh}",
                    "_source_url": "https://github.com/nflverse/nfldata/blob/master/data/games.csv",
                    "_source_label": "nflverse/nfldata games.csv (community mirror — not an official source)",
                    "_source_org": "nflverse (community)",
                    "_retrieved_at": SNAPSHOT,
                    "_flags": ["community mirror disagrees with the official page"],
                })

    # ------------------------------------------------ settlement
    settle_rows = []
    for o in originated:
        gid = o["game_id"]
        g = next((x for x in finals if x["game_id"] == gid), None)
        if g is None:
            continue
        margin = g["away_score"] - g["home_score"]
        total = g["away_score"] + g["home_score"]

        def row(mtype, side, line, price, outcome, note):
            settle_rows.append({
                "game_id": gid,
                "market_type": mtype,
                "side": side,
                "our_line": line,
                "our_price": price,
                "result": f"{g['away_score']}-{g['home_score']}",
                "outcome": outcome,
                "note": note,
                "_source_url": g["game_url"],
                "_source_label": "NFL.com game page (official final score)",
                "_source_org": "NFL",
                "_retrieved_at": SNAPSHOT,
                "_flags": [],
                "_verified": True,
            })

        sl = float(o["x1_spread_away"])
        cov = margin + sl
        row("spread", "away", sl, "", "WIN" if cov > 0 else ("PUSH" if cov == 0 else "LOSS"),
            f"away margin {margin:+g} vs our away spread {sl:g}")
        row("spread", "home", -sl, "", "WIN" if cov < 0 else ("PUSH" if cov == 0 else "LOSS"),
            f"home margin {-margin:+g} vs our home spread {-sl:g}")
        tl = float(o["x1_total"])
        row("total", "over", tl, "", "WIN" if total > tl else ("PUSH" if total == tl else "LOSS"),
            f"game total {total} vs our total {tl:g}")
        row("total", "under", tl, "", "WIN" if total < tl else ("PUSH" if total == tl else "LOSS"),
            f"game total {total} vs our total {tl:g}")
        ml_a, ml_h = o["x1_ml_away"], o["x1_ml_home"]
        row("moneyline", "away", "", ml_a, "WIN" if margin > 0 else ("PUSH" if margin == 0 else "LOSS"),
            "our away moneyline price")
        row("moneyline", "home", "", ml_h, "WIN" if margin < 0 else ("PUSH" if margin == 0 else "LOSS"),
            "our home moneyline price")

    wins = sum(1 for r in settle_rows if r["outcome"] == "WIN")
    losses = sum(1 for r in settle_rows if r["outcome"] == "LOSS")
    pushes = sum(1 for r in settle_rows if r["outcome"] == "PUSH")

    # ROI is computable only where we originated a price (moneyline legs).
    # Profit per 1 unit staked at American odds o: 100/|o| if o < 0 else o/100.
    def american_profit_per_unit(odds: float) -> float:
        return 100.0 / abs(odds) if odds < 0 else odds / 100.0

    ml_rows = [r for r in settle_rows if r["market_type"] == "moneyline" and r["our_price"]]
    staked = float(len(ml_rows))  # flat 1-unit stakes
    profit = sum(
        (american_profit_per_unit(float(r["our_price"])) if r["outcome"] == "WIN" else
         (-1.0 if r["outcome"] == "LOSS" else 0.0))
        for r in ml_rows)
    roi = profit / staked if staked else None

    summary = {
        "games_final": len(finals),
        "games_scheduled": len(scheduled),
        "markets_originated_and_settled": len(settle_rows),
        "wins": wins, "losses": losses, "pushes": pushes,
        "moneyline_legs_priced": len(ml_rows),
        "units_staked_at_our_prices": round(staked, 4),
        "units_profit_at_our_prices": round(profit, 4),
        "roi_at_our_prices": round(roi, 4) if roi is not None else None,
        "roi_note": ("n = 1 graded game (Week 10 TNF). The ROI is arithmetically "
                     "computable but statistically meaningless; no skill claim is "
                     "made from it. Both sides of each originated number are "
                     "settled for bookkeeping — a strategy bets only the legs a "
                     "pre-registered rule selects. Spread and total legs have no "
                     "originated price yet (price authority open — see decisions "
                     "Q-31), so no ROI is computed for them. Never inferred."),
    }

    feed_rows = []
    for g in games:
        feed_rows.append({
            "week": g["week"],
            "game_id": g["game_id"],
            "away": g["away"],
            "away_score": g["away_score"] if g["away_score"] is not None else "",
            "home": g["home"],
            "home_score": g["home_score"] if g["home_score"] is not None else "",
            "gameday": g["gameday"],
            "status": g["status"],
            "_source_url": g["game_url"],
            "_source_label": f"NFL.com game page (Week {g['week']} schedule)",
            "_source_org": "NFL",
            "_retrieved_at": SNAPSHOT,
            "_flags": [] if g["status"] == "FINAL" else ["not played — result blank until the official page prints FINAL"],
            "_verified": True,
        })

    doc = {
        "dataset": "results_feed",
        "title": "Verified results feed — 2026 NFL regular season",
        "generated_at": GEN,
        "retrieved_at": SNAPSHOT,
        "policy": {
            "settlement_source": "Official NFL.com game/week pages only. A result is graded only after the official page prints FINAL.",
            "blank_rule": "A value the official page does not publish stays blank and is flagged. Nothing is inferred.",
            "roi_rule": "ROI is computed only from legs whose price we originated ourselves. n is published with every ROI.",
            "mirror_rule": "nflverse/nfldata is a community mirror. It is used only for labelled cross-checks and is never a source of truth.",
            "origination_order": "side (spread) first, then total, then moneyline",
        },
        "columns": ["week", "game_id", "away", "away_score", "home", "home_score", "gameday", "status"],
        "rows": feed_rows,
        "settlement": settle_rows,
        "settlement_summary": summary,
        "integrity_checks": {
            "standings_arithmetic": {
                "description": ("Every club's W-L-T, points for and points against recomputed "
                                "from the feed must equal the official NFL.com standings."),
                "teams_checked": len(check_rows),
                "match": n_ok,
                "mismatch": n_bad,
                "rows": check_rows,
            },
            "mirror_cross_check": {
                "description": ("Community-mirror scores compared with the official page. "
                                "The mirror is not an official source; agreement is corroboration only."),
                "games_compared": m_ok + m_bad,
                "agree": m_ok,
                "disagree": m_bad,
                "disagreement_rows": m_rows,
                "_source_url": "https://github.com/nflverse/nfldata/blob/master/data/games.csv",
                "_source_label": "nflverse/nfldata games.csv (community mirror — not an official source)",
            },
        },
        "historical_mirror": {
            "file": "data/raw/nflverse/games.csv",
            "seasons": "2006-2026",
            "rows": 7548,
            "verified": False,
            "_flags": [
                "historical results are community-mirror values (I-11): they are not checked game by game against NFL.com and are not rendered as fact",
            ],
            "_source_url": "https://github.com/nflverse/nfldata/blob/master/data/games.csv",
            "_source_label": "nflverse/nfldata games.csv (community mirror — not an official source)",
        },
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")

    print(f"results feed: {len(finals)} final, {len(scheduled)} scheduled")
    print(f"standings arithmetic: {n_ok}/{len(check_rows)} match, {n_bad} mismatch")
    print(f"mirror cross-check   : {m_ok} agree, {m_bad} disagree of {m_ok + m_bad}")
    print(f"settlement           : {wins}W-{losses}L-{pushes}P over {len(settle_rows)} legs")
    if n_bad:
        print("FAIL: feed disagrees with the official standings", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
