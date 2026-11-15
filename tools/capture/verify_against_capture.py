#!/usr/bin/env python3
"""Line-by-line check of the published Week 10 injury table against a stored capture.

Session `arena-8e329878-x1` (R4-2). For every published row it finds the official
row with the same club and player and compares four cells: position, injury,
practice status and game status. Every comparison is written to
`data/captures/official_injuries/verification_week10.json` with the capture id,
the capture SHA-256 and the official URL, so each result can be re-run.

Nothing is filled in. A published row with no official match, or an official row
with no published match, is reported as such and counts as a failure.

Usage:  python3 tools/capture/verify_against_capture.py [CAPTURE_ID]
Exit 1 on any mismatch or unmatched row.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import official_injuries as O  # noqa: E402

PUBLISHED = os.path.join(O.ROOT, "data", "injuries", "injuries_2026_week10.csv")
OUT = os.path.join(O.STORE, "verification_week10.json")

# The published table uses "LA" (the logo code on NFL.com's standings page); the
# injury page's matchup strip prints "LAR". Same club, different code. Recorded as
# a naming difference in the output, not as a value difference.
CODE_ALIASES = {"LA": "LAR"}
FIELDS = [
    ("position", "position"),
    ("injuries", "injury"),
    ("practice_status", "practice_status"),
    ("game_status", "game_status"),
]


def _captures():
    return O._read_jsonl(os.path.join(O.STORE, "captures.jsonl"))


def run(capture_id: str | None = None) -> dict:
    caps = _captures()
    if not caps:
        raise SystemExit("no captures in the store")
    cap = caps[-1] if capture_id is None else next(c for c in caps if c["capture_id"] == capture_id)
    with gzip.open(os.path.join(O.ROOT, cap["raw_path"]), "rb") as fh:
        raw = fh.read()
    if hashlib.sha256(raw).hexdigest() != cap["sha256"]:
        raise SystemExit("stored raw capture does not match its logged sha256")
    with open(os.path.join(O.ROOT, cap["rows_path"]), encoding="utf-8") as fh:
        official = list(csv.DictReader(fh))

    with open(PUBLISHED, encoding="utf-8") as fh:
        published = list(csv.DictReader(fh))

    off_index: dict = {}
    for r in official:
        off_index.setdefault((r["team"], r["player"]), []).append(r)
    pub_index: dict = {}
    for r in published:
        team = CODE_ALIASES.get(r["team"], r["team"])
        pub_index.setdefault((team, r["player"]), []).append(r)

    results = []
    counts: Counter = Counter()
    for key in sorted(set(off_index) | set(pub_index)):
        team, player = key
        o_list = off_index.get(key, [])
        p_list = pub_index.get(key, [])
        if len(o_list) != 1 or len(p_list) != 1:
            results.append({
                "team": team, "player": player,
                "status": "unmatched" if (not o_list or not p_list) else "ambiguous",
                "official_rows": len(o_list), "published_rows": len(p_list),
            })
            counts["unmatched_or_ambiguous_rows"] += 1
            continue
        o, p = o_list[0], p_list[0]
        cells = []
        for pub_field, off_field in FIELDS:
            pv = (p.get(pub_field) or "").strip()
            ov = (o.get(off_field) or "").strip()
            ok = pv == ov
            counts["comparisons"] += 1
            counts["matches" if ok else "mismatches"] += 1
            cells.append({
                "field": pub_field,
                "published": pv,
                "official": ov,
                "match": ok,
            })
        results.append({
            "team": team,
            "published_team_code": p["team"],
            "player": player,
            "status": "checked",
            "cells": cells,
            "official_url": o.get("player_url", ""),
        })

    counts["published_rows"] = len(published)
    counts["official_rows"] = len(official)
    passed = counts["mismatches"] == 0 and counts["unmatched_or_ambiguous_rows"] == 0 and len(published) == len(official)
    doc = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "official_source": O.URL,
        "capture_id": cap["capture_id"],
        "capture_fetched_at_utc": cap["fetched_at_utc"],
        "capture_method": cap.get("method", "live"),
        "capture_sha256": cap["sha256"],
        "published_file": "data/injuries/injuries_2026_week10.csv",
        "code_aliases": CODE_ALIASES,
        "summary": {
            "published_rows": counts["published_rows"],
            "official_rows": counts["official_rows"],
            "comparisons": counts["comparisons"],
            "matches": counts["matches"],
            "mismatches": counts["mismatches"],
            "unmatched_or_ambiguous_rows": counts["unmatched_or_ambiguous_rows"],
            "passed": passed,
        },
        "rows": results,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return doc


if __name__ == "__main__":
    doc = run(sys.argv[1] if len(sys.argv) > 1 else None)
    s = doc["summary"]
    print(f"capture {doc['capture_id']} ({doc['capture_method']}), sha256 {doc['capture_sha256'][:12]}")
    print(f"published rows {s['published_rows']}  official rows {s['official_rows']}")
    print(f"comparisons {s['comparisons']}  matches {s['matches']}  mismatches {s['mismatches']}  "
          f"unmatched/ambiguous rows {s['unmatched_or_ambiguous_rows']}")
    print("PASS" if s["passed"] else "FAIL")
    sys.exit(0 if s["passed"] else 1)
