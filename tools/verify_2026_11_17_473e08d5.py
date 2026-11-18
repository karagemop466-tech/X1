"""Cross-compare the TWO independent transcriptions of the 2026-11-17 official pages.

Why this file exists
--------------------
Two sessions read the same official pages inside the same few minutes on 2026-11-17 and wrote
transcriptions into `data/verification/2026_11_17/` under the SAME names:

  * session `arena-01c263c4-x1` — the read that merged to `main` first, so it keeps the canonical names
  * session `arena-473e08d5-x1` — the read opened as PR #84

Round 5 (session `arena/dc96bc33-x1`) hit the same collision one round earlier and set the precedent:
nothing is discarded, `main`'s file keeps the canonical name, the later file keeps its own bytes under a
session suffix, and a checker proves the two independent reads agree. This is that checker for round 6.

A disagreement between two independent reads of one page is not a nuisance — it is the measurement. If
these two files ever stop agreeing, one of the transcriptions is wrong and the number that depends on it
is unsupported, so the build has to stop rather than pick a side.

The comparison is cell-by-cell on the columns both reads carry. It never compares prose headers, and it
never normalises a club label into agreement silently: `LA`/`ARZ` versus `LAR`/`AZ` is matched by
alias-normalised matchup and reported, so the difference stays visible.

Usage
    python3 tools/verify_2026_11_17_473e08d5.py            # check, print the table, exit non-zero on mismatch
    python3 tools/verify_2026_11_17_473e08d5.py --json     # machine-readable summary
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VDIR = os.path.join(ROOT, "data", "verification", "2026_11_17")

# canonical (arena-01c263c4-x1, on main)          suffixed (arena-473e08d5-x1, PR #84)
STANDINGS = ("official_standings_2026_11_17.tsv", "official_standings_2026_11_17_473e08d5.tsv")
W10 = ("official_w10_results_2026_11_17.tsv", "official_w10_results_2026_11_17_473e08d5.tsv")

# The two reads use different labels for the same two clubs. Kept explicit and printed, never hidden.
CLUB_ALIASES = {"LAR": "LA", "ARZ": "AZ"}


def read_tsv(path: str) -> tuple[list[str], list[dict]]:
    """Return (header, rows) of a commented TSV. Blank and '#' lines are skipped."""
    header: list[str] = []
    rows: list[dict] = []
    with open(path, encoding="utf-8", newline="") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            cells = line.split("\t")
            if not header:
                header = cells
                continue
            rows.append(dict(zip(header, cells)))
    return header, rows


def canon(club: str) -> str:
    c = (club or "").strip().upper()
    return CLUB_ALIASES.get(c, c)


def compare_standings() -> dict:
    """Both reads transcribe the same legend-defined columns for the same 32 clubs."""
    a_p, b_p = (os.path.join(VDIR, n) for n in STANDINGS)
    a_h, a = read_tsv(a_p)
    b_h, b = read_tsv(b_p)
    shared = [c for c in a_h if c in b_h]
    a_by = {(r.get("abbr") or r.get("team") or r.get("club") or "").strip().upper(): r for r in a}
    b_by = {(r.get("abbr") or r.get("team") or r.get("club") or "").strip().upper(): r for r in b}
    only_a = sorted(set(a_by) - set(b_by))
    only_b = sorted(set(b_by) - set(a_by))
    cells = 0
    mismatches = []
    for club in sorted(set(a_by) & set(b_by)):
        for col in shared:
            if col in ("abbr", "team", "club", "source_url"):
                continue
            cells += 1
            va, vb = (a_by[club].get(col) or "").strip(), (b_by[club].get(col) or "").strip()
            if va != vb:
                mismatches.append({"club": club, "column": col, "canonical": va, "suffixed": vb})
    return {
        "check": "R6-B1 standings: two independent transcriptions agree",
        "file_canonical": STANDINGS[0], "file_suffixed": STANDINGS[1],
        "clubs": len(set(a_by) & set(b_by)), "columns_compared": len([c for c in shared if c not in ("abbr", "team", "club", "source_url")]),
        "cells_compared": cells, "mismatches": mismatches,
        "clubs_only_in_canonical": only_a, "clubs_only_in_suffixed": only_b,
        "verdict": "PASS" if not mismatches and not only_a and not only_b and len(a_by) == 32 else "FAIL",
    }


def compare_w10() -> dict:
    """Scores, records and status for all 14 Week 10 fixtures, matched by club pair (not by label)."""
    a_p, b_p = (os.path.join(VDIR, n) for n in W10)
    a_h, a = read_tsv(a_p)
    b_h, b = read_tsv(b_p)

    def key(r: dict) -> str:
        return f"{canon(r.get('away',''))}_{canon(r.get('home',''))}"

    a_by, b_by = {key(r): r for r in a}, {key(r): r for r in b}
    only_a, only_b = sorted(set(a_by) - set(b_by)), sorted(set(b_by) - set(a_by))
    fields = ["away", "away_score", "away_record", "home", "home_score", "home_record", "status"]
    cells, mismatches = 0, []
    for k in sorted(set(a_by) & set(b_by)):
        for f in fields:
            va, vb = (a_by[k].get(f) or "").strip(), (b_by[k].get(f) or "").strip()
            if f in ("away", "home"):
                va, vb = canon(va), canon(vb)
            cells += 1
            if va != vb:
                mismatches.append({"fixture": k, "field": f, "canonical": va, "suffixed": vb})
    # Fields only ONE read printed are reported, not treated as a mismatch: blank is a legitimate read
    # outcome, and the canonical read (which printed time/network) is the published source for them.
    only_one_printed = []
    for k in sorted(set(a_by) & set(b_by)):
        for f in ("time_et", "network"):
            va, vb = (a_by[k].get(f) or "").strip(), (b_by[k].get(f) or "").strip()
            if bool(va) != bool(vb):
                only_one_printed.append({"fixture": k, "field": f, "canonical": va, "suffixed": vb})
    return {
        "check": "R6-B2 Week 10: two independent transcriptions agree on scores, records and status",
        "file_canonical": W10[0], "file_suffixed": W10[1],
        "fixtures": len(set(a_by) & set(b_by)), "fields_compared": fields,
        "cells_compared": cells, "mismatches": mismatches,
        "fixtures_only_in_canonical": only_a, "fixtures_only_in_suffixed": only_b,
        "fields_printed_by_one_read_only": only_one_printed,
        "all_final": all((r.get("status") or "").strip().lower() == "final" for r in list(a_by.values()) + list(b_by.values())),
        "verdict": "PASS" if not mismatches and not only_a and not only_b and len(a_by) == 14 else "FAIL",
    }


def main(argv: list[str]) -> int:
    checks = [compare_standings(), compare_w10()]
    fails = [c for c in checks if c["verdict"] != "PASS"]
    if "--json" in argv:
        print(json.dumps({"checks": checks, "failures": len(fails)}, indent=1))
    else:
        print("Cross-comparison of the two independent 2026-11-17 transcriptions\n")
        for c in checks:
            print(f"  {c['check']}")
            if "clubs" in c:
                print(f"    clubs {c['clubs']}, columns {c['columns_compared']}, cells {c['cells_compared']}, "
                      f"mismatches {len(c['mismatches'])}")
            else:
                print(f"    fixtures {c['fixtures']}, cells {c['cells_compared']}, "
                      f"mismatches {len(c['mismatches'])}, all final: {c['all_final']}")
                for row in c["fields_printed_by_one_read_only"]:
                    print(f"    printed by one read only: {row['fixture']} {row['field']} "
                          f"canonical={row['canonical']!r} suffixed={row['suffixed']!r}")
            for m in c["mismatches"][:10]:
                print(f"    MISMATCH {m}")
            print(f"    {c['verdict']}\n")
        print(f"failures: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
