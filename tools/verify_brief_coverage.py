#!/usr/bin/env python3
"""Mechanical check for docs/audit/brief-coverage-2026-11-17.md.

Fails (exit 1) when:
  * a row's status is not one of the legal statuses;
  * a row is BUILT / PARTIAL / DEFINED but cites no existing repo path;
  * a path cited in backticks (no wildcard, no placeholder) does not exist;
  * a row is BUILT but its evidence has no existing path;
  * an https link in the document is not on an official or project host.

Prints the status counts it computed, so the document's counts can be checked.
Run from the repository root:  python3 tools/verify_brief_coverage.py
"""
import collections
import os
import re
import sys
from urllib.parse import urlparse

DOC = "docs/audit/brief-coverage-2026-11-17.md"
LEGAL = {"BUILT", "PARTIAL", "DEFINED", "NOT BUILT", "DECLINED"}
NEEDS_PATH = {"BUILT", "PARTIAL", "DEFINED"}
# Official NFL / club hosts plus this project's own Pages and GitHub hosts.
ALLOWED_HOSTS = {
    "www.nfl.com", "static.www.nfl.com", "www.atlantafalcons.com",
    "www.packers.com", "karagemop466-tech.github.io", "github.com",
}
PATH_EXT = (".csv", ".json", ".tsv", ".psv", ".py", ".html", ".md", ".yml", ".txt", ".jsonl", ".sh", ".css")


def looks_like_path(tok: str) -> bool:
    if any(ch in tok for ch in "*{}…<>") or " " in tok:
        return False
    return "/" in tok or tok.endswith(PATH_EXT)


def main() -> int:
    root = os.getcwd()
    text = open(os.path.join(root, DOC), encoding="utf-8").read()
    failures = []

    # Row register lines look like: | 12 | item | STATUS | evidence | gap | link | flag |
    rows = []
    in_register = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_register = line.strip() == "## Row register"
            continue
        if in_register and re.match(r"^\| \d+ \|", line):
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if len(cells) != 7:
                failures.append(f"row {cells[0]}: expected 7 cells, found {len(cells)}")
                continue
            rows.append(cells)

    counts = collections.Counter()
    flagged = 0
    for num, item, status, evidence, gap, link, flag in rows:
        if status not in LEGAL:
            failures.append(f"row {num}: illegal status '{status}'")
            continue
        counts[status] += 1
        if flag.strip().lower() == "yes":
            flagged += 1
        toks = re.findall(r"`([^`]+)`", evidence)
        existing = []
        for tok in toks:
            tok = tok.split(" ")[0]
            if not looks_like_path(tok):
                continue
            if os.path.exists(os.path.join(root, tok)):
                existing.append(tok)
            else:
                failures.append(f"row {num}: cited path does not exist: {tok}")
        if status in NEEDS_PATH and not existing and status != "DEFINED":
            failures.append(f"row {num}: status {status} but no existing evidence path")
        if status == "DEFINED" and not existing:
            failures.append(f"row {num}: status DEFINED but no existing policy/gate path")

    if len(rows) != 82:
        failures.append(f"expected 82 register rows, found {len(rows)}")

    for url in set(re.findall(r"https://[^\s)|`\"']+", text)):
        host = urlparse(url).netloc
        if host not in ALLOWED_HOSTS:
            failures.append(f"link host not on allow-list: {url}")

    print(f"rows: {len(rows)}")
    for st in ["BUILT", "PARTIAL", "DEFINED", "NOT BUILT", "DECLINED"]:
        print(f"  {st:<10} {counts.get(st, 0)}")
    print(f"  rows with Flag = yes: {flagged}")
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    print("brief coverage: all rows, paths and links verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
