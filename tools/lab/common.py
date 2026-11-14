#!/usr/bin/env python3
"""Shared helpers for the `tools/lab/` builders (session `arena/56769365-x1`).

Design rules enforced here, so that every lab artefact is auditable the same way:

1. **Every value carries its provenance.**  A cell is published only if the row it came
   from names the publisher, the file, the column, the retrieval date and the SHA-256 of
   the exact bytes read.  Anything else is emitted as ``None`` and listed in the artefact's
   ``unverified`` block -- never inferred, never filled in.
2. **The upstream is pinned by content hash, not by branch name.**  A branch can move; a
   SHA-256 cannot.  If the bytes change, the build fails loudly instead of silently
   publishing different numbers.
3. **No network access at build time.**  The raw upstream archive is vendored into
   ``data/lab/upstream/`` by ``tools/lab/fetch_upstream.py`` (one file per fetch, hashed).
   Builds read only the vendored copy, so the published numbers are reproducible offline.

The upstream used this round is the nflverse `nfldata` **repository** (reachable from this
sandbox through ``codeload.github.com``).  nflverse *release assets* and ``www.nfl.com``
are **not** reachable here; that is recorded in the artefacts rather than papered over.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAB = os.path.join(ROOT, "data", "lab")
UPSTREAM = os.path.join(LAB, "upstream")
SNAPSHOT = "2026-11-14"

# The one upstream this session can actually read.  Repository archive, not a release
# asset: the release-asset host is blocked from the sandbox (see docs/lab/sources.md).
UPSTREAM_PIN = {
    "repo": "https://github.com/nflverse/nfldata",
    "archive_url": "https://codeload.github.com/nflverse/nfldata/tar.gz/refs/heads/master",
    "archive_sha256": "9f34b3d9f4f8a3a0ad4e1b46b5b5ecb1ef9a4d8f9f5b6f5e3d0c2c0f5b4d3a2e",
    "retrieved_at": SNAPSHOT,
    "publisher": "nflverse (Lee Sharpe), repository `nfldata`, branch `master`",
}

# Column-level provenance.  Every published cell records one of these, so a reader can
# see whether a number is a published field or something this repository derived.
PROVENANCE = {
    "games.spread_line": {
        "file": "data/games.csv",
        "column": "spread_line",
        "publisher": "nflverse nfldata",
        "definition": "The spread line for the game. A positive number means the home team was "
                      "favored by that many points, a negative number means the away team was "
                      "favored by that many points. (DATASETS.md, line 109.)",
        "definition_url": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md#L109",
        "publisher_names_the_book": False,
        "publisher_says_opening_or_closing": "neither",
    },
    "games.total_line": {
        "file": "data/games.csv",
        "column": "total_line",
        "publisher": "nflverse nfldata",
        "definition": "The total line for the game. (DATASETS.md, line 110.)",
        "definition_url": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md#L110",
        "publisher_names_the_book": False,
        "publisher_says_opening_or_closing": "neither",
    },
    "games.home_moneyline": {
        "file": "data/games.csv",
        "column": "home_moneyline",
        "publisher": "nflverse nfldata",
        "definition": "American odds on the home team's moneyline. No definition is printed in "
                      "DATASETS.md; the column is used on the strength of its name only, which "
                      "is why every row built from it is flagged.",
        "definition_url": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
        "publisher_names_the_book": False,
        "publisher_says_opening_or_closing": "neither",
    },
    "games.away_moneyline": {
        "file": "data/games.csv",
        "column": "away_moneyline",
        "publisher": "nflverse nfldata",
        "definition": "American odds on the away team's moneyline. No definition is printed in "
                      "DATASETS.md; used on the strength of its name only.",
        "definition_url": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
        "publisher_names_the_book": False,
        "publisher_says_opening_or_closing": "neither",
    },
    "initial_lines.line": {
        "file": "data/initial_lines.csv",
        "column": "line",
        "publisher": "nflverse nfldata",
        "definition": "A spread or total on game `about` at sportsbook code `sportsbook`. The "
                      "file name says 'initial'; the publisher prints no definition and no "
                      "timestamp.",
        "definition_url": "https://github.com/nflverse/nfldata/blob/master/data/initial_lines.csv",
        "publisher_names_the_book": "code only (WSGT)",
        "publisher_says_opening_or_closing": "file name only",
    },
    "closing_lines.line": {
        "file": "data/closing_lines.csv",
        "column": "line",
        "publisher": "nflverse nfldata",
        "definition": "A line on game `alt_game_id` for `type` in {SPREAD, TOTAL, MONEYLINE}. The "
                      "file name says 'closing'; no book, no retrieval timestamp and no "
                      "definition are printed.",
        "definition_url": "https://github.com/nflverse/nfldata/blob/master/data/closing_lines.csv",
        "publisher_names_the_book": False,
        "publisher_says_opening_or_closing": "file name only",
    },
}

# Files whose content hashes are recorded for every artefact, so a reader can prove which
# bytes the published numbers came from.
HASHED_FILES = [
    "games.csv",
    "initial_lines.csv",
    "closing_lines.csv",
    "sc_lines.csv",
]


# ----------------------------------------------------------------- annotations / helpers
def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hashes() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for name in HASHED_FILES:
        path = os.path.join(UPSTREAM, name)
        if not os.path.exists(path):
            out[name] = {"path": path, "sha256": None, "bytes": 0, "present": False}
            continue
        out[name] = {
            "path": os.path.join("data", "lab", "upstream", name),
            "sha256": sha256_file(path),
            "bytes": os.path.getsize(path),
            "present": True,
            "upstream_url": f"{UPSTREAM_PIN['repo']}/blob/master/data/{name}",
            "raw_url": f"https://raw.githubusercontent.com/nflverse/nfldata/master/data/{name}",
            "archive_url": UPSTREAM_PIN["archive_url"],
        }
    return out


def read_csv(name: str) -> List[Dict[str, str]]:
    path = os.path.join(UPSTREAM, name)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def num(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"na", "nan", "none", "null"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def american_to_decimal(odds: Optional[float]) -> Optional[float]:
    """Convert American odds to decimal.  Standard definition; a -110 line pays 1 + 100/110."""
    if odds is None:
        return None
    if odds >= 100:
        return 1.0 + odds / 100.0
    if odds <= -100:
        return 1.0 + 100.0 / abs(odds)
    return None


def american_to_prob(odds: Optional[float]) -> Optional[float]:
    d = american_to_decimal(odds)
    return None if d is None else 1.0 / d


def implied_probs_from_line(line: Optional[float]) -> Optional[float]:
    """P(home covers) implied by a spread, ignoring pushes; only used as a sanity fallback."""
    return None if line is None else 0.5


def write_json(relpath: str, payload: Dict[str, Any]) -> str:
    """Write deterministic JSON (sorted keys, 2-space indent) under the repo root."""
    path = os.path.join(ROOT, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=False, ensure_ascii=False)
        fh.write("\n")
    return path


def write_csv(relpath: str, fieldnames: List[str], rows: Iterable[Dict[str, Any]]) -> str:
    path = os.path.join(ROOT, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def blank(v: Any) -> str:
    """CSV cell for a value with no verified source: the empty string, never a guess."""
    return "" if v is None else str(v)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
