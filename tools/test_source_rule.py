#!/usr/bin/env python3
"""Mutation test for the shared source-link rule.

Proves that scripts/verify_site.py actually fails when a data-table row loses its Source
link. A checker that cannot fail is decoration; this test exists so the rule cannot rot
silently (an earlier version of the checker passed a mutated page because it only looked
for *any* link in the row).
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("vs", ROOT / "scripts/verify_site.py")
vs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vs)

TARGET = ROOT / "pages" / "standings.html"
LINK = ('<td><a class="src-link" href="https://www.nfl.com/standings/division/2026/REG" '
        'target="_blank" rel="noopener noreferrer">nfl.com ↗</a></td>')

original = TARGET.read_text(encoding="utf-8")
if LINK not in original:
    print("FAIL: could not find the expected Source cell to mutate")
    sys.exit(1)


def count_errors(text: str) -> int:
    tmp = TARGET.with_suffix(".mutant.html")
    tmp.write_text(text, encoding="utf-8")
    try:
        vs.errors.clear()
        parser = vs.SiteParser(tmp)
        parser.feed(text)
        return len(vs.errors)
    finally:
        tmp.unlink(missing_ok=True)


clean = count_errors(original)
mutant = count_errors(original.replace(LINK, "", 1))

print(f"clean page    : {clean} errors (expected 0)")
print(f"mutated page  : {mutant} errors (expected >0)")
if clean != 0:
    print("FAIL: the pristine page must pass")
    sys.exit(1)
if mutant == 0:
    print("FAIL: removing a data row's Source link did not fail the checker")
    sys.exit(1)
print("source-link rule is enforced (mutation detected)")
