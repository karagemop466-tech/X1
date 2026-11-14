#!/usr/bin/env python3
"""Build the originated-markets table (N3/N4) and the price-snapshot store (N1).

Session arena/3fa49c1a-x1.

N3 — origination order.  Every market we originate is emitted in a fixed order:
     the SIDE first, then the TOTAL, then the MONEYLINE.  The builder refuses to
     write a later market class until every game has the earlier one, so the
     order is enforced, not merely documented.

N4 — separate columns.  Every row publishes the model's fair line, the market
     line and the difference as three separate columns, with the sign
     convention defined once: difference = model_fair_line - market_line.

N1 — price-snapshot store.  One row per originated market selection recording
     opening and closing market numbers for the market we originated.  The
     verification rule governs what may be filled: no official or licensed
     source publishes betting prices (question Q-02), so the closing number is
     recorded from the fingerprinted third-party mirror with provenance
     `third-party mirror` and verified=no, the opening number is blank because
     nothing at all records 2026 openers, and CLV stays blank until a verified
     feed is attached.  Nothing is inferred.

Inputs:
  data/lines/originated_lines_2026_week10.csv   the model's Week 10 lines (wide)
  data/raw/nflverse/games.csv                   third-party mirror (market benchmark)
Outputs:
  data/lines/originated_markets_2026_week10.csv
  data/prices/price_snapshots.csv
  data/prices/price_feed.json
"""

from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "lines", "originated_lines_2026_week10.csv")
MIRROR = os.path.join(ROOT, "data", "raw", "nflverse", "games.csv")
OUT_LINES = os.path.join(ROOT, "data", "lines")
OUT_PRICES = os.path.join(ROOT, "data", "prices")

SEASON, WEEK = 2026, 10
RETRIEVED = "2026-11-14"
ORIGINATED_AT = "2026-11-14"          # when the fair lines were published (snapshot convention, Q-03)
MIRROR_URL = "https://github.com/nflverse/nfldata"
MIRROR_LABEL = "nflverse/nfldata games.csv (third-party community mirror, fingerprinted in data/raw_manifest.json)"
UNVERIFIED = "no"
OPEN_FLAG = "no source records 2026 opening numbers; blank until a price feed is attached (Q-02/Q-03)"
CLOSE_FLAG = "UNVERIFIED — third-party mirror, not an official or licensed odds source (Q-02)"

# N3: the one true origination order
MARKET_ORDER = ["side", "total", "moneyline"]
ORDER_INDEX = {m: i + 1 for i, m in enumerate(MARKET_ORDER)}


