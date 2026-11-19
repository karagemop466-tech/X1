#!/usr/bin/env python3
"""Three reads of the same official page, side by side — the unstable cell, pinned.

Session arena/6b45af7e-x1, 2026-11-19.

Two independent reads of https://www.nfl.com/injuries/league/2026/reg11 left exactly one disputed
cell (IND Charlie Heck, game status: "Questionable" in read A, blank in read B) and a free-text
Injuries column that disagreed between them. This tool adds a THIRD read of that club block, taken
later the same day, and reports what all three say.

The point is not to break the tie. It is to show, with three dated reads of one printed cell, that
the value is not stable between reads — which is why the repository publishes it as unconfirmed
rather than picking the majority.

Inputs
  A  data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv          (session arena/427c1843-x1)
  B  data/verification/2026_11_19_second_read/official_w11_injuries_second_reader_2026_11_19.tsv
  C  data/verification/2026_11_19_second_read/third_read_ind_hou_2026_11_19.tsv   (this read)

Output data/verification/2026_11_19_second_read/three_reads_ind_hou_2026_11_19.json
`--check` fails if the committed JSON is stale, or if any read is missing a source URL.

Usage: python3 tools/build_third_read_2026_11_19.py [--check]
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv"
B = ROOT / "data/verification/2026_11_19_second_read/official_w11_injuries_second_reader_2026_11_19.tsv"
C = ROOT / "data/verification/2026_11_19_second_read/third_read_ind_hou_2026_11_19.tsv"
OUT = ROOT / "data/verification/2026_11_19_second_read/three_reads_ind_hou_2026_11_19.json"
SOURCE = "https://www.nfl.com/injuries/league/2026/reg11"
CLUBS = ("IND", "HOU")


def read(path: Path) -> dict[tuple[str, str], dict]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    rows = list(csv.DictReader(lines, delimiter="\t"))
    return {(r["team"], r["player"]): r for r in rows}


def main() -> int:
    a, b, c = read(A), read(B), read(C)
    errors = []
    for label, rows in (("A", a), ("B", b), ("C", c)):
        missing = [k for k, r in rows.items() if not (r.get("source_url") or "").strip()]
        if missing:
            errors.append(f"read {label}: {len(missing)} rows without a source URL")
    keys = [k for k in c if k[0] in CLUBS]
    if len(keys) != len(c):
        errors.append("the third read contains rows for clubs outside IND/HOU")
    absent = [k for k in keys if k not in a or k not in b]
    if absent:
        errors.append(f"{len(absent)} rows of the third read do not exist in read A or read B")

    rows_out = []
    for k in sorted(keys):
        entry = {"team": k[0], "player": k[1], "read_a": {}, "read_b": {}, "read_c": {},
                 "fields_that_disagree_across_the_three": []}
        for label, src in (("read_a", a), ("read_b", b), ("read_c", c)):
            r = src.get(k, {})
            entry[label] = {f: (r.get(f) or "").strip()
                            for f in ("position", "injury", "practice_status", "game_status")}
        for f in ("position", "practice_status", "game_status"):
            vals = {entry[x][f] for x in ("read_a", "read_b", "read_c")}
            if len(vals) > 1:
                entry["fields_that_disagree_across_the_three"].append(f)
        rows_out.append(entry)

    unstable = [e for e in rows_out if e["fields_that_disagree_across_the_three"]]
    text_vals = {}
    for e in rows_out:
        vals = {e[x]["injury"] for x in ("read_a", "read_b", "read_c")}
        if len(vals) > 1:
            text_vals[f"{e['team']} {e['player']}"] = sorted(vals)

    doc = {
        "title": "Three reads of the same official page: the disputed Week 11 cell",
        "session": "arena/6b45af7e-x1",
        "read_date": "2026-11-19",
        "source": SOURCE,
        "reads": {
            "A": "data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv (session arena/427c1843-x1)",
            "B": "data/verification/2026_11_19_second_read/official_w11_injuries_second_reader_2026_11_19.tsv (this session)",
            "C": "data/verification/2026_11_19_second_read/third_read_ind_hou_2026_11_19.tsv (this session, later)",
        },
        "rows_compared": len(rows_out),
        "clubs": list(CLUBS),
        "rows_where_a_printed_status_field_disagrees_across_the_three": len(unstable),
        "unstable_rows": unstable,
        "free_text_injury_strings_that_differ_between_reads": text_vals,
        "conclusion": ("The printed status fields are stable across three reads for "
                       f"{len(rows_out) - len(unstable)} of {len(rows_out)} rows. Where they are not stable, "
                       "the cell is published as UNCONFIRMED. The free-text Injuries column changes between "
                       "reads for the players listed, so it is never used as a value."),
        "errors": errors,
        "verdict": "pass" if not errors else "fail",
    }
    body = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"

    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != body:
            print("FAIL: committed three-read JSON is stale or missing")
            return 1
        if errors:
            print("FAIL:", *errors, sep="\n  ")
            return 1
        print(f"three reads: {doc['rows_compared']} rows, "
              f"{doc['rows_where_a_printed_status_field_disagrees_across_the_three']} unstable, "
              f"{len(doc['free_text_injury_strings_that_differ_between_reads'])} unstable free-text strings")
        return 0

    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"{doc['rows_compared']} rows; {doc['rows_where_a_printed_status_field_disagrees_across_the_three']} "
          f"unstable status fields; {len(doc['free_text_injury_strings_that_differ_between_reads'])} "
          f"unstable free-text strings")
    for e in unstable:
        print("  unstable:", e["team"], e["player"], e["fields_that_disagree_across_the_three"],
              "| A:", e["read_a"], "| B:", e["read_b"], "| C:", e["read_c"])
    if errors:
        print("ERRORS:", *errors, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
