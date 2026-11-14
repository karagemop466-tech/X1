"""Depth-chart deficiency analysis.

The question this module answers: *when a starter is unavailable, how much
depth does the club actually have behind them, and what is the expected
on-field impact of the replacement?*

Everything is derived from two official league publications:

* the weekly **injury report** (practice status and game status per player), and
* the **game book** for each completed game (starting lineups, substitution
  list, did-not-play list and inactive list).

Method
------
1. From the game books, build each club's *on-field depth chart* per position
   group. A player who started a game is recorded as a starter for that
   position group; players who entered the game are recorded as backups, ordered
   by when they first appear in the substitution order.
2. For the current week, read the official injury report. A player whose game
   status is ``Out`` cannot play; ``Doubtful`` and ``Questionable`` are
   uncertain and are treated as *at risk* rather than absent.
3. For each club, find the starters who are unavailable and identify who is
   next in line. The *deficiency* is the number of starting slots at that
   position group that are being filled by a backup rather than a starter.

Nothing about impact size is invented. The module reports *depth position*
(which string is replacing which), which is a fact read from official data.
Effect size is left to the modelling layer and is flagged as requiring the
licensed outcome history.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: Position groups used for depth analysis. Backup quality is only meaningful
#: inside a position group, because a backup safety cannot cover for a tackle.
POSITION_GROUPS: Dict[str, List[str]] = {
    "QB": ["QB"],
    "RB": ["RB", "FB"],
    "WR": ["WR"],
    "TE": ["TE"],
    "OL": ["LT", "LG", "C", "RG", "RT", "OL", "T/G", "C/G", "G/T"],
    "DL": ["DL", "DT", "DE", "NT"],
    "LB": ["LB", "OLB", "ILB", "MLB"],
    "DB": ["CB", "DB", "S", "SAF", "FS", "SS"],
    "ST": ["K", "P", "LS"],
}

#: Which groups belong to the offence and which to the defence.
OFFENSE_GROUPS = ("QB", "RB", "WR", "TE", "OL", "ST")
DEFENSE_GROUPS = ("DL", "LB", "DB", "ST")

_POS_TO_GROUP: Dict[str, str] = {}
for _group, _positions in POSITION_GROUPS.items():
    for _position in _positions:
        _POS_TO_GROUP[_position] = _group

#: Game-status designations that mean the player will not play.
ABSENT_STATUSES = {"Out"}
#: Designations that leave availability genuinely uncertain.
UNCERTAIN_STATUSES = {"Doubtful", "Questionable"}

_STRING_LABELS = {1: "1st string", 2: "2nd string", 3: "3rd string", 4: "4th string"}


def position_group(position: Optional[str]) -> Optional[str]:
    """Map an official position code to its depth-chart group."""
    if not position:
        return None
    key = position.strip().upper()
    return _POS_TO_GROUP.get(key)


@dataclass
class DepthPlayer:
    """One player's place on a club's depth chart."""

    name: str
    position: Optional[str]
    group: Optional[str]
    starts: int = 0
    games_played: int = 0
    substitution_order: Optional[int] = None
    #: Total snaps recorded by the league across the sampled games.
    snaps: int = 0
    #: Games in which the player appeared at all.
    appearances: int = 0

    @property
    def is_starter(self) -> bool:
        return self.starts > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "position": self.position,
            "group": self.group,
            "starts": self.starts,
            "games_played": self.games_played,
            "substitution_order": self.substitution_order,
            "snaps": self.snaps,
            "appearances": self.appearances,
        }


@dataclass
class DepthChart:
    """A club's depth chart, grouped by position group and by side of ball."""

    club: str
    offense: Dict[str, List[DepthPlayer]] = field(default_factory=dict)
    defense: Dict[str, List[DepthPlayer]] = field(default_factory=dict)
    games_sampled: int = 0

    def starters(self, side: str, group: str) -> List[DepthPlayer]:
        table = self.offense if side == "offense" else self.defense
        return [p for p in table.get(group, []) if p.is_starter]

    def backups(self, side: str, group: str) -> List[DepthPlayer]:
        table = self.offense if side == "offense" else self.defense
        return [p for p in table.get(group, []) if not p.is_starter]


