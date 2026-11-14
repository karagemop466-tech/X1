"""Parser for the NFL's official Game Book PDF (the league statistical summary).

The Game Book is the most complete primary source the league publishes for a
single game. It contains:

* officials by position (referee, umpire, line judge, …)
* game-day weather (temperature, humidity, wind, roof status, surface)
* the official starting lineups for both teams (offence *and* defence)
* the substitution list, the "did not play" list and the "not active" list
* the complete individual box score for both teams
* per-team aggregate statistics and per-player playtime percentages

That is enough to derive, for each club, who actually starts at each position
group and who is available behind them - the raw material for a depth-chart
deficiency model.

The PDF text layer is read in *layout* mode, which preserves the horizontal
column boundaries the league uses to print the two clubs side by side. The
column boundaries are recovered from the printed headers rather than guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Position groups used for depth analysis. Backup quality is only meaningful
#: inside a position group, because a backup safety cannot cover for a tackle.
POSITION_GROUPS: Dict[str, List[str]] = {
    "QB": ["QB"],
    "RB": ["RB", "FB"],
    "WR": ["WR"],
    "TE": ["TE"],
    "OL": ["LT", "LG", "C", "RG", "RT", "OL", "T/G", "C/G", "G/T", "T", "G"],
    "DL": ["DL", "DT", "DE", "NT"],
    "LB": ["LB", "OLB", "ILB", "MLB"],
    "DB": ["CB", "DB", "S", "FS", "SS", "SAF"],
    "ST": ["K", "P", "LS"],
}

OFFICIAL_ROLES = (
    "Referee",
    "Umpire",
    "Line Judge",
    "Field Judge",
    "Side Judge",
    "Down Judge",
    "Back Judge",
    "Replay Official",
)

OFFICIAL_RE = re.compile(
    r"(?P<role>" + "|".join(re.escape(r) for r in OFFICIAL_ROLES) + r")\s*:\s*"
    r"(?P<name>[^(]+?)\s*\((?P<num>\d+)\)"
)

SCORE_ROW_RE = re.compile(
    r"^(?P<side>VISITOR|HOME)\s*:\s*(?P<club>\S.*?)\s+"
    r"(?P<q1>\d+)\s+(?P<q2>\d+)\s+(?P<q3>\d+)\s+(?P<q4>\d+)\s+"
    r"(?P<ot>\d+)\s+(?P<total>\d+)\s*$"
)

#: A player cell: position, jersey number and the player's name.
CELL_RE = re.compile(
    r"^\s*(?P<pos>\d?[A-Z]{1,3}(?:/[A-Z])?)\s+(?P<num>\d{1,2}[A-Z]?)\s+"
    r"(?P<name>[A-Z][A-Za-z'\.\-]*(?:\s[A-Z][A-Za-z'\.\-]*)?)"
)

WEATHER_RE = re.compile(
    r"Temp:\s*(?P<temp>-?\d+(?:\.\d+)?)\D{0,4}F.*?Humidity:\s*(?P<humidity>\d+)%.*?"
    r"Wind:\s*(?P<wind>[A-Z]{1,3}\s+\d+)\s*mph",
    re.IGNORECASE,
)
WIND_CHILL_RE = re.compile(r"Wind Chill:\s*(?P<chill>-?\d+(?:\.\d+)?)", re.IGNORECASE)
ATTENDANCE_RE = re.compile(r"Paid Attendance:\s*(?P<attendance>[\d,]+)")
GAME_TIME_RE = re.compile(r"Time:\s*(?P<length>\d+:\d+)")
DATE_RE = re.compile(r"Date:\s*(?P<date>[A-Za-z]+,\s*\d{1,2}/\d{1,2}/\d{4})")
MATCHUP_RE = re.compile(
    r"^(?P<away>.+?)\s+at\s+(?P<home>.+?)\s{2,}Start Time:\s*(?P<time>.+?)\s*$"
)
VENUE_RE = re.compile(r"^\s*at\s+(?P<venue>.+?)\s*$")


@dataclass
class Official:
    role: str
    name: Optional[str]
    number: Optional[str]


@dataclass
class PlayerEntry:
    position: str
    number: Optional[str]
    name: str

    def to_dict(self) -> Dict[str, Any]:
        return {"position": self.position, "number": self.number, "name": self.name}


@dataclass
class GameBook:
    """A parsed official game book."""

    matchup: Optional[str] = None
    venue: Optional[str] = None
    date: Optional[str] = None
    start_time: Optional[str] = None
    surface: Optional[str] = None
    roof: Optional[str] = None
    temperature_f: Optional[float] = None
    humidity_pct: Optional[int] = None
    wind: Optional[str] = None
    wind_chill: Optional[float] = None
    attendance: Optional[int] = None
    game_length: Optional[str] = None
    officials: List[Official] = field(default_factory=list)
    visitor: Optional[str] = None
    home: Optional[str] = None
    visitor_points: Optional[int] = None
    home_points: Optional[int] = None
    #: ``{team: {"offense": [...], "defense": [...]}}`` from the lineup grid.
    lineups: Dict[str, Dict[str, List[PlayerEntry]]] = field(default_factory=dict)
    #: ``{team: [PlayerEntry, ...]}`` players who entered the game.
    substitutions: Dict[str, List[PlayerEntry]] = field(default_factory=dict)
    #: ``{team: [PlayerEntry, ...]}`` active but did not play.
    did_not_play: Dict[str, List[PlayerEntry]] = field(default_factory=dict)
    #: ``{team: [PlayerEntry, ...]}`` inactive list.
    not_active: Dict[str, List[PlayerEntry]] = field(default_factory=dict)
    #: The league's per-team aggregate statistics.
    team_statistics: Dict[str, Any] = field(default_factory=dict)
    #: The league's per-player playtime split.
    playtime: Dict[str, Any] = field(default_factory=dict)
    #: The published penalty log, grouped by club.
    penalty_log: Dict[str, List[str]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        def dump(entries: List[PlayerEntry]):
            return [p.to_dict() for p in entries]

        return {
            "matchup": self.matchup,
            "venue": self.venue,
            "date": self.date,
            "start_time": self.start_time,
            "surface": self.surface,
            "roof": self.roof,
            "temperature_f": self.temperature_f,
            "humidity_pct": self.humidity_pct,
            "wind": self.wind,
            "wind_chill": self.wind_chill,
            "attendance": self.attendance,
            "game_length": self.game_length,
            "officials": [
                {"role": o.role, "name": o.name, "number": o.number} for o in self.officials
            ],
            "visitor": self.visitor,
            "home": self.home,
            "visitor_points": self.visitor_points,
            "home_points": self.home_points,
            "lineups": {
                team: {unit: dump(players) for unit, players in units.items()}
                for team, units in self.lineups.items()
            },
            "substitutions": {team: dump(players) for team, players in self.substitutions.items()},
            "did_not_play": {team: dump(players) for team, players in self.did_not_play.items()},
            "not_active": {team: dump(players) for team, players in self.not_active.items()},
            "team_statistics": self.team_statistics,
            "playtime": self.playtime,
            "penalty_log": self.penalty_log,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# column geometry
# ---------------------------------------------------------------------------
def _find_token_offsets(line: str, token: str) -> List[int]:
    """Offsets of every occurrence of ``token`` in ``line``."""
    offsets: List[int] = []
    start = 0
    while True:
        index = line.find(token, start)
        if index < 0:
            break
        offsets.append(index)
        start = index + len(token)
    return offsets


def _column_boundaries(line: str, tokens: List[str]) -> Optional[List[int]]:
    """Character offsets at which each printed column begins.

    ``tokens`` is the sequence of labels the league prints, for example
    ``["Offense", "Defense", "Offense", "Defense"]``. The offsets are the
    positions of those labels in the header line, which is how the league
    itself aligns the columns.
    """
    offsets: List[int] = []
    cursor = 0
    for token in tokens:
        index = line.find(token, cursor)
        if index < 0:
            return None
        offsets.append(index)
        cursor = index + len(token)
    return offsets


def _slice_columns(line: str, offsets: List[int]) -> List[str]:
    """Cut a line into the given columns."""
    parts: List[str] = []
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < len(offsets) else len(line)
        parts.append(line[offset:end])
    return parts


def _parse_cell(text: str) -> Optional[PlayerEntry]:
    """Parse one ``POS NUM Name`` cell."""
    match = CELL_RE.match(text.strip())
    if not match:
        return None
    name = match.group("name").strip()
    if not name:
        return None
    return PlayerEntry(
        position=match.group("pos"),
        number=match.group("num"),
        name=name,
    )


def _parse_cell_list(text: str) -> List[PlayerEntry]:
    """Parse a run of ``POS NUM Name`` cells written back to back."""
    entries: List[PlayerEntry] = []
    for chunk in re.split(r",\s*(?=\d?[A-Z]{1,3}(?:/[A-Z])?\s+\d)", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        cell = _parse_cell(chunk)
        if cell is not None:
            entries.append(cell)
    return entries


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def parse_gamebook(text: str) -> GameBook:
    """Parse the extracted text layer of an official NFL Game Book PDF."""
    book = GameBook()
    lines = text.splitlines()

    _parse_header(book, lines)
    _parse_officials(book, lines)
    _parse_score(book, lines)
    _parse_lineup_grid(book, lines)
    _parse_paired_block(book, lines, "Substitutions", "substitutions")
    _parse_paired_block(book, lines, "Did Not Play", "did_not_play")
    _parse_paired_block(book, lines, "Not Active", "not_active")

    from .gamebook_stats import parse_penalty_log, parse_playtime, parse_team_statistics

    book.team_statistics = parse_team_statistics(text, book.visitor, book.home)
    book.playtime = parse_playtime(text)
    book.penalty_log = parse_penalty_log(text)
    return book


def _parse_header(book: GameBook, lines: List[str]) -> None:
    """Matchup, venue, date, kickoff, weather, attendance and game length."""
    for raw in lines[:80]:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        date_match = DATE_RE.search(stripped)
        if date_match and not book.date:
            book.date = date_match.group("date")

        match = MATCHUP_RE.match(stripped)
        if match and not book.matchup:
            away = match.group("away").strip()
            # The league prints the date on the same line as the matchup.
            away = DATE_RE.sub("", away).strip()
            home = match.group("home").strip()
            if away and home:
                book.matchup = f"{away} at {home}"
                book.start_time = match.group("time").strip()
            continue

        venue_match = VENUE_RE.match(line)
        if venue_match and not book.venue:
            book.venue = venue_match.group("venue").strip()
            continue

        attendance_match = ATTENDANCE_RE.search(stripped)
        if attendance_match:
            book.attendance = int(attendance_match.group("attendance").replace(",", ""))

        length_match = GAME_TIME_RE.search(stripped)
        if length_match and not book.game_length:
            book.game_length = length_match.group("length")

        if "Stadium" in stripped:
            if "Closed Stadium" in stripped:
                book.roof = "Closed Stadium"
            elif "Open Stadium" in stripped:
                book.roof = "Open Stadium"
            surface = re.search(r"on\s+(Field Turf|Field|Dome|Artificial Turf|Turf)", stripped)
            if surface:
                book.surface = surface.group(1)

        weather = WEATHER_RE.search(stripped)
        if weather and book.temperature_f is None:
            book.temperature_f = float(weather.group("temp"))
            book.humidity_pct = int(weather.group("humidity"))
            book.wind = weather.group("wind").strip()
        chill = WIND_CHILL_RE.search(stripped)
        if chill and book.wind_chill is None:
            book.wind_chill = float(chill.group("chill"))


def _parse_officials(book: GameBook, lines: List[str]) -> None:
    """Officials are printed as ``Role: Name (number)``."""
    seen = set()
    for raw in lines[:80]:
        for match in OFFICIAL_RE.finditer(raw):
            role = match.group("role")
            if role in seen:
                continue
            seen.add(role)
            book.officials.append(
                Official(
                    role=role,
                    name=match.group("name").strip(),
                    number=match.group("num"),
                )
            )


def _parse_score(book: GameBook, lines: List[str]) -> None:
    """The scoring line gives each club's quarter-by-quarter points."""
    for raw in lines[:120]:
        match = SCORE_ROW_RE.match(raw.strip())
        if not match:
            continue
        club = match.group("club").strip()
        total = int(match.group("total"))
        if match.group("side") == "VISITOR":
            book.visitor = club
            book.visitor_points = total
        else:
            book.home = club
            book.home_points = total


