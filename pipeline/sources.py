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

DEPTH_CHART_PATH = "/team/depth-chart"

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


def depth_chart_url(abbrev: str) -> str:
    domain = CLUB_DOMAINS.get(abbrev)
    return f"https://www.{domain}{DEPTH_CHART_PATH}" if domain else ""


# ------------------------------------------------------- extra probe candidates
# Pages we want to know about but have not validated yet. The pipeline probes
# them and records status/table shape in data/_probe.json. Nothing is published
# from a probe.
PROBE_URLS: List[str] = [
    f"{NFL}/schedules/2026/REG",
    f"{NFL}/schedules/2026/reg1",
    f"{NFL}/scores/",
    f"{NFL}/standings/league/2025/REG",
    f"{NFL}/stats/team-stats/offense/passing/2025/reg/all",
]

# ---------------------------------------------------------- non-official notice
MARKET_LINES_NOTE = (
    "No official NFL or club source publishes betting lines, spreads, totals, "
    "moneylines or player-prop prices. Market lines therefore cannot be "
    "verified and are never filled in from memory. Licensed sportsbook output "
    "or the user's own account feed must be supplied before this table can be "
    "populated."
)
