#!/usr/bin/env python3
"""D3 — independent re-verification of published tables against official pages, 2026-11-15.

What this does, and what it deliberately does not do:

  * It compares `data/nfl/standings.tsv` (the table the site publishes, captured 2026-11-14)
    against `data/verification/2026_11_15/official_standings_2026_11_15.tsv`, an independent
    transcription of https://www.nfl.com/standings/ read live on 2026-11-15.
  * It does not "fix" anything. A mismatch is a dated fact: the published table was true of the
    2026-11-14 page and is false of the 2026-11-15 page. The correct output is a flag with both
    values and both dates, which is what this writes.
  * It re-checks internal arithmetic on the official side (PCT = (W + T/2) / (W + L + T),
    NET PTS = PF - PA) so a transcription slip in either file is caught instead of published.

Exit 0 always when the comparison ran; the *finding* is the output, not the exit code.
Exit 2 if an input is missing. Exit 1 if the transcription itself fails its arithmetic check —
a broken transcription must never reach a page.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
PUBLISHED = os.path.join(D, "nfl", "standings.tsv")
OFFICIAL = os.path.join(D, "verification", "2026_11_15", "official_standings_2026_11_15.tsv")
OUT_DIR = os.path.join(D, "verification", "2026_11_15")
OUT_JSON = os.path.join(OUT_DIR, "standings_diff.json")
OUT_CSV = os.path.join(OUT_DIR, "standings_diff.csv")
SOURCE_URL = "https://www.nfl.com/standings/"

CHECK_COLS = ["w", "l", "t", "pct", "pf", "pa", "diff", "streak"]


def read_tsv(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            rows.append(line.rstrip("\n").split("\t"))
    hdr = rows[0]
    return [dict(zip(hdr, r)) for r in rows[1:]]


def fnum(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def arithmetic_checks(row):
    """Recompute PCT and NET PTS from the row's own W/L/T/PF/PA. Returns list of problems."""
    bad = []
    w, l, t = fnum(row.get("w")), fnum(row.get("l")), fnum(row.get("t"))
    pf, pa, diff = fnum(row.get("pf")), fnum(row.get("pa")), fnum(row.get("diff"))
    pct = row.get("pct")
    abbr = row.get("abbr")
    if None not in (w, l, t) and (w + l + t) > 0:
        want = round((w + 0.5 * t) / (w + l + t), 3)
        got = fnum(pct)
        if got is not None and abs(got - want) > 0.0006:
            bad.append(f"{abbr}: PCT {pct} != (W+T/2)/(W+L+T) = {want:.3f}")
    if None not in (pf, pa, diff) and abs((pf - pa) - diff) > 0.001:
        bad.append(f"{abbr}: NET PTS {diff} != PF-PA = {pf - pa:g}")
    return bad


