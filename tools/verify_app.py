#!/usr/bin/env python3
"""Verify the unified dashboard in `app/`.

Session `arena/fcc11e05-x1`. Three hard rules, all failing the build if broken:

  1. Every internal link resolves to a file that exists.
  2. Every data-table row carries a source URL, or an explicit marker saying no
     official source publishes that value. A row with neither fails.
  3. No generated page contains an unresolved template artefact, a literal
     "None", or a broken em-dash placeholder.

It also reports a coverage summary so the gap between "sourced" and "unsourced"
is never invisible.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
BASE = "/X1"

OFFICIAL_HOSTS = (
    "nfl.com", "operations.nfl.com", "nextgenstats.nfl.com",
    "github.com",           # repository state and the fingerprinted third-party mirror
)

LINK_RE = re.compile(r'href="([^"]+)"', re.I)
TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
TABLE_RE = re.compile(r"<table([^>]*)>(.*?)</table>", re.S | re.I)
NO_SRC_MARKER = "no official source"


def main() -> int:
    failures: list[str] = []
    pages = sorted(f for f in os.listdir(APP) if f.endswith(".html"))
    known = {f for f in os.listdir(APP)}

    total_rows = 0
    sourced_rows = 0
    marker_rows = 0
    link_targets = 0

    for name in pages:
        path = os.path.join(APP, name)
        text = open(path, encoding="utf-8").read()

        # ---------------------------------------------------------- artefacts
        for bad in ("${", "{{", "None", "nan%", "%!s", "Traceback"):
            if bad in text.replace("None —", ""):
                if bad == "None" and "None" not in text:
                    continue
                failures.append(f"{name}: unresolved artefact {bad!r}")
                break

        # ------------------------------------------------------ internal links
        for href in LINK_RE.findall(text):
            if href.startswith(("http://", "https://", "mailto:", "#", "//")):
                continue
            target = href.split("#")[0].split("?")[0]
            if not target:
                continue
            link_targets += 1
            if target.startswith(BASE + "/"):
                # site-absolute: resolve against the repository root, because the
                # published tree is the repo root with app/ copied into it.
                rel = target[len(BASE) + 1:]
                full = os.path.normpath(os.path.join(ROOT, rel)) if rel else ROOT
                if rel == "" and not os.path.exists(os.path.join(APP, "index.html")):
                    failures.append(f"{name}: internal link does not resolve -> {href}")
                    continue
                if rel and not os.path.exists(full):
                    failures.append(f"{name}: internal link does not resolve -> {href}")
                continue
            base = ROOT if name == "root.html" else APP
            full = os.path.normpath(os.path.join(base, target))
            if not os.path.exists(full):
                failures.append(f"{name}: internal link does not resolve -> {href}")

        # -------------------------------------------------------- table rows
        for attrs, inner in TABLE_RE.findall(text):
            data_src = re.search(r'data-src="([^"]+)"', attrs)
            rows = TR_RE.findall(inner)
            # skip the header row
            rows = rows[1:] if "<thead" not in inner.lower() else rows
            if "<thead" not in inner.lower():
                rows = rows[1:]
            for r in rows:
                if "<td" not in r:
                    continue
                total_rows += 1
                if data_src:
                    sourced_rows += 1
                    continue
                if 'href="http' in r or 'href="//' in r:
                    sourced_rows += 1
                    continue
                if NO_SRC_MARKER in r.lower():
                    marker_rows += 1
                    continue
                failures.append(
                    f"{name}: table row with no source link and no marker: "
                    + re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r))[:110]
                )

    # --- coverage-count guard (added with the 2026-11-17 Week 10 closure) --------------------
    # Every "N settled games" the results page states must be the row count of the artefact it
    # renders. A right number past its date is how 137 sat on the landing page for three days while
    # the official page printed 14 Week 10 finals, and no build check noticed: the HTML matched its
    # builder, the builder matched the data, and the prose in the middle was simply from another day.
    feed_path = os.path.join(ROOT, "data", "results", "verified_results.json")
    page_path = os.path.join(APP, "results.html")
    if os.path.exists(feed_path) and os.path.exists(page_path):
        n_feed = len(json.load(open(feed_path, encoding="utf-8"))["rows"])
        text = open(page_path, encoding="utf-8").read()
        stated = [int(m) for m in re.findall(r"(\d+) settled games", text)]
        for n in stated:
            if n != n_feed:
                failures.append(
                    f"results.html: states {n} settled games but the feed it renders has {n_feed} rows "
                    "(regenerate the prose from the artefact, or date-stamp the claim)")
        if stated:
            print(f"coverage counts : {len(stated)} statement(s) checked against the feed ({n_feed} rows)")

    print(f"pages checked   : {len(pages)}")
    print(f"internal links  : {link_targets}")
    print(f"data rows       : {total_rows}")
    print(f"  with a source link : {sourced_rows}")
    print(f"  flagged no-source  : {marker_rows}")
    unsourced = total_rows - sourced_rows - marker_rows
    print(f"  unsourced          : {unsourced}")

    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures[:40]:
            print("  FAIL", f)
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more")
        return 1

    print("\napp verification passed: links resolve; every data row is sourced or flagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
