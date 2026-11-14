#!/usr/bin/env python3
"""Record a price capture into the price-snapshot store (append-only).

Session `arena-1d3600f8-x1` (T15). Use this whenever a price becomes available
from a source you are entitled to use (a licensed odds feed, or the owner's own
book account). Example:

    python3 tools/record_price.py \\
        --game 2026_10_BUF_NYJ --market spread --selection away \\
        --price -8.5 --kind line --capture closing \\
        --book "example book" --source-url "https://example.com/odds" \\
        --source-type book-feed --verification unverified-book-feed \\
        --note "closing capture 2026-11-15"

The tool appends one row to data/price_snapshots/snapshots.csv and refreshes
data/price_snapshots/market_index.csv. It never edits or deletes an existing
capture. A capture with no real source URL is rejected: this store records
prices, it does not invent them.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "price_snapshots")
SNAP = os.path.join(OUT, "snapshots.csv")

CAPTURE_TYPES = ("opening", "closing", "intraday")
MARKET_TYPES = ("spread", "total", "moneyline_away", "moneyline_home", "prop")
PRICE_KINDS = ("line", "odds")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--game", required=True, help="game_id, e.g. 2026_10_BUF_NYJ")
    p.add_argument("--market", required=True, choices=MARKET_TYPES)
    p.add_argument("--selection", required=True, help="e.g. away / home / over / under / player prop name")
    p.add_argument("--price", required=True, help="the number: a line (e.g. -8.5) or American odds (e.g. -110)")
    p.add_argument("--kind", required=True, choices=PRICE_KINDS)
    p.add_argument("--capture", required=True, choices=CAPTURE_TYPES)
    p.add_argument("--book", default="", help="book or feed name")
    p.add_argument("--source-url", required=True, help="where the price was published")
    p.add_argument("--source-type", required=True,
                   help="official-league | book-feed | owner-account | third-party-mirror")
    p.add_argument("--verification", required=True,
                   help="verified-official | unverified-book-feed | unverified-third-party | ...")
    p.add_argument("--note", default="")
    p.add_argument("--captured-at", default="", help="ISO timestamp; defaults to today's UTC date")
    args = p.parse_args()

    if not args.source_url.startswith(("http://", "https://")):
        print("REJECTED: --source-url must be a real URL (this store never records unsourced prices)")
        return 2

    rows = list(csv.DictReader(open(SNAP, encoding="utf-8")))
    fields = list(rows[0]) if rows else []
    if not fields:
        print("REJECTED: snapshots.csv missing or empty — run tools/build_price_snapshots.py first")
        return 2

    row = {f: "" for f in fields}
    row.update({
        "snapshot_id": f"PS-{len(rows) + 1:04d}",
        "captured_at": args.captured_at or __import__("datetime").date.today().isoformat(),
        "capture_type": args.capture,
        "season": "2026",
        "week": args.game.split("_")[1] if "_" in args.game else "",
        "game_id": args.game,
        "market_type": args.market,
        "selection": args.selection,
        "price_kind": args.kind,
        "price": args.price,
        "book": args.book,
        "source_url": args.source_url,
        "source_type": args.source_type,
        "verification": args.verification,
        "note": args.note,
    })
    with open(SNAP, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writerow(row)
    print(f"recorded {row['snapshot_id']}: {args.game} {args.market}/{args.selection} "
          f"{args.capture} {args.price} ({args.verification})")

    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_price_snapshots.py")],
                   check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
