#!/usr/bin/env python3
"""Regression test for data/parlay_results.csv (added by arena/b38a21d8-x1).

Found on integration: 14 of 45 rows pair a strategy with its own mirror or a subset of
itself. Those correlations are tautologies, not measurements:

    A and complement(A)  -> phi = -1.00 by construction, p_both = 0 exactly
    B subset of A        -> phi = +1.00 by construction, p_both = p_B exactly

The file already marks them `redundant_mirror_or_nested=True`, but the derived parlay ROI
columns are still computed and read like results. One row reports parlay_roi_observed =
+0.836, i.e. an 83.6% return, which is a tautology (both legs are the same event family).

This script fails if a genuinely independent pair violates the Frechet bounds
[max(0,pa+pb-1), min(pa,pb)], or if a pair flagged `redundant_mirror_or_nested` turns
out to be statistically independent (which would make the flag itself wrong).

Note on scope, learned by getting it wrong: the flag covers *near*-nested pairs too
(e.g. an Elo-edge subset of all favourites lands at phi = 0.99, not 1.00). Requiring an
exact +/-1 tautology produced three false failures on correct data. The test therefore
checks the direction of the flag, not an exact identity.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "parlay_results.csv"
TOL = 1e-6

if not PATH.exists():
    print(f"{PATH.name} not present — nothing to check")
    sys.exit(0)

rows = list(csv.DictReader(PATH.open(encoding="utf-8")))
errors, tautologies, independent = [], 0, 0

for i, r in enumerate(rows, start=2):
    pa, pb = float(r["p_leg_a"]), float(r["p_leg_b"])
    pab = float(r["p_both_observed"])
    phi = float(r["phi"])
    nested = r["redundant_mirror_or_nested"].strip().lower() == "true"

    lo, hi = max(0.0, pa + pb - 1.0), min(pa, pb)
    if not (lo - TOL <= pab <= hi + TOL):
        errors.append(f"row {i}: p_both={pab} outside Frechet bounds [{lo:.4f},{hi:.4f}]")

    if nested:
        tautologies += 1
        # the flag means "these legs are not independent". If the data says they ARE
        # independent (p_both == p_a*p_b), the flag is wrong and must fail.
        if abs(pab - pa * pb) <= TOL:
            errors.append(f"row {i}: flagged nested but p_both == p_a*p_b (legs look independent)")
        # and a nested pair must be strongly dependent: |phi| must be high
        if abs(phi) < 0.85:
            errors.append(f"row {i}: flagged nested but |phi|={abs(phi):.3f} is weak")
    else:
        independent += 1

print(f"parlay rows        : {len(rows)}")
print(f"tautological pairs : {tautologies} (phi = +/-1 by construction — not correlations)")
print(f"independent pairs  : {independent}")

if errors:
    print("\nFAILURES:")
    for e in errors:
        print("  FAIL ", e)
    sys.exit(1)
print("all rows satisfy the Frechet bounds; every flagged-nested pair is strongly dependent")
