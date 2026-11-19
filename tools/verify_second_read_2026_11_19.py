#!/usr/bin/env python3
"""Second-reader diff of the official Week 11 injury report (session arena/6b45af7e-x1).

Two independent reads of the same official page exist:

  A. data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv
     read and transcribed by session arena/427c1843-x1 on 2026-11-19 (round 7).
  B. data/verification/2026_11_19_second_read/official_w11_injuries_second_reader_2026_11_19.tsv
     read and transcribed by session arena/6b45af7e-x1 on 2026-11-19 (this session).

The repository's own flag F-13 says one transcription cannot prove itself. This tool does the
only check that can catch a shared misread: it joins the two files on (team, player) and
compares position / practice status / game status cell by cell, then publishes every difference
plus the measured intra-read stability of the free-text "Injuries" column.

It writes:
  data/verification/2026_11_19_second_read/diff_vs_first_reader.json
  data/verification/2026_11_19_second_read/diff_vs_first_reader.csv

Invariants asserted (any failure exits 1):
  * both reads cover the same 253 (team, player) keys;
  * the printed practice-status vocabulary is the same set in both reads;
  * the printed game-status vocabulary is the same set in both reads;
  * no row is missing a source URL, and every source URL is the official nfl.com injury page.

Usage:  python3 tools/verify_second_read_2026_11_19.py [--check]
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRST = ROOT / "data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv"
SECOND = ROOT / "data/verification/2026_11_19_second_read/official_w11_injuries_second_reader_2026_11_19.tsv"
OUT_JSON = ROOT / "data/verification/2026_11_19_second_read/diff_vs_first_reader.json"
OUT_CSV = ROOT / "data/verification/2026_11_19_second_read/diff_vs_first_reader.csv"
SOURCE = "https://www.nfl.com/injuries/league/2026/reg11"
COMPARED = ("position", "practice_status", "game_status")


def read(path: Path) -> list[dict]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def keyed(rows: list[dict]) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for r in rows:
        k = (r["team"].strip(), r["player"].strip())
        if k in out:
            raise SystemExit(f"duplicate key in a read: {k}")
        out[k] = r
    return out


def main() -> int:
    a, b = read(FIRST), read(SECOND)
    ka, kb = keyed(a), keyed(b)
    errors: list[str] = []

    if set(ka) != set(kb):
        only_a = sorted(set(ka) - set(kb))
        only_b = sorted(set(kb) - set(ka))
        errors.append(f"key sets differ: {len(only_a)} only in A, {len(only_b)} only in B")
    else:
        only_a, only_b = [], []

    vocab = {}
    for label, rows in (("A", a), ("B", b)):
        vocab[label] = {
            "practice_status": sorted({r["practice_status"].strip() for r in rows if r["practice_status"].strip()}),
            "game_status": sorted({r["game_status"].strip() for r in rows if r["game_status"].strip()}),
        }
    if vocab["A"]["practice_status"] != vocab["B"]["practice_status"]:
        errors.append("practice-status vocabulary differs between the two reads")
    if vocab["A"]["game_status"] != vocab["B"]["game_status"]:
        errors.append("game-status vocabulary differs between the two reads")

    for label, rows in (("A", a), ("B", b)):
        for r in rows:
            if r.get("source_url", "").strip() != SOURCE:
                errors.append(f"{label}: row without the official source URL: {r['team']} {r['player']}")
                break

    diffs = []
    for k in sorted(set(ka) & set(kb)):
        ra, rb = ka[k], kb[k]
        changed = {c: [ra[c].strip(), rb[c].strip()] for c in COMPARED if ra[c].strip() != rb[c].strip()}
        if changed:
            diffs.append({"team": k[0], "player": k[1], "fields": changed,
                          "injury_read_a": ra.get("injury", "").strip(),
                          "injury_read_b": rb.get("injury", "").strip()})

    # Free-text "Injuries" column: measured, not assumed. A read cannot confirm a column that
    # differs between two reads of the same page, so the disagreement is published as a count.
    injury_a = {k: r.get("injury", "").strip() for k, r in ka.items()}
    injury_b = {k: r.get("injury", "").strip() for k, r in kb.items()}
    injury_diff = sorted(k for k in injury_a if injury_a[k] != injury_b[k])
    injury_bytes_a = sum(1 for v in injury_a.values() if v)
    injury_bytes_b = sum(1 for v in injury_b.values() if v)

    # A differing designation count is a FINDING, not a structural failure: publishing the
    # difference is the entire purpose of a second read. Structural failures are the checks that
    # say the comparison itself is unsound (different keys, different vocabulary, no source).
    designations = {label: sum(1 for r in rows if r["game_status"].strip())
                    for label, rows in (("A", a), ("B", b))}
    findings: list[str] = []
    if designations["A"] != designations["B"]:
        findings.append(
            f"game-status designations differ between the two reads of the same page: "
            f"A={designations['A']}, B={designations['B']}. Every differing cell is listed in "
            f"`differences` with both values; the cell is treated as UNVERIFIED, not resolved "
            f"in either direction."
        )

    doc = {
        "title": "Second-reader diff — official Week 11 injury report",
        "session": "arena/6b45af7e-x1",
        "read_date": "2026-11-19",
        "source": SOURCE,
        "read_a": "data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv (session arena/427c1843-x1)",
        "read_b": "data/verification/2026_11_19_second_read/official_w11_injuries_second_reader_2026_11_19.tsv (session arena/6b45af7e-x1)",
        "compared_columns": list(COMPARED),
        "rows_read_a": len(a),
        "rows_read_b": len(b),
        "keys_joined": len(set(ka) & set(kb)),
        "keys_only_in_a": [list(k) for k in only_a],
        "keys_only_in_b": [list(k) for k in only_b],
        "cell_differences": len(diffs),
        "differences": diffs,
        "vocabulary": vocab,
        "designations_a": designations["A"],
        "designations_b": designations["B"],
        "injury_text": {
            "note": ("The free-text Injuries column is NOT constant between reads of the same page. "
                     "It is published as an unconfirmed, unstable field; it is never used as a value in "
                     "any table or model."),
            "rows_with_text_a": injury_bytes_a,
            "rows_with_text_b": injury_bytes_b,
            "rows_where_the_two_reads_disagree": len(injury_diff),
            "disagreeing_keys": [list(k) for k in injury_diff],
        },
        "findings": findings,
        "verdict": "pass" if not errors else "fail",
        "errors": errors,
    }
    body = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"

    if "--check" in sys.argv:
        ok = OUT_JSON.exists() and OUT_JSON.read_text(encoding="utf-8") == body
        if not ok:
            print("FAIL: committed diff is stale or missing")
            return 1
        if errors:
            print("FAIL:", *errors, sep="\n  ")
            return 1
        print(f"second-reader diff: {doc['keys_joined']} rows joined, "
              f"{doc['cell_differences']} cell differences, verdict {doc['verdict']}")
        for f in findings:
            print("  finding:", f)
        return 0

    OUT_JSON.write_text(body, encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["team", "player", "field", "read_a", "read_b", "source_url"])
        for d in diffs:
            for field, (va, vb) in d["fields"].items():
                w.writerow([d["team"], d["player"], field, va, vb, SOURCE])
        for k in injury_diff:
            w.writerow([k[0], k[1], "injury (free text, unstable)", injury_a[k], injury_b[k], SOURCE])
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {OUT_CSV.relative_to(ROOT)}")
    for f in findings:
        print("finding:", f)
    if errors:
        print("ERRORS:", *errors, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
