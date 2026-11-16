#!/usr/bin/env python3
"""Regenerate every published artefact that a data refresh can move, then prove it is consistent.

Why this exists
---------------
`verify.yml` guards staleness by *rebuilding and diffing*: "Fail if committed HTML is stale", "Fail if
the audit registers are stale", "Fail if the re-capture, depth parse or readiness files are stale". That
rule is right, and it is also why the scheduled collector could never push: it writes
`data/pipeline/*.json`, and eleven other artefacts are derived from those files. Pushing the data alone
would turn `main` red on the next build, which is a worse failure than pushing nothing — so the old step
pushed nothing, silently, and the site's "daily capture" claim quietly became false.

This script is the missing half of the refresh: derive, then verify, then commit as one unit. It is a
list, not a framework, because the list IS the contract — it mirrors the steps in `verify.yml`, and if a
new guarded artefact is added there, it has to appear here too (the `MIRROR` note records the last
reconciliation).

    python3 tools/rebuild_for_refresh.py            # rebuild + verify; exit 1 if the set is not safe
    python3 tools/rebuild_for_refresh.py --rebuild  # rebuild only (what the refresh job commits)
    python3 tools/rebuild_for_refresh.py --verify   # verify only
    python3 tools/rebuild_for_refresh.py --paths    # print the paths a refresh may legitimately change

A failing builder is reported and makes the exit code nonzero; the refresh job then retains the captures
(evidence) and withholds the derived analysis (which would be inconsistent), instead of publishing half.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Reconciliation of the derived set, per `.github/workflows/verify.yml` on 2026-11-16.
REBUILD = [
    ["python3", "tools/build_availability.py"],
    ["python3", "tools/official/week10_reconcile.py"],
    ["python3", "tools/official/depth_parse.py"],
    ["python3", "tools/official/readiness.py"],
    ["python3", "tools/build_audit_registers.py"],
    ["python3", "tools/build_state_audit.py"],
    ["python3", "tools/build_decision_readiness.py"],
    ["python3", "tools/build_app.py"],
    ["python3", "tools/build_console.py"],
    ["python3", "tools/lab/build_site.py"],
    ["python3", "tools/build_site.py"],
]

VERIFY = [
    ["python3", "tools/verify_data.py"],
    ["python3", "tools/verify_app.py"],
    ["python3", "tools/verify_console.py"],
    ["python3", "tools/official/verify_published.py"],
    ["python3", "tools/verify_against_official.py"],
    ["python3", "tools/cross_check.py"],
    ["python3", "tools/build_state_audit.py", "--check"],
    ["python3", "tools/build_decision_readiness.py", "--check"],
    ["python3", "tools/build_results_r3.py", "--check"],
    ["python3", "tools/build_snapshots.py", "--check"],
    ["python3", "tools/build_origination.py", "--check"],
    ["python3", "tools/build_round3.py", "--check"],
    ["python3", "tools/check_links.py"],
    ["python3", "scripts/verify_site.py"],
    ["python3", "scripts/pipeline/verify_site.py"],
    ["python3", "scripts/pipeline/verify_captures.py", "--no-freshness"],
]

# Everything the builders above are allowed to write. Deliberately explicit, and deliberately not `.`:
# a refresh must never be able to commit `COORDINATION.md`, a workflow or a source file by accident.
PATHS = [
    "data/pipeline", "data/captures", "data/nfl/availability_derived.tsv", "data/audit",
    "data/console/week10_reconcile.json", "data/console/week10_reconcile.csv",
    "data/console/depth_parse.json", "data/console/depth_parse.csv",
    "data/console/readiness.json", "data/console/readiness.csv",
    "data/console/repo_inventory.csv",
    "data/readiness", "data/verification", "app", "lab", "pages", "index.html",
]

# Deliberately NOT committed by a refresh, although they are rebuilt and verified:
#   data/console/payload.json       "as_of"  = the build clock
#   data/console/price_snapshots.csv 37,804 rows whose captured_at_utc column IS the build clock
#   console/, hub/                  their builders stamp an "As of" line into every page
# A daily job that committed those would add ~40k lines of pure clock per run to the repository history
# and would look like a data change to anyone diffing it. They stay accurate where it matters:
# pages.yml rebuilds the console and the hub from the committed data at deploy time, so what is
# published is generated from what is committed, and the guard in verify.yml only diffs the six
# deterministic files listed above.
NOT_COMMITTED = [
    "data/console/payload.json", "data/console/price_snapshots.csv",
    "console/*.html", "hub/*.html",
]


def run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    tail = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()][-3:]
    for ln in tail:
        print("   ", ln[:200])
    return proc.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--paths", action="store_true")
    ap.add_argument("--explain", action="store_true", help="show what a refresh commits and what it refuses to")
    args = ap.parse_args(argv)
    if args.explain:
        for pth in PATHS:
            print(f"commit  {pth}")
        for pth in NOT_COMMITTED:
            print(f"skip    {pth}")
        return 0
    if args.paths:
        print("\n".join(PATHS))
        return 0
    bad = 0
    if not args.verify:
        for cmd in REBUILD:
            bad += run(cmd) != 0
    if not args.rebuild:
        for cmd in VERIFY:
            bad += run(cmd) != 0
    print(f"rebuild_for_refresh: {'FAIL' if bad else 'ok'} ({bad} step(s) failed)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
