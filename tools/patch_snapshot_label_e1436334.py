#!/usr/bin/env python3
"""One-shot, attributed edit of tools/build_site.py (session arena-e1436334-x1, group "site-snapshot").

The rail on every page printed one blanket date, `Data snapshot 2026-11-14`. After Week 10 closed that
became wrong in both directions: the results corpus, the standings baseline and the sealed ledger were read
on 2026-11-17, while the injury, availability and depth tables are genuinely 2026-11-14 reads. One date
cannot describe both, and quietly advancing it to 2026-11-17 would have over-claimed the injury tables.

So the note now names the split. No new CSS class is introduced: `tools/check_links.py` fails the build when
markup uses a class the shared stylesheet does not define, and assets/site.css is not this session's file.

Usage:  python3 tools/patch_snapshot_label_e1436334.py [--revert]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "tools", "build_site.py")
SIGNATURE = "sealed ledger re-read"

OLD = '''    <span class="dot"></span> Data snapshot <strong>{RETRIEVED}</strong>
    <p>This dashboard publishes league-verified tables only.'''

NEW = '''    <span class="dot"></span> Data snapshot <strong>{RETRIEVED}</strong> &middot; results, standings and the
    sealed ledger re-read <strong>2026-11-17</strong>, injury/availability/depth tables still the
    <strong>{RETRIEVED}</strong> read
    <p>This dashboard publishes league-verified tables only.'''


def main() -> int:
    revert = "--revert" in sys.argv
    src = open(TARGET, encoding="utf-8").read()
    old, new = (NEW, OLD) if revert else (OLD, NEW)
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor occurs {n} times (expected exactly 1)")
        return 1
    if (SIGNATURE in src) and not revert:
        print("ABORT: the split-date note is already present — refusing to edit twice")
        return 1
    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(src.replace(old, new, 1))
    print(f"{'rolled back' if revert else 'applied'}: 1 edit to tools/build_site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
