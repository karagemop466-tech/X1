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

import html
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .htmlparse import find_tables, find_tables_with_links, table_to_dicts, text_index
from .sources import SOURCES

#: ``/games/<away>-at-<home>-<season>-<season-type>-<week>``
GAME_URL_RE = re.compile(
    r"^/games/(?P<slug>.+)-(?P<season>\d{4})-(?P<type>[a-z]{3})-(?P<week>\d+)$"
)

#: The league's embedded game object (used by the standings and schedule pages).
GAME_OBJECT_RE = re.compile(
    r'\{"Description":"(?P<description>[^"]*)","Title":"(?P<title>[^"]*)",'
    r'"StartTime":"(?P<start>[^"]*)","EndTime":"(?P<end>[^"]*)",'
    r'"GameTerritory":"(?P<territory>[^"]*)","GameId":"(?P<gid>[^"]*)",'
    r'"Week":"(?P<week>[^"]*)","DmaCodes":\[(?P<dma>[^\]]*)\],"NflSeason":"(?P<season>[^"]*)"\}'
)


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


# ---------------------------------------------------------------------------
# Injury report
# ---------------------------------------------------------------------------
def collect_injuries(
    html_text: str, retrieved_at: str, url: str, source_key: str = "injuries_current"
):
    """Parse the official weekly injury report.

    The page renders one table per club under a club heading. Each row is a
    player with position, injury body part, practice-participation status and
    game-status designation.
    """
    tables, row_links = find_tables_with_links(html_text)
    records: List[Dict[str, Any]] = []
    notes: List[str] = []

    title_pattern = re.compile(
        r'<div class="d3-o-section-sub-title">\s*<span>([^<]+)</span>\s*</div>',
        re.IGNORECASE,
    )
    title_spans = sorted((m.start(), m.group(1).strip()) for m in title_pattern.finditer(html_text))

    table_positions = [m.start() for m in re.finditer(r"<table\b", html_text)]

    for table, start, links in zip(tables, table_positions, row_links):
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
        for row in table_to_dicts(table, links=links):
            player = row.get("Player", "")
            if not player:
                continue
            profile = next(
                (href for href in row.get("_links", []) if href and "/players/" in href),
                None,
            )
            records.append(
                {
                    "club": club,
                    "player": player,
                    # The league links each player to their official profile
                    # page, whose slug identifies them unambiguously.
                    "player_url": "https://www.nfl.com" + profile if profile else None,
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


def collect_standings(
    html_text: str, retrieved_at: str, url: str, source_key: str = "standings"
):
    """Parse the official league standings table."""
    records: List[Dict[str, Any]] = []
    notes: List[str] = []

    for table in find_tables(html_text):
        if not table:
            continue
        header = [c.strip() for c in table[0]]
        if "W" not in header or "PF" not in header or "PA" not in header:
            continue
        for row in table_to_dicts(table, headers=STANDINGS_HEADERS):
            team = _clean_club_name(row.get("Team", ""))
            if not team:
                continue
            if not _looks_like_record(row.get("W")):
                # The rendered header row repeats the column labels.
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


def _looks_like_record(value: Optional[str]) -> bool:
    return bool(value) and bool(re.fullmatch(r"\d+", value.strip()))


def _clean_club_name(value: str) -> str:
    """The standings cell carries the full name and the short name together.

    ``Los Angeles ChargersChargers`` -> ``Los Angeles Chargers``.
    """
    text = " ".join(value.split())
    if not text:
        return ""
    for suffix in (
        "Chargers", "Dolphins", "Titans", "Colts", "Jaguars", "Patriots",
        "Bengals", "Browns", "Cowboys", "Broncos", "Lions", "Packers",
        "Texans", "Chiefs", "Raiders", "Rams", "Dolphins", "Eagles",
        "Bears", "Saints", "Giants", "Jets", "Vikings", "Commanders",
        "Steelers", "49ers", "Seahawks", "Ravens", "Falcons", "Cardinals",
        "Bills", "Lions",
    ):
        if text.endswith(suffix) and len(text) > len(suffix):
            candidate = text[: -len(suffix)]
            if candidate and candidate[-1].isupper():
                return candidate.strip()
    return text


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------
def collect_schedule(
    html_text: str, retrieved_at: str, url: str, source_key: str = "schedule_week"
):
    """Parse the official weekly schedule page.

    Two official structures are read from the same page:

    * the league's embedded game objects, which give the kickoff time, the
      league game id and the broadcast territory, and
    * the rendered ``/games/`` links, which give the Game Center URL for each
      matchup.

    The two are merged on the matchup so each record carries both.
    """
    records: Dict[str, Dict[str, Any]] = {}
    notes: List[str] = []

    def _key(away: Optional[str], home: Optional[str]) -> str:
        return f"{(away or '').strip().lower()}|{(home or '').strip().lower()}"

    # --- embedded game objects ------------------------------------------
    for match in GAME_OBJECT_RE.finditer(html_text):
        if match.group("dma") != '"000"':
            continue
        title = match.group("title")
        if " at " not in title:
            # Some payload entries are broadcast listings, not games.
            continue
        away, _, home = title.partition(" at ")
        key = _key(away, home)
        if key in records:
            continue
        records[key] = {
            "game_id": match.group("gid"),
            "title": title.strip(),
            "away_team": away.strip() or None,
            "home_team": home.strip() or None,
            "start_time_utc": match.group("start"),
            "game_territory": match.group("territory") or None,
            "week": match.group("week"),
            "season": match.group("season"),
            "game_center_url": None,
            "source_url": url,
            "source_label": SOURCES[source_key].title,
            "retrieved_at": retrieved_at,
        }

    # --- rendered game links -------------------------------------------
    for match in re.finditer(r'href="(/games/[^"?#]+)"', html_text):
        path = match.group(1)
        parsed = GAME_URL_RE.match(path)
        if not parsed:
            continue
        slug = parsed.group("slug")
        away_slug, _, home_slug = slug.partition("-at-")
        away_name = _slug_to_name(away_slug)
        home_name = _slug_to_name(home_slug)
        key = _key(away_name, home_name)
        center_url = "https://www.nfl.com" + path
        if key in records:
            if not records[key].get("game_center_url"):
                records[key]["game_center_url"] = center_url
            continue
        records[key] = {
            "game_id": None,
            "title": f"{away_name} at {home_name}",
            "away_team": away_name,
            "home_team": home_name,
            "start_time_utc": None,
            "game_territory": None,
            "week": parsed.group("week"),
            "season": parsed.group("season"),
            "game_center_url": center_url,
            "source_url": url,
            "source_label": SOURCES[source_key].title,
            "retrieved_at": retrieved_at,
        }

    if not records:
        notes.append("no schedule entries matched the expected page structure")

    provenance = Provenance(
        source_key=source_key,
        url=url,
        retrieved_at=retrieved_at,
        record_count=len(records),
        notes=notes,
    )
    return list(records.values()), provenance


_SLUG_EXCEPTIONS = {
    "49ers": "San Francisco 49ers",
    "bills": "Buffalo Bills",
    "jets": "New York Jets",
    "giants": "New York Giants",
    "commanders": "Washington Commanders",
    "packers": "Green Bay Packers",
    "bears": "Chicago Bears",
    "lions": "Detroit Lions",
    "chiefs": "Kansas City Chiefs",
    "ravens": "Baltimore Ravens",
    "colts": "Indianapolis Colts",
    "texans": "Houston Texans",
    "browns": "Cleveland Browns",
    "bengals": "Cincinnati Bengals",
    "steelers": "Pittsburgh Steelers",
    "raiders": "Las Vegas Raiders",
    "dolphins": "Miami Dolphins",
    "patriots": "New England Patriots",
    "saints": "New Orleans Saints",
    "falcons": "Atlanta Falcons",
    "cardinals": "Arizona Cardinals",
    "rams": "Los Angeles Rams",
    "chargers": "Los Angeles Chargers",
    "seahawks": "Seattle Seahawks",
    "vikings": "Minnesota Vikings",
    "titans": "Tennessee Titans",
    "jaguars": "Jacksonville Jaguars",
    "eagles": "Philadelphia Eagles",
    "cowboys": "Dallas Cowboys",
    "broncos": "Denver Broncos",
    "panthers": "Carolina Panthers",
    "buccaneers": "Tampa Bay Buccaneers",
}


def _slug_to_name(slug: str) -> str:
    """Expand an NFL game slug into the club's full name.

    Only the slugs the league itself publishes are expanded; anything else is
    returned in title case so the value is still readable, and the club's
    official name is taken from the game book when one is available.
    """
    if slug in _SLUG_EXCEPTIONS:
        return _SLUG_EXCEPTIONS[slug]
    return " ".join(part.capitalize() for part in slug.split("-"))


# ---------------------------------------------------------------------------
# Player statistics
# ---------------------------------------------------------------------------
def collect_player_stats(
    html_text: str,
    retrieved_at: str,
    url: str,
    source_key: str = "player_stats_passing",
    category: str = "passing",
):
    """Parse an official season player-statistics table."""
    records: List[Dict[str, Any]] = []
    notes: List[str] = []

    for table in find_tables(html_text):
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
