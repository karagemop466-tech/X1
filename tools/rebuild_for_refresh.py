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
    # The results/price/leaderboard stores. CI gates these for staleness
    # (`git diff --exit-code -- data/results_feed.json data/price_snapshots.json
    # data/leaderboard_split_907c.json app`), and the first version of this list verified them
    # without rebuilding them, so `--check` correctly failed: a refresh moved their inputs and left
    # the committed artefacts behind. Read `PAIRS` below for why the two lists are no longer separate.
    ["python3", "tools/build_results_feed_907c.py"],
    ["python3", "tools/build_price_store_907c.py"],
    ["python3", "tools/build_leaderboard_split.py"],
    ["python3", "tools/build_results_r3.py"],
    ["python3", "tools/build_snapshots.py"],
    ["python3", "tools/build_origination.py"],
    ["python3", "tools/build_round3.py"],
    ["python3", "tools/lab/build_controls.py"],
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

# Any `--check` builder whose output this job commits must FIRST be run without `--check`, or the
# check compares a stale committed artefact against new inputs and fails for a reason the job cannot
# fix. Rather than maintain that rule by hand, `pairs()` derives the rebuild set from the verify set:
# every `X --check` in VERIFY is executed as `X` then `X --check`. This exists because the first
# version of this file listed `build_round3.py --check` in VERIFY and not `build_round3.py` in
# REBUILD, and CI correctly reported the register as stale on a run whose inputs had just moved.
# One artefact is checked but never rebuilt by a refresh: data/shadow/forecasts_pre_kickoff.csv is a
# pre-kickoff record whose entire value is that nobody regenerates it. The builder refuses to overwrite
# it when the numbers would change, and a daily job must not be able to touch that.
#
# The pre-registration register is the opposite case and is deliberately rebuilt here: it is a function
# of the repository's commit history, so a rebase or a squash legitimately moves its anchors. It failed
# CI for exactly that reason once it was excluded (the committed register still named the pre-rebase
# commit), and pinning it against a rebuild would have meant pinning it against the truth.
NEVER_REBUILD = {"tools/build_shadow_baseline.py"}


# A `X --check` command compares the artefact in the working tree against what a fresh build produces,
# and several of them read the comparison base from git (build_round3.py --check diffs the COMMITTED
# register). Inside the refresh job that is unfalsifiable by construction: the job has every right to
# change the register, so the check reports STALE, the gate withholds the artefacts, and the new data
# never lands - which is how a green-looking collector ends up publishing nothing again. So the checks
# are split: content verifiers run before the commit, and the HEAD-comparing `--check` set runs AFTER it,
# where HEAD is the commit that was just made and the comparison finally means "the thing we published
# reproduces from the thing we published it from".
def is_post_commit(cmd: list[str]) -> bool:
    return "--check" in cmd


def pairs(verify: list[list[str]]) -> tuple[list[list[str]], list[list[str]]]:
    rebuild, check = list(REBUILD), []
    for cmd in verify:
        if "--check" in cmd:
            build = [c for c in cmd if c != "--check"]
            if build[-1] in NEVER_REBUILD:
                continue
            if build not in rebuild:
                rebuild.append(build)
            check.append(cmd)
        elif cmd not in check:
            check.append(cmd)
    return rebuild, check


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
    ["python3", "tools/build_preregistration.py", "--check"],
    ["python3", "tools/build_shadow_baseline.py", "--check"],
    ["python3", "tools/build_next_decisions.py", "--check"],
]

# What the builders are allowed to write, kept as documentation and as `--explain` output. The workflow
# does NOT stage from this list - it stages the `data app lab pages index.html` allowlist prefix, because
# an enumeration that must be kept in sync with 20 builders silently under-commits (it did: build_round3's
# three registers were rebuilt, not staged, and the post-commit reproducibility check failed on a commit
# that was in fact incomplete). Deliberately not `.`:
# a refresh must never be able to commit `COORDINATION.md`, a workflow or a source file by accident.
PATHS = [
    "data/pipeline", "data/captures", "data/nfl/availability_derived.tsv", "data/audit",
    "data/console/week10_reconcile.json", "data/console/week10_reconcile.csv",
    "data/console/depth_parse.json", "data/console/depth_parse.csv",
    "data/console/readiness.json", "data/console/readiness.csv",
    "data/console/repo_inventory.csv",
    "data/readiness", "data/verification", "data/shadow", "data/preregistration", "data/next_decisions",
    "data/results_feed.json", "data/price_snapshots.json", "data/leaderboard_split_907c.json",
    "data/results/verified_results_2026_n2.csv", "data/results/results_feed.json",
    "data/results/results_verification.json", "data/results/verification_report.json",
    "data/results/verified_results_2026.csv",
    "app", "lab", "pages", "index.html",
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
    ap.add_argument("--pairs", action="store_true", help="print the derived rebuild/verify plan and exit")
    ap.add_argument("--pre-commit", action="store_true",
                    help="rebuild everything, then run only the checks that do not compare against HEAD")
    ap.add_argument("--post-commit", action="store_true",
                    help="run the HEAD-comparing checks, after the commit that moved HEAD")
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
    rebuild, check = pairs(VERIFY)
    if args.post_commit:
        bad = 0
        for cmd in check:
            if is_post_commit(cmd):
                bad += run(cmd) != 0
        print(f"rebuild_for_refresh --post-commit: {'FAIL' if bad else 'ok'} "
              f"({bad} check(s) failed against the new commit)")
        return 1 if bad else 0
    if args.pre_commit:
        bad = 0
        for cmd in rebuild:
            bad += run(cmd) != 0
        for cmd in check:
            if not is_post_commit(cmd):
                bad += run(cmd) != 0
        print(f"rebuild_for_refresh --pre-commit: {'FAIL' if bad else 'ok'} ({bad} step(s) failed)")
        return 1 if bad else 0
    if args.pairs:
        for cmd in rebuild:
            print("rebuild " + " ".join(cmd))
        for cmd in check:
            print("verify  " + " ".join(cmd))
        return 0
    bad = 0
    if not args.verify:
        for cmd in rebuild:
            bad += run(cmd) != 0
    if not args.rebuild:
        for cmd in check:
            bad += run(cmd) != 0
    print(f"rebuild_for_refresh: {'FAIL' if bad else 'ok'} ({bad} step(s) failed)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
