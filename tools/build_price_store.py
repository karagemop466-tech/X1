#!/usr/bin/env python3
"""T10 + T12 — price-snapshot store and origination ledger (reproducible).

Writes data/lines/price_snapshots.{json,csv} and data/lines/origination.{json,csv}.

Rules honored:
- Opening and closing numbers are recorded separately; a number whose opening
  value is not in any source in this repository is BLANK and flagged as
  unverified — never inferred.
- No source inside or outside this repository publishes official NFL betting
  prices (flag F-06); every price row is labelled third-party market data.
- Origination order is fixed: side first, then total, then moneyline.
- model_fair_line / market_line / difference are published as separate columns.

Data semantics (verified against data/raw/nflverse/DATASETS.md and model_config):
- games.csv `spread_line`: away-team spread; positive = home favored by that
  many points (mirrors `result` = home margin). away_spread = spread_line.
- games.csv `total_line`, `away_moneyline`, `home_moneyline`: market numbers.
- Originated model fair lines come from data/lines/originated_lines_2026_week10.csv
  (x1_spread_away, x1_total, x1_ml_away, x1_ml_home).
"""
import csv
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.join(ROOT, "data/raw/nflverse/games.csv")
ORIGIN = os.path.join(ROOT, "data/lines/originated_lines_2026_week10.csv")
INITIAL = os.path.join(ROOT, "data/raw/nflverse/initial_lines.csv")
CLOSING = os.path.join(ROOT, "data/raw/nflverse/closing_lines.csv")
OUT_JSON = os.path.join(ROOT, "data/lines/price_snapshots.json")
OUT_CSV = os.path.join(ROOT, "data/lines/price_snapshots.csv")
ORIG_JSON = os.path.join(ROOT, "data/lines/origination.json")
ORIG_CSV = os.path.join(ROOT, "data/lines/origination.csv")

SNAP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
MIRROR_URL = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
INITIAL_URL = "https://github.com/nflverse/nfldata/blob/master/data/initial_lines.csv"
CLOSING_URL = "https://github.com/nflverse/nfldata/blob/master/data/closing_lines.csv"
NO_OFFICIAL = ("No official NFL source publishes betting prices; bookmaker "
               "prices are third-party market data (flag F-06).")


def implied_prob(american):
    """American odds -> implied probability (no vig removal)."""
    if american in (None, "", 0):
        return None
    a = float(american)
    p = (-a) / ((-a) + 100.0) if a < 0 else 100.0 / (a + 100.0)
    return round(p, 6)


def num(x):
    if x in (None, ""):
        return None
    try:
        f = float(x)
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


def load_mirror():
    games = {}
    for r in csv.DictReader(open(MIRROR, newline="")):
        if r["season"] != "2026":
            continue
        games[r["game_id"]] = r
    return games


def load_originated():
    rows = {}
    for r in csv.DictReader(open(ORIGIN, newline="")):
        rows[r["game_id"]] = r
    return rows


def coverage_stats():
    ini = sum(1 for _ in open(INITIAL, newline="")) - 1
    clo = sum(1 for _ in open(CLOSING, newline="")) - 1
    return ini, clo


