"""Line-by-line repo review, generated rather than asserted.

Walks every tracked file, hashes it, counts lines, applies a fixed set of
mechanical review rules, and writes one row per file with a link to the file on
GitHub so a human can open it and check. The rules are deliberately mechanical:
anything a script can decide is reported by the script, and anything that needs
judgement is listed on the Flagged for Review page instead of being guessed at.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
REPO_URL = "https://github.com/karagemop466-tech/X1"

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "site/data"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".mp3", ".zip"}
REVIEW_RULES = [
    ("todo-marker", re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")),
    ("placeholder-value", re.compile(r"\b(PLACEHOLDER|CHANGEME|<your[- ])")),
    ("hardcoded-secret-shape", re.compile(r"(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9/+_-]{12,}")),
    ("bare-except", re.compile(r"except\s*:" )),
    ("print-debug", re.compile(r"\bprint\s*\(")),
]


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def tracked_files() -> List[str]:
    out = git("ls-files")
    if out:
        return [line for line in out.splitlines() if line.strip()]
    # Fallback when git is unavailable: walk the tree.
    collected = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            path = os.path.relpath(os.path.join(base, name), ROOT)
            collected.append(path)
    return sorted(collected)


def review_file(path: str) -> Dict[str, Any]:
    full = os.path.join(ROOT, path)
    ext = os.path.splitext(path)[1].lower()
    if not os.path.exists(full):
        return {"lines": 0, "bytes": 0, "sha256": "", "findings": ["file is tracked but missing on disk"]}

    raw = open(full, "rb").read()
    digest = hashlib.sha256(raw).hexdigest()
    if ext in BINARY_EXT:
        return {"lines": 0, "bytes": len(raw), "sha256": digest,
                "findings": ["binary asset; not line reviewed"]}

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"lines": 0, "bytes": len(raw), "sha256": digest,
                "findings": ["not valid UTF-8; not line reviewed"]}

    lines = text.splitlines()
    findings: List[str] = []
    if not lines:
        findings.append("file is empty")
    if len(lines) > 400:
        findings.append(f"large file ({len(lines)} lines); consider splitting")
    if any(len(line) > 400 for line in lines):
        findings.append("contains a line longer than 400 characters")
    if not text.endswith("\n"):
        findings.append("no trailing newline")
    for label, pattern in REVIEW_RULES:
        hits = [i + 1 for i, line in enumerate(lines) if pattern.search(line)]
        if hits:
            where = ", ".join(str(h) for h in hits[:6])
            findings.append(f"{label} on line(s): {where}{' …' if len(hits) > 6 else ''}")
    if path.endswith(".html") and "<html" in text.lower() and "</html>" not in text.lower():
        findings.append("HTML file without a closing </html> tag")

    return {"lines": len(lines), "bytes": len(raw), "sha256": digest, "findings": findings}


def build() -> Dict[str, Any]:
    files = tracked_files()
    rows: List[Dict[str, Any]] = []
    for path in files:
        if any(part in SKIP_DIRS for part in path.split(os.sep)):
            continue
        info = review_file(path)
        findings = info["findings"]
        status = "ok" if not findings else "review"
        rows.append(
            {
                "path": path,
                "lines_reviewed": info["lines"],
                "bytes": info["bytes"],
                "sha256_short": info["sha256"][:12],
                "finding": "; ".join(findings) if findings else "no mechanical finding",
                "status": status,
                "_source_url": f"{REPO_URL}/blob/main/{path}",
                "_source_label": f"Source file on GitHub: {path}",
                "_source_org": "Repository",
                "_retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "_flags": [] if status == "ok" else ["flagged by an automated review rule"],
                "_unverified": [],
                "_verified": status == "ok",
            }
        )
    rows.sort(key=lambda row: (row["status"] != "review", row["path"]))
    return {
        "dataset": "repo_review",
        "title": "Repository review — file by file",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {"url": REPO_URL, "label": "Repository on GitHub", "org": "Repository"},
        "columns": ["path", "lines_reviewed", "bytes", "sha256_short", "finding", "status"],
        "rows": rows,
        "total_files": len(rows),
        "review_commit": git("rev-parse", "HEAD")[:12],
        "method": (
            "Every tracked file is hashed, line counted and run through fixed mechanical "
            "rules (empty file, missing trailing newline, TODO/FIXME, placeholder value, "
            "hardcoded-secret shape, bare except, debug print, oversized file/line, "
            "unclosed HTML). Findings are reproducible by running "
            "`python3 -m pipeline.repo_review`."
        ),
    }


def main() -> None:
    payload = build()
    rows = payload["rows"]
    payload["verification"] = {
        "rows": len(rows),
        "rows_verified": sum(1 for r in rows if r.get("_verified")),
        "rows_flagged": sum(1 for r in rows if not r.get("_verified")),
        "unverified_cells": 0,
        "flagged_reasons": {"flagged by an automated review rule":
                            sum(1 for r in rows if not r.get("_verified"))},
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "repo_review.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"repo_review: {len(rows)} files, {payload['verification']['rows_flagged']} flagged")


if __name__ == "__main__":
    main()