def build_depth_charts(gamebooks: List[Dict[str, Any]]) -> Dict[str, DepthChart]:
    """Build a depth chart per club from the official game books.

    Only games with a parsed visitor/home pairing are used. A club's chart
    accumulates starts and appearances across every game sampled.
    """
    charts: Dict[str, DepthChart] = {}

    for book in gamebooks:
        visitor = book.get("visitor")
        home = book.get("home")
        lineups = book.get("lineups") or {}
        if not visitor or not home or not lineups:
            continue

        for club, other in ((visitor, home), (home, visitor)):
            chart = charts.setdefault(club, DepthChart(club=club))
            units = lineups.get(club) or {}
            for side in ("offense", "defense"):
                for entry in units.get(side, []):
                    group = position_group(entry.get("position"))
                    if not group:
                        continue
                    table = chart.offense if side == "offense" else chart.defense
                    bucket = table.setdefault(group, [])
                    player = _find(bucket, entry.get("name"))
                    if player is None:
                        player = DepthPlayer(
                            name=entry.get("name"),
                            position=entry.get("position"),
                            group=group,
                        )
                        bucket.append(player)
                    player.starts += 1
                    player.games_played += 1

            subs = (book.get("substitutions") or {}).get(club) or []
            for order, entry in enumerate(subs, start=1):
                group = position_group(entry.get("position"))
                if not group:
                    continue
                side = "offense" if group in OFFENSE_GROUPS else "defense"
                table = chart.offense if side == "offense" else chart.defense
                bucket = table.setdefault(group, [])
                player = _find(bucket, entry.get("name"))
                if player is None:
                    player = DepthPlayer(
                        name=entry.get("name"),
                        position=entry.get("position"),
                        group=group,
                    )
                    bucket.append(player)
                player.games_played += 1
                if player.substitution_order is None:
                    player.substitution_order = order

            # The league's own playtime table orders the depth chart.
            playtime = (book.get("playtime") or {}).get("visitor" if club == visitor else "home")
            for name, entry in (playtime or {}).items():
                group = position_group(entry.get("position"))
                if not group:
                    continue
                side = "offense" if group in OFFENSE_GROUPS else "defense"
                table = chart.offense if side == "offense" else chart.defense
                bucket = table.setdefault(group, [])
                player = _find(bucket, name)
                if player is None:
                    player = DepthPlayer(
                        name=name,
                        position=entry.get("position"),
                        group=group,
                    )
                    bucket.append(player)
                player.snaps += int(entry.get("snaps") or 0)
                player.appearances += 1

            chart.games_sampled += 1

    # Order each bucket: starters first (by starts, then name), then backups by
    # first substitution appearance.
    for chart in charts.values():
        for table in (chart.offense, chart.defense):
            for group, bucket in table.items():
                bucket.sort(
                    key=lambda p: (
                        0 if p.is_starter else 1,
                        -p.starts,
                        -p.snaps,
                        p.substitution_order if p.substitution_order is not None else 10_000,
                        p.name or "",
                    )
                )
    return charts


def _find(bucket: List[DepthPlayer], name: Optional[str]) -> Optional[DepthPlayer]:
    if not name:
        return None
    for player in bucket:
        if player.name == name:
            return player
    return None


@dataclass
class Deficiency:
    """One unavailable starter and the replacement who must take the slot."""

    club: str
    side: str
    group: str
    starter: str
    starter_position: Optional[str]
    status: str
    injury: Optional[str]
    replacement: Optional[str]
    replacement_string: Optional[str]
    #: ``1`` means a starter is replaced by the next listed player (2nd string).
    depth_deficit: Optional[int]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "club": self.club,
            "side": self.side,
            "group": self.group,
            "starter": self.starter,
            "starter_position": self.starter_position,
            "status": self.status,
            "injury": self.injury,
            "replacement": self.replacement,
            "replacement_string": self.replacement_string,
            "depth_deficit": self.depth_deficit,
            "notes": self.notes,
        }