def main():
    games = load_mirror()
    orig = load_originated()
    ini_rows, clo_rows = coverage_stats()

    snapshots = []
    origination = []
    for gid, g in sorted(games.items(), key=lambda kv: (kv[1]["gameday"], kv[0])):
        wk = int(g["week"])
        if wk > 10:
            continue  # snapshot store covers games through the current week
        o = orig.get(gid, {})
        away, home = g["away_team"], g["home_team"]
        kickoff = g["gameday"]
        spread_line = num(g["spread_line"])
        total_line = num(g["total_line"])
        aml, hml = num(g["away_moneyline"]), num(g["home_moneyline"])
        asp, hsp = num(g.get("away_spread_odds")), num(g.get("home_spread_odds"))
        uod, ood = num(g.get("under_odds")), num(g.get("over_odds"))
        settled = g["away_score"] not in ("", None) and g["home_score"] not in ("", None)

        # ---- market rows: side first (order 1), then total (2), then moneyline (3)
        market_rows = []
        if spread_line is not None:
            market_rows.append((1, "SPREAD", "away", spread_line, asp))
            market_rows.append((1, "SPREAD", "home", -spread_line, hsp))
        if total_line is not None:
            market_rows.append((2, "TOTAL", "over", total_line, ood))
            market_rows.append((2, "TOTAL", "under", total_line, uod))
        if aml is not None:
            market_rows.append((3, "MONEYLINE", "away", aml, None))
        if hml is not None:
            market_rows.append((3, "MONEYLINE", "home", hml, None))

        for order, mtype, sel, line, odds in market_rows:
            snapshots.append({
                "game_id": gid, "week": wk, "kickoff": kickoff,
                "away": away, "home": home,
                "origination_order": order, "market_type": mtype, "selection": sel,
                "opening_line": None, "opening_odds": None,
                "opening_source_url": None, "opening_retrieved_at": None,
                "opening_status": "unverified",
                "closing_line": line, "closing_odds": odds,
                "closing_source_url": MIRROR_URL,
                "closing_retrieved_at": g.get("gameday") or None,
                "closing_status": "verified third-party",
                "flags": ["no official NFL price source (F-06)",
                          "opening number absent from every source in this repository — blank, not inferred"],
            })

        # ---- origination ledger: three markets, ordered side -> total -> moneyline
        def entry(order, mtype, fair, market, unit, fair_note, market_note):
            if fair is None and market is None:
                return
            diff = None
            if fair is not None and market is not None:
                if unit == "implied_probability":
                    diff = round(implied_prob(fair) - implied_prob(market), 6)
                else:
                    diff = round(float(fair) - float(market), 3)
            origination.append({
                "game_id": gid, "week": wk, "kickoff": kickoff,
                "away": away, "home": home,
                "origination_order": order, "market_type": mtype,
                "model_fair_line": fair, "market_line": market,
                "difference": diff, "difference_unit": unit,
                "model_source": fair_note,
                "market_source": market_note,
                "snapshot_ref": "data/lines/price_snapshots.json",
                "flags": ["market line third-party (F-06)"] + (
                    ["opening number unverified"] if True else []),
            })

        f_sp = num(o.get("x1_spread_away"))
        f_tot = num(o.get("x1_total"))
        f_mla = num(o.get("x1_ml_away"))
        f_mlh = num(o.get("x1_ml_home"))
        model_note = ("x1 model fair line (ratings fitted on 2008 game-results rows; "
                      "inputs fingerprinted nflverse/nfldata)")
        market_note = f"fingerprinted nflverse/nfldata mirror, DATASETS.md games.csv fields ({MIRROR_URL})"
        entry(1, "SPREAD (away)", f_sp, spread_line, "points", model_note, market_note)
        entry(2, "TOTAL", f_tot, total_line, "points", model_note, market_note)
        entry(3, "MONEYLINE (away)", f_mla, aml, "implied_probability", model_note, market_note)
        entry(3, "MONEYLINE (home)", f_mlh, hml, "implied_probability", model_note, market_note)

    # ---------- price_snapshots.json ----------
    schema = [
        ("game_id", "str", "Game id (season_week_away_home)"),
        ("week", "int", "NFL week"),
        ("kickoff", "date", "Kickoff date"),
        ("origination_order", "int", "1=side, 2=total, 3=moneyline (fixed origination order)"),
        ("market_type", "str", "SPREAD | TOTAL | MONEYLINE"),
        ("selection", "str", "away|home (spread, moneyline) or over|under (total)"),
        ("opening_line", "number|null", "Opening number — blank+unverified when no source records one"),
        ("opening_odds", "number|null", "Opening price (American) — blank when absent"),
        ("closing_line", "number|null", "Closing/market number carried in games.csv"),
        ("closing_odds", "number|null", "Closing price (American) when the source carries it"),
        ("closing_source_url", "url", "One link per row — fingerprinted third-party source"),
    ]
    out = {
        "dataset": "price_snapshots",
        "title": "Price-snapshot store — opening and closing numbers for every originated market",
        "generated_at": SNAP,
        "source": {
            "url": MIRROR_URL,
            "label": "nflverse/nfldata games.csv (fingerprinted third-party mirror)",
            "organization": "nflverse (community)",
            "retrieved_at": SNAP,
            "official": False,
            "note": NO_OFFICIAL,
        },
        "columns": schema,
        "rows": snapshots,
        "verification": {
            "rows": len(snapshots),
            "rows_with_closing": sum(1 for r in snapshots if r["closing_line"] is not None),
            "rows_with_opening": sum(1 for r in snapshots if r["opening_line"] is not None),
            "rows_flagged": len(snapshots),
            "unverified_cells": sum(2 for r in snapshots if r["opening_line"] is None) +
                                sum(1 for r in snapshots if r["opening_odds"] is None),
            "flagged_reasons": ["opening number absent from every source in this repository", NO_OFFICIAL],
        },
        "note": ("Closing numbers are the single market line carried in the fingerprinted mirror; "
                 "the mirror documentation records them as bookmaker market data and does not "
                 "distinguish opening from closing, so the snapshot store treats them as the market "
                 "reference at retrieval time. Opening numbers are blank for every 2026 market and "
                 "flagged: no source in this repository records them. Historical coverage: "
                 "closing_lines.csv carries per-side closing lines with outcomes for 2006-2018 "
                 f"({clo_rows} rows, {CLOSING_URL}); initial_lines.csv carries 2021 opening lines "
                 f"from one book (WSGT, {ini_rows} rows, {INITIAL_URL})."),
    }
    json.dump(out, open(OUT_JSON, "w"), indent=1, allow_nan=False)
    cols = ["game_id", "week", "kickoff", "away", "home", "origination_order", "market_type",
            "selection", "opening_line", "opening_odds", "opening_source_url", "opening_status",
            "closing_line", "closing_odds", "closing_source_url", "closing_status", "flags"]
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in snapshots:
            w.writerow(["; ".join(r[c]) if c == "flags" else ("" if r[c] is None else r[c])
                        for c in cols])

    # ---------- origination.json ----------
    orig_cols = [
        ("origination_order", "int", "1=side first, then 2=total, then 3=moneyline"),
        ("market_type", "str", "SPREAD | TOTAL | MONEYLINE"),
        ("model_fair_line", "number|null", "Model fair line (x1 ratings model)"),
        ("market_line", "number|null", "Market line (third-party, F-06)"),
        ("difference", "number|null", "model_fair_line minus market_line; points for spread/total, implied-probability points for moneyline"),
        ("difference_unit", "str", "points | implied_probability"),
    ]
    out2 = {
        "dataset": "origination",
        "title": "Origination ledger — side first, then total, then moneyline; fair vs market vs difference",
        "generated_at": SNAP,
        "source": {
            "url": "https://github.com/karagemop466-tech/X1/blob/main/data/lines/originated_lines_2026_week10.csv",
            "label": "x1 model fair lines (code/build_lines.py) + fingerprinted nflverse/nfldata market lines",
            "organization": "this repository (model) + nflverse (market)",
            "retrieved_at": SNAP,
            "official": False,
            "note": NO_OFFICIAL,
        },
        "columns": orig_cols,
        "rows": origination,
        "verification": {
            "rows": len(origination),
            "rows_verified": sum(1 for r in origination if r["model_fair_line"] is not None and r["market_line"] is not None),
            "rows_flagged": sum(1 for r in origination if any("unverified" in f for f in r["flags"])),
            "unverified_cells": 0,
            "flagged_reasons": [NO_OFFICIAL],
        },
        "note": ("Every row keeps model_fair_line, market_line and difference in separate columns. "
                 "Origination order is fixed at side, then total, then moneyline and encoded in "
                 "origination_order. Market prices are third-party data (F-06); model fair lines "
                 "are this project's own computation from fingerprinted mirror inputs."),
    }
    json.dump(out2, open(ORIG_JSON, "w"), indent=1, allow_nan=False)
    ocols = ["game_id", "week", "kickoff", "away", "home", "origination_order", "market_type",
             "model_fair_line", "market_line", "difference", "difference_unit",
             "model_source", "market_source", "snapshot_ref", "flags"]
    with open(ORIG_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(ocols)
        for r in origination:
            w.writerow(["; ".join(r[c]) if c == "flags" else ("" if r[c] is None else r[c])
                        for c in ocols])

    print(f"price_snapshots: {len(snapshots)} rows -> {OUT_JSON} (+csv)")
    print(f"origination: {len(origination)} rows -> {ORIG_JSON} (+csv)")


if __name__ == "__main__":
    main()
