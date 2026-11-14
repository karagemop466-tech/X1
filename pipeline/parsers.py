"""Dataset parsers. Each returns a list of flat, source-stamped rows.

Every row carries `_source_url` (the official page the value was read from) and
`_source_org`. Any field the parser could not read is left as `None` and named in
`_unverified`; such a row is `_verified: False` and is routed to the
"Flagged for Review" page by the site.
"""

from __future__ import annotations

import re
import urllib.parse
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import htmlutil as H
from .sources import CLUB_DOMAINS

NOW = lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()

KICKOFF_RE = re.compile(r"\d{1,2}:\d{2}\s*(?:AM|PM)", re.I)
DATE_HEADING_RE = re.compile(
    r"^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY),?\s+.+$", re.I
)
RECORD_RE = re.compile(r"^\(?(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\)?$")
TZ_RE = re.compile(r"^(E|C|M|P)(S|D)T$", re.I)
WEEK_RE = re.compile(r"Week\s+(\d+)", re.I)
SEASON_RE = re.compile(r"(20\d{2})")

INJURY_HEADER = ["player", "position", "injuries", "practice status", "game status"]


# --------------------------------------------------------------------- helpers
def make_row(
    values: Dict[str, Any],
    source_url: str,
    source_label: str,
    source_org: str,
    flags: Optional[List[str]] = None,
    allow_blank: Optional[set] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "_source_url": source_url,
        "_source_label": source_label,
        "_source_org": source_org,
        "_retrieved_at": NOW(),
        "_flags": list(flags or []),
    }
    row.update(values)
    blanks = allow_blank or set()
    unverified = [k for k, v in values.items() if (v is None or v == "") and k not in blanks]
    if blanks:
        row["_allow_blank"] = sorted(blanks)
    row["_unverified"] = unverified
    row["_verified"] = not unverified and not row["_flags"]
    return row


def _pick_table(tables: List[Dict[str, Any]], min_rows: int = 1) -> Optional[Dict[str, Any]]:
    if not tables:
        return None
    return max(tables, key=lambda t: len(t["rows"]))


def _parse_record(text: str) -> Optional[Tuple[int, int, int]]:
    match = RECORD_RE.match((text or "").strip())
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    return None


# ------------------------------------------------------------------- standings
# NFL.com prints the standings table without a text header row; the page's own
# LEGEND block defines W, L, T, PCT, HOME, ROAD, DIV, CONF, PF, PA, NET PTS and
# STRK. DIV PCT / CONF PCT / NON-CONF / LAST 5 are positional and are validated
# by the arithmetic check below instead of by a printed label.
STANDINGS_COLUMNS = [
    "W", "L", "T", "PCT", "PF", "PA", "NET_PTS",
    "HOME", "ROAD", "DIV", "DIV_PCT", "CONF", "CONF_PCT", "NON_CONF", "STRK", "LAST_5",
]
LEGEND_LABELLED = {"W", "L", "T", "PCT", "HOME", "ROAD", "DIV", "CONF", "PF", "PA", "NET_PTS", "STRK"}


