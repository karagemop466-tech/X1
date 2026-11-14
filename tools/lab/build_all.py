#!/usr/bin/env python3
"""Rebuild every lab artefact in dependency order.

    python3 tools/lab/build_all.py           # ~4 minutes (tunes the model)
    python3 tools/lab/build_all.py --fast    # reuses the frozen model parameters

Order matters: prices -> results -> lines -> strategies -> correlation -> deficiency ->
questions -> summary.  Each step reads only the artefacts the steps before it wrote, so a
failure upstream is visible as a downstream file that refuses to build rather than a page
that silently shows stale numbers.
"""
import subprocess
import sys
import time

STEPS = [
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
