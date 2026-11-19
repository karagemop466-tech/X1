#!/usr/bin/env python3
"""Week 11 official injury report: hash-bound parse, delta series and freshness.

Session `arena-2d1ba329-x1` (branch `arena/2d1ba329-x1`).

Inputs (nothing is fetched by this file):
  * data/ledger/injuries/ledger.jsonl  - the append-only ledger written by
    tools/snapshot_ledger.py (raw bytes, UTC capture time, SHA-256 of the page).
  * data/ledger/injuries/raw/*.html.gz - the stored page bytes.

Outputs (regenerated, deterministic):
  * data/week11/captures.json       - one record per Week 11 capture: hashes, flags,
                                      parsed table/row counts, clubs with no table.
  * data/week11/latest_read.tsv     - the parse of the most recent Week 11 capture
                                      (one row per official listing, with source link).
  * data/week11/deltas.tsv          - only what changed between consecutive DISTINCT
                                      captures (added / removed / field changed).
  * data/week11/parse_checks.json   - the expected-shape assertions and their results.

Rules enforced (fail loudly, never publish a blank by accident):
  * every raw file re-hashes to the SHA-256 the ledger recorded;
  * every club table has the five expected headers and five cells per row;
  * a club shown in a matchup strip with no table is a COVERAGE GAP, reported as
    such, never read as "healthy";
  * an unknown practice or game-status string is reported, not mapped.

Usage:
  python3 tools/week11/build_week11.py          # rebuild data/week11/*
  python3 tools/week11/build_week11.py --check  # rebuild in memory, fail if committed files differ
"""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEDGER_DIR = os.path.join(ROOT, "data", "ledger", "injuries")
LEDGER = os.path.join(LEDGER_DIR, "ledger.jsonl")
OUT = os.path.join(ROOT, "data", "week11")
SOURCE_URL = "https://www.nfl.com/injuries/"
SEASON = 2026
WEEK = 11
HEADERS = ["Player", "Position", "Injuries", "Practice Status", "Game Status"]
PRACTICE_OK = {
    "", "Full Participation in Practice", "Limited Participation in Practice",
    "Did Not Participate In Practice",
}
GAME_OK = {"", "Questionable", "Doubtful", "Out"}


