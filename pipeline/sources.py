"""Registry of the official sources this project is allowed to cite.

Rule enforced everywhere downstream: a row may only be published with
`verified: true` when its `source_url` points at one of these official pages and
the value was actually read off that page. Anything else stays null and is
flagged.

Official = published by the league (nfl.com) or by a club on its own official
team site. Odds / betting lines are NOT available from any official NFL source,
so they are deliberately absent from this registry (see data/market_lines.json,
which ships empty and flagged).
"""

from __future__ import annotations

from typing import Dict, List

NFL = "https://www.nfl.com"

# ---------------------------------------------------------------- team registry
# NFL.com slugs are discovered at runtime from the standings page (never guessed).
# Only the official club domain is listed here, and it is validated by the
# pipeline at runtime (HTTP status + page title must contain "Depth Chart").
CLUB_DOMAINS: Dict[str, str] = {
    "ARI": "arizonacardinals.com",
    "ATL": "atlantafalcons.com",
    "BAL": "baltimoreravens.com",
    "BUF": "buffalobills.com",
    "CAR": "carolinapanthers.com",
    "CHI": "chicagobears.com",
    "CIN": "cincinnatibengals.com",
    "CLE": "clevelandbrowns.com",
    "DAL": "dallascowboys.com",
    "DEN": "denverbroncos.com",
    "DET": "detroitlions.com",
    "GB": "greenbaypackers.com",
    "HOU": "houstontexans.com",
    "IND": "indianapoliscolts.com",
    "JAX": "jacksonvillejaguars.com",
    "KC": "kansascitychiefs.com",
    "LV": "lasvegasraiders.com",
    "LAC": "chargers.com",
    "LA": "rams.com",
    "MIA": "miamidolphins.com",
    "MIN": "minnesotavikings.com",
    "NE": "newenglandpatriots.com",
    "NO": "neworleanssaints.com",
    "NYG": "giants.com",
    "NYJ": "newyorkjets.com",
    "PHI": "philadelphiaeagles.com",
    "PIT": "steelers.com",
    "SF": "49ers.com",
    "SEA": "seahawks.com",
    "TB": "tampabaybuccaneers.com",
    "TEN": "tennesseetitans.com",
    "WAS": "commanders.com",
}

# NFL.com logo assets use AZ where the club domain list uses ARI.
ABBREV_ALIASES: Dict[str, str] = {"AZ": "ARI"}

# Candidate paths; the first one that yields a page whose title contains
# "depth chart" and that parses to rows wins.
DEPTH_CHART_PATHS: List[str] = [
    "/team/depth-chart",
    "/team/depth-chart/",
    "/depth-chart",
]

# ------------------------------------------------------------- league datasets
STANDINGS_URL = f"{NFL}/standings/league/2026/REG"
INJURIES_URL = f"{NFL}/injuries/"
INJURY_POLICY_URL = (
    "https://www.nfl.com/news/competition-committee-approves-revisions-to-injury-report"
    "-0ap3000000688693"
)
TIEBREAK_URL = f"{NFL}/standings/tiebreakingprocedures"

TEAM_STAT_CATEGORIES: List[Dict[str, str]] = [
    {"side": "offense", "category": "passing", "label": "Offense — Passing"},
    {"side": "offense", "category": "rushing", "label": "Offense — Rushing"},
    {"side": "offense", "category": "receiving", "label": "Offense — Receiving"},
    {"side": "offense", "category": "scoring", "label": "Offense — Scoring"},
    {"side": "offense", "category": "downs", "label": "Offense — Downs"},
    {"side": "defense", "category": "passing", "label": "Defense — Passing"},
    {"side": "defense", "category": "rushing", "label": "Defense — Rushing"},
    {"side": "defense", "category": "scoring", "label": "Defense — Scoring"},
    {"side": "defense", "category": "downs", "label": "Defense — Downs"},
]


def team_stat_url(side: str, category: str, season: int = 2026) -> str:
    return f"{NFL}/stats/team-stats/{side}/{category}/{season}/reg/all"


def club_domain(abbrev: str) -> str:
    return CLUB_DOMAINS.get(ABBREV_ALIASES.get(abbrev, abbrev), "")


def depth_chart_url(abbrev: str, path: str = "/team/depth-chart") -> str:
    domain = club_domain(abbrev)
    return f"https://www.{domain}{path}" if domain else ""


# ------------------------------------------------------- extra probe candidates
# Pages we want to know about but have not validated yet. The pipeline probes
# them and records status/table shape in data/_probe.json. Nothing is published
# from a probe.
PROBE_URLS: List[str] = [
    # Already validated: standings (2026 + 2025), injuries, team stats, club
    # depth charts. Everything below is still unvalidated, so nothing is
    # published from it until a probe shows real server-rendered tables.
    f"{NFL}/standings/league/2025/REG",
    f"{NFL}/standings/division/2026/REG",
    f"{NFL}/schedules/2026/REG",
    f"{NFL}/schedules/2026/reg10",
    f"{NFL}/scores/",
    f"{NFL}/scores/2026/REG10",
    f"{NFL}/stats/player-stats/category/passing/2026/reg/all",
    f"{NFL}/stats/player-stats/category/receiving/2026/reg/all",
    f"{NFL}/stats/player-stats/category/rushing/2026/reg/all",
]

# ---------------------------------------------------------- non-official notice
MARKET_LINES_NOTE = (
    "No official NFL or club source publishes betting lines, spreads, totals, "
    "moneylines or player-prop prices. Market lines therefore cannot be "
    "verified and are never filled in from memory. Licensed sportsbook output "
    "or the user's own account feed must be supplied before this table can be "
    "populated."
)