def parse_standings(doc: H.DocParser, source_url: str, retrieved: str) -> Dict[str, Any]:
    table = _pick_table(doc.tables)
    if table is None or not table["rows"]:
        return {"rows": [], "columns": [], "error": "no standings table found"}

    header_raw = table.get("header") or []
    header_clean = [h for h in header_raw if h]
    columns_labeled = len(header_clean) >= len(STANDINGS_COLUMNS)

    rows: List[Dict[str, Any]] = []
    for cells in table["rows"]:
        if len(cells) < 2:
            continue
        first = cells[0]
        abbrev = H.abbrev_from_imgs(first.get("imgs", []))
        slug = None
        for href in first.get("hrefs", []):
            slug = H.slug_from_href(href)
            if slug:
                break
        values_list = [H.cell_text(c) for c in cells[1:]]
        if len(values_list) < len(STANDINGS_COLUMNS):
            values_list += [None] * (len(STANDINGS_COLUMNS) - len(values_list))

        values: Dict[str, Any] = {"team_abbrev": abbrev, "team_slug": slug}
        if slug:
            values["team_name"] = H.titleize_slug(slug)
        else:
            values["team_name"] = H.cell_text(first) or None
        for name, raw in zip(STANDINGS_COLUMNS, values_list):
            values[name] = raw

        flags: List[str] = []
        if not abbrev:
            flags.append("team abbreviation could not be read from the official logo asset")
        if not slug:
            flags.append("team could not be resolved to an official NFL.com team page")
        if not columns_labeled:
            flags.append("column labels are not printed in the official table markup")
        rows.append(
            make_row(
                values,
                source_url=source_url,
                source_label="NFL.com — 2026 League Standings (regular season)",
                source_org="NFL",
                flags=flags,
            )
        )

    consistency = _check_standings(rows)
    return {
        "rows": rows,
        "columns": ["team_name"] + (header_clean if columns_labeled else STANDINGS_COLUMNS),
        "columns_officially_labelled": columns_labeled,
        "consistency_check": consistency,
        "note": (
            "Only the metrics defined in the official LEGEND block (W, L, T, PCT, HOME, "
            "ROAD, DIV, CONF, PF, PA, NET PTS, STRK) are labelled by the source. DIV PCT, "
            "CONF PCT, NON-CONF and LAST 5 are positional; their order is validated by "
            "the arithmetic consistency check, not by a printed label."
        ),
    }


