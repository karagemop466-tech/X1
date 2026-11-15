#!/usr/bin/env python3
"""Immutable, timestamped capture of the official NFL injury report.

Session `arena-8e329878-x1` (round 4). Standard library only, so the scheduled
GitHub Actions job needs no install step.

What it does
------------
1. Fetches https://www.nfl.com/injuries/ and keeps the response bytes' SHA-256,
   the UTC clock time of the read and the server's own Date header.
2. Parses the club tables with a strict parser. The parser is pinned to the
   layout it was written against (table header, club-name subtitle, matchup
   strip). Any drift in those fields FAILS the run (non-zero exit) rather than
   publishing a blank. Each failure is also written to the read log.
3. Appends one line per read to `reads.jsonl` (never rewritten). The raw HTML is
   stored gzip-compressed, named by its capture id, only when its SHA-256 differs
   from the previous distinct capture, so a re-read of an unchanged page costs one
   log line, not a copy.
4. Writes the row-level table of each NEW capture and a `delta_latest.json`
   that lists what changed since the previous distinct capture. The site
   publishes deltas; levels stay in the store.

Subcommands
-----------
    capture            fetch live, parse, append, store (exit 1 on any failure)
    parse FILE         parse a local HTML file, print a summary, write nothing
    import FILE ASOF SOURCE
                       store an earlier raw capture as a labelled baseline
    check              freshness + integrity of the store (exit 1 on failure)

Store layout (all under data/captures/official_injuries/)
---------------------------------------------------------
    reads.jsonl                 append-only log, one line per read attempt
    captures.jsonl              append-only index, one line per distinct capture
    raw/<capture_id>.html.gz    the exact decoded HTML that was parsed
    rows/<capture_id>.csv       the parsed player rows of that capture
    delta_latest.json           derived: changes since the previous capture
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORE = os.path.join(ROOT, "data", "captures", "official_injuries")
URL = "https://www.nfl.com/injuries/"
PARSER_VERSION = "official_injuries_v1"

# Pinned layout. If NFL.com changes any of these, the run fails loudly.
EXPECTED_HEADER = ["Player", "Position", "Injuries", "Practice Status", "Game Status"]
KNOWN_PRACTICE = {
    "",
    "Full Participation in Practice",
    "Limited Participation in Practice",
    "Did Not Participate In Practice",
}
KNOWN_GAME = {"", "Out", "Doubtful", "Questionable"}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MAX_STALE_HOURS = 6.0  # freshness budget for the 3-hourly schedule


class CaptureError(Exception):
    """A failure that must stop the run loudly."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


# --------------------------------------------------------------------- parsing
@dataclass
class Table:
    club: Optional[str]
    header: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    first_cell_links: List[Optional[str]] = field(default_factory=list)


