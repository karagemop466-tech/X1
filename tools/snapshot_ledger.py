#!/usr/bin/env python3
"""Immutable, hash-chained ledger of official NFL injury-report captures.

Why this exists: the 6-hourly pipeline (`python3 -m pipeline`) OVERWRITES its
output (data/pipeline/injuries.json). A practice designation can therefore only be
replayed as it was known if every read of the official page is kept, unchanged,
with the time it was taken. This tool does that and nothing else.

Each capture is stored as:
  * raw bytes  -> data/ledger/injuries/raw/<UTC>_<sha12>.html.gz  (never rewritten)
  * one JSON line -> data/ledger/injuries/ledger.jsonl            (append-only)

A ledger line records the UTC capture time, the source URL, the HTTP status, the
SHA-256 of the decoded page bytes, the week/season read from the page title, the
change flags, and `prev_sha256`, the hash of the previous line. Editing or deleting
any past line breaks the chain, and `verify` reports it.

Commands
  capture [--out DIR] [--dry-run]   fetch the official page and append one line
  verify  [--dir DIR]               re-hash every raw file and walk the chain
  status  [--dir DIR] [--max-age-hours H]   latest capture age; exit 1 if stale

Exit codes: capture exits 1 on a fatal flag (http_error, empty_body, schema_drift)
so the scheduled job fails loudly. verify exits 1 on any mismatch.

Standard library only. Source: https://www.nfl.com/injuries/ (official NFL.com).
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_URL = "https://www.nfl.com/injuries/"
DEFAULT_DIR = os.path.join(REPO, "data", "ledger", "injuries")
LEDGER_NAME = "ledger.jsonl"
RAW_SUBDIR = "raw"
GENESIS = "0" * 64
TOOL_ID = "tools/snapshot_ledger.py@1"
FATAL_FLAGS = {"http_error", "empty_body", "schema_drift"}
MIN_BYTES = 20_000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_WEEK_RE = re.compile(r"Week\s+(\d+)\s+of the\s+(\d{4})\s+Season", re.IGNORECASE)
_SSL = ssl.create_default_context()


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_UUID_RE = re.compile(rb"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def content_sha256(body: bytes) -> str:
    """Hash of the page with random UUIDs masked.

    The official page embeds a fresh random UUID on each render (for example a carousel
    `data-jsonid`). Two reads of an unchanged report therefore differ in exact bytes. Change
    detection uses this normalised hash; the exact-bytes SHA-256 is still stored for integrity.
    Found on the first two live reads: same length, 28 differing characters, all UUIDs.
    """
    return sha256_hex(_UUID_RE.sub(b"<uuid>", body))


def canonical(entry: Dict[str, Any]) -> bytes:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def fetch_bytes(url: str, timeout: float = 45.0) -> Tuple[int, str, bytes, Optional[str]]:
    """Return (status, final_url, decoded_body, error). Never raises."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip",
        "Cache-Control": "no-cache",
    }
    last_error: Optional[str] = None
    status = 0
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as resp:
                raw = resp.read()
                status = resp.status
                final_url = resp.geturl()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return status, final_url, raw, None
        except urllib.error.HTTPError as exc:
            status = exc.code
            last_error = f"HTTP {exc.code} {exc.reason}"
        except Exception as exc:  # noqa: BLE001 - capture must be total
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < 3:
            time.sleep(2.0 * attempt)
    return status, url, b"", last_error


def read_index(dir_: str) -> List[Dict[str, Any]]:
    path = os.path.join(dir_, LEDGER_NAME)
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def describe(body: bytes) -> Dict[str, Any]:
    """Extract the title, week and season the official page itself declares."""
    text = body.decode("utf-8", "replace")
    m = _TITLE_RE.search(text)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    wk = _WEEK_RE.search(title) or _WEEK_RE.search(text[:200000])
    return {
        "title": title,
        "week": int(wk.group(1)) if wk else None,
        "season": int(wk.group(2)) if wk else None,
        "has_injury_report_title": "injury report" in title.lower(),
        "has_practice_status_text": "Practice Status" in text,
    }


