"""Immutable, hashed capture archive for the scheduled official-source pipeline.

Why this exists: `pipeline/run.py` overwrites `data/pipeline/injuries.json` on every
run, so the repository kept one capture and no history. A designation can only be
replayed "as it was known" if every distinct capture is kept with its fetch time and
a hash of the exact bytes the league served.

What it writes (all under `data/pipeline/archive/<dataset>/`, which the Pages copy
step does NOT publish — it copies only top-level `data/pipeline/*.json`):

  index.jsonl                 one line per capture ATTEMPT, appended, never rewritten:
                              {captured_at, source_url, body_sha256, rows, status, ...}
                              status = "stored"    (raw hash differs from the last stored one)
                                       "unchanged" (same raw hash as the last stored one)
                                       "fetch_failed"
  <UTC-time>_<sha12>.json     one file per CHANGED capture: the parsed rows, the full
                              sha256, the byte count, the previous stored file and any
                              conflict flags. Never edited after it is written.

Standard library only, so the scheduled job needs no install step.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_ROOT = os.path.join(ROOT, "data", "pipeline", "archive")

# A capture whose row count falls below this share of the previous stored capture is
# flagged. Injury reports shrink when a week's list is replaced, so a fall is a prompt
# to look, not proof of an error.
ROW_DROP_FLAG_SHARE = 0.80


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_index(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _append_index(path: str, entry: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def conflict_flags(rows: List[Dict[str, Any]], previous_row_count: Optional[int]) -> List[str]:
    """Flags that a reviewer should read before trusting this capture."""
    flags: List[str] = []
    if not rows:
        flags.append("zero_rows")
    missing = sum(1 for r in rows if not (r.get("team_abbrev") and r.get("player")))
    if missing:
        flags.append(f"rows_missing_team_or_player:{missing}")
    seen = set()
    dupes = 0
    for r in rows:
        key = (r.get("team_abbrev"), r.get("player"))
        if key in seen:
            dupes += 1
        seen.add(key)
    if dupes:
        flags.append(f"duplicate_team_player:{dupes}")
    if previous_row_count and len(rows) < ROW_DROP_FLAG_SHARE * previous_row_count:
        flags.append(f"row_count_drop:{previous_row_count}->{len(rows)}")
    return flags


def archive_capture(
    dataset: str,
    source_url: str,
    body: str,
    rows: List[Dict[str, Any]],
    *,
    fetch_ok: bool = True,
    fetch_error: Optional[str] = None,
    now: Optional[datetime] = None,
    root: Optional[str] = None,
) -> Dict[str, Any]:
    """Record one capture attempt. Never raises; returns the index entry written."""
    when = now or _utc_now()
    base = os.path.join(root or ARCHIVE_ROOT, dataset)
    index_path = os.path.join(base, "index.jsonl")
    history = _read_index(index_path)
    stored = [h for h in history if h.get("status") == "stored"]
    last_stored = stored[-1] if stored else None

    if not fetch_ok or not body:
        entry = {
            "captured_at": when.isoformat(),
            "source_url": source_url,
            "status": "fetch_failed",
            "error": fetch_error or "empty body",
        }
        _append_index(index_path, entry)
        return entry

    digest = sha256_text(body)
    entry: Dict[str, Any] = {
        "captured_at": when.isoformat(),
        "source_url": source_url,
        "body_sha256": digest,
        "body_bytes": len(body.encode("utf-8")),
        "rows": len(rows),
    }

    if last_stored and last_stored.get("body_sha256") == digest:
        entry["status"] = "unchanged"
        entry["same_as_file"] = last_stored.get("file")
        _append_index(index_path, entry)
        return entry

    stamp = when.strftime("%Y%m%dT%H%M%SZ")
    file_name = f"{stamp}_{digest[:12]}.json"
    previous_rows = last_stored.get("rows") if last_stored else None
    flags = conflict_flags(rows, previous_rows)
    payload = {
        "dataset": dataset,
        "captured_at": when.isoformat(),
        "source_url": source_url,
        "body_sha256": digest,
        "body_bytes": entry["body_bytes"],
        "row_count": len(rows),
        "previous_stored_file": last_stored.get("file") if last_stored else None,
        "previous_stored_sha256": last_stored.get("body_sha256") if last_stored else None,
        "conflict_flags": flags,
        "rows": rows,
    }
    os.makedirs(base, exist_ok=True)
    file_path = os.path.join(base, file_name)
    if os.path.exists(file_path):
        # Same timestamp and hash prefix already on disk: never overwrite an archive file.
        entry["status"] = "fetch_failed"
        entry["error"] = "archive file name collision; capture not written"
        _append_index(index_path, entry)
        return entry
    with open(file_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=False)
        handle.write("\n")
    entry["status"] = "stored"
    entry["file"] = file_name
    entry["conflict_flags"] = flags
    _append_index(index_path, entry)
    return entry