def build():
    pub = read_tsv(PUBLISHED)
    off = read_tsv(OFFICIAL)
    if not pub or not off:
        raise SystemExit("one of the inputs is empty")

    pub_by = {r["abbr"]: r for r in pub}
    off_by = {r["abbr"]: r for r in off}

    transcription_problems = []
    for r in off:
        transcription_problems.extend(arithmetic_checks(r))

    rows = []
    mismatched_cells = 0
    for abbr in sorted(set(pub_by) | set(off_by)):
        p = pub_by.get(abbr)
        o = off_by.get(abbr)
        if p is None:
            rows.append({"abbr": abbr, "status": "only on the official page", "field": "",
                         "published": "", "official": "", "note": "club missing from the published table"})
            mismatched_cells += 1
            continue
        if o is None:
            rows.append({"abbr": abbr, "status": "only in the published table", "field": "",
                         "published": "", "official": "", "note": "club not on the official page"})
            mismatched_cells += 1
            continue
        for col in CHECK_COLS:
            pv = (p.get(col) or "").strip()
            ov = (o.get(col) or "").strip()
            if pv == "" and ov == "":
                continue
            if pv == ov:
                continue
            # numeric-tolerant compare so 0.750 vs 0.75 is not called a mismatch
            pn, on = fnum(pv), fnum(ov)
            if pn is not None and on is not None and abs(pn - on) < 1e-9:
                continue
            mismatched_cells += 1
            rows.append({
                "abbr": abbr,
                "status": "cell differs",
                "field": col,
                "published": pv,
                "official": ov,
                "note": "",
            })

    changed_clubs = sorted({r["abbr"] for r in rows if r["status"] == "cell differs"})
    clean_clubs = sorted(set(pub_by) & set(off_by) - set(changed_clubs))

    # what the change is, stated as arithmetic rather than as a narrative
    impact = {}
    for abbr in changed_clubs:
        p, o = pub_by[abbr], off_by[abbr]
        impact[abbr] = {
            "published_record": f"{p['w']}-{p['l']}-{p['t']}",
            "official_record": f"{o['w']}-{o['l']}-{o['t']}",
            "published_net_pts": p["diff"],
            "official_net_pts": o["diff"],
            "net_pts_delta": (fnum(o["diff"]) - fnum(p["diff"]))
            if fnum(o["diff"]) is not None and fnum(p["diff"]) is not None else None,
            "fields": sorted({r["field"] for r in rows if r["abbr"] == abbr}),
        }

    doc = {
        "dataset": "standings_diff_2026_11_15",
        "title": "Published 2026-11-14 standings vs the official nfl.com page as it reads on 2026-11-15",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "tools/verify_2026_11_15.py (session arena-73e6cbac-x1)",
        "source": {"url": SOURCE_URL, "org": "NFL.com", "tier": "official"},
        "published_file": "data/nfl/standings.tsv",
        "official_file": "data/verification/2026_11_15/official_standings_2026_11_15.tsv",
        "compare_columns": CHECK_COLS,
        "counts": {
            "clubs_published": len(pub_by),
            "clubs_on_official_page": len(off_by),
            "clubs_with_a_differing_cell": len(changed_clubs),
            "clubs_identical": len(clean_clubs),
            "cells_compared": len(pub_by) * len(CHECK_COLS),
            "cells_that_differ": mismatched_cells,
        },
        "transcription_arithmetic_problems": transcription_problems,
        "changed_clubs": impact,
        "unchanged_clubs": clean_clubs,
        "why_this_is_not_silently_fixed": (
            "The published table is a dated artefact of the 2026-11-14 page and is cited as such "
            "throughout the site. Rewriting it would destroy the record of what was known before "
            "kickoff, which the owner's point-in-time requirement depends on. The diff is published "
            "instead, and the stale cells are flagged."
        ),
        "rows": rows,
    }
    return doc


def write(doc):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["abbr", "status", "field", "published", "official", "note"],
                           lineterminator="\n")
        w.writeheader()
        for r in doc["rows"]:
            w.writerow(r)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if not os.path.exists(PUBLISHED) or not os.path.exists(OFFICIAL):
        print("INPUT MISSING")
        return 2
    doc = build()
    if doc["transcription_arithmetic_problems"]:
        print("TRANSCRIPTION FAILED ITS OWN ARITHMETIC — refusing to publish a diff from it:")
        for p in doc["transcription_arithmetic_problems"]:
            print("  -", p)
        return 1
    if args.check:
        if not os.path.exists(OUT_JSON):
            print("CHECK FAILED: no committed diff")
            return 1
        with open(OUT_JSON, encoding="utf-8") as fh:
            com = json.load(fh)
        a = {k: v for k, v in com.items() if k != "generated_at"}
        b = {k: v for k, v in doc.items() if k != "generated_at"}
        if a != b:
            print("CHECK FAILED: committed standings diff is stale")
            return 1
        print("CHECK OK: standings diff matches")
        return 0
    write(doc)
    c = doc["counts"]
    print(f"standings diff: {c['clubs_with_a_differing_cell']} of {c['clubs_published']} clubs "
          f"differ on the 2026-11-15 page ({c['cells_that_differ']} of {c['cells_compared']} cells)")
    for abbr, imp in doc["changed_clubs"].items():
        print(f"  {abbr}: {imp['published_record']} -> {imp['official_record']}   "
              f"net pts {imp['published_net_pts']} -> {imp['official_net_pts']} "
              f"fields {','.join(imp['fields'])}")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
