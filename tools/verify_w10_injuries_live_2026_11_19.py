#!/usr/bin/env python3
"""Line-by-line re-read of the PUBLISHED Week 10 injury table against the live official page.

Session arena/6b45af7e-x1, 2026-11-19.

The published table is data/nfl/injuries_week10.tsv — a 2026-11-15 snapshot of 347 rows, which is what
the site has shown since. This session re-read the live page
(https://www.nfl.com/injuries/league/2026/reg10) into
data/integration/live_w10_injuries_recheck_2026_11_19.tsv and joins the two on (club, player).

Three states are reported per published row, and they are not the same thing:

  agree                     every printed cell matches the live page
  differ                    a printed cell disagrees (listed field by field, both values, source URL)
  not_covered               the club's block sits in a chunk this read did not fetch
  not_reached_within_chunk  the club is covered but the row falls past the chunk boundary

`differ` is published as a finding. `not_covered` and `not_reached_within_chunk` are coverage limits
and are counted separately, never folded into agreement. The tool exits 0 when the comparison is sound;
a stale committed JSON fails `--check`.

Usage: python3 tools/verify_w10_injuries_live_2026_11_19.py [--check]
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED = ROOT / "data/nfl/injuries_week10.tsv"
LIVE = ROOT / "data/integration/live_w10_injuries_recheck_2026_11_19.tsv"
OUT = ROOT / "data/integration/live_w10_injuries_recheck_2026_11_19.json"
SOURCE = "https://www.nfl.com/injuries/league/2026/reg10"
FIELDS = ("position", "injury", "practice_status", "game_status")


def read(path: Path) -> list[dict]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def main() -> int:
    pub = read(PUBLISHED)
    live = read(LIVE)
    live_by = {(r["club"], r["player"]): r for r in live}
    if len(live_by) != len(live):
        print("FAIL: duplicate (club, player) key in the live read")
        return 1

    covered_clubs = sorted({r["club"] for r in live})
    agree, differ, not_covered, not_reached = [], [], [], []
    for r in pub:
        k = (r["team"], r["player"])
        if r["team"] not in covered_clubs:
            not_covered.append({"club": r["team"], "player": r["player"]})
            continue
        lr = live_by.get(k)
        if lr is None:
            not_reached.append({"club": r["team"], "player": r["player"]})
            continue
        changed = {f: [r.get(f, "").strip(), lr.get(f, "").strip()]
                   for f in FIELDS if r.get(f, "").strip() != lr.get(f, "").strip()}
        if changed:
            differ.append({"club": k[0], "player": k[1], "fields": changed})
        else:
            agree.append({"club": k[0], "player": k[1]})

    live_not_published = [{"club": r["club"], "player": r["player"]}
                          for r in live if (r["club"], r["player"]) not in {(p["team"], p["player"]) for p in pub}]

    doc = {
        "title": "Week 10 injury table: published rows re-read against the live official page",
        "session": "arena/6b45af7e-x1",
        "read_at": "2026-11-19 (UTC), page-fetch tool, chunks 0-2 of 8",
        "source": SOURCE,
        "published_table": "data/nfl/injuries_week10.tsv (2026-11-15 snapshot)",
        "live_read": "data/integration/live_w10_injuries_recheck_2026_11_19.tsv",
        "published_rows": len(pub),
        "clubs_published": len({r["team"] for r in pub}),
        "live_rows": len(live),
        "clubs_covered": covered_clubs,
        "agree": len(agree),
        "differ": len(differ),
        "not_covered": len(not_covered),
        "not_reached_within_chunk": len(not_reached),
        "live_rows_not_in_published_table": live_not_published,
        "differences": differ,
        "coverage_note": ("Only the club blocks inside chunks 0-2 were read (10 clubs, 115 rows). "
                          "Every other published row is counted as not covered, not as agreement. "
                          "The published table itself is a dated 2026-11-15 snapshot and was NOT edited "
                          "by this session."),
        "verdict": "pass",
    }
    body = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"

    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != body:
            print("FAIL: committed JSON is stale or missing")
            return 1
        print(f"week-10 re-read: {doc['agree']} agree, {doc['differ']} differ, "
              f"{doc['not_covered']} not covered, {doc['not_reached_within_chunk']} past the chunk boundary")
        return 0

    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"published {doc['published_rows']} rows / {doc['clubs_published']} clubs; "
          f"live read {doc['live_rows']} rows / {len(covered_clubs)} clubs")
    print(f"agree {doc['agree']} · differ {doc['differ']} · not covered {doc['not_covered']} · "
          f"not reached {doc['not_reached_within_chunk']}")
    for d in differ:
        print("  differ:", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