def analyse_deficiency(
    injuries: List[Dict[str, Any]],
    charts: Dict[str, DepthChart],
    *,
    source_url: str,
    source_label: str,
    retrieved_at: str,
    min_games_sampled: int = 1,
) -> List[Dict[str, Any]]:
    """Cross the official injury report against the depth charts.

    Returns one record per unavailable starter. ``depth_deficit`` is the
    number of *additional* depth levels consumed by the absence: a 1st string
    replaced by the 2nd string is a deficit of 1.
    """
    by_club: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in injuries:
        by_club[row.get("club") or ""].append(row)

    results: List[Dict[str, Any]] = []

    for club, rows in by_club.items():
        chart = charts.get(club)
        if chart is None or chart.games_sampled < min_games_sampled:
            continue

        # Index the starters by position group so we can find who is missing.
        starters_by_group: Dict[str, List[DepthPlayer]] = {}
        for side in ("offense", "defense"):
            for group in POSITION_GROUPS:
                found = chart.starters(side, group)
                if found:
                    starters_by_group.setdefault(group, []).extend(found)

        for row in rows:
            status = (row.get("game_status") or "").strip()
            if status not in ABSENT_STATUSES and status not in UNCERTAIN_STATUSES:
                continue
            name = row.get("player")
            group = position_group(row.get("position"))
            if not name or not group:
                continue

            # Find the starter entry for this player.
            starters = starters_by_group.get(group, [])
            starter_entry = None
            for player in starters:
                if player.name == name:
                    starter_entry = player
                    break

            if starter_entry is None:
                # The player is on the report but never started in the sampled
                # games - not a starter absence.
                continue

            side = "offense" if group in OFFENSE_GROUPS else "defense"
            all_players = (chart.offense if side == "offense" else chart.defense).get(group, [])
            index = all_players.index(starter_entry)
            replacement = all_players[index + 1] if index + 1 < len(all_players) else None

            deficit = None
            replacement_string = None
            if replacement is not None:
                replacement_string = _string_for(index + 1)
                deficit = replacement_string_index(index + 1)

            notes: List[str] = []
            if replacement is None:
                notes.append(
                    "no further player at this position group appears in the sampled "
                    "game books; replacement is unverified"
                )
            if status in UNCERTAIN_STATUSES:
                notes.append(
                    f"status '{status}' leaves availability uncertain; the absence is "
                    "not confirmed"
                )

            results.append(
                {
                    "club": club,
                    "side": side,
                    "group": group,
                    "starter": name,
                    "starter_position": row.get("position"),
                    "status": status,
                    "injury": row.get("injuries"),
                    "replacement": replacement.name if replacement else None,
                    "replacement_position": replacement.position if replacement else None,
                    "replacement_string": replacement_string,
                    "depth_deficit": deficit,
                    "starter_starts": starter_entry.starts,
                    "games_sampled": chart.games_sampled,
                    "notes": notes,
                    "source_url": source_url,
                    "source_label": source_label,
                    "retrieved_at": retrieved_at,
                }
            )

    results.sort(key=lambda r: (r["club"], r["group"], r["starter"]))
    return results


def _string_for(index: int) -> Optional[str]:
    """``index`` is 0-based into the depth list; 0 = first listed player."""
    label = _STRING_LABELS.get(index + 1)
    return label


def replacement_string_index(index: int) -> Optional[int]:
    """Numeric depth level of the replacement (1-based)."""
    return index + 1 if index >= 0 else None


def summarize_deficiency(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate deficiency records into headline counts."""
    out: Dict[str, Any] = {
        "clubs_affected": len({r["club"] for r in records}),
        "absences": 0,
        "uncertain": 0,
        "no_verified_replacement": 0,
        "by_group": defaultdict(int),
        "by_string": defaultdict(int),
    }
    for record in records:
        if record["status"] in ABSENT_STATUSES:
            out["absences"] += 1
        else:
            out["uncertain"] += 1
        if record.get("replacement") is None:
            out["no_verified_replacement"] += 1
        out["by_group"][record["group"]] += 1
        if record.get("replacement_string"):
            out["by_string"][record["replacement_string"]] += 1
    out["by_group"] = dict(out["by_group"])
    out["by_string"] = dict(out["by_string"])
    return out
