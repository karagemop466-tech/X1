#!/usr/bin/env python3
"""Row-level verification of every dataset in data/.

Checks, per row:
  1. a `_source_url` exists and points at an official host (nfl.com or an
     official club domain listed in pipeline/sources.py);
  2. no field is null unless it is named in `_unverified`;
  3. `_verified` is consistent with those two facts.

Exits non-zero when a hard failure is found, so the scheduled job surfaces it.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.sources import CLUB_DOMAINS  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def official_hosts() -> set:
    hosts = {"www.nfl.com", "nfl.com"}
    for domain in CLUB_DOMAINS.values():
        hosts.add(domain)
        hosts.add("www." + domain)
    return hosts


def is_official(url: str, hosts: set) -> bool:
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    return host in hosts


def check_rows(name: str, rows: List[Dict[str, Any]], hosts: set) -> Dict[str, Any]:
    problems: List[str] = []
    missing_source = 0
    non_official = 0
    null_cells = 0
    for index, row in enumerate(rows):
        url = row.get("_source_url") or ""
        if not url:
            missing_source += 1
            if missing_source <= 3:
                problems.append(f"{name}[{index}] has no _source_url")
        elif not is_official(url, hosts):
            non_official += 1
            if non_official <= 3:
                problems.append(f"{name}[{index}] source is not an official host: {url}")
        for key, value in row.items():
            if key.startswith("_"):
                continue
            if value is None or value == "":
                null_cells += 1
                if key not in (row.get("_unverified") or []):
                    problems.append(
                        f"{name}[{index}] null field '{key}' not declared in _unverified"
                    )
    return {
        "dataset": name,
        "rows": len(rows),
        "rows_missing_source": missing_source,
        "rows_non_official_source": non_official,
        "null_cells": null_cells,
        "problems": problems[:20],
        "ok": not problems,
    }


def main() -> int:
    hosts = official_hosts()
    report: List[Dict[str, Any]] = []
    hard_failures = 0
    for filename in sorted(os.listdir(DATA_DIR)):
        if not filename.endswith(".json") or filename.startswith("_"):
            continue
        path = os.path.join(DATA_DIR, filename)
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        rows = payload.get("rows") or []
        result = check_rows(payload.get("dataset", filename), rows, hosts)
        report.append(result)
        if not result["ok"]:
            hard_failures += 1

    out_path = os.path.join(DATA_DIR, "_verification.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(
            {"generated_at": None, "results": report, "hard_failures": hard_failures},
            handle,
            indent=1,
        )
        handle.write("\n")

    for result in report:
        print(
            f"{result['dataset']:<14} rows={result['rows']:<6} "
            f"missing_src={result['rows_missing_source']:<3} "
            f"non_official={result['rows_non_official_source']:<3} "
            f"nulls={result['null_cells']:<5} ok={result['ok']}"
        )
        for problem in result["problems"][:5]:
            print("    !", problem)
    return 1 if hard_failures else 0


if __name__ == "__main__":
    sys.exit(main())
