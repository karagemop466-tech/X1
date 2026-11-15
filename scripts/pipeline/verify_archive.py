#!/usr/bin/env python3
"""Verify the immutable capture archive (data/pipeline/archive/**).

Hard failures (exit 1): schema or integrity breaks — a stored file missing from disk, a
name that does not carry its hash prefix, a row_count that disagrees with its rows, a
predecessor link that points at nothing, an index line that is not valid JSON, or a
"stored" entry whose hash repeats the previous stored hash.

Warnings (exit 0, printed): freshness — the last capture attempt older than
FRESH_HOURS. The scheduled job runs every 6 hours, so this is an alert for a stalled job,
not a publication blocker.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVE = os.path.join(ROOT, "data", "pipeline", "archive")
FRESH_HOURS = 13  # two scheduled runs (every 6 h) plus margin


def main() -> int:
    hard, warn = [], []
    if not os.path.isdir(ARCHIVE):
        print("archive: no archive directory yet (first scheduled run creates it)")
        return 0
    datasets = [d for d in sorted(os.listdir(ARCHIVE)) if os.path.isdir(os.path.join(ARCHIVE, d))]
    summary = {}
    for dataset in datasets:
        base = os.path.join(ARCHIVE, dataset)
        index_path = os.path.join(base, "index.jsonl")
        if not os.path.exists(index_path):
            hard.append(f"{dataset}: no index.jsonl")
            continue
        entries = []
        for number, line in enumerate(open(index_path, encoding="utf-8"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                hard.append(f"{dataset}/index.jsonl line {number}: invalid JSON ({exc})")
        stored = [e for e in entries if e.get("status") == "stored"]
        names = {e["file"] for e in stored}
        on_disk = {f for f in os.listdir(base) if f.endswith(".json")}
        for name in names:
            if name not in on_disk:
                hard.append(f"{dataset}: indexed file missing on disk: {name}")
        for name in on_disk - names:
            hard.append(f"{dataset}: file on disk but not in index: {name}")
        last_hash = None
        for entry in stored:
            if entry.get("body_sha256") == last_hash:
                hard.append(f"{dataset}: stored entry repeats the previous hash ({entry.get('file')})")
            last_hash = entry.get("body_sha256")
        for entry in stored:
            path = os.path.join(base, entry["file"])
            if not os.path.exists(path):
                continue
            payload = json.load(open(path, encoding="utf-8"))
            if payload.get("row_count") != len(payload.get("rows", [])):
                hard.append(f"{dataset}/{entry['file']}: row_count disagrees with rows")
            if not entry["file"].endswith(payload.get("body_sha256", "")[:12] + ".json"):
                hard.append(f"{dataset}/{entry['file']}: name does not carry the hash prefix")
            prev = payload.get("previous_stored_file")
            if prev and prev not in names:
                hard.append(f"{dataset}/{entry['file']}: predecessor {prev} is not in the index")
        if entries:
            last = entries[-1]
            when = datetime.fromisoformat(last["captured_at"].replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - when).total_seconds() / 3600
            if age_h > FRESH_HOURS:
                warn.append(f"{dataset}: last capture attempt is {age_h:.1f} h old (limit {FRESH_HOURS} h)")
        summary[dataset] = {"attempts": len(entries), "stored": len(stored),
                            "unchanged": sum(1 for e in entries if e.get("status") == "unchanged"),
                            "fetch_failed": sum(1 for e in entries if e.get("status") == "fetch_failed")}
    for dataset, s in summary.items():
        print(f"archive {dataset}: {s}")
    for w in warn:
        print("WARN", w)
    for h in hard:
        print("FAIL", h)
    if not datasets:
        print("archive: empty (no capture has run yet)")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
