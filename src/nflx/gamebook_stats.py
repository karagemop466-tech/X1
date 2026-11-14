"""Parsers for the statistical sections of the official Game Book PDF.

Two sections matter for the analysis:

``Final Team Statistics``
    Per-team aggregates (first downs, net yards, turnovers, penalties …). The
    league prints the two clubs side by side, visitor on the left.

``Playtime Percentage``
    The league's own per-player participation split across offence, defence
    and special teams. This is the measurement that separates a genuine
    starter from a rotation regular, and it is the basis of the depth model.

Both parsers work on the extracted text layer and never substitute a value
they cannot read.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

#: Team-statistic labels as the game book prints them, with the label text
#: that appears in the extracted layer.
TEAM_STAT_LABELS = {
    "TOTAL FIRST DOWNS": "first_downs",
    "By Rushing": "first_downs_by_rushing",
    "By Passing": "first_downs_by_passing",
    "By Penalty": "first_downs_by_penalty",
    "THIRD DOWN EFFICIENCY": "third_down_efficiency",
    "FOURTH DOWN EFFICIENCY": "fourth_down_efficiency",
    "TOTAL NET YARDS": "net_yards",
    "Total Offensive Plays (inc. times thrown passing)": "offensive_plays",
    "Average gain per offensive play": "avg_gain_per_play",
    "NET YARDS RUSHING": "net_yards_rushing",
    "Total Rushing Plays": "rushing_plays",
    "Average gain per rushing play": "avg_gain_per_rush",
    "Tackles for a loss-number and yards": "tackles_for_loss",
    "NET YARDS PASSING": "net_yards_passing",
    "Times thrown - yards lost attempting to pass": "times_thrown",
    "Gross yards passing": "gross_yards_passing",
    "PASS ATTEMPTS-COMPLETIONS-HAD INTERCEPTED": "pass_att_completions_int",
    "Avg gain per pass play (inc.# thrown passing)": "avg_gain_per_pass",
    "KICKOFFS Number-In End Zone-Touchbacks": "kickoffs",
    "PUNTS Number and Average": "punts",
    "Had Blocked": "had_blocked",
    "FGs - PATs Had Blocked": "fgs_pats_blocked",
    "Net Punting Average": "net_punting_average",
    "TOTAL RETURN YARDAGE (Not Including Kickoffs)": "return_yardage",
    "No. and Yards Punt Returns": "punt_returns",
    "No. and Yards Kickoff Returns": "kickoff_returns",
    "No. and Yards Interception Returns": "interception_returns",
    "PENALTIES Number and Yards": "penalties",
    "FUMBLES Number and Lost": "fumbles",
    "TOUCHDOWNS": "touchdowns",
    "EXTRA POINTS Made-Attempts": "extra_points",
    "Kicking Made-Attempts": "kicking",
    "FIELD GOALS Made-Attempts": "field_goals",
}

#: A game-book statistic value: a number, a compound figure such as
#: ``7-14-50.0%`` or a pair such as ``4-17``.
VALUE_RE = r"-?\d+(?:\.\d+)?(?:%|(?:-\d+(?:\.\d+)?)*)"

#: The playtime section prints three parallel percentage columns.
PLAYTIME_COLUMNS = ("offense", "defense", "special_teams")


def parse_team_statistics(
    text: str,
    visitor: Optional[str] = None,
    home: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse the ``Final Team Statistics`` block.

    Returns a mapping with one entry per club, keyed by the league's own
    statistic names.
    """
    result: Dict[str, Any] = {"visitor": {}, "home": {}, "raw_rows": []}
    lines = text.splitlines()

    start = None
    for index, line in enumerate(lines):
        if line.strip() == "Final Team Statistics":
            start = index
            break
    if start is None:
        return result

    for raw in lines[start + 1 : start + 120]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Final Individual Statistics"):
            break
        label, values = _split_label_values(line)
        if label is None or not values:
            continue
        key = TEAM_STAT_LABELS.get(label)
        if key is None:
            # Keep the raw label so nothing is silently dropped.
            key = label.lower().replace(" ", "_").replace("-", "_")
        result["raw_rows"].append({"label": label, "values": values})
        result["visitor"][key] = values[0] if len(values) > 0 else None
        result["home"][key] = values[1] if len(values) > 1 else None

    return result


def _split_label_values(line: str) -> Tuple[Optional[str], List[str]]:
    """Split a team-statistic row into its label and its per-club values.

    The league prints the label at the end of the row for most statistics and
    at the start for a few, so the label is located by matching a known
    label rather than by position.
    """
    for label in TEAM_STAT_LABELS:
        index = line.find(label)
        if index < 0:
            continue
        before = line[:index].strip()
        after = line[index + len(label) :].strip()
        values: List[str] = []
        if before:
            values.extend(re.findall(VALUE_RE, before))
        if after:
            values.extend(re.findall(VALUE_RE, after))
        if values:
            return label, values
    return None, []