def prev_content_sha(prev: Dict[str, Any]) -> Optional[str]:
    """Normalised hash of the previous read. Older lines (written before the normalised hash
    existed) are recomputed from their stored raw file; the ledger line itself is never edited."""
    if prev.get("content_sha256"):
        return prev["content_sha256"]
    if prev.get("file"):
        path = os.path.join(_CURRENT_DIR[0], prev["file"])
        if os.path.exists(path):
            with open(path, "rb") as fh:
                return content_sha256(gzip.decompress(fh.read()))
    return None


_CURRENT_DIR: List[str] = [DEFAULT_DIR]


def build_flags(status: int, error: Optional[str], body: bytes, info: Dict[str, Any],
                prev: Optional[Dict[str, Any]], new_content_sha: str) -> List[str]:
    flags: List[str] = []
    if error or status != 200:
        flags.append("http_error")
    if len(body) < MIN_BYTES:
        flags.append("empty_body")
    if not info["has_injury_report_title"] or info["week"] is None:
        flags.append("schema_drift")
    if info["week"] is not None and info["season"] is not None:
        if prev and prev.get("week") is not None:
            if (prev.get("season"), prev.get("week")) != (info["season"], info["week"]):
                flags.append("week_rollover")
            elif prev_content_sha(prev) == new_content_sha:
                flags.append("unchanged")
            else:
                flags.append("revised")
        elif prev is None:
            flags.append("first_capture")
    if not info["has_practice_status_text"] and "schema_drift" not in flags:
        flags.append("schema_drift")
    return flags


