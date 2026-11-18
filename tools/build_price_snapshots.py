#!/usr/bin/env python3
"""Build the price-snapshot store for every market we originate.

Session `arena-1d3600f8-x1` (T15). The store records OPENING and CLOSING
numbers for every market originated on the Week 10 slate, in origination order
(1 side, 2 total, 3 moneyline — see docs/methodology/origination-order.md).

Data rules (the repo's verification contract):
  * No official or licensed source publishes betting prices. Therefore price
    cells that cannot be confirmed from an official source are recorded as
    BLANK and flagged, never filled from memory or inference.
  * The one price capture that exists is the third-party closing line carried
    in the nflverse/nfldata mirror (data/processed/schedule_2026.json). It is
    recorded as a `closing` capture with source_type=third-party-mirror and
    verification=unverified-third-party. It is NOT presented as verified.
  * Price-data policy decision, 2026-11-17 (the N-4 decision this session was
    told to settle before any backtest is published): mirror-derived prices MAY
    be stored and published, always in the labelled columns above and always
    beside the sha256 of the pinned file they were read from
    (data/raw_manifest.json -> data/raw/nflverse/games.csv). They may NOT be
    relabelled as an official price, and no opening capture is back-filled from
    a closing file. Published with the decision: provenance.json next to the
    two CSVs, written by this tool. 
  * Opening captures: none exist yet. The rows are reserved with blank price
    and flag `no-opening-capture (Q-02)` so the store is complete by design.

Files:
  data/price_snapshots/snapshots.csv   append-only capture log (seeded here,
                                       appended by tools/record_price.py)
  data/price_snapshots/market_index.csv  one row per originated market with
                                       opening/closing columns resolved from
                                       the capture log

Regenerating is idempotent: existing captures are never deleted or edited.
"""

from __future__ import annotations

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "price_snapshots")
ORIG = os.path.join(ROOT, "data", "lines", "originated_lines_2026_week10.csv")
MIRROR = os.path.join(ROOT, "data", "processed", "schedule_2026.json")
TODAY = "2026-11-14"

SNAP_COLS = ["snapshot_id", "captured_at", "capture_type", "season", "week", "game_id",
             "market_type", "selection", "price_kind", "price", "book", "source_url",
             "source_type", "verification", "note"]