def _check_standings(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    checked = failed = 0
    failures: List[str] = []
    for row in rows:
        try:
            w, l, t = int(row["W"]), int(row["L"]), int(row["T"])
        except (TypeError, ValueError):
            continue
        checked += 1
        problems = []
        home = _parse_record(row.get("HOME") or "")
        road = _parse_record(row.get("ROAD") or "")
        if home and road:
            if home[0] + road[0] != w or home[1] + road[1] != l or home[2] + road[2] != t:
                problems.append("HOME+ROAD != overall record")
        try:
            if int(row["PF"]) - int(row["PA"]) != int(row["NET_PTS"]):
                problems.append("PF-PA != NET_PTS")
        except (TypeError, ValueError):
            pass
        try:
            pct = float(row["PCT"])
            games = w + l + t
            if games and abs(pct - (w + 0.5 * t) / games) > 0.02:
                problems.append("PCT inconsistent with W-L-T")
        except (TypeError, ValueError):
            pass
        if problems:
            failed += 1
            failures.append(f"{row.get('team_abbrev')}: {'; '.join(problems)}")
    return {
        "rows_checked": checked,
        "rows_failed": failed,
        "passed": failed == 0 and checked > 0,
        "failures": failures[:20],
    }


# -------------------------------------------------------------------- injuries
def parse_injuries(
    doc: H.DocParser,
    source_url: str,
    team_index: Dict[str, Dict[str, str]],
    nick_to_abbrev: Dict[str, str],
) -> Dict[str, Any]:
    week = None
    season = None
    for event in doc.events:
        if event[0] == "heading":
            match = WEEK_RE.search(event[2])
            if match:
                week = int(match.group(1))
            smatch = SEASON_RE.search(event[2])
            if smatch:
                season = int(smatch.group(1))
            if week and season:
                break

    # Walk the event stream, keeping context so each injury table can be tied to
    # a team and a game.
    current_date: Optional[str] = None
    block_texts: List[str] = []
    recent_texts: deque = deque(maxlen=10)
    recent_team_links: deque = deque(maxlen=6)   # abbreviations, most recent last
    current_meta: List[str] = []
    last_text: Optional[str] = None
    rows: List[Dict[str, Any]] = []
    tables_seen = 0
    link_queue: List[Tuple[str, Optional[str]]] = []  # (abbrev, slug) in document order

    for event in doc.events:
        if event[0] == "heading":
            if DATE_HEADING_RE.match(event[2]):
                current_date = event[2]
                block_texts = []
            continue
        if event[0] == "text":
            block_texts.append(event[1])
            recent_texts.append(event[1])
            last_text = event[1]
            continue
        if event[0] == "link":
            href, _text, imgs = event[1], event[2], event[3]
            slug = H.slug_from_href(href)
            if slug:
                # Resolve through the official standings index first (reliable),
                # then fall back to the club logo referenced by the link.
                for ab, meta in team_index.items():
                    if meta.get("slug") == slug:
                        abbrev = ab
                        break
                if abbrev is None:
                    abbrev = H.abbrev_from_imgs(imgs)
                if not recent_team_links or recent_team_links[-1] != abbrev:
                    recent_team_links.append(abbrev)
                if len(recent_team_links) <= 1 or recent_team_links[-2] != abbrev:
                    current_meta = list(recent_texts)
                block_texts = []
            continue
        if event[0] != "table":
            continue

        table = doc.tables[event[1]]
        header = [h.lower() for h in (table.get("header") or [])]
        if header != INJURY_HEADER:
            continue
        tables_seen += 1

        # Team identity: the club name printed immediately above the table is
        # the primary key; the official team links just above it are the check.
        text_abbrev = nick_to_abbrev.get((last_text or "").strip().lower())
        abbrev = text_abbrev
        flags: List[str] = []
        if text_abbrev is None:
            if recent_team_links:
                abbrev = recent_team_links[0]
                flags.append(
                    "club label was not printed above this table; team taken from the "
                    "official team link that precedes it"
                )
            else:
                flags.append("team could not be resolved for this injury table")
        elif text_abbrev not in recent_team_links:
            flags.append(
                f"club label '{last_text}' is not among the official team links "
                "immediately above this table"
            )

        meta = dict(current_meta and {"game_meta": current_meta} or {})
        kickoff = None
        tv = None
        for i, text in enumerate(current_meta):
            if KICKOFF_RE.search(text):
                kickoff = text
                for follow in current_meta[i + 1:]:
                    if not TZ_RE.match(follow):
                        tv = follow
                        break
                break

        team_meta = team_index.get(abbrev or "", {})
        for cells in table["rows"]:
            if len(cells) < 5:
                continue
            values = {
                "team_abbrev": abbrev,
                "team_name": team_meta.get("name"),
                "player": H.cell_text(cells[0]) or None,
                "position": H.cell_text(cells[1]) or None,
                "injuries": H.cell_text(cells[2]) or None,
                "practice_status": H.cell_text(cells[3]) or None,
                "game_status": H.cell_text(cells[4]) or None,
                "game_date": current_date,
                "kickoff_et": kickoff,
                "broadcast": tv,
                "week": week,
                "season": season,
                "player_url": (cells[0].get("hrefs") or [None])[0],
            }
            row_flags = list(flags)
            if not values["player_url"]:
                row_flags.append("player profile link missing")
            rows.append(
                make_row(
                    values,
                    source_url=source_url,
                    source_label=(
                        f"NFL.com — Official NFL Injury Report, Week {week} of the "
                        f"{season} season"
                        if week and season
                        else "NFL.com — Official NFL Injury Report"
                    ),
                    source_org="NFL",
                    flags=row_flags,
                    allow_blank={"injuries", "game_status"},
                )
            )
        last_text = None

    return {"rows": rows, "tables_parsed": tables_seen, "week": week, "season": season}


# ---------------------------------------------------------------- depth charts
UNIT_ORDER = ["Offense", "Defense", "Special Teams"]

# A real depth chart prints a short position code in the first column and player
# links after it. A roster page prints jersey numbers and names instead, so this
# is what tells the two apart when a club uses a generic page title.
POSITION_RE = re.compile(r"^[A-Z]{1,3}$")


def depth_chart_quality(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    if not rows:
        return {"rows": 0, "position_like": 0.0, "with_link": 0.0}
    position_like = sum(1 for r in rows if POSITION_RE.match(str(r.get("position") or "")))
    with_link = sum(1 for r in rows if r.get("player_url"))
    return {
        "rows": len(rows),
        "position_like": round(position_like / len(rows), 3),
        "with_link": round(with_link / len(rows), 3),
    }


def parse_depth_chart(
    doc: H.DocParser, source_url: str, abbrev: str, team_name: str
) -> Dict[str, Any]:
    # Map each table to the unit heading that precedes it.
    unit_by_table: Dict[int, str] = {}
    last_heading: Optional[str] = None
    heading_seen: List[str] = []
    for event in doc.events:
        if event[0] == "heading":
            text = event[2].strip()
            for unit in UNIT_ORDER:
                if text.lower().startswith(unit.lower()):
                    last_heading = unit
                    heading_seen.append(unit)
                    break
        elif event[0] == "table":
            unit_by_table[event[1]] = last_heading or ""

    rows: List[Dict[str, Any]] = []
    slot_counters: Dict[Tuple[str, str], int] = {}
    for index, table in enumerate(doc.tables):
        if not table["rows"]:
            continue
        unit = unit_by_table.get(index)
        if not unit:
            unit = UNIT_ORDER[index] if index < len(UNIT_ORDER) else f"Unit {index + 1}"
        for cells in table["rows"]:
            if not cells:
                continue
            position = H.cell_text(cells[0]) or None
            # Clubs print several rows with the same label (WR, CB, DL, S ...).
            # Each is its own slot, so "2nd string" means second in that slot.
            slot_key = (unit, position or "?")
            slot_counters[slot_key] = slot_counters.get(slot_key, 0) + 1
            slot = slot_counters[slot_key]
            for depth, cell in enumerate(cells[1:], start=1):
                player = H.cell_text(cell)
                if not player:
                    continue
                href = (cell.get("hrefs") or [None])[0]
                if href and href.startswith("/"):
                    href = urllib.parse.urljoin(source_url, href)
                flags: List[str] = []
                if not position:
                    flags.append("position label missing")
                if not href:
                    flags.append("player profile link missing")
                rows.append(
                    make_row(
                        {
                            "team_abbrev": abbrev,
                            "team_name": team_name,
                            "unit": unit,
                            "position": position,
                            "slot": slot,
                            "depth": depth,
                            "player": player,
                            "player_url": href,
                        },
                        source_url=source_url,
                        source_label=f"{team_name} official site — Depth Chart ({unit})",
                        source_org=f"Club — {team_name}",
                        flags=flags,
                    )
                )
    return {
        "rows": rows,
        "tables_parsed": len([t for t in doc.tables if t["rows"]]),
        "quality": depth_chart_quality(rows),
    }


# ------------------------------------------------------------------ team stats
def parse_team_stats(
    doc: H.DocParser, source_url: str, label: str, team_index: Dict[str, Dict[str, str]]
) -> Dict[str, Any]:
    table = _pick_table(doc.tables)
    if table is None or not table["rows"]:
        return {"rows": [], "columns": [], "error": "no team stats table found"}

    header = [h for h in (table.get("header") or []) if h]
    columns_labeled = bool(header) and len(header) >= 2

    rows: List[Dict[str, Any]] = []
    for cells in table["rows"]:
        if len(cells) < 2:
            continue
        first = cells[0]
        abbrev = H.abbrev_from_imgs(first.get("imgs", []))
        text_label = H.cell_text(first)
        team_name = team_index.get(abbrev or "", {}).get("name") or text_label or None
        raw_values = [H.cell_text(c) for c in cells[1:]]
        if columns_labeled:
            columns = header[1:] if len(header) == len(cells) else [f"metric_{i+1}" for i in range(len(raw_values))]
            values = dict(zip(columns, raw_values))
        else:
            columns = [f"metric_{i+1}" for i in range(len(raw_values))]
            values = dict(zip(columns, raw_values))
        row_flags: List[str] = []
        if not abbrev:
            row_flags.append("team abbreviation could not be read from the official logo asset")
        if not columns_labeled:
            row_flags.append("official page does not print column labels for this table")
        row = make_row(
            {"team_abbrev": abbrev, "team_name": team_name, **values},
            source_url=source_url,
            source_label=f"NFL.com — 2026 Team Stats, {label}",
            source_org="NFL",
            flags=row_flags,
        )
        if not columns_labeled:
            row["_verified"] = False
        rows.append(row)

    return {
        "rows": rows,
        "columns": ["team_name"] + columns,
        "columns_officially_labelled": columns_labeled,
        "header_raw": table.get("header") or [],
    }
