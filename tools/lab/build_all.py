#!/usr/bin/env python3
"""Rebuild every lab artefact in dependency order.

    python3 tools/lab/build_all.py           # ~4 minutes (tunes the model)
    python3 tools/lab/build_all.py --fast    # reuses the frozen model parameters

Order matters: the 2026-11-17 reads pack is verified first (build_reads.py), the feed-closure
measurement and the PR-04 escrow are built next, then prices -> results -> lines -> strategies
-> correlation -> deficiency -> questions -> summary.  Each step reads only the artefacts the
steps before it wrote, so a failure upstream is visible as a downstream file that refuses to
build rather than a page that silently shows stale numbers.

No step here writes to data/results, data/shadow, data/preregistration or data/verification:
the reads, escrow and closure artefacts live under data/lab and are the only outputs.

One warning about --fast, learned the hard way on 2026-11-17: it reuses the parameters recorded in
the committed model report rather than re-tuning, and the committed report was produced by a FULL
run. So --fast is not idempotent - re-running it on an up-to-date tree rewrites the originated lines,
the leaderboard and the correlation file with a different lambda and materially different numbers. Use
--fast only inside a build that is going to re-tune anyway, or on a scratch copy; after a --fast run,
`git checkout -- data/lab/lines data/lab/leaderboard.json data/lab/correlations.json
data/lab/deficiency.json data/lab/results data/lab/prices data/lab/summary.json
data/lab/questions.json data/lab/suggestions.json lab/` restores the published numbers.
"""
import subprocess
import sys
import time

# The R1 steps come first: they read only committed inputs (the official reads pack, the shadow
# record, the results log) and everything the reads/escrow/closure pages render depends on them.
STEPS = [
    ("tools/lab/build_reads.py", False),
    ("tools/lab/build_closure_measurement.py", False),
    ("tools/lab/build_escrow.py", False),
    ("tools/lab/fetch_upstream.py", True),   # skipped unless data/lab/upstream is missing
    ("tools/lab/build_prices.py", False),
    ("tools/lab/build_results.py", False),
    ("tools/lab/build_lines.py", False),
    ("tools/lab/build_strategies.py", False),
    ("tools/lab/build_correlation.py", False),
    ("tools/lab/build_deficiency.py", False),
    ("tools/lab/build_questions.py", False),
    ("tools/lab/build_summary.py", False),
]

def main() -> int:
    fast = ["--fast"] if "--fast" in sys.argv else []
    for script, optional in STEPS:
        if optional and __import__("os").path.exists("data/lab/upstream/games.csv"):
            print(f"skip {script} (upstream already vendored)")
            continue
        t0 = time.time()
        print(f"== {script}")
        rc = subprocess.call([sys.executable, script] + (fast if "build_lines" in script else []))
        if rc != 0:
            print(f"FAILED {script} rc={rc}", file=sys.stderr)
            return rc
        print(f"   ok in {time.time() - t0:.1f}s")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
