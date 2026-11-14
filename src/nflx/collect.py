"""Collectors for the official NFL endpoints registered in :mod:`nflx.sources`.

Each collector returns a list of plain dictionaries. Every record includes:

``source_url``
    The exact URL the value was read from.
``source_label``
    The human-readable source title shown on the site.
``retrieved_at``
    UTC timestamp of the retrieval.

Anything that cannot be read from the source is left as ``None``. Nothing is
inferred, defaulted, or back-filled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .htmlparse import find_tables, table_to_dicts, text_index
from .sources import SOURCES

_WEEK_HEADER_RE = re.compile(r"^Injuries\s*-\s*WEEK\s+(\d+)", re.IGNORECASE)


@dataclass
class Provenance:
    """Bookkeeping for one retrieval."""

    source_key: str
    url: str
    retrieved_at: str
    record_count: int
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_url": self.url,
            "retrieved_at": self.retrieved_at,
            "record_count": self.record_count,
            "notes": self.notes,
        }


def _source_meta(source_key: str) -> Dict[str, str]:
    source = SOURCES[source_key]
    return {"source_key": source_key, "source_url": source.url, "source_label": source.title}


# ---------------------------------------------------------------------------
# Injury report
# ---------------------------------------------------------------------------
def collect_injuries(html: str, retrieved_at: str, url: str, source_key: str = "injuries_current"):
    """Parse the official weekly injury report.

    The page renders one table per club under a club heading. Each row is a
    player with position, injury body part, practice-participation status and
    game-status designation.
    """
    tables = find_tables(html)
    records: List[Dict[str, Any]] = []
    notes: List[str] = []

    # Map table start offsets to the nearest preceding club name.
    index = text_index(html)
    clubs = {
        offset: text
        for offset, text in index
        if re.fullmatch(r"[A-Z][A-Za-z&'.\- ]+", text) and len(text) <= 30
    }

    # The injury page nests tables inside "nfl-c-matchup-strip" blocks that also
    # carry both club abbreviations. Resolve the club from the preceding
    # section-title span instead.
    title_spans = []
    title_pattern = re.compile(
        r'<div class="d3-o-section-sub-title">\s*<span>([^<]+)</span>\s*</div>',
        re.IGNORECASE,
    )
    for match in title_pattern.finditer(html):
        title_spans.append((match.start(), match.group(1).strip()))
    title_spans.sort()

    table_positions = [m.start() for m in re.finditer(r"<table\b", html)]
    table_ends = [m.end() for m in re.finditer(r"</table>", html)]

    for table, start, end in zip(tables, table_positions, table_ends):
        if not table:
            continue
        header = [c.strip() for c in table[0]]
        if "Game Status" not in header:
            continue
        club = None
        for pos, name in title_spans:
            if pos < start:
                club = name
            else:
                break
        if club is None:
            notes.append("injury table without a resolvable club heading skipped")
            continue
        rows = table_to_dicts(table)
        for row in rows:
            player = row.get("Player", "")
            if not player:
                continue
            records.append(
                {
                    "club": club,
                    "player": player,
                    "position": row.get("Position") or None,
                    "injuries": row.get("Injuries") or None,
                    "practice_status": row.get("Practice Status") or None,
                    "game_status": row.get("Game Status") or None,
                    "source_url": url,
                    "source_label": SOURCES[source_key].title,
                    "retrieved_at": retrieved_at,
                }
            )

    provenance = Provenance(
        source_key=source_key,
        url=url,
        retrieved_at=retrieved_at,
        record_count=len(records),
        notes=notes,
    )
    return records, provenance


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------
STANDINGS_HEADERS = [
    "Team",
    "W",
    "L",
    "T",
    "PCT",
    "PF",
    "PA",
    "Net Pts",
    "Home",
    "Road",
    "Div",
    "Div Pct",
    "Conf",
    "Conf Pct",
    "Non-Conf",
    "Strk",
    "Last 5",
]


def collect_standings(html: str, retrieved_at: str, url: str, source_key: str = "standings"):
    """Parse the official league standings table."""
    records: List[Dict[str, Any]] = []
    notes: List[str] = []

    for table in find_tables(html):
        if not table:
            continue
        header = [c.strip() for c in table[0]]
        if "W" not in header or "PF" not in header or "PA" not in header:
            continue
        for row in table_to_dicts(table, headers=STANDINGS_HEADERS):
            team = row.get("Team", "")
            if not team:
                continue
            records.append(
                {
                    "team": team,
                    "wins": _int_or_none(row.get("W")),
                    "losses": _int_or_none(row.get("L")),
                    "ties": _int_or_none(row.get("T")),
                    "win_pct": _float_or_none(row.get("PCT")),
                    "points_for": _int_or_none(row.get("PF")),
                    "points_against": _int_or_none(row.get("PA")),
                    "net_points": _int_or_none(row.get("Net Pts")),
                    "home_record": row.get("Home") or None,
                    "road_record": row.get("Road") or None,
                    "div_record": row.get("Div") or None,
                    "conf_record": row.get("Conf") or None,
                    "non_conf_record": row.get("Non-Conf") or None,
                    "streak": row.get("Strk") or None,
                    "last_5": row.get("Last 5") or None,
                    "source_url": url,
                    "source_label": SOURCES[source_key].title,
                    "retrieved_at": retrieved_at,
                }
            )
        break
    else:
        notes.append("no standings table matched the expected column signature")

    provenance = Provenance(
        source_key=source_key,
        url=url,
        retrieved_at=retrieved_at,
        record_count=len(records),
        notes=notes,
    )
    return records, provenance


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------
def collect_schedule(html: str, retrieved_at: str, url: str, source_key: str = "schedule_week"):
    """Parse the official weekly schedule, including final scores.

    The page embeds a JSON description block for every game. That block carries
    the canonical title, kickoff time and game id, which is more reliable than
    scraping the rendered scoreboard.
    """
    records: List[Dict[str, Any]] = []
    notes: List[str] = []

    seen = set()
    game_pattern = re.compile(
        r'\{"Description":"(?P<description>[^"]*)","Title":"(?P<title>[^"]*)",'
        r'"StartTime":"(?P<start>[^"]*)","EndTime":"(?P<end>[^"]*)",'
        r'"GameTerritory":"(?P<territory>[^"]*)","GameId":"(?P<gid>[^"]*)",'
        r'"Week":"(?P<week>[^"]*)","DmaCodes":\[(?P<dma>[^\]]*)\],"NflSeason":"(?P<season>[^"]*)"\}'
    )
    for match in game_pattern.finditer(html):
        if match.group("dma") != '"000"':
            continue
        gid = match.group("gid")
        title = match.group("title")
        key = (gid, title)
        if key in seen:
            continue
        seen.add(key)
        away, _, home = title.partition(" at ")
        records.append(
            {
                "game_id": gid,
                "title": title,
                "away_team": away.strip() or None,
                "home_team": home.strip() or None,
                "start_time_utc": match.group("start"),
                "game_territory": match.group("territory") or None,
                "week": match.group("week"),
                "season": match.group("season"),
                "source_url": url,
                "source_label": SOURCES[source_key].title,
                "retrieved_at": retrieved_at,
            }
        )

    if not records:
        notes.append("no schedule game objects matched the expected JSON shape")

    provenance = Provenance(
        source_key=source_key,
        url=url,
        retrieved_at=retrieved_at,
        record_count=len(records),
        notes=notes,
    )
    return records, provenance


# ---------------------------------------------------------------------------
# Player statistics
# ---------------------------------------------------------------------------
def collect_player_stats(
    html: str,
    retrieved_at: str,
    url: str,
    source_key: str = "player_stats_passing",
    category: str = "passing",
):
    """Parse an official season player-statistics table.

    Column labels are category specific, so the first row of the table is used
    as the header and the column semantics are recorded alongside each value.
    """
    records: List[Dict[str, Any]] = []
    notes: List[str] = []

    for table in find_tables(html):
        if not table:
            continue
        rows = [r for r in table if any(c.strip() for c in r)]
        if len(rows) < 2:
            continue
        header = [c.strip() for c in rows[0]]
        if not header or header[0] != "Player":
            continue
        for row in table_to_dicts(table):
            player = row.get("Player", "")
            if not player:
                continue
            record: Dict[str, Any] = {
                "category": category,
                "player": player,
                "source_url": url,
                "source_label": SOURCES[source_key].title,
                "retrieved_at": retrieved_at,
            }
            for key, value in row.items():
                if key == "Player":
                    continue
                record[f"stat_{key.lower().replace(' ', '_')}"] = value or None
            records.append(record)
        break
    else:
        notes.append("no player-statistics table matched the expected header signature")

    provenance = Provenance(
        source_key=source_key,
        url=url,
        retrieved_at=retrieved_at,
        record_count=len(records),
        notes=notes,
    )
    return records, provenance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _int_or_none(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    text = value.strip().replace(",", "")
    if not text or not re.fullmatch(r"-?\d+", text):
        return None
    return int(text)


def _float_or_none(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = value.strip()
    if not re.fullmatch(r"-?\d+(\.\d+)?", text):
        return None
    return float(text)