#: A playtime cell: name, position and the numeric columns.
#:
#: ``A.Vera-Tucker            G       71 100%                       2      9%``
#:
#: The first number is the player's total snaps. The second is the share of
#: the snaps he played on his primary unit - offence for an offensive
#: position, defence for a defensive one, special teams for a specialist. When
#: two further numbers follow they are the special-teams snaps and the share
#: of the special-teams snaps.
PLAYTIME_CELL_RE = re.compile(
    r"(?P<name>[A-Z][A-Za-z'\.\-]*(?:\s[A-Z][a-z]+)?)\s+"
    r"(?P<pos>\d?[A-Z]{1,3}(?:/[A-Z])?)\s+"
    r"(?P<numbers>[\d\s%]+?)(?=\s{2,}[A-Z]|\s*$)"
)

OFFENSE_POSITIONS = {
    "QB", "RB", "FB", "WR", "TE", "OL", "T", "G", "C", "LG", "RG", "LT", "RT",
}
DEFENSE_POSITIONS = {
    "DL", "DT", "DE", "NT", "LB", "OLB", "ILB", "MLB", "CB", "DB", "S", "FS", "SS",
}
SPECIALISTS = {"K", "P", "LS"}


def parse_playtime(text: str) -> Dict[str, Any]:
    """Parse the league's ``Playtime Percentage`` block.

    The league prints two tables side by side: the visitor's players on the
    left and the home team's on the right. Each row therefore holds at most
    two cells, and the first cell always belongs to the visitor.
    """
    result: Dict[str, Any] = {"visitor": {}, "home": {}, "units": {}}
    lines = text.splitlines()

    start = None
    for index, line in enumerate(lines):
        if line.strip() == "Playtime Percentage":
            start = index
            break
    if start is None:
        return result

    # The club names identify which column belongs to whom.
    visitor_name = ""
    home_name = ""
    for index in range(start, min(start + 8, len(lines))):
        candidate = lines[index].strip()
        if candidate and candidate != "Playtime Percentage" and not candidate.startswith(
            ("Percent of playtime", "Offense")
        ):
            parts = re.split(r"\s{4,}", candidate)
            if len(parts) >= 2:
                visitor_name = parts[0].strip()
                home_name = parts[1].strip()
                break

    visitor: Dict[str, Any] = {}
    home: Dict[str, Any] = {}

    for raw in lines[start + 1 :]:
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.strip().startswith("Percent of playtime"):
            continue
        if not re.search(r"\d", line):
            # Header and blank lines carry no figures.
            continue
        cells = list(PLAYTIME_CELL_RE.finditer(line))
        if not cells:
            continue
        parsed = []
        for cell in cells:
            values = _parse_playtime_numbers(
                cell.group("numbers"), cell.group("pos")
            )
            if values is None:
                parsed = []
                break
            parsed.append(
                {
                    "name": cell.group("name").strip(),
                    "position": cell.group("pos"),
                    **values,
                }
            )
        if not parsed:
            continue
        if len(parsed) >= 1:
            visitor[parsed[0]["name"]] = parsed[0]
        if len(parsed) >= 2:
            home[parsed[1]["name"]] = parsed[1]

    result["visitor"] = visitor
    result["home"] = home
    result["units"] = {"visitor": visitor_name, "home": home_name}
    return result


def _parse_playtime_numbers(text: str, position: str) -> Optional[Dict[str, Any]]:
    """Read the numeric columns of a playtime row.

    The primary unit is determined by the position the league prints: an
    offensive position means the share is of offensive snaps, a defensive
    position means defensive snaps, and a specialist means special teams.
    A row that cannot be read unambiguously is rejected rather than guessed.
    """
    tokens = re.findall(r"(\d+(?:\.\d+)?)(%?)", text)
    numbers = [(float(v), bool(pct)) for v, pct in tokens]
    if len(numbers) not in (2, 4):
        return None

    snaps = int(numbers[0][0])
    if not numbers[1][1]:
        # The share column is always printed as a percentage.
        return None
    share = numbers[1][0] / 100.0

    values: Dict[str, Any] = {
        "snaps": snaps,
        "offense": None,
        "defense": None,
        "special_teams": None,
    }

    pos = position.upper()
    if pos in SPECIALISTS:
        values["special_teams"] = share
    elif pos in OFFENSE_POSITIONS:
        values["offense"] = share
    elif pos in DEFENSE_POSITIONS:
        values["defense"] = share
    else:
        # An unknown position is not guessed at.
        return None

    if len(numbers) == 4:
        if not numbers[3][1]:
            return None
        values["special_teams"] = numbers[3][0] / 100.0
        values["special_teams_snaps"] = int(numbers[2][0])
    return values


def parse_penalty_log(text: str) -> Dict[str, Any]:
    """Parse the penalty log, which the game book publishes per team.

    Returns a mapping of team name to the list of penalty descriptions.
    """
    result: Dict[str, Any] = {}
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ("Penalties", "Penalty"):
            club = ""
            for back in range(index - 1, max(index - 6, -1), -1):
                candidate = lines[back].strip()
                if candidate and "Washington" not in candidate:
                    club = candidate
                    break
            entries: List[str] = []
            for forward in range(index + 1, min(index + 40, len(lines))):
                candidate = lines[forward].strip()
                if not candidate:
                    break
                if re.match(r"^[A-Z][a-z]+\s+\d+:\d+\s+", candidate):
                    entries.append(candidate)
                elif entries:
                    break
            if club:
                result.setdefault(club, []).extend(entries)
    return result