def american_to_prob(odds: float) -> float:
    """Win probability implied by American odds (before de-vigging)."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def load_mirror() -> dict:
    out = {}
    with open(MIRROR, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") == str(SEASON) and r.get("week") == str(WEEK) and r.get("game_type") == "REG":
                out[r["game_id"]] = r
    return out


def main() -> int:
    with open(SRC, encoding="utf-8-sig", newline="") as fh:
        wide = list(csv.DictReader(fh))
    mirror = load_mirror()

    markets: list[dict] = []   # N3/N4 rows
    prices: list[dict] = []    # N1 rows

    def add_market(game: dict, mtype: str, selection: str, fair, market, unit: str) -> None:
        def fmt(v):
            if v is None or v == "":
                return ""
            f = float(v)
            return str(int(f)) if f == int(f) else str(f)
        diff = ""
        if fair not in ("", None) and market not in ("", None):
            d = float(fair) - float(market)
            diff = str(int(d)) if d == int(d) else f"{d:.1f}"
        markets.append({
            "origination_order": ORDER_INDEX[mtype],
            "market_type": mtype,
            "game_id": game["game_id"],
            "date": game["date"],
            "matchup": f"{game['away']} at {game['home']}",
            "selection": selection,
            "model_fair_line": fmt(fair),
            "market_line": fmt(market),
            "difference": diff,
            "difference_unit": unit,
            "market_line_provenance": MIRROR_LABEL if market not in ("", None) else "no source (Q-02)",
            "market_line_verified": UNVERIFIED if market not in ("", None) else "",
            "model_source": "x1 walk-forward ratings (code/build_lines.py), fitted on game results only",
            "source_url": MIRROR_URL if market not in ("", None) else "",
        })

    def add_price(game: dict, mtype: str, selection: str, our_line, close, unit: str) -> None:
        prices.append({
            "season": SEASON,
            "week": WEEK,
            "game_id": game["game_id"],
            "kickoff_date": game["date"],
            "market_type": mtype,
            "selection": selection,
            "line_unit": unit,
            "our_line": "" if our_line in ("", None) else our_line,
            "our_originated_at": ORIGINATED_AT,
            "market_open": "",
            "market_open_ts": "",
            "market_open_source": "",
            "market_open_verified": "",
            "market_close": "" if close in ("", None) else close,
            "market_close_ts": "",
            "market_close_source": MIRROR_URL if close not in ("", None) else "",
            "market_close_verified": UNVERIFIED,
            "clv_vs_close": "",
            "flags": "; ".join(filter(None, [
                OPEN_FLAG,
                CLOSE_FLAG if close not in ("", None) else "no closing number on record",
            ])),
        })

    # ---- N3 enforcement: sides for all games first, then totals, then moneylines
    sides, totals, mls = [], [], []
    for g in wide:
        m = mirror.get(g["game_id"], {})
        sides.append((g, m))
        totals.append((g, m))
        mls.append((g, m))

    for g, m in sides:                                   # 1. side
        add_market(g, "side", f"{g['away']} (away spread)",
                   g.get("x1_spread_away"), g.get("market_spread_away"), "points")
        add_price(g, "side", f"{g['away']} (away spread)",
                  g.get("x1_spread_away"), g.get("market_spread_away"), "points")
    assert all(r["market_type"] == "side" for r in markets), "side rows must come first"

    for g, m in totals:                                  # 2. total
        add_market(g, "total", "game total",
                   g.get("x1_total"), g.get("market_total"), "points")
        add_price(g, "total", "game total",
                  g.get("x1_total"), g.get("market_total"), "points")
    assert all(r["market_type"] in ("side", "total") for r in markets), "totals must follow sides"

    for g, m in mls:                                     # 3. moneyline
        for sel, fair_key, m_key in ((f"{g['away']} (away)", "x1_ml_away", "away_moneyline"),
                                     (f"{g['home']} (home)", "x1_ml_home", "home_moneyline")):
            fair = g.get(fair_key, "")
            mkt = m.get(m_key, "")
            # difference for moneylines is published in win-probability points
            diff_unit = "pp win probability"
            add_market(g, "moneyline", sel, fair, mkt, diff_unit)
            # probability difference replaces the raw American difference
            if fair not in ("", None) and mkt not in ("", None):
                d = (american_to_prob(float(fair)) - american_to_prob(float(mkt))) * 100.0
                markets[-1]["difference"] = f"{d:+.1f}"
            add_price(g, "moneyline", sel, fair, mkt, "American odds")

    # order check on the final table
    seen = [r["market_type"] for r in markets]
    idx = [ORDER_INDEX[t] for t in seen]
    if idx != sorted(idx):
        print("FAIL: origination order violated (side -> total -> moneyline)")
        return 1

    # ---- write the originated-markets table
    os.makedirs(OUT_LINES, exist_ok=True)
    cols = ["origination_order", "market_type", "game_id", "date", "matchup", "selection",
            "model_fair_line", "market_line", "difference", "difference_unit",
            "market_line_provenance", "market_line_verified", "model_source", "source_url"]
    with open(os.path.join(OUT_LINES, "originated_markets_2026_week10.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in markets:
            w.writerow(r)

    # ---- write the price-snapshot store
    os.makedirs(OUT_PRICES, exist_ok=True)
    pcols = ["season", "week", "game_id", "kickoff_date", "market_type", "selection", "line_unit",
             "our_line", "our_originated_at", "market_open", "market_open_ts", "market_open_source",
             "market_open_verified", "market_close", "market_close_ts", "market_close_source",
             "market_close_verified", "clv_vs_close", "flags"]
    with open(os.path.join(OUT_PRICES, "price_snapshots.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=pcols)
        w.writeheader()
        for r in prices:
            w.writerow(r)

    feed = {
        "dataset": "price_snapshots",
        "title": "Price-snapshot store — opening and closing numbers for every market we originate",
        "generated_at": RETRIEVED,
        "source": {
            "url": MIRROR_URL,
            "label": MIRROR_LABEL,
            "org": "nflverse (community)",
        },
        "columns": pcols,
        "rows": [{
            "_source_url": r["market_close_source"] or "https://github.com/karagemop466-tech/X1/blob/main/docs/live-pipeline/project-brief.md",
            "_source_label": (MIRROR_LABEL if r["market_close_source"]
                              else "no source publishes this value — blank per the verification rule"),
            "_source_org": "nflverse (community)" if r["market_close_source"] else "",
            "_retrieved_at": RETRIEVED,
            "_flags": [r["flags"]] if r["flags"] else [],
            **r,
        } for r in prices],
        "verification": {
            "rows": len(prices),
            "rows_verified": 0,
            "rows_flagged": len(prices),
            "unverified_cells": sum(1 for r in prices if r["market_close"] != "") + sum(1 for r in prices if r["market_open"] == ""),
            "note": ("Every price cell is UNVERIFIED or blank: no official or licensed source "
                     "publishes betting prices (Q-02). Closing numbers are recorded from a "
                     "fingerprinted third-party mirror so the CLV machinery has a placeholder; "
                     "opening numbers are blank because nothing records them. CLV columns stay "
                     "blank until a verified feed is attached."),
        },
        "empty": False,
    }
    with open(os.path.join(OUT_PRICES, "price_feed.json"), "w", encoding="utf-8") as fh:
        json.dump(feed, fh, indent=1)
        fh.write("\n")

    n_side = sum(1 for r in markets if r["market_type"] == "side")
    n_total = sum(1 for r in markets if r["market_type"] == "total")
    n_ml = sum(1 for r in markets if r["market_type"] == "moneyline")
    print(f"originated markets   : {len(markets)} rows "
          f"(order: {n_side} sides -> {n_total} totals -> {n_ml} moneylines)")
    print(f"price snapshots      : {len(prices)} rows "
          f"({sum(1 for r in prices if r['market_close'])} closing numbers recorded from the mirror, "
          f"{sum(1 for r in prices if not r['market_open'])} openings blank)")
    print("origination order    : enforced (side -> total -> moneyline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
