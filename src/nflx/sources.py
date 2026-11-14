"""Canonical registry of official, NFL-controlled source endpoints.

Every table row published by the site resolves to one of these. The registry is
the single source of truth: the collector reads from it, the verifier checks
against it, and the site renders a "Sources" page from it.

``OFFICIAL_HOSTS`` is the allow-list used by the verifier. A row whose source
link does not resolve to one of these hosts fails the build.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

#: Hosts that are operated by the NFL itself.
OFFICIAL_HOSTS = (
    "nfl.com",
    "nextgenstats.nfl.com",
    "operations.nfl.com",
    "static.www.nfl.com",
)

#: Hosts that are operated by an individual NFL club (also primary sources).
CLUB_HOSTS = (
    "buffalobills.com",
    "baltimoreravens.com",
    "chicagobears.com",
    "cincinnatibengals.com",
    "clevelandbrowns.com",
    "dallascowboys.com",
    "denverbroncos.com",
    "detroitlions.com",
    "greenbaypackers.com",
    "houstontexans.com",
    "indianapoliscolts.com",
    "jacksonvillejaguars.com",
    "kansascitychiefs.com",
    "lasvegasraiders.com",
    "losangeleschargers.com",
    "losangelesrams.com",
    "miamidolphins.com",
    "minnesotavikings.com",
    "newenglandpatriots.com",
    "neworleanssaints.com",
    "newyorkgiants.com",
    "newyorkjets.com",
    "philadelphiaeagles.com",
    "pittsburghsteelers.com",
    "sanfrancisco49ers.com",
    "seattl Seahawks.com",
    "tampabaybuccaneers.com",
    "tennesseetitans.com",
    "washingtoncommanders.com",
)


@dataclass(frozen=True)
class Source:
    """A single official source endpoint."""

    key: str
    title: str
    url: str
    publisher: str
    description: str
    #: What the endpoint authoritatively provides.
    provides: str
    #: Values that change over time (week-scoped endpoints).
    volatile: bool = False

    @property
    def host(self) -> str:
        from urllib.parse import urlparse

        return (urlparse(self.url).hostname or "").lower()

    @property
    def is_official(self) -> bool:
        host = self.host
        return any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS)


SOURCES: Dict[str, Source] = {}


def _add(*args, **kwargs) -> None:
    source = Source(*args, **kwargs)
    SOURCES[source.key] = source


# --- League-wide data -------------------------------------------------------
_add(
    "injuries_current",
    "Official NFL Injury Report (current week)",
    "https://www.nfl.com/injuries/",
    "National Football League",
    "League-published practice-participation status and game-status designation "
    "for every player on every club's report for the current week.",
    "Player name, position, injury body part, practice status, game status",
    volatile=True,
)
_add(
    "injuries_by_week",
    "Official NFL Injury Report (archived by week)",
    "https://www.nfl.com/injuries/league/2026/REG10",
    "National Football League",
    "Week-indexed view of the same league injury report.",
    "Player name, position, injury body part, practice status, game status",
    volatile=True,
)
_add(
    "standings",
    "NFL Standings",
    "https://www.nfl.com/standings/league/2026/REG",
    "National Football League",
    "Official league standings including points for, points against, home/road "
    "splits and division/conference records.",
    "W-L-T, win percentage, points for, points against, splits",
    volatile=True,
)
_add(
    "schedule_week",
    "NFL Schedule (by week)",
    "https://www.nfl.com/schedules/2026/by-week/week-10",
    "National Football League",
    "Official weekly schedule with final scores, broadcast partners and kickoff "
    "times.",
    "Matchup, date, kickoff time, network, final score",
    volatile=True,
)
_add(
    "scores",
    "NFL Scores",
    "https://www.nfl.com/scores/",
    "National Football League",
    "Official live and final scoreboard for the current slate.",
    "Final score, game state",
    volatile=True,
)
_add(
    "player_stats_passing",
    "NFL Player Stats - Passing",
    "https://www.nfl.com/stats/player-stats/category/passing/2026/reg/all/passingyards/desc",
    "National Football League",
    "Official season passing statistics for every qualifying player.",
    "Attempts, completions, yards, TD, INT, passer rating",
    volatile=True,
)
_add(
    "player_stats_rushing",
    "NFL Player Stats - Rushing",
    "https://www.nfl.com/stats/player-stats/category/rushing/2026/reg/all/rushingyards/desc",
    "National Football League",
    "Official season rushing statistics for every qualifying player.",
    "Attempts, yards, TD, average, longest",
    volatile=True,
)
_add(
    "player_stats_receiving",
    "NFL Player Stats - Receiving",
    "https://www.nfl.com/stats/player-stats/category/receiving/2026/reg/all/receivingreceptions/desc",
    "National Football League",
    "Official season receiving statistics for every qualifying player.",
    "Targets, receptions, yards, TD, average, longest",
    volatile=True,
)
_add(
    "player_career_stats",
    "NFL Player Stats - Career",
    "https://www.nfl.com/players/josh-allen/stats/career",
    "National Football League",
    "Official career and per-season splits for an individual player.",
    "Per-season career totals by statistical category",
    volatile=True,
)
_add(
    "team_roster",
    "NFL Team Roster",
    "https://www.nfl.com/teams/buffalo-bills/roster/",
    "National Football League",
    "Official club roster listing jersey number, position, status, height, "
    "weight and college.",
    "Jersey number, position, roster status, physical profile",
    volatile=True,
)
_add(
    "game_center",
    "NFL Game Center",
    "https://www.nfl.com/games/commanders-at-giants-2026-reg-10",
    "National Football League",
    "Official game center page for a single game: venue, officials, standings, "
    "and links to the official game book PDF.",
    "Venue, stadium, officials, box score, game book link",
    volatile=True,
)
_add(
    "game_book",
    "NFL Official Game Book (PDF)",
    "https://static.www.nfl.com/image/upload/v1794570519/gamecenter/ab5828d9-4feb-11f1-abca-2c54536568a9.pdf",
    "National Football League",
    "The league's official statistical summary and play-by-play for a game: "
    "starting lineups, substitutes, did-not-play and not-active lists, "
    "officials, weather, final box score and playtime percentages.",
    "Lineups, inactives, officials, weather, box score, playtime %",
    volatile=True,
)

# --- Rules, policy and operations ------------------------------------------
_add(
    "rulebook_2026",
    "2026 NFL Rulebook",
    "https://operations.nfl.com/rules-officiating/2026-nfl-rulebook",
    "National Football League (Football Operations)",
    "The official playing rules for the 2026 season, the adopted rule changes, "
    "and the downloadable rulebook PDF.",
    "Rule text, adopted rule changes, field and bench-area specifications",
)
_add(
    "rulebook_pdf_2026",
    "2026 Official Playing Rules (PDF)",
    "https://static.www.nfl.com/image/upload/fl_attachment/league/tqivdkzt9mu6wdgsh1ku.pdf",
    "National Football League (Football Operations)",
    "The complete printable 2026 rulebook.",
    "Full rule text",
)
_add(
    "important_dates",
    "NFL Important Dates",
    "https://operations.nfl.com/calendar-events/nfl-important-dates",
    "National Football League (Football Operations)",
    "The league's official calendar: signing deadlines, cutdown dates, "
    "international games, draft and league meetings.",
    "Deadlines, cutdown dates, calendar events",
    volatile=True,
)
_add(
    "game_and_stadium_prep",
    "NFL Game and Stadium Prep",
    "https://operations.nfl.com/game-operations-logistics/preparation-safety/game-and-stadium-prep",
    "National Football League (Football Operations)",
    "League description of game-day medical operations, including the certified "
    "athletic trainer injury spotters who alert medical staff, and the "
    "countdown to kickoff.",
    "Game-day medical staffing, injury spotting, sideline technology",
)
_add(
    "next_gen_stats",
    "NFL Next Gen Stats",
    "https://nextgenstats.nfl.com/",
    "National Football League",
    "League-tracked participant data: player movement, route and coverage charts, "
    "pass and carry charts, and advanced participation metrics.",
    "Tracking-derived movement, route and coverage data, participation metrics",
    volatile=True,
)
_add(
    "next_gen_stats_passing",
    "Next Gen Stats - Passing",
    "https://nextgenstats.nfl.com/stats/passing",
    "National Football League",
    "Tracking-derived passing metrics by player and team.",
    "Air yards, separation, time to throw, pressure rate",
    volatile=True,
)
_add(
    "next_gen_stats_stats",
    "Next Gen Stats - League Stats",
    "https://nextgenstats.nfl.com/stats",
    "National Football League",
    "League-wide tracking-derived statistical leaders.",
    "Fastest ball carriers, sacks, longest completions, average separation",
    volatile=True,
)
_add(
    "media_access_policy",
    "NFL Media Access Policy",
    "https://www.profootballwriters.org/wp-content/uploads/2025/07/25NFLMediaAccessPolicy.pdf",
    "Pro Football Writers Association of America (publishing the NFL Media "
    "Access Policy)",
    "The published Media Access Policy, including the section that requires "
    "clubs to enter in-game injury information through the league's online "
    "Injury Reporting Platform and to keep medical information specific to a "
    "body part.",
    "In-game injury reporting duties, medical specificity rules",
)

#: Endpoints whose values are re-fetched on every scheduled run.
VOLATILE_KEYS = tuple(k for k, s in SOURCES.items() if s.volatile)


def all_sources() -> List[Source]:
    return [SOURCES[k] for k in sorted(SOURCES)]


def official_hosts() -> List[str]:
    return sorted(set(OFFICIAL_HOSTS) | set(CLUB_HOSTS))