IDX_COLS = ["market_id", "origin_seq", "origin_order", "season", "week", "game_id",
            "date", "away", "home", "market_type", "selection", "fair_line",
            "opening_price", "opening_captured_at", "opening_source", "opening_verification",
            "closing_price", "closing_captured_at", "closing_source", "closing_verification",
            "flags"]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    import json

    orig = list(csv.DictReader(open(ORIG, encoding="utf-8")))
    mirror = {}
    for g in json.load(open(MIRROR, encoding="utf-8"))["games"]:
        if g["week"] == 10:
            gid = g["game_id"].replace("_LAR", "_LA").replace("_ARI", "_AZ")
            mirror[gid] = g

    # ------------------------------------------------ existing captures (keep)
    snap_path = os.path.join(OUT, "snapshots.csv")
    captures: list[dict] = []
    if os.path.exists(snap_path):
        captures = list(csv.DictReader(open(snap_path, encoding="utf-8")))
    have = {(c["game_id"], c["market_type"], c["selection"], c["capture_type"]): c for c in captures}

    seeds: list[dict] = []

    def seed(game_id: str, mtype: str, sel: str, ctype: str, kind: str, price: str,
             src: str, stype: str, verif: str, note: str) -> None:
        key = (game_id, mtype, sel, ctype)
        if key in have:
            return
        seeds.append({
            "snapshot_id": f"PS-{len(captures) + len(seeds) + 1:04d}",
            "captured_at": TODAY, "capture_type": ctype, "season": "2026", "week": "10",
            "game_id": game_id, "market_type": mtype, "selection": sel,
            "price_kind": kind, "price": price, "book": "",
            "source_url": src, "source_type": stype, "verification": verif, "note": note,
        })

    index_rows: list[dict] = []
    seq_map = {"spread": (1, "side"), "total": (2, "total"),
               "moneyline_away": (3, "moneyline"), "moneyline_home": (3, "moneyline")}

    for row in orig:
        gid_raw = row["game_id"]
        gid = gid_raw.replace("_LAR", "_LA").replace("_ARI", "_AZ")
        m = mirror.get(gid, {})
        murl = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
        specs = [
            ("spread", "away", row["x1_spread_away"], "line",
             str(m.get("spread_line", ""))),
            ("total", "over", row["x1_total"], "line", str(m.get("total_line", ""))),
            ("moneyline_away", "away", row["x1_ml_away"], "odds", str(m.get("away_moneyline", ""))),
            ("moneyline_home", "home", row["x1_ml_home"], "odds", str(m.get("home_moneyline", ""))),
        ]
        for mtype, sel, fair, kind, mkt in specs:
            seq, order = seq_map[mtype]
            closing_val = mkt.strip()
            # closing capture from the third-party mirror, if present
            if closing_val and closing_val not in ("None", ""):
                seed(gid_raw, mtype, sel, "closing", kind, closing_val, murl,
                     "third-party-mirror", "unverified-third-party",
                     "nfldata closing line (benchmark only); no official price source exists")
                cverif, csrc = "unverified-third-party", murl
            else:
                cverif, csrc = "blank-no-source", ""
            # opening capture: reserved, blank
            seed(gid_raw, mtype, sel, "opening", kind, "", "",
                 "none", "blank-no-source",
                 "no opening capture recorded yet — supply a licensed feed via tools/record_price.py (Q-02)")
            flags = []
            if not closing_val or closing_val in ("None", ""):
                flags.append("closing price blank: no source (Q-02)")
            flags.append("all prices unverified: no official source publishes betting prices")
            index_rows.append({
                "market_id": f"MK-2026W10-{seq:02d}-{gid_raw}-{mtype}",
                "origin_seq": str(seq), "origin_order": order,
                "season": "2026", "week": "10", "game_id": gid_raw, "date": row["date"],
                "away": row["away"], "home": row["home"],
                "market_type": mtype, "selection": sel, "fair_line": fair,
                "opening_price": "", "opening_captured_at": "", "opening_source": "",
                "opening_verification": "blank-no-source",
                "closing_price": closing_val if closing_val not in ("None", "") else "",
                "closing_captured_at": TODAY if closing_val not in ("None", "") else "",
                "closing_source": csrc, "closing_verification": cverif,
                "flags": "; ".join(flags),
            })

    all_captures = captures + seeds
    with open(snap_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SNAP_COLS)
        w.writeheader()
        w.writerows(all_captures)

    # resolve opening/closing columns from the full capture log (latest wins)
    resolved: dict[tuple, dict] = {}
    for c in all_captures:
        key = (c["game_id"], c["market_type"], c["selection"])
        slot = resolved.setdefault(key, {})
        slot[c["capture_type"]] = c
    for r in index_rows:
        key = (r["game_id"], r["market_type"], r["selection"])
        for ctype in ("opening", "closing"):
            c = resolved.get(key, {}).get(ctype)
            if c and c["price"]:
                r[f"{ctype}_price"] = c["price"]
                r[f"{ctype}_captured_at"] = c["captured_at"]
                r[f"{ctype}_source"] = c["source_url"]
                r[f"{ctype}_verification"] = c["verification"]

    idx_path = os.path.join(OUT, "market_index.csv")
    with open(idx_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=IDX_COLS)
        w.writeheader()
        w.writerows(index_rows)

    n_open = sum(1 for r in index_rows if r["opening_price"])
    n_close = sum(1 for r in index_rows if r["closing_price"])
    print(f"captures: {len(all_captures)} ({len(seeds)} seeded this run)")
    print(f"originated markets: {len(index_rows)} (side/total/moneyline, games {len(orig)})")
    print(f"  with opening capture : {n_open}")
    print(f"  with closing capture : {n_close} (third-party mirror, unverified)")

    # ------------------------------------------------------------- provenance (N-4 decision record)
    import hashlib
    import json as _json
    pinned = os.path.join(ROOT, "data", "raw", "nflverse", "games.csv")
    raw = open(pinned, "rb").read()
    digest = hashlib.sha256(raw).hexdigest()
    man = _json.load(open(os.path.join(ROOT, "data", "raw_manifest.json"), encoding="utf-8"))
    entry = next((e for e in man if e.get("name") == "games.csv"), {})
    prov = {
        "dataset": "price_snapshot_provenance",
        "written_by": "tools/build_price_snapshots.py",
        "decision": ("price-data policy, 2026-11-17 (N-4): third-party mirror prices are stored and "
                     "published as labelled third-party captures and never as an official price; the "
                     "opening stage stays blank until a licensed feed exists"),
        "pinned_mirror": {"file": "data/raw/nflverse/games.csv", "sha256": digest, "bytes": len(raw),
                          "sha256_in_manifest": entry.get("sha256"),
                          "manifest_matches_file": entry.get("sha256") == digest,
                          "retrieved_at": entry.get("retrieved_at", ""),
                          "url": entry.get("url", "")},
        "prices_read_from": {"file": "data/processed/schedule_2026.json",
                             "note": ("a derived file, kept as this tool's input so the store's history "
                                      "is reproducible; the pinned bytes above are what a reader should "
                                      "re-derive the same numbers from")},
        "counts": {"captures": len(all_captures), "markets": len(index_rows),
                   "with_opening": n_open, "with_closing": n_close},
        "opening_stage": "blank by policy, not by omission — see Q-02/Q-03 and tools/record_price.py",
    }
    with open(os.path.join(OUT, "provenance.json"), "w", encoding="utf-8") as fh:
        _json.dump(prov, fh, indent=1)
        fh.write("\n")
    print(f"provenance: mirror pin {'matches' if prov['pinned_mirror']['manifest_matches_file'] else 'DOES NOT MATCH'} "
          f"the manifest ({digest[:12]}..); writing data/price_snapshots/provenance.json")
    if not prov["pinned_mirror"]["manifest_matches_file"]:
        print("  ! the mirror file on disk is not the pinned bytes — the closing captures above are "
              "cited by an older fingerprint and must be re-read before this store is trusted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
