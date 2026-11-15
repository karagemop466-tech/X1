#!/usr/bin/env python3
"""Self-test for pipeline/archive.py. Runs in a temporary directory; writes nothing to the repo.

Proves the four behaviours the archive promises:
  stored      - first capture, and any capture whose raw bytes changed
  unchanged   - same raw bytes as the last stored capture: no new file, index line only
  fetch_failed- the fetch failed: an index line records the failure, no file is written
  flags       - a row-count drop and a duplicate player are flagged, not silently kept
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from pipeline import archive as A  # noqa: E402


def row(team, player):
    return {"team_abbrev": team, "player": player, "position": "WR", "injuries": None,
            "practice_status": "Full Participation in Practice", "game_status": None}


def main() -> int:
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        t0 = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
        url = "https://www.nfl.com/injuries/"
        rows_a = [row("WAS", "A"), row("WAS", "B"), row("NYG", "C")]
        e1 = A.archive_capture("injuries", url, "<html>v1</html>", rows_a, now=t0, root=tmp)
        e2 = A.archive_capture("injuries", url, "<html>v1</html>", rows_a, now=t0.replace(hour=18), root=tmp)
        e3 = A.archive_capture("injuries", url, "<html>v1</html>", [], fetch_ok=False,
                               fetch_error="HTTP 503", now=t0.replace(hour=0, day=12), root=tmp)
        e4 = A.archive_capture("injuries", url, "<html>v2</html>", [row("WAS", "A"), row("WAS", "A")],
                               now=t0.replace(day=12), root=tmp)
        if e1["status"] != "stored": failures.append("first capture not stored")
        if e2["status"] != "unchanged": failures.append("identical bytes not marked unchanged")
        if e3["status"] != "fetch_failed": failures.append("failed fetch not recorded as fetch_failed")
        if e4["status"] != "stored": failures.append("changed bytes not stored")
        flags = e4.get("conflict_flags", [])
        if not any(f.startswith("row_count_drop") for f in flags): failures.append("row-count drop not flagged")
        if not any(f.startswith("duplicate_team_player") for f in flags): failures.append("duplicate not flagged")
        files = sorted(f for f in os.listdir(os.path.join(tmp, "injuries")) if f.endswith(".json"))
        if len(files) != 2: failures.append(f"expected 2 archive files, found {len(files)}")
        index = [json.loads(x) for x in open(os.path.join(tmp, "injuries", "index.jsonl"))]
        if len(index) != 4: failures.append(f"expected 4 index lines (one per attempt), found {len(index)}")
        payload = json.load(open(os.path.join(tmp, "injuries", e4["file"])))
        if payload["previous_stored_file"] != e1["file"]: failures.append("changed capture does not point to its predecessor")
        if payload["row_count"] != len(payload["rows"]): failures.append("row_count disagrees with rows")
        if payload["body_sha256"] != A.sha256_text("<html>v2</html>"): failures.append("stored hash is not the sha256 of the body")
        # A second write with the same timestamp and hash must never overwrite.
        e5 = A.archive_capture("injuries", url, "<html>v2 changed</html>", rows_a,
                               now=t0.replace(day=12), root=tmp)
        if e5["status"] == "stored" and e5.get("file") == e4["file"]:
            failures.append("archive file was overwritten")
    if failures:
        print("FAIL"); [print(" -", f) for f in failures]
        return 1
    print("archive self-test: 4 behaviours verified (stored, unchanged, fetch_failed, flags); repo untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
