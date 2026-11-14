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


#: ``B.Coleman 100%69 4 15%T/G`` - name, then three percentage columns.
PLAYTIME_RE = re.compile(
    r"^(?P<name>[A-Z][A-Za-z'\.\-]*)\s+(?P<rest>.+)$"
)


def parse_playtime(text: str) -> Dict[str, Any]:
    """Parse the league's ``Playtime Percentage`` block.

    The block prints, for each player, the share of snaps on offence, defence
    and special teams. A column that shows no percentage (for example a
    player who was only on the field for one unit) is left ``None``.
    """
    result: Dict[str, Any] = {"visitor": {}, "home": {}}
    lines = text.splitlines()

    start = None
    for index, line in enumerate(lines):
        if line.strip() == "Playtime Percentage":
            start = index
            break
    if start is None:
        return result

    visitor: Dict[str, Any] = {}
    home: Dict[str, Any] = {}
    # The header names the two clubs.
    club_line = ""
    for index in range(start, min(start + 6, len(lines))):
        candidate = lines[index].strip()
        if candidate and candidate != "Playtime Percentage":
            club_line = candidate
            break

    for raw in lines[start + 1 :]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Percent of playtime"):
            continue
        match = PLAYTIME_RE.match(line)
        if not match:
            break
        name = match.group("name")
        rest = match.group("rest")
        columns = _parse_playtime_columns(rest)
        if not columns:
            continue
        visitor[name] = columns

    result["visitor"] = visitor
    result["header"] = club_line
    return result


def _parse_playtime_columns(rest: str) -> Optional[Dict[str, Any]]:
    """Split the three percentage columns of a playtime row."""
    values: Dict[str, Optional[float]] = {
        "offense": None,
        "defense": None,
        "special_teams": None,
    }
    # The league prints the three columns with no separator, so the numbers are
    # read left to right: an explicit percentage, or a bare integer followed
    # by the unit position.
    tokens = re.findall(r"(\d+)(%?)", rest)
    if not tokens:
        return None
    numbers = [(int(v), bool(pct)) for v, pct in tokens if v != ""]
    if not numbers:
        return None

    # The final token is the unit position for the last player column, so the
    # trailing letters are stripped before parsing.
    stripped = re.sub(r"[A-Z]{1,2}(?:/[A-Z])?$", "", rest).strip()
    tokens = re.findall(r"(\d+)(%?)", stripped)
    numbers = [(int(v), bool(pct)) for v, pct in tokens]
    if not numbers:
        return None

    # Only rows whose three columns are unambiguous are read. A row that does
    # not resolve cleanly is left blank rather than guessed.
    percent_values = [n / 100.0 for n, is_pct in numbers if is_pct]
    bare_values = [n for n, is_pct in numbers if not is_pct]
    if len(percent_values) == 3 and not bare_values:
        values["offense"] = percent_values[0]
        values["defense"] = percent_values[1]
        values["special_teams"] = percent_values[2]
    elif len(percent_values) == 2 and len(bare_values) == 1:
        values["offense"] = percent_values[0]
        values["defense"] = percent_values[1]
        values["special_teams"] = bare_values[0]
    elif len(percent_values) == 1 and not bare_values:
        values["offense"] = percent_values[0]
    else:
        return None
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