class _Parser(HTMLParser):
    """Collects matchup-strip abbreviations, club subtitles and d3 tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.in_title = False
        self.abbr_stack: List[str] = []       # abbreviations in page order
        self.nick_to_abbr: Dict[str, str] = {}
        self.club: Optional[str] = None
        self.tables: List[Table] = []
        self._capture: Optional[str] = None   # which text we are collecting
        self._buf: List[str] = []
        self._pending_subtitle = False
        self._in_table: Optional[Table] = None
        self._in_thead = False
        self._cell: Optional[List[str]] = None
        self._cell_is_first = False
        self._row: Optional[List[str]] = None
        self._row_links: List[Optional[str]] = []
        self._cell_href: Optional[str] = None
        self._last_abbr: Optional[str] = None
        self._pending_fullname_end = False
        self._tag_stack: List[str] = []

    # helpers
    def _cls(self, attrs: List[Tuple[str, Optional[str]]]) -> str:
        return " ".join(v or "" for k, v in attrs if k == "class")

    def handle_starttag(self, tag: str, attrs) -> None:
        cls = self._cls(attrs)
        self._tag_stack.append(tag)
        if tag == "title":
            self.in_title = True
            self._buf = []
        if tag == "span" and "nfl-c-matchup-strip__team-abbreviation" in cls:
            self._capture = "abbr"
            self._buf = []
        elif tag == "a" and "nfl-c-matchup-strip__team-fullname" in cls:
            self._capture = "fullname"
            self._buf = []
        elif tag == "div" and "d3-o-section-sub-title" in cls:
            self._pending_subtitle = True
        elif tag == "span" and self._pending_subtitle:
            self._capture = "club"
            self._buf = []
            self._pending_subtitle = False
        elif tag == "table" and "d3-o-table" in cls:
            self._in_table = Table(club=self.club)
        elif self._in_table is not None:
            if tag == "thead":
                self._in_thead = True
            elif tag == "tr":
                self._row = []
                self._row_links = []
            elif tag in ("td", "th"):
                self._cell = []
                self._cell_is_first = len(self._row or []) == 0
                self._cell_href = None
            elif tag == "a" and self._cell is not None and self._cell_is_first:
                href = dict(attrs).get("href")
                if href and self._cell_href is None:
                    self._cell_href = href

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        if tag == "title" and self.in_title:
            self.title = squash("".join(self._buf))
            self.in_title = False
        if self._capture == "abbr" and tag == "span":
            self._last_abbr = squash("".join(self._buf))
            self._capture = None
        elif self._capture == "fullname" and tag == "a":
            nick = squash("".join(self._buf))
            if self._last_abbr and nick:
                self.nick_to_abbr[nick] = self._last_abbr
            self._capture = None
        elif self._capture == "club" and tag == "span":
            self.club = squash("".join(self._buf))
            self._capture = None
        if self._in_table is not None:
            if tag == "thead":
                self._in_thead = False
            elif tag in ("td", "th") and self._cell is not None:
                if self._row is not None:
                    self._row.append(squash("".join(self._cell)))
                    if self._cell_is_first:
                        self._row_links.append(self._cell_href)
                self._cell = None
            elif tag == "tr":
                if self._row is not None:
                    if self._in_thead:
                        self._in_table.header = self._row
                    else:
                        self._in_table.rows.append(self._row)
                        self._in_table.first_cell_links.append(self._row_links[0] if self._row_links else None)
                self._row = None
            elif tag == "table":
                self.tables.append(self._in_table)
                self._in_table = None

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self._buf.append(data)
        elif self._capture in ("abbr", "fullname", "club"):
            self._buf.append(data)
        elif self._cell is not None:
            self._cell.append(data)


def parse_html(html: str) -> Dict[str, object]:
    """Parse the injury page. Raises CaptureError on any layout drift."""
    p = _Parser()
    p.feed(html)
    p.close()

    m = re.search(r"Week\s+(\d+)\s+of the\s+(\d{4})\s+Season", p.title)
    if not m:
        raise CaptureError(f"week/season not found in page title: {p.title!r}")
    week, season = int(m.group(1)), int(m.group(2))

    if not p.tables:
        raise CaptureError("no 'd3-o-table' tables found: layout drift or blocked page")

    flags: List[str] = []
    rows_out: List[Dict[str, object]] = []
    for t in p.tables:
        if t.header != EXPECTED_HEADER:
            raise CaptureError(f"table header drift: {t.header!r} (pinned {EXPECTED_HEADER!r})")
        if not t.club:
            raise CaptureError("a table has no club-name subtitle above it")
        abbr = p.nick_to_abbr.get(t.club)
        if not abbr:
            raise CaptureError(f"club subtitle {t.club!r} not found in the matchup strip")
        seen = set()
        for cells, link in zip(t.rows, t.first_cell_links):
            if len(cells) != 5:
                raise CaptureError(f"{abbr}: row has {len(cells)} cells, pinned 5: {cells!r}")
            player, position, injury, practice, game = cells
            if not player:
                raise CaptureError(f"{abbr}: row with an empty player name")
            if practice not in KNOWN_PRACTICE:
                raise CaptureError(f"{abbr} {player}: unknown practice status {practice!r}")
            if game not in KNOWN_GAME:
                raise CaptureError(f"{abbr} {player}: unknown game status {game!r}")
            row_flags: List[str] = []
            if player in seen:
                row_flags.append("duplicate player within club table")
            seen.add(player)
            if game and not injury:
                row_flags.append("game designation printed with no injury description")
            if injury and not practice:
                row_flags.append("injury printed with no practice status")
            if not link:
                row_flags.append("player profile link missing")
            rows_out.append(
                {
                    "team": abbr,
                    "club_label": t.club,
                    "player": player,
                    "position": position,
                    "injury": injury,
                    "practice_status": practice,
                    "game_status": game,
                    "player_url": ("https://www.nfl.com" + link) if link and link.startswith("/") else (link or ""),
                    "row_flags": "; ".join(row_flags),
                }
            )
    tables_by_club = {t.club for t in p.tables}
    if len(tables_by_club) != len(p.tables):
        flags.append("two tables share one club subtitle")
    matchup_teams = sorted(set(p.nick_to_abbr.values()))
    if len(matchup_teams) != len(p.tables):
        flags.append(
            f"matchup strip lists {len(matchup_teams)} clubs but {len(p.tables)} injury tables were parsed"
        )
    return {
        "week": week,
        "season": season,
        "title": p.title,
        "tables": len(p.tables),
        "clubs": sorted({r["team"] for r in rows_out}),
        "rows": rows_out,
        "page_flags": flags,
        "nick_to_abbr": p.nick_to_abbr,
    }


# --------------------------------------------------------------------- fetch
def fetch(url: str, timeout: float = 45.0, retries: int = 3) -> Tuple[int, bytes, Dict[str, str], datetime]:
    """Return (status, body bytes as decoded from transfer encoding, headers, fetched_at)."""
    last = "unknown"
    for attempt in range(1, retries + 1):
        fetched_at = utc_now()
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                headers = {k.lower(): v for k, v in resp.headers.items()}
                if headers.get("content-encoding", "").lower() == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return resp.status, raw, headers, fetched_at
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code} {exc.reason}"
        except Exception as exc:  # noqa: BLE001 - the capture must report, not crash silently
            last = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(2 * attempt)
    raise CaptureError(f"fetch failed after {retries} attempts: {last}")


# --------------------------------------------------------------------- store
def _read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _append_jsonl(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, sort_keys=True) + "\n")


def _key(row: dict) -> Tuple[str, str]:
    return row["team"], row["player"]


def delta(prev_rows: List[dict], new_rows: List[dict]) -> Dict[str, object]:
    """Player-level change since the previous distinct capture (never the level)."""
    a = {_key(r): r for r in prev_rows}
    b = {_key(r): r for r in new_rows}
    added = [b[k] for k in sorted(set(b) - set(a))]
    removed = [a[k] for k in sorted(set(a) - set(b))]
    changed = []
    for k in sorted(set(a) & set(b)):
        diffs = {}
        for f in ("injury", "practice_status", "game_status", "position"):
            if a[k][f] != b[k][f]:
                diffs[f] = {"from": a[k][f], "to": b[k][f]}
        if diffs:
            changed.append({"team": k[0], "player": k[1], "changes": diffs})
    return {
        "added": [{"team": r["team"], "player": r["player"], "game_status": r["game_status"], "practice_status": r["practice_status"]} for r in added],
        "removed": [{"team": r["team"], "player": r["player"], "game_status": r["game_status"], "practice_status": r["practice_status"]} for r in removed],
        "changed": changed,
    }


def capture(now: Optional[datetime] = None) -> Dict[str, object]:
    status, raw, headers, fetched_at = fetch(URL)
    sha = hashlib.sha256(raw).hexdigest()
    reads_path = os.path.join(STORE, "reads.jsonl")
    captures_path = os.path.join(STORE, "captures.jsonl")
    read = {
        "fetched_at_utc": iso(fetched_at),
        "url": URL,
        "http_status": status,
        "server_date": headers.get("date"),
        "bytes": len(raw),
        "sha256": sha,
        "parser": PARSER_VERSION,
    }
    try:
        if status != 200:
            raise CaptureError(f"HTTP status {status}")
        parsed = parse_html(raw.decode("utf-8", "replace"))
    except CaptureError as exc:
        read["error"] = str(exc)
        _append_jsonl(reads_path, read)
        raise

    captures = _read_jsonl(captures_path)
    previous = captures[-1] if captures else None
    read["week"], read["season"] = parsed["week"], parsed["season"]
    read["tables"], read["rows"] = parsed["tables"], len(parsed["rows"])
    read["page_flags"] = parsed["page_flags"]
    read["row_flags"] = sum(1 for r in parsed["rows"] if r["row_flags"])

    if previous and previous["sha256"] == sha:
        read["stored_as"] = previous["capture_id"]
        read["new_capture"] = False
        _append_jsonl(reads_path, read)
        return {"new_capture": False, "read": read}

    capture_id = fetched_at.strftime("%Y%m%dT%H%M%SZ") + "_" + sha[:12]
    raw_path = os.path.join(STORE, "raw", capture_id + ".html.gz")
    rows_path = os.path.join(STORE, "rows", capture_id + ".csv")
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    os.makedirs(os.path.dirname(rows_path), exist_ok=True)
    with gzip.GzipFile(raw_path, "wb", mtime=0) as fh:
        fh.write(raw)
    cols = ["team", "club_label", "player", "position", "injury", "practice_status", "game_status", "player_url", "row_flags"]
    with open(rows_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in parsed["rows"]:
            w.writerow({c: r[c] for c in cols})

    read["stored_as"] = capture_id
    read["new_capture"] = True
    _append_jsonl(reads_path, read)
    entry = {
        "capture_id": capture_id,
        "fetched_at_utc": iso(fetched_at),
        "server_date": headers.get("date"),
        "sha256": sha,
        "bytes": len(raw),
        "week": parsed["week"],
        "season": parsed["season"],
        "clubs": len(parsed["clubs"]),
        "tables": parsed["tables"],
        "rows": len(parsed["rows"]),
        "row_flags": read["row_flags"],
        "page_flags": parsed["page_flags"],
        "raw_path": os.path.relpath(raw_path, ROOT),
        "rows_path": os.path.relpath(rows_path, ROOT),
        "previous_capture_id": previous["capture_id"] if previous else None,
    }
    _append_jsonl(captures_path, entry)

    prev_rows: List[dict] = []
    if previous:
        with open(os.path.join(ROOT, previous["rows_path"]), encoding="utf-8") as fh:
            prev_rows = list(csv.DictReader(fh))
    d = delta(prev_rows, parsed["rows"])
    delta_doc = {
        "generated_at_utc": iso(fetched_at),
        "capture_id": capture_id,
        "previous_capture_id": previous["capture_id"] if previous else None,
        "source": URL,
        "delta": d,
        "counts": {
            "added": len(d["added"]),
            "removed": len(d["removed"]),
            "changed": len(d["changed"]),
        },
    }
    with open(os.path.join(STORE, "delta_latest.json"), "w", encoding="utf-8") as fh:
        json.dump(delta_doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return {"new_capture": True, "entry": entry, "read": read, "delta": delta_doc}


def import_sample(path: str, asof: str, source: str) -> Dict[str, object]:
    """Store an earlier raw official capture as a baseline, labelled as an import.

    Used once, for the 2026-11-14 page captured by an earlier CI run and kept in git
    history (ci/raw-samples). Its `method` is `import` and `fetched_at_utc` is the
    commit time of that file, the earliest clock time the history can prove.
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    sha = hashlib.sha256(raw).hexdigest()
    captures_path = os.path.join(STORE, "captures.jsonl")
    if any(c["sha256"] == sha for c in _read_jsonl(captures_path)):
        raise CaptureError("this capture is already in the store")
    parsed = parse_html(raw.decode("utf-8", "replace"))
    capture_id = asof.replace("-", "").replace(":", "").replace("Z", "Z").replace("T", "T") + "_" + sha[:12]
    raw_path = os.path.join(STORE, "raw", capture_id + ".html.gz")
    rows_path = os.path.join(STORE, "rows", capture_id + ".csv")
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    os.makedirs(os.path.dirname(rows_path), exist_ok=True)
    with gzip.GzipFile(raw_path, "wb", mtime=0) as fh:
        fh.write(raw)
    cols = ["team", "club_label", "player", "position", "injury", "practice_status", "game_status", "player_url", "row_flags"]
    with open(rows_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in parsed["rows"]:
            w.writerow({c: r[c] for c in cols})
    entry = {
        "capture_id": capture_id,
        "method": "import",
        "fetched_at_utc": asof,
        "import_source": source,
        "server_date": None,
        "sha256": sha,
        "bytes": len(raw),
        "week": parsed["week"],
        "season": parsed["season"],
        "clubs": len(parsed["clubs"]),
        "tables": parsed["tables"],
        "rows": len(parsed["rows"]),
        "row_flags": sum(1 for r in parsed["rows"] if r["row_flags"]),
        "page_flags": parsed["page_flags"],
        "raw_path": os.path.relpath(raw_path, ROOT),
        "rows_path": os.path.relpath(rows_path, ROOT),
        "previous_capture_id": None,
    }
    _append_jsonl(captures_path, entry)
    return entry


def check(now: Optional[datetime] = None) -> List[str]:
    """Integrity + freshness of the store. Returns a list of problems (empty = healthy)."""
    now = now or utc_now()
    problems: List[str] = []
    reads = _read_jsonl(os.path.join(STORE, "reads.jsonl"))
    captures = _read_jsonl(os.path.join(STORE, "captures.jsonl"))
    if not reads:
        return ["no reads logged"]
    last_ok = [r for r in reads if "error" not in r]
    if not last_ok:
        problems.append("no successful read has ever been logged")
    else:
        age = now - datetime.strptime(last_ok[-1]["fetched_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if age > timedelta(hours=MAX_STALE_HOURS):
            problems.append(f"stale: last successful read {age} ago (budget {MAX_STALE_HOURS} h)")
    seen_ids = set()
    for c in captures:
        if c["capture_id"] in seen_ids:
            problems.append(f"duplicate capture id {c['capture_id']}")
        seen_ids.add(c["capture_id"])
        raw_path = os.path.join(ROOT, c["raw_path"])
        if not os.path.exists(raw_path):
            problems.append(f"missing raw file {c['raw_path']}")
            continue
        with gzip.open(raw_path, "rb") as fh:
            data = fh.read()
        if hashlib.sha256(data).hexdigest() != c["sha256"]:
            problems.append(f"hash mismatch {c['capture_id']}: raw bytes no longer match the logged sha256")
    return problems


def _cli(argv: List[str]) -> int:
    if not argv or argv[0] not in ("capture", "parse", "check", "import"):
        print(__doc__)
        return 2
    cmd = argv[0]
    try:
        if cmd == "capture":
            out = capture()
            if out["new_capture"]:
                e = out["entry"]
                print(f"NEW capture {e['capture_id']}: week {e['week']} season {e['season']}, "
                      f"{e['clubs']} clubs, {e['tables']} tables, {e['rows']} rows, {e['row_flags']} rows flagged")
                print(f"delta: +{out['delta']['counts']['added']} -{out['delta']['counts']['removed']} "
                      f"~{out['delta']['counts']['changed']}")
            else:
                print(f"unchanged (sha256 matches {out['read']['stored_as']}); read logged")
            problems = check()
            for p in problems:
                print("CHECK:", p)
            return 1 if problems else 0
        if cmd == "parse":
            with open(argv[1], encoding="utf-8", errors="replace") as fh:
                parsed = parse_html(fh.read())
            print(json.dumps({k: v for k, v in parsed.items() if k not in ("rows", "nick_to_abbr")}, indent=2))
            print(f"rows: {len(parsed['rows'])}")
            return 0
        if cmd == "import":
            # import FILE ASOF_UTC SOURCE_LABEL
            entry = import_sample(argv[1], argv[2], argv[3])
            print(f"IMPORTED {entry['capture_id']}: {entry['rows']} rows, {entry['tables']} tables")
            return 0
        if cmd == "check":
            problems = check()
            for p in problems:
                print("PROBLEM:", p)
            print("store healthy" if not problems else f"{len(problems)} problem(s)")
            return 1 if problems else 0
    except CaptureError as exc:
        print(f"CAPTURE FAILED: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
