"""Source registry.

Every number published on the site must be traceable to one of these sources.
`kind` is used by the site to distinguish league-operated sources from
community mirrors, and `official` drives the "Verified"/"Unverified" flag that
is rendered on the Flagged for Review page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    publisher: str
    url: str
    kind: str  # "league" | "state" | "community" | "derived"
    official: bool
    accessed: str
    supports: List[str] = field(default_factory=list)
    notes: str = ""


SOURCES: List[Source] = [
    Source(
        key="nfl_important_dates",
        title="2026-27 National Football League important dates",
        publisher="National Football League (NFL Communications)",
        url="https://www.nfl.com/news/2026-27-national-football-league-important-dates",
        kind="league",
        official=True,
        accessed="2026-11-14",
        supports=["Injury-report filing deadlines", "Practice/Game status report timing", "Season calendar"],
        notes="Official league announcement; also published as a PDF on media.nfl.com.",
    ),
    Source(
        key="nfl_important_dates_pdf",
        title="2026-2027 National Football League Important Dates (PDF)",
        publisher="NFL Communications / media.nfl.com",
        url="https://media.nfl.com/content/dam/communications/football-communications/2026/news/07%2007%2026%20-%20Important%20Dates.pdf",
        kind="league",
        official=True,
        accessed="2026-11-14",
        supports=["Practice Report filing windows", "Game Status Report filing deadlines"],
        notes="League-issued PDF of the same calendar.",
    ),
    Source(
        key="nfl_injuries_w10",
        title="Official NFL Injury Report - Week 10 of the 2026 Season",
        publisher="National Football League",
        url="https://www.nfl.com/injuries/league/2026/reg10",
        kind="league",
        official=True,
        accessed="2026-11-14",
        supports=["Current-week injury status (Out / Doubtful / Questionable)", "Practice participation status"],
        notes="Week-scoped URL pattern: /injuries/league/{season}/reg{week}.",
    ),
    Source(
        key="nfl_injuries_index",
        title="NFL Official Injury Report (all weeks)",
        publisher="National Football League",
        url="https://www.nfl.com/injuries/",
        kind="league",
        official=True,
        accessed="2026-11-14",
        supports=["Injury report index / week selector"],
        notes="Landing page for the weekly reports.",
    ),
    Source(
        key="nfl_rules_2026",
        title="2026 Official Playing Rules of the National Football League",
        publisher="National Football League",
        url="https://static.www.nfl.com/image/upload/fl_attachment/league/tqivdkzt9mu6wdgsh1ku.pdf",
        kind="league",
        official=True,
        accessed="2026-11-14",
        supports=["Game definitions (overtime, injury timeouts, scoring)", "Rule citations"],
        notes="League-published rule book PDF.",
    ),
    Source(
        key="nfl_schedule_2026",
        title="2026 NFL Schedule",
        publisher="National Football League",
        url="https://www.nfl.com/schedules/2026/REG1/",
        kind="league",
        official=True,
        accessed="2026-11-14",
        supports=["Official game schedule / kickoff times", "Week-by-week game list"],
        notes="Week-scoped URL pattern: /schedules/2026/REG{week}/.",
    ),
    Source(
        key="nfl_standings",
        title="NFL Standings",
        publisher="National Football League",
        url="https://www.nfl.com/standings/league/2026/REG",
        kind="league",
        official=True,
        accessed="2026-11-14",
        supports=["League standings", "Division and conference records"],
        notes="League-operated standings page.",
    ),
    Source(
        key="nfl_ngs",
        title="NFL Next Gen Stats (Receiving)",
        publisher="National Football League",
        url="https://nextgenstats.nfl.com/",
        kind="league",
        official=True,
        accessed="2026-11-14",
        supports=["Separation / cushion / intended air yards (receiving model inputs)"],
        notes="League-operated tracking data product.",
    ),
    Source(
        key="nfldata_games",
        title="nfldata - games.csv (results, market lines, odds, weather, rest)",
        publisher="nflverse / Lee Sharpe (GitHub)",
        url="https://github.com/nflverse/nfldata/blob/master/data/games.csv",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Final scores", "Point spread and total lines", "Moneyline and spread/total prices", "Rest days, weather, roof, stadium, coaches"],
        notes="Community mirror. Field semantics documented in the repository's DATASETS.md.",
    ),
    Source(
        key="nfldata_closing_lines",
        title="nfldata - closing_lines.csv (2006-2018 closing lines by sportsbook)",
        publisher="nflverse / Lee Sharpe (GitHub)",
        url="https://github.com/nflverse/nfldata/blob/master/data/closing_lines.csv",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Historical closing line comparison (2006-2018)"],
        notes="Ends at the 2018 season; later seasons rely on games.csv lines.",
    ),
    Source(
        key="nfldata_rosters",
        title="nfldata - rosters.csv (season rosters, games and starts)",
        publisher="nflverse / Lee Sharpe (GitHub)",
        url="https://github.com/nflverse/nfldata/blob/master/data/rosters.csv",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Starter identification (games/starts by season)", "Player tenure (years)"],
        notes="Derived from Pro Football Reference by the publisher.",
    ),
    Source(
        key="nfldata_standings",
        title="nfldata - standings.csv",
        publisher="nflverse / Lee Sharpe (GitHub)",
        url="https://github.com/nflverse/nfldata/blob/master/data/standings.csv",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Standings, strength of schedule, playoff seed"],
        notes="Mirrors league standings for 2002+.",
    ),
    Source(
        key="nflverse_injuries",
        title="nflverse injuries (2026 weekly injury reports)",
        publisher="nflverse (GitHub mirror used by Beexly/Sports)",
        url="https://github.com/Beexly/Sports/blob/main/data/nflverse/injuries_2026.csv",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Machine-readable injury history 2024-2026", "Practice participation and game status fields"],
        notes="Transcription of the official NFL weekly injury reports; spot-checked against nfl.com (see Flagged for Review).",
    ),
    Source(
        key="nflverse_weekly_rosters",
        title="Weekly rosters (2026, with roster status)",
        publisher="nflverse (GitHub mirror used by Beexly/Sports)",
        url="https://github.com/Beexly/Sports/blob/main/data/nflverse/rosters_2026.csv",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Weekly active / IR / reserve status by player", "Depth chart construction"],
        notes="Weekly roster snapshot per game week.",
    ),
    Source(
        key="depth_charts_2025",
        title="Depth charts (2024-2025, with explicit depth tier)",
        publisher="mikeysports dataset (GitHub mirror used by Beexly/Sports)",
        url="https://github.com/Beexly/Sports/blob/main/data/nflverse/hf_mikeysports_2025_depth_charts_zone1.parquet",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Depth tier per position group (depth_team 1 = first string)", "Replacement identification"],
        notes="No league-operated depth chart publication exists; tiering is derived data and is flagged.",
    ),
    Source(
        key="player_week_stats",
        title="Weekly player statistics archive (1999-2026)",
        publisher="nflverse (GitHub mirror used by Beexly/Sports)",
        url="https://github.com/Beexly/Sports/blob/main/data/nflverse/player_stats_weekly_archive.parquet",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Player prop modelling inputs", "Prop correlation estimates"],
        notes="Weekly game-level player stats with EPA/CPOE where available.",
    ),
    Source(
        key="weather_history",
        title="Historical game scores with weather (1966-2026)",
        publisher="tobycrabtree/kaggle dataset (GitHub mirror used by Beexly/Sports)",
        url="https://github.com/Beexly/Sports/blob/main/data/nflverse/kaggle_tobycrabtree_scores_weather_zone1.parquet",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Temperature / wind / humidity joins", "Weather-based total models"],
        notes="Used only where the mirror's own weather fields are missing.",
    ),
    Source(
        key="player_week_stats_2026",
        title="2026 weekly player statistics (current season)",
        publisher="nflverse (GitHub mirror used by Beexly/Sports)",
        url="https://github.com/Beexly/Sports/blob/main/data/nflverse/player_week_stats_2026.csv",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Current-season usage volumes (attempts, targets, carries) used to derive depth tiers",
                  "2026 prop projections"],
        notes="Covers weeks 1-7 of the 2026 season at the time of this build.",
    ),
    Source(
        key="derived_depth_tiers",
        title="Depth tiers derived from 2026 usage and games played",
        publisher="Derived by this project from the current-season weekly player statistics",
        url="https://www.nfl.com/injuries/league/2026/reg10",
        kind="derived",
        official=False,
        accessed="2026-11-14",
        supports=["Which player must start when the first string is unavailable"],
        notes="No league-operated depth chart exists. Tier 1 = most games played, usage as the tiebreaker; "
              "ambiguous defensive groups are left unranked rather than guessed.",
    ),
    Source(
        key="ngs_receiving",
        title="Next Gen Stats receiving (2016-2026)",
        publisher="nflverse (GitHub mirror used by Beexly/Sports)",
        url="https://github.com/Beexly/Sports/blob/main/data/nflverse/ngs_receiving.csv.gz",
        kind="community",
        official=False,
        accessed="2026-11-14",
        supports=["Separation, cushion and intended air yards by player-week"],
        notes="Mirror of the league's Next Gen Stats receiving feed.",
    ),
]

SOURCE_BY_KEY: Dict[str, Source] = {s.key: s for s in SOURCES}


def url_for(key: str) -> str:
    return SOURCE_BY_KEY[key].url


def cite(key: str) -> str:
    """Short citation label used inside generated tables."""
    return SOURCE_BY_KEY[key].title


def official_keys() -> List[str]:
    return [s.key for s in SOURCES if s.official]