def _parse_lineup_grid(book: GameBook, lines: List[str]) -> None:
    """Parse the four-column starting-lineup grid.

    The league prints the club names, then an ``Offense / Defense / Offense /
    Defense`` header, then one row per starting slot. The column boundaries
    are taken from that header.
    """
    header_index = None
    offsets: Optional[List[int]] = None
    for index, raw in enumerate(lines[:120]):
        stripped = raw.strip()
        if stripped.startswith("Offense") and stripped.count("Offense") == 2:
            found = _column_boundaries(stripped, ["Offense", "Defense", "Offense", "Defense"])
            if found:
                header_index = index
                offsets = found
                break
    if header_index is None or offsets is None:
        return

    visitor_offense: List[PlayerEntry] = []
    visitor_defense: List[PlayerEntry] = []
    home_offense: List[PlayerEntry] = []
    home_defense: List[PlayerEntry] = []

    for raw in lines[header_index + 1 : header_index + 20]:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith(("Substitutions", "Field Goals", "Did Not Play")):
            break
        cells = _slice_columns(raw, offsets)
        parsed = [_parse_cell(cell) for cell in cells]
        if len(parsed) < 4 or any(cell is None for cell in parsed[:4]):
            continue
        visitor_offense.append(parsed[0])
        visitor_defense.append(parsed[1])
        home_offense.append(parsed[2])
        home_defense.append(parsed[3])

    if book.visitor and book.home:
        book.lineups[book.visitor] = {
            "offense": visitor_offense,
            "defense": visitor_defense,
        }
        book.lineups[book.home] = {"offense": home_offense, "defense": home_defense}


def _parse_paired_block(
    book: GameBook, lines: List[str], title: str, attribute: str
) -> None:
    """Parse a two-column roster block (visitor left, home right).

    The league prints the block title twice, once above each club's column.
    Those two titles give the column boundaries.
    """
    header_index = None
    offsets: Optional[List[int]] = None
    for index, raw in enumerate(lines[:140]):
        stripped = raw.strip()
        if not stripped.startswith(title):
            continue
        positions = _find_token_offsets(stripped, title)
        if len(positions) >= 2:
            header_index = index
            offsets = positions[:2]
            break
    if header_index is None or offsets is None:
        return

    left: List[str] = []
    right: List[str] = []
    for raw in lines[header_index + 1 : header_index + 30]:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith(
            ("Substitutions", "Did Not Play", "Not Active", "Field Goals", "Scoring Plays")
        ):
            break
        cells = _slice_columns(raw, offsets)
        if cells[0].strip():
            left.append(cells[0].strip())
        if len(cells) > 1 and cells[1].strip():
            right.append(cells[1].strip())

    if book.visitor and book.home:
        setattr(
            book,
            attribute,
            {
                book.visitor: _parse_cell_list(" ".join(left)),
                book.home: _parse_cell_list(" ".join(right)),
            },
        )
