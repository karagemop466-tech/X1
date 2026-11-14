#!/usr/bin/env python3
"""Build the origination table: fair line, market line, difference as separate
columns, in strict origination order — side first, then the total, then the
moneyline (owner brief; see docs/methodology/origination-order.md).

Session `arena-1d3600f8-x1` (T17). One row per originated market, ordered by
  origin_seq 1 = side (spread), 2 = total, 3 = moneyline (away, then home).

Columns `fair_line`, `market_line`, `difference` are always three SEPARATE
columns. difference = fair_line − market_line in the market's own units
(points for side/total; odds points for moneyline). A blank market_line with
the flag `no official source` means the value could not be confirmed from an
official source and is left blank per the verification contract — it is never
inferred.

Inputs: data/lines/originated_lines_2026_week10.csv (our model's fair lines),
        data/price_snapshots/market_index.csv (market captures + provenance).
Output: data/lines/origination_2026_week10.csv
"""

from __future__ import annotations

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "lines", "origination_2026_week10.csv")
IDX = os.path.join(ROOT, "data", "price_snapshots", "market_index.csv")

COLS = ["origin_seq", "origin_order", "game_id", "date", "away", "home",
        "market_type", "selection", "fair_line", "market_line", "difference",
        "difference_unit", "fair_source", "market_source", "market_verification", "flags"]

FAIR_SRC = ("our own model (walk-forward Poisson points model, code/build_lines.py) — "
            "published as our computation, not a league fact")


def main() -> int:
    rows = list(csv.DictReader(open(IDX, encoding="utf-8")))
    rows.sort(key=lambda r: (int(r["origin_seq"]), r["game_id"], r["market_type"]))

    out = []
    for r in rows:
        fair = r["fair_line"].strip()
        mkt = r["closing_price"].strip() or r["opening_price"].strip()
        unit = "odds points (American)" if "moneyline" in r["market_type"] else "points"
        diff = ""
        if fair and mkt:
            try:
                diff = f"{float(fair) - float(mkt):g}"
            except ValueError:
                diff = ""
        flags = r["flags"]
        if not mkt:
            flags += "; market line blank: no official source"
        out.append({
            "origin_seq": r["origin_seq"], "origin_order": r["origin_order"],
            "game_id": r["game_id"], "date": r["date"], "away": r["away"], "home": r["home"],
            "market_type": r["market_type"], "selection": r["selection"],
            "fair_line": fair, "market_line": mkt, "difference": diff,
            "difference_unit": unit,
            "fair_source": FAIR_SRC,
            "market_source": r["closing_source"] or "",
            "market_verification": r["closing_verification"] if mkt else "blank-no-source",
            "flags": flags,
        })

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(out)

    n_diff = sum(1 for r in out if r["difference"])
    print(f"origination rows: {len(out)} (order: side -> total -> moneyline)")
    print(f"  with all three of fair/market/difference filled: {n_diff}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