def capture(dir_: str, dry_run: bool) -> int:
    index = read_index(dir_)
    prev_entry = index[-1] if index else None
    prev_week = next((e for e in reversed(index) if e.get("week") is not None), None)
    ts = utc_now()
    status, final_url, body, error = fetch_bytes(SOURCE_URL)
    info = describe(body) if body else {"title": "", "week": None, "season": None,
                                        "has_injury_report_title": False,
                                        "has_practice_status_text": False}
    new_sha = sha256_hex(body) if body else ""
    new_content = content_sha256(body) if body else ""
    _CURRENT_DIR[0] = dir_
    flags = build_flags(status, error, body, info, prev_week, new_content)

    raw_name = None
    gz_sha = None
    # Identical bytes already stored: reuse that file (the ledger line still records
    # this read and its time). Storage therefore grows with page CHANGES, not reads.
    reuse = next((e for e in reversed(index) if e.get("sha256") == new_sha and e.get("file")), None) if new_sha else None
    if body and not dry_run:
        if reuse:
            raw_name = os.path.basename(reuse["file"])
            gz_sha = reuse["gzip_sha256"]
        else:
            raw_dir = os.path.join(dir_, RAW_SUBDIR)
            os.makedirs(raw_dir, exist_ok=True)
            raw_name = f"{ts.strftime('%Y%m%dT%H%M%SZ')}_{new_sha[:12]}.html.gz"
            path = os.path.join(raw_dir, raw_name)
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
                gz.write(body)
            data = buf.getvalue()
            gz_sha = sha256_hex(data)
            with open(path, "xb") as fh:  # exclusive create: never overwrite
                fh.write(data)

    entry: Dict[str, Any] = {
        "seq": (index[-1]["seq"] + 1) if index else 1,
        "captured_at_utc": iso(ts),
        "source_url": SOURCE_URL,
        "final_url": final_url,
        "http_status": status,
        "error": error,
        "bytes": len(body),
        "sha256": new_sha or None,
        "content_sha256": new_content or None,
        "file": (f"{RAW_SUBDIR}/{raw_name}" if raw_name else None),
        "gzip_sha256": gz_sha,
        "season": info["season"],
        "week": info["week"],
        "title": info["title"],
        "flags": flags,
        "prev_sha256": (prev_entry["entry_sha256"] if prev_entry else GENESIS),
        "runner": os.environ.get("GITHUB_RUN_ID", "local"),
        "tool": TOOL_ID,
    }
    entry["entry_sha256"] = sha256_hex(canonical({k: v for k, v in entry.items() if k != "entry_sha256"}))

    print(f"capture {iso(ts)}  HTTP {status}  bytes {len(body)}  week {info['week']} season {info['season']}")
    print(f"  title : {info['title'] or '(none)'}")
    print(f"  sha256: {new_sha or '(none)'}")
    print(f"  flags : {', '.join(flags) or '(none)'}")
    if dry_run:
        print("  dry run: nothing written")
    else:
        os.makedirs(dir_, exist_ok=True)
        with open(os.path.join(dir_, LEDGER_NAME), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        print(f"  appended seq {entry['seq']} to {os.path.relpath(os.path.join(dir_, LEDGER_NAME), REPO)}")
    fatal = sorted(set(flags) & FATAL_FLAGS)
    if fatal:
        print(f"ALARM: fatal flags {fatal} — the official page changed or failed; see the ledger line.")
        return 1
    return 0


def verify(dir_: str) -> int:
    problems: List[str] = []
    index = read_index(dir_)
    prev = GENESIS
    seen_seq = 0
    for i, e in enumerate(index):
        if e.get("prev_sha256") != prev:
            problems.append(f"line {i + 1}: prev_sha256 does not chain")
        recomputed = sha256_hex(canonical({k: v for k, v in e.items() if k != "entry_sha256"}))
        if recomputed != e.get("entry_sha256"):
            problems.append(f"line {i + 1} (seq {e.get('seq')}): entry_sha256 mismatch — line was altered")
        if e.get("seq") != seen_seq + 1:
            problems.append(f"line {i + 1}: seq {e.get('seq')} is not contiguous")
        seen_seq = e.get("seq", seen_seq)
        prev = e.get("entry_sha256", "")
        if e.get("file"):
            path = os.path.join(dir_, e["file"])
            if not os.path.exists(path):
                problems.append(f"seq {e['seq']}: raw file missing: {e['file']}")
                continue
            with open(path, "rb") as fh:
                gz = fh.read()
            if sha256_hex(gz) != e.get("gzip_sha256"):
                problems.append(f"seq {e['seq']}: gzip file hash mismatch")
            body = gzip.decompress(gz)
            if sha256_hex(body) != e.get("sha256"):
                problems.append(f"seq {e['seq']}: decoded page hash mismatch")
            if len(body) != e.get("bytes"):
                problems.append(f"seq {e['seq']}: byte count mismatch")
    print(f"ledger lines : {len(index)}")
    print(f"raw captures : {sum(1 for e in index if e.get('file'))}")
    print(f"chain head   : {prev}")
    if problems:
        for p in problems:
            print("FAIL", p)
        return 1
    if not index:
        print("verify: empty ledger (nothing to check yet)")
        return 0
    print("verify: chain intact; every stored page re-hashes to its ledger line")
    return 0


def status(dir_: str, max_age_hours: Optional[float]) -> int:
    index = read_index(dir_)
    if not index:
        print("no captures yet")
        return 1 if max_age_hours is not None else 0
    last = index[-1]
    last_ok = next((e for e in reversed(index) if e.get("sha256")), None)
    ts = dt.datetime.strptime(last["captured_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    age_h = (utc_now() - ts).total_seconds() / 3600.0
    print(f"lines {len(index)}  last line {last['captured_at_utc']} ({age_h:.1f} h ago) flags {last['flags']}")
    if last_ok:
        print(f"last successful page read {last_ok['captured_at_utc']} week {last_ok['week']} season {last_ok['season']}")
    if max_age_hours is not None and (age_h > max_age_hours or last.get("sha256") is None):
        print(f"STALE: no successful capture within {max_age_hours} h")
        return 1
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--out", default=DEFAULT_DIR)
    c.add_argument("--dry-run", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("--dir", default=DEFAULT_DIR)
    s = sub.add_parser("status")
    s.add_argument("--dir", default=DEFAULT_DIR)
    s.add_argument("--max-age-hours", type=float, default=None)
    args = ap.parse_args(argv)
    if args.cmd == "capture":
        return capture(args.out, args.dry_run)
    if args.cmd == "verify":
        return verify(args.dir)
    return status(args.dir, args.max_age_hours)


if __name__ == "__main__":
    sys.exit(main())