class ParseError(Exception):
    pass


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ").strip()


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def read_ledger() -> List[Dict[str, Any]]:
    rows = []
    with open(LEDGER, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def week11_captures(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Week 11 reads in CAPTURE-TIME order.

    The chain order is not always chronological: two writers can fork the ledger (see the
    fork note in data/ledger/injuries/ledger.jsonl), and a re-chained line keeps its
    original capture time. Deltas must follow capture time, so sort on it here.
    """
    out = []
    for e in entries:
        if e.get("error") or e.get("http_status") != 200:
            continue
        if e.get("season") != SEASON or e.get("week") != WEEK:
            continue
        out.append(e)
    return sorted(out, key=lambda e: (e["captured_at_utc"], e.get("seq", 0)))


_UUID_RE = re.compile(rb"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _content_sha(page: bytes) -> str:
    return hashlib.sha256(_UUID_RE.sub(b"<uuid>", page)).hexdigest()


def load_raw(entry: Dict[str, Any]) -> Tuple[bytes, Dict[str, str]]:
    path = os.path.join(LEDGER_DIR, entry["file"])
    with open(path, "rb") as fh:
        gz_bytes = fh.read()
    checks = {"gzip_sha256": hashlib.sha256(gz_bytes).hexdigest() == entry["gzip_sha256"]}
    page = gzip.decompress(gz_bytes)
    # sha256 = exact decoded bytes (integrity). content_sha256 = bytes with random UUIDs masked
    # (change detection), exactly as tools/snapshot_ledger.py defines them.
    checks["sha256_exact_bytes"] = hashlib.sha256(page).hexdigest() == entry["sha256"]
    checks["content_sha256_uuid_masked"] = _content_sha(page) == entry["content_sha256"]
    if not all(checks.values()):
        raise ParseError(f"hash mismatch for {entry['file']}: {checks}")
    return page, checks


def parse_page(page: bytes) -> Dict[str, Any]:
    """Return games, club tables and rows from one capture. Raises on shape drift."""
    t = page.decode("utf-8", "replace")

    # Matchup strips: two per game, in order. Abbreviation and full nickname.
    strips = []
    strip_pos = [m.start() for m in re.finditer(r"nfl-c-matchup-strip__team-abbreviation", t)]
    for p in strip_pos:
        seg = t[p:p + 900]
        ab = re.search(r"nfl-c-matchup-strip__team-abbreviation\"[^>]*>\s*([A-Z]{2,3})\s*<", seg)
        fn = re.search(r"nfl-c-matchup-strip__team-fullname\"[^>]*>\s*([^<]+?)\s*<", seg)
        if not ab or not fn:
            raise ParseError("matchup strip without abbreviation or nickname")
        strips.append({"pos": p, "abbr": ab.group(1), "nick": _collapse(html.unescape(fn.group(1)))})
    if len(strips) % 2 or not strips:
        raise ParseError(f"expected an even, non-zero number of matchup strips, found {len(strips)}")
    nick_to_abbr = {s["nick"]: s["abbr"] for s in strips}
    if len(nick_to_abbr) != len(strips):
        raise ParseError("duplicate club nickname across matchup strips")

    games = []
    for i in range(0, len(strips), 2):
        a, b = strips[i], strips[i + 1]
        games.append({"game_index": i // 2 + 1, "away_or_first": a["abbr"], "home_or_second": b["abbr"],
                      "nicks": [a["nick"], b["nick"]], "pos": a["pos"]})

    # Day headers, e.g. "THURSDAY, NOVEMBER 19TH", located before each game.
    day_marks = [(m.start(), _collapse(m.group(0))) for m in re.finditer(
        r"(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY), (JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|"
        r"AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER) \d{1,2}(ST|ND|RD|TH)", t)]
    for g in games:
        prior = [d for pos, d in day_marks if pos < g["pos"]]
        g["day"] = prior[-1] if prior else None

    # Club sub-titles and the table that follows each one.
    subs = [(m.start(), m.end(), _collapse(html.unescape(m.group(1))))
            for m in re.finditer(r'd3-o-section-sub-title"><span>(.*?)</span>', t)]
    tables = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"<table[^>]*>.*?</table>", t, re.S)]
    if len(subs) != len(strips):
        raise ParseError(f"club sub-titles ({len(subs)}) differ from matchup strips ({len(strips)})")

    clubs = []
    for idx, (spos, send, nick) in enumerate(subs):
        if nick not in nick_to_abbr:
            raise ParseError(f"sub-title {nick!r} is not a matchup-strip nickname")
        nxt = subs[idx + 1][0] if idx + 1 < len(subs) else len(t)
        inside = [tb for tb in tables if spos < tb[0] < nxt]
        if len(inside) > 1:
            raise ParseError(f"more than one table under {nick!r}")
        club = {"nick": nick, "abbr": nick_to_abbr[nick], "table": None, "rows": []}
        if inside:
            table_html = inside[0][2]
            heads = [_collapse(_text(h)) for h in re.findall(r"<th[^>]*>(.*?)</th>", table_html, re.S)]
            if heads != HEADERS:
                raise ParseError(f"unexpected headers under {nick!r}: {heads}")
            body = re.search(r"<tbody>(.*?)</tbody>", table_html, re.S)
            if not body:
                raise ParseError(f"table without tbody under {nick!r}")
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S):
                cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
                if len(cells) != 5:
                    raise ParseError(f"row with {len(cells)} cells under {nick!r}")
                href = re.search(r'href="(/players/[^"]+)"', cells[0])
                aria = re.search(r'aria-label="Visit (.+?) profile page"', cells[0])
                name = _collapse(_text(cells[0]))
                if not href or not aria:
                    raise ParseError(f"player cell without profile link under {nick!r}: {name!r}")
                if _collapse(html.unescape(aria.group(1))) != name:
                    raise ParseError(f"name/link mismatch under {nick!r}: {name!r}")
                row = {
                    "player": name,
                    "profile_path": href.group(1),
                    "position": _collapse(_text(cells[1])),
                    "injury": _collapse(_text(cells[2])),
                    "practice_status": _collapse(_text(cells[3])),
                    "game_status": _collapse(_text(cells[4])),
                }
                if not row["position"]:
                    raise ParseError(f"blank position under {nick!r}: {name!r}")
                club["rows"].append(row)
            club["table"] = True
        clubs.append(club)

    for g in games:
        g["clubs"] = [c for c in clubs if c["abbr"] in (g["away_or_first"], g["home_or_second"])]
    return {"games": games, "clubs": clubs, "strip_count": len(strips)}


def shape_checks(parsed: Dict[str, Any]) -> Dict[str, Any]:
    rows = [r for c in parsed["clubs"] for r in c["rows"]]
    unknown_practice = sorted({r["practice_status"] for r in rows} - PRACTICE_OK)
    unknown_game = sorted({r["game_status"] for r in rows} - GAME_OK)
    return {
        "matchup_strips": parsed["strip_count"],
        "games": len(parsed["games"]),
        "clubs_in_strips": len(parsed["clubs"]),
        "clubs_with_table": sum(1 for c in parsed["clubs"] if c["table"]),
        "clubs_without_table": [c["abbr"] for c in parsed["clubs"] if not c["table"]],
        "player_rows": len(rows),
        "unknown_practice_values": unknown_practice,
        "unknown_game_status_values": unknown_game,
        "unknown_values_pass": not unknown_practice and not unknown_game,
    }


def key_of(club_abbr: str, row: Dict[str, Any]) -> str:
    return f"{club_abbr}|{row['profile_path']}"


def deltas_between(prev: Dict[str, Any], cur: Dict[str, Any]) -> List[Dict[str, str]]:
    """Level-to-level changes; only changed fields are listed."""
    def index(p):
        d = {}
        for c in p["clubs"]:
            for r in c["rows"]:
                d[key_of(c["abbr"], r)] = (c["abbr"], r)
        return d
    a, b = index(prev), index(cur)
    out = []
    for k in sorted(set(a) | set(b)):
        if k in a and k not in b:
            club, r = a[k]
            out.append({"club": club, "player": r["player"], "field": "row",
                        "before": "listed", "after": "not listed in this capture"})
        elif k in b and k not in a:
            club, r = b[k]
            out.append({"club": club, "player": r["player"], "field": "row",
                        "before": "not listed", "after": "listed"})
        else:
            club, ra = a[k]
            _, rb = b[k]
            for f in ("position", "injury", "practice_status", "game_status"):
                if ra[f] != rb[f]:
                    out.append({"club": club, "player": rb["player"], "field": f,
                                "before": ra[f], "after": rb[f]})
    return out


def build() -> Dict[str, Any]:
    entries = read_ledger()
    caps = week11_captures(entries)
    if not caps:
        raise ParseError("no Week 11 captures in the ledger")

    records = []
    parsed_by_capture: Dict[str, Dict[str, Any]] = {}
    for e in caps:
        page, checks = load_raw(e)
        parsed = parse_page(page)
        sc = shape_checks(parsed)
        parsed_by_capture[e["content_sha256"]] = parsed
        records.append({
            "captured_at_utc": e["captured_at_utc"],
            "file": e["file"],
            "flags": e.get("flags", []),
            "content_sha256": e["content_sha256"],
            "gzip_sha256": e["gzip_sha256"],
            "entry_sha256": e["entry_sha256"],
            "bytes": e["bytes"],
            "hash_checks_pass": all(checks.values()),
            "title": e.get("title"),
            "shape": sc,
        })

    # Distinct content in capture order; repeated identical reads are counted, not re-diffed.
    distinct: List[Dict[str, Any]] = []
    seen_hash = None
    for rec in records:
        if rec["content_sha256"] != seen_hash:
            distinct.append(rec)
            seen_hash = rec["content_sha256"]
    delta_rows: List[Dict[str, str]] = []
    for i in range(1, len(distinct)):
        prev, cur = distinct[i - 1], distinct[i]
        for d in deltas_between(parsed_by_capture[prev["content_sha256"]],
                                parsed_by_capture[cur["content_sha256"]]):
            delta_rows.append({"from_utc": prev["captured_at_utc"], "to_utc": cur["captured_at_utc"], **d})

    latest = records[-1]
    latest_parsed = parsed_by_capture[latest["content_sha256"]]
    level_rows = []
    for g in latest_parsed["games"]:
        for c in g["clubs"]:
            for r in c["rows"]:
                level_rows.append({
                    "capture_utc": latest["captured_at_utc"], "capture_content_sha256": latest["content_sha256"],
                    "game_day": g["day"] or "", "matchup": f"{g['away_or_first']} @ {g['home_or_second']}",
                    "club": c["abbr"], "player": r["player"], "profile_path": r["profile_path"],
                    "position": r["position"], "injury": r["injury"], "practice_status": r["practice_status"],
                    "game_status": r["game_status"], "source_url": SOURCE_URL,
                })
    gaps = []
    for g in latest_parsed["games"]:
        for c in g["clubs"]:
            if not c["table"]:
                gaps.append({"capture_utc": latest["captured_at_utc"], "club": c["abbr"],
                             "matchup": f"{g['away_or_first']} @ {g['home_or_second']}",
                             "reason": "matchup strip shown, no club table in this capture (not read as healthy)"})

    return {
        "records": records, "delta_rows": delta_rows, "level_rows": level_rows, "gaps": gaps,
        "distinct_captures": [d["captured_at_utc"] for d in distinct],
        "games": [{"day": g["day"], "matchup": f"{g['away_or_first']} @ {g['home_or_second']}"}
                  for g in latest_parsed["games"]],
        "latest_capture_utc": latest["captured_at_utc"],
    }


def _tsv(path: str, cols: List[str], rows: List[Dict[str, Any]]) -> str:
    lines = ["\t".join(cols)]
    for r in rows:
        lines.append("\t".join(str(r.get(c, "")).replace("\t", " ").replace("\n", " ") for c in cols))
    return "\n".join(lines) + "\n"


def outputs(res: Dict[str, Any]) -> Dict[str, str]:
    cap_json = json.dumps({
        "source_url": SOURCE_URL,
        "season": SEASON, "week": WEEK,
        "method": "tools/week11/build_week11.py parses the raw bytes stored by tools/snapshot_ledger.py; nothing is fetched here",
        "captures": res["records"],
        "distinct_capture_count": len(res["distinct_captures"]),
        "latest_capture_utc": res["latest_capture_utc"],
        "games": res["games"],
        "coverage_gaps_latest": res["gaps"],
    }, indent=2, ensure_ascii=False) + "\n"
    checks = {
        "all_hash_checks_pass": all(r["hash_checks_pass"] for r in res["records"]),
        "all_unknown_values_pass": all(r["shape"]["unknown_values_pass"] for r in res["records"]),
        "latest_player_rows": len(res["level_rows"]),
        "latest_clubs_without_table": [g["club"] for g in res["gaps"]],
        "delta_rows": len(res["delta_rows"]),
    }
    return {
        "captures.json": cap_json,
        "latest_read.tsv": _tsv(os.path.join(OUT, "latest_read.tsv"),
                                ["capture_utc", "capture_content_sha256", "game_day", "matchup", "club", "player",
                                 "profile_path", "position", "injury", "practice_status", "game_status", "source_url"],
                                res["level_rows"]),
        "deltas.tsv": _tsv(os.path.join(OUT, "deltas.tsv"),
                           ["from_utc", "to_utc", "club", "player", "field", "before", "after"],
                           res["delta_rows"]),
        "parse_checks.json": json.dumps(checks, indent=2, ensure_ascii=False) + "\n",
    }


def main(argv: List[str]) -> int:
    res = build()
    outs = outputs(res)
    if "--check" in argv:
        bad = []
        for name, text in outs.items():
            p = os.path.join(OUT, name)
            cur = open(p, encoding="utf-8").read() if os.path.exists(p) else None
            if cur != text:
                bad.append(name)
        if bad:
            print("STALE: regenerate with python3 tools/week11/build_week11.py:", ", ".join(bad))
            return 1
        print("week11 outputs match the ledger")
        return 0
    os.makedirs(OUT, exist_ok=True)
    for name, text in outs.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote data/week11/{name} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ParseError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
