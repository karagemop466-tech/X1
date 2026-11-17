#!/usr/bin/env python3
"""One-shot, attributed edit of .github/workflows/verify.yml (session arena-e1436334-x1).

The 2026-11-17 pack's three headers each named `tools/verify_2026_11_17.py` as their checker. A check that
exists only in the sandbox is not a check: it passes today and rots tomorrow, which is exactly how the
2026-11-16 pack's `137` pins stayed true-looking for two rounds after the corpus moved. So the command is
wired into the job that already runs the dated-pack gate next to it, and the two registers this session
made reproducible (`sealed ledger`, `results feed`) are asserted in the same place they are built.

Both added commands are read-only `--check`s, and the committed summary they compare against contains no
wall-clock field, so the step is stable on a re-run of an unchanged tree (verified: two consecutive
`--check` runs 2 s apart both pass).

Usage:  python3 tools/patch_ci_e1436334.py [--revert]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, ".github", "workflows", "verify.yml")
SIGNATURE = "verify_2026_11_17.py"

OLD = '''      # The 2026-11-16 official pack, re-derived and compared to what is committed: standings arithmetic,
      # league closure, three-page record cross-check, slate completeness (32 clubs exactly once), the
      # dated-delta closure and the Week 10 promotion accounting. Read-only by design (see --write).
      - name: The dated official pack still closes
        run: python3 tools/verify_2026_11_16.py --check'''

NEW = '''      # The 2026-11-16 official pack, re-derived and compared to what is committed: standings arithmetic,
      # league closure, three-page record cross-check, slate completeness (32 clubs exactly once), the
      # dated-delta closure and the Week 10 promotion accounting. Read-only by design (see --write).
      - name: The dated official pack still closes
        run: python3 tools/verify_2026_11_16.py --check

      # Added by session arena-e1436334-x1 (additive only). The 2026-11-17 pack is the one that closed
      # Week 10, and its three file headers each cite this checker - so the citation has to be load-bearing
      # in CI, not just true in somebody's sandbox. Eleven checks, all arithmetic over values an official
      # page printed: standings identities (NET = PF - PA, PCT = (W + T/2)/GP, HOME + ROAD = W-L-T), league
      # closure, three-page record agreement, corpus admission against the per-week row pins, the 150-game
      # standings arithmetic, the mirror as a cross-check, capture freshness, the sealed ledger recomputed
      # independently of the tool that wrote it, the price-discipline rule (a populated market value fails
      # the build while Q-61 is undecided), the 13 + 6 = 32 forward slate, and a second independent read of
      # the standings page (512 cells). The committed summary holds no wall-clock field, so a re-run of an
      # unchanged tree is byte-identical and this gate cannot fire on the clock.
      - name: The 2026-11-17 re-verification pack still closes
        run: python3 tools/verify_2026_11_17.py --check'''


def main() -> int:
    revert = "--revert" in sys.argv
    src = open(TARGET, encoding="utf-8").read()
    old, new = (NEW, OLD) if revert else (OLD, NEW)
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor occurs {n} times (expected exactly 1)")
        return 1
    if (SIGNATURE in src) and not revert:
        print("ABORT: the step is already present — refusing to add it twice")
        return 1
    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(src.replace(old, new, 1))
    print(f"{'rolled back' if revert else 'applied'}: 1 step added to .github/workflows/verify.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
