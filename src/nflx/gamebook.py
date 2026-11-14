"""Parser for the NFL's official Game Book PDF (the league statistical summary).

The Game Book is the most complete primary source the league publishes for a
single game. It contains:

* officials by position (referee, umpire, line judge, …)
* game-day weather (temperature, humidity, wind, wind chill, roof/surface)
* the official starting lineups for both teams (offence *and* defence)
* the substitution list, the "did not play" list and the "not active" list
* the complete individual box score for both teams
* playtime percentages

That is enough to derive, for each club, who actually starts at each position
and who is available behind them - the raw material for a depth-chart
deficiency model.

The PDF text layer is parsed with :mod:`pypdf`, which is installed in CI. The
parsing itself is pure Python and line-oriented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Positions that appear in the official lineup grid.
OFFENSE_POSITIONS = ("WR", "TE", "LT", "LG", "C", "RG", "RT", "QB", "RB", "FB", "OL")
DEFENSE_POSITIONS = ("OLB", "DL", "DT", "DE", "LB", "CB", "S", "DB", "NT")

POSITION_LABELS = set(OFFENSE_POSITIONS) | set(DEFENSE_POSITIONS) | {"OLB", "DL"}

#: ``<POS> <num> <Name>`` as it appears in lineup / substitution blocks.
PLAYER_RE = re.compile(
    r"(?P<pos>[A-Z]{1,2}(?:/[A-Z])?)\s+"
    r"(?P<num>\d{1,2}[A-Z]?)\s+"
    r"(?P<name>[A-Z][A-Za-z'\.\-]*(?:\s+[A-Z][A-Za-z'\.\-]*)*?)"
    r"(?=(?:,\s|\s{2,}|\s*$))"
)

WEATHER_RE = re.compile(
    r"Temp:\s*(?P<temp>[-\d.]+)\s*°?\s*F.*?Humidity:\s*(?P<humidity>\d+)%.*?"
    r"Wind:\s*(?P<wind>[A-Z]{1,3}\s+\d+)\s*mph",
    re.IGNORECASE,
)
WIND_CHILL_RE = re.compile(r"Wind Chill:\s*(?P<chill>[-\d.]+)", re.IGNORECASE)
SURFACE_RE = re.compile(
    r"(Closed Stadium|Open Stadium|.*?)\s+on\s+(Field Turf|Field|Dome|Artificial Turf|Turf)",
    re.IGNORECASE,
)
ATTENDANCE_RE = re.compile(r"Paid Attendance:\s*(?P<attendance>[\d,]+)")
GAME_TIME_RE = re.compile(r"Time:\s*(?P<length>\d+:\d+)")
DATE_RE = re.compile(r"Date:\s*(?P<date>[A-Za-z]+,\s*\d{1,2}/\d{1,2}/\d{4})")
SCORE_ROW_RE = re.compile(
    r"^(?P<side>VISITOR|HOME):\s*(?P<club>.+?)\s+"
    r"(?P<q1>\d+)\s+(?P<q2>\d+)\s+(?P<q3>\d+)\s+(?P<q4>\d+)\s+"
    r"(?P<ot>\d+)\s+(?P<total>\d+)\s*$"
)
SCORE_RE = re.compile(
    r"VISITOR:\s*(?P<visitor>.+?)\s+(?P<v1>\d+)\s+(?P<v2>\d+)\s+(?P<v3>\d+)\s+"
    r"(?P<v4>\d+)\s+(?P<vo>\d+)\s+(?P<vtotal>\d+)\s+"
    r"HOME:\s*(?P<home>.+?)\s+(?P<h1>\d+)\s+(?P<h2>\d+)\s+(?P<h3>\d+)\s+"
    r"(?P<h4>\d+)\s+(?P<ho>\d+)\s+(?P<htotal>\d+)"
)

OFFICIAL_ROLES = (
    "Referee",
    "Umpire",
    "Line Judge",
    "Field Judge",
    "Side Judge",
    "Back Judge",
    "Down Judge",
    "Replay Official",
)


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

    def to_dict(self) -> Dict:
        def dump(entries: List[PlayerEntry]):
            return [
                {"position": p.position, "number": p.number, "name": p.name}
                for p in entries
            ]

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


def _parse_player_list(text: str) -> List[PlayerEntry]:
    """Parse a comma-separated ``POS number Name`` list."""
    entries: List[PlayerEntry] = []
    if not text:
        return entries
    # Split on commas that separate player records (not on name commas).
    for chunk in re.split(r",\s*(?=[A-Z]{1,2}(?:/[A-Z])?\s+\d)", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.match(
            r"^(?P<pos>[A-Z]{1,2}(?:/[A-Z])?)\s+(?P<num>\d{1,2}[A-Z]?)\s+(?P<name>.+)$",
            chunk.strip(),
        )
        if match:
            entries.append(
                PlayerEntry(
                    position=match.group("pos"),
                    number=match.group("num"),
                    name=match.group("name").strip(),
                )
            )
    return entries


#: Positions run to three letters (OLB, ILB) and may be qualified (T/G, 3QB).
_CELL_MARKER_RE = re.compile(
    r"(?P<pos>\d?[A-Z]{1,3}(?:/[A-Z])?)\s+(?P<num>\d{1,2}[A-Z]?)\s+"
)


def _split_player_cells(text: str) -> List[PlayerEntry]:
    """Split a run of player cells into individual entries.

    The game-book text layer writes ``POS NUM Name`` cells back to back. A
    name never contains a position marker, so the cell boundaries are found
    by locating each ``POS NUM`` marker and taking the text up to the next.
    """
    text = text.strip()
    if not text:
        return []
    markers = list(_CELL_MARKER_RE.finditer(text))
    if not markers:
        return []
    entries: List[PlayerEntry] = []
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        name = text[start:end].strip().rstrip(",")
        # A cell name is a single token; anything after a wide gap belongs to
        # the neighbouring column.
        name = re.split(r"\s{2,}", name)[0].strip()
        if not name:
            continue
        entries.append(
            PlayerEntry(
                position=marker.group("pos"),
                number=marker.group("num"),
                name=name,
            )
        )
    return entries


def _split_sides(line: str) -> Tuple[str, str]:
    """Split a two-sided game-book line into its left and right halves.

    Game-book lines such as the lineup grid interleave the visitor's offence
    and defence with the home team's offence and defence. The two halves are
    separated by a run of two or more spaces in the extracted text layer.
    """
    parts = re.split(r"\s{2,}", line.strip())
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return line.strip(), ""


def parse_gamebook(text: str) -> GameBook:
    """Parse the extracted text layer of an official NFL Game Book PDF."""
    book = GameBook()
    lines = text.splitlines()

    # --- header ---------------------------------------------------------
    for raw in lines[:60]:
        line = raw.strip()
        if not line:
            continue
        match = re.match(
            r"^(?P<away>.+?) at (?P<home>.+?)\s+Start Time:\s*(?P<time>.+)$", line
        )
        if match and not book.matchup:
            book.matchup = f"{match.group('away')} at {match.group('home')}"
            book.start_time = match.group("time").strip()
            continue
        if line.startswith("at ") and not book.venue:
            book.venue = line[3:].strip()
            continue
        date_match = DATE_RE.search(line)
        if date_match and not book.date:
            book.date = date_match.group("date")
        attendance_match = ATTENDANCE_RE.search(line)
        if attendance_match:
            book.attendance = int(attendance_match.group("attendance").replace(",", ""))
        length_match = GAME_TIME_RE.search(line)
        if length_match and not book.game_length:
            book.game_length = length_match.group("length")

    # --- weather --------------------------------------------------------
    for raw in lines[:60]:
        line = raw.strip()
        if line.startswith("Game Weather:") or line.startswith("Game Day Weather"):
            weather = WEATHER_RE.search(line)
            if weather:
                book.temperature_f = float(weather.group("temp"))
                book.humidity_pct = int(weather.group("humidity"))
                book.wind = weather.group("wind").strip()
            chill = WIND_CHILL_RE.search(line)
            if chill:
                book.wind_chill = float(chill.group("chill"))
            if "Closed Stadium" in line:
                book.roof = "Closed Stadium"
            elif "Open Stadium" in line:
                book.roof = "Open Stadium"
            surface = SURFACE_RE.search(line)
            if surface:
                book.surface = surface.group(2)
            break

    # --- officials ------------------------------------------------------
    book.officials = _parse_officials(lines)

    # --- score line -----------------------------------------------------
    # The game book prints the scoring line as two rows:
    #   VISITOR: <club> <Q1> <Q2> <Q3> <Q4> <OT> <total>
    #   HOME:    <club> <Q1> <Q2> <Q3> <Q4> <OT> <total>
    for raw in lines[:80]:
        stripped = raw.strip()
        match = SCORE_ROW_RE.match(stripped)
        if not match:
            continue
        side = match.group("side")
        club = match.group("club").strip()
        total = int(match.group("total"))
        if side == "VISITOR":
            book.visitor = club
            book.visitor_points = total
        else:
            book.home = club
            book.home_points = total

    # --- roster blocks --------------------------------------------------
    _parse_roster_blocks(book, lines)

    # --- statistical sections -------------------------------------------
    from .gamebook_stats import parse_penalty_log, parse_playtime, parse_team_statistics

    book.team_statistics = parse_team_statistics(text, book.visitor, book.home)
    book.playtime = parse_playtime(text)
    book.penalty_log = parse_penalty_log(text)

    return book


def _parse_officials(lines: List[str]) -> List[Official]:
    """Officials are listed as role labels followed by the names."""
    officials: List[Official] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line == "Officials":
            index += 1
            roles: List[str] = []
            values: List[str] = []
            while index < len(lines) and len(roles) < len(OFFICIAL_ROLES):
                candidate = lines[index].strip()
                index += 1
                if not candidate:
                    continue
                if candidate.rstrip(":") in OFFICIAL_ROLES:
                    roles.append(candidate.rstrip(":"))
                    continue
                values.append(candidate)
            for role, value in zip(roles, values):
                name, number = _split_official(value)
                officials.append(Official(role=role, name=name, number=number))
            break
        index += 1
    return officials


def _split_official(value: str) -> Tuple[Optional[str], Optional[str]]:
    match = re.match(r"^(?P<name>[^(]+?)\s*\((?P<num>\d+)\)\s*$", value.strip())
    if match:
        return match.group("name").strip(), match.group("num")
    return value.strip() or None, None


def _parse_roster_blocks(book: GameBook, lines: List[str]) -> None:
    """Parse lineups, substitutions, did-not-play and not-active blocks.

    The game book prints a four-column lineup grid:

        visitor offence | visitor defence | home offence | home defence

    and then three two-column roster blocks (substitutions, did-not-play,
    not-active), each with the visitor on the left and the home team on the
    right.
    """
    grid_index = None
    for index, raw in enumerate(lines[:120]):
        if raw.strip().startswith("Offense Defense Offense Defense"):
            grid_index = index
            break
    if grid_index is not None:
        visitor_offense: List[PlayerEntry] = []
        visitor_defense: List[PlayerEntry] = []
        home_offense: List[PlayerEntry] = []
        home_defense: List[PlayerEntry] = []
        for raw in lines[grid_index + 1 : grid_index + 16]:
            line = raw.rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Substitutions"):
                break
            # The grid row holds four cells: visitor offence, visitor defence,
            # home offence, home defence.
            cells = _split_player_cells(stripped)
            if len(cells) >= 4:
                visitor_offense.append(cells[0])
                visitor_defense.append(cells[1])
                home_offense.append(cells[2])
                home_defense.append(cells[3])
            elif len(cells) == 2:
                visitor_offense.append(cells[0])
                home_defense.append(cells[1])
        if book.visitor and book.home:
            book.lineups[book.visitor] = {
                "offense": visitor_offense,
                "defense": visitor_defense,
            }
            book.lineups[book.home] = {"offense": home_offense, "defense": home_defense}

    # Substitutions / did-not-play / not-active come as paired columns.
    _parse_paired_block(book, lines, "Substitutions", "substitutions")
    _parse_paired_block(book, lines, "Did Not Play", "did_not_play")
    _parse_paired_block(book, lines, "Not Active", "not_active")


def _parse_paired_block(book: GameBook, lines: List[str], title: str, attribute: str) -> None:
    """Parse a two-column roster block (visitor left, home right).

    The block header repeats the title on both sides, for example
    ``Substitutions Substitutions``. The first line is therefore skipped and
    the remaining text is split on the column boundary.
    """
    index = 0
    while index < len(lines):
        if lines[index].strip() == title:
            index += 1
            # The next non-empty line repeats the title for both columns.
            while index < len(lines) and not lines[index].strip():
                index += 1
            if index < len(lines) and lines[index].strip().startswith(title):
                index += 1
            left: List[str] = []
            right: List[str] = []
            while index < len(lines):
                line = lines[index].rstrip()
                index += 1
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped in (
                    "Did Not Play",
                    "Not Active",
                    "Substitutions",
                    "Field Goals",
                    "Scoring Plays",
                ):
                    break
                if stripped.startswith(
                    ("Play Description", "Scoring", "Total", "RUSHING", "PASSING", "Field Goals")
                ):
                    break
                a, b = _split_sides(line)
                if a:
                    left.append(a)
                if b:
                    right.append(b)
            if book.visitor and book.home:
                setattr(
                    book,
                    attribute,
                    {
                        book.visitor: _parse_player_list(" ".join(left)),
                        book.home: _parse_player_list(" ".join(right)),
                    },
                )
            return
        index += 1
