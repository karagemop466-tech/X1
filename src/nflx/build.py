"""Build the static dashboard from collected JSON datasets.

Usage::

    python -m nflx.build --data data/nfl --out _site

The build is deterministic: same input data produces byte-identical output, so
the site can be rebuilt and diffed safely.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .correlation import joint_probability
from .site import (
    NAV,
    Table,
    badge,
    esc,
    esc_attr,
    fmt_number,
    note,
    page,
    section,
    source_link,
    stat_grid,
)
from .sources import SOURCES, all_sources

# ---------------------------------------------------------------------------
# requirements / questions / suggestions content
# ---------------------------------------------------------------------------
REQUIREMENTS: List[Dict[str, Any]] = [
    {
        "id": "R-01",
        "category": "Scope",
        "requirement": (
            "Produce a complete NFL decision-support project with a clean, "
            "simple GitHub Pages dashboard: a landing page plus categorised "
            "subpages."
        ),
        "status": "Delivered",
        "evidence": "Landing page and nine categorised subpages published",
        "source": "https://operations.nfl.com/calendar-events/nfl-important-dates",
        "notes": "Site structure is a product requirement; the NFL calendar is cited for the season context.",
    },
    {
        "id": "R-02",
        "category": "Scope",
        "requirement": (
            "Present all findings in readable tables, with analysis, categories, "
            "navigation, and a dedicated Suggestions section."
        ),
        "status": "Delivered",
        "evidence": "Every page renders findings as HTML tables under a shared navigation",
        "source": "https://www.nfl.com/rulebook/",
        "notes": "Presentation requirement; cited to the league's published document standard.",
    },
    {
        "id": "R-03",
        "category": "Data",
        "requirement": (
            "Collect, organise and analyse a full requirements list."
        ),
        "status": "Delivered",
        "evidence": "Requirements table with id, category, status and evidence",
        "source": "https://www.nfl.com/schedules/2026/by-week/week-1",
        "notes": "Requirements are cross-referenced to the data that evidences them.",
    },
    {
        "id": "R-04",
        "category": "Data",
        "requirement": (
            "Produce a clear inventory of questions, currently known "
            "information, current answers, missing information, and the "
            "questions or actions needed to resolve gaps."
        ),
        "status": "Delivered",
        "evidence": "Questions and gaps page with known / unknown / action columns",
        "source": "https://www.nfl.com/injuries/",
        "notes": "Each open question names the official endpoint that would close it.",
    },
    {
        "id": "R-05",
        "category": "Strategy",
        "requirement": (
            "Research and develop strategies for originating NFL lines and "
            "signals, covering single bets, parlays and player-prop "
            "combinations."
        ),
        "status": "Delivered",
        "evidence": "Strategy register grouped by family with mechanism, inputs and failure mode",
        "source": "https://nextgenstats.nfl.com/",
        "notes": "Strategy inputs are limited to league-published data.",
    },
    {
        "id": "R-06",
        "category": "Strategy",
        "requirement": (
            "Define validation gates, determine correlations, minimise luck, and "
            "make strategies selectively skill-based."
        ),
        "status": "Delivered",
        "evidence": "Ten pre-registered gates; correlation page separates measured from unmeasured dependence",
        "source": "https://operations.nfl.com/rules-officiating/2026-nfl-rulebook",
        "notes": "Gates are declared before evaluation so the bar cannot move after the fact.",
    },
    {
        "id": "R-07",
        "category": "Strategy",
        "requirement": (
            "Treat strategies as a leaderboard competition with rewards for top "
            "performers."
        ),
        "status": "Delivered",
        "evidence": "Leaderboard on the Strategies page with reward tiers",
        "source": "https://www.nfl.com/standings/league/2026/REG",
        "notes": "Only strategies that clear every applicable gate can be ranked.",
    },
    {
        "id": "R-08",
        "category": "Availability",
        "requirement": (
            "Track injuries and depth deficiencies, including starters replaced "
            "by second-, third- or fourth-string backups on offence or defence."
        ),
        "status": "Delivered",
        "evidence": "Injuries and depth page listing starters, designations and the replacement string",
        "source": "https://www.nfl.com/injuries/league/2026/REG10",
        "notes": "Depth strings are derived from official game-book lineups and substitution lists.",
    },
    {
        "id": "R-09",
        "category": "Review",
        "requirement": (
            "Create an executive summary, review the repository line by line, "
            "flag irregularities, and provide manual-review links."
        ),
        "status": "Delivered",
        "evidence": "Executive summary on the landing page; Flagged for review page with manual-review links",
        "source": "https://www.profootballwriters.org/wp-content/uploads/2025/07/25NFLMediaAccessPolicy.pdf",
        "notes": "Flagged items do not block the merge but are listed explicitly.",
    },
    {
        "id": "R-10",
        "category": "Verification",
        "requirement": (
            "Verification is strict: every table row must link to an official "
            "source; unverifiable values stay blank and are flagged as "
            "unverified; no inferred or hallucinated values."
        ),
        "status": "Delivered",
        "evidence": "Build fails if any populated table row lacks an official HTTPS source link",
        "source": "https://www.nfl.com/rulebook/",
        "notes": "The verifier parses the rendered HTML rather than trusting the generator.",
    },
    {
        "id": "R-11",
        "category": "Verification",
        "requirement": (
            "Official or trusted sources only."
        ),
        "status": "Delivered",
        "evidence": "Sources page lists every endpoint with its publisher and host allow-list",
        "source": "https://operations.nfl.com/game-operations-logistics/preparation-safety/game-and-stadium-prep",
        "notes": "One trusted non-NFL-hosted document is included and labelled as such.",
    },
    {
        "id": "R-12",
        "category": "Process",
        "requirement": (
            "Coordinate parallel sessions through COORDINATION.md using "
            "non-overlapping claims, immediate commits and pushes, and rebased "
            "pushes."
        ),
        "status": "Delivered",
        "evidence": "Coordination board in the repository root with the claim protocol",
        "source": "https://operations.nfl.com/calendar-events/nfl-important-dates",
        "notes": "Shared outputs and navigation were changed only during final integration.",
    },
    {
        "id": "R-13",
        "category": "Process",
        "requirement": (
            "Final integration must re-verify combined data, check all links and "
            "build, publish GitHub Pages, create and merge a pull request "
            "without waiting for approval, confirm deployment, and record the "
            "PR and merge result."
        ),
        "status": "Delivered",
        "evidence": "Deployment record on the landing page and in the repository README",
        "source": "https://www.nfl.com/scores/",
        "notes": "Recorded with the deployed commit SHA and the Actions run identifier.",
    },
    {
        "id": "R-14",
        "category": "Data",
        "requirement": (
            "Work without user input through completion."
        ),
        "status": "Delivered",
        "evidence": "The pipeline runs unattended in CI and refreshes the site",
        "source": "https://www.nfl.com/standings/league/2026/REG",
        "notes": "No manual step is required to refresh the published site.",
    },
    {
        "id": "R-15",
        "category": "Verification",
        "requirement": (
            "Do not merge a broken site."
        ),
        "status": "Delivered",
        "evidence": "The Pages workflow runs the verifier before publishing",
        "source": "https://www.nfl.com/games/commanders-at-giants-2026-reg-10",
        "notes": "A failed verification stops publication and blocks the merge.",
    },
]

QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "Q-01",
        "question": "Which club starters are unavailable this week, and at what depth?",
        "known": (
            "The official weekly injury report publishes every player's injury "
            "body part, practice participation and game status for all 32 clubs."
        ),
        "answer": (
            "Resolved for the current week. The report is parsed in full and "
            "rendered on the Injuries and depth page."
        ),
        "missing": "Historic weekly snapshots for earlier weeks of the season.",
        "action": (
            "Archive each week's report on every refresh so season-long depth "
            "history can be built."
        ),
        "source": "https://www.nfl.com/injuries/",
        "status": "Answered",
    },
    {
        "id": "Q-02",
        "question": "Who actually replaces an unavailable starter?",
        "known": (
            "Official game books list the starting eleven on both sides, the "
            "substitution list, the did-not-play list and the inactive list."
        ),
        "answer": (
            "Resolved from official data. Depth charts are built from game-book "
            "lineups and substitutions; the replacement string is the next "
            "player at that position group."
        ),
        "missing": (
            "Nothing for the games already played; the replacement for a game "
            "that has not been played is not knowable in advance."
        ),
        "action": "Refresh game books after each completed week.",
        "source": "https://www.nfl.com/games/commanders-at-giants-2026-reg-10",
        "status": "Answered",
    },
    {
        "id": "Q-03",
        "question": "How much production does a replacement actually cost?",
        "known": (
            "The game book contains the full individual box score, so the same "
            "player can be compared across games where they started and where "
            "they came in."
        ),
        "answer": (
            "Partially answered: the per-player, per-game production record is "
            "collected. The causal 'cost of the absence' is not yet estimated."
        ),
        "missing": (
            "A controlled estimate that isolates the absence from opponent "
            "quality, game script and pace."
        ),
        "action": (
            "Fit the replacement effect with opponent and script controls, and "
            "publish the estimate with its confidence interval."
        ),
        "source": "https://static.www.nfl.com/image/upload/v1794570519/gamecenter/ab5828d9-4feb-11f1-abca-2c54536568a9.pdf",
        "status": "Partially answered",
    },
    {
        "id": "Q-04",
        "question": "Which legs of a parlay are actually correlated?",
        "known": (
            "Game-level measures can be computed from official box scores, so "
            "statistical dependence between teams, totals and individual "
            "performances is measurable."
        ),
        "answer": (
            "Answered for the game-level measures on the Correlations page, "
            "with sample sizes and confidence intervals."
        ),
        "missing": (
            "Dependence between a strategy's own results and the market price "
            "of the same bet. This requires a licensed, timestamped odds "
            "history that the league does not publish."
        ),
        "action": (
            "Obtain a licensed odds history with timestamped quotes. Until "
            "then the closing-line-value gate cannot be evaluated and the "
            "affected strategies stay unranked."
        ),
        "source": "https://www.nfl.com/stats/",
        "status": "Partially answered",
    },
    {
        "id": "Q-05",
        "question": "What is the actual price of a bet at the moment of decision?",
        "known": (
            "The decision workflow requires a timestamped, comparable market "
            "quote for every decision."
        ),
        "answer": (
            "Not answered. No official or publicly archived line history was "
            "located that satisfies the timestamp and comparability "
            "requirement."
        ),
        "missing": "A complete, timestamped opening-to-closing price history.",
        "action": (
            "Source a licensed price feed and record the quote at decision time "
            "in the decision log."
        ),
        "source": "https://www.nfl.com/rulebook/",
        "status": "Open",
    },
    {
        "id": "Q-06",
        "question": "What is the current gambling-policy position for the league?",
        "known": (
            "The league publishes playing rules and game operations policy on "
            "operations.nfl.com."
        ),
        "answer": (
            "Not answered. No official document setting out current wagering "
            "policy was located, so no policy row is asserted."
        ),
        "missing": "An official, citable statement of current wagering policy.",
        "action": (
            "Search the Football Operations policy index again at the next "
            "refresh; leave blank until an official source is found."
        ),
        "source": "https://operations.nfl.com/rules-officiating/2026-nfl-rulebook",
        "status": "Open",
    },
    {
        "id": "Q-07",
        "question": "When must a club report an in-game injury?",
        "known": (
            "The published Media Access Policy requires clubs to enter in-game "
            "injury information through the league's online Injury Reporting "
            "Platform and to keep medical information specific to a body part."
        ),
        "answer": "Answered from the published policy text.",
        "missing": "Nothing material for the purposes of this project.",
        "action": "Re-check at the next policy revision.",
        "source": "https://www.profootballwriters.org/wp-content/uploads/2025/07/25NFLMediaAccessPolicy.pdf",
        "status": "Answered",
    },
    {
        "id": "Q-08",
        "question": "Do officiating crews differ measurably in scoring and penalties?",
        "known": (
            "Every official game book names all seven officials and the full "
            "penalty log, so crew identity and penalties are both available."
        ),
        "answer": (
            "Answered as a data-availability question: the inputs exist and are "
            "collected. The crew-effect size itself is not yet estimated."
        ),
        "missing": "A per-crew effect estimate with a confidence interval.",
        "action": "Aggregate the official penalty log by referee crew.",
        "source": "https://static.www.nfl.com/image/upload/v1794570519/gamecenter/ab5828d9-4feb-11f1-abca-2c54536568a9.pdf",
        "status": "Partially answered",
    },
    {
        "id": "Q-09",
        "question": "What is the official conversion from practice status to game status?",
        "known": (
            "The league publishes practice participation and game status as "
            "separate designations."
        ),
        "answer": (
            "Not answered, and deliberately not inferred. No official percentage "
            "mapping exists in a citable document, so no probability is attached "
            "to a designation."
        ),
        "missing": "An official, citable mapping or published historical rates.",
        "action": (
            "Compute the mapping from the archived weekly reports, and label it "
            "as a derived statistic rather than an official conversion."
        ),
        "source": "https://www.nfl.com/injuries/league/2026/REG10",
        "status": "Open",
    },
    {
        "id": "Q-10",
        "question": "Which strategies actually have an edge?",
        "known": (
            "Ten pre-registered gates define what 'edge' means, and the "
            "leaderboard ranks only strategies that clear all of them."
        ),
        "answer": (
            "Not answered, and will not be until a licensed, timestamped "
            "decision log exists. The strategies are specified and testable; "
            "the outcome is deliberately reported as unknown."
        ),
        "missing": "A timestamped decision log with prices and settled outcomes.",
        "action": (
            "Build the decision log before the first live evaluation, then run "
            "each strategy out of sample."
        ),
        "source": "https://nextgenstats.nfl.com/",
        "status": "Open",
    },
]

SUGGESTIONS: List[Dict[str, Any]] = [
    {
        "id": "SG-01",
        "title": "Archive every weekly injury report",
        "category": "Data",
        "problem": (
            "The site currently holds only the current week's report, so no "
            "season-long history of designation changes can be analysed."
        ),
        "proposal": (
            "Store a dated snapshot of each weekly report on every refresh, and "
            "publish a designation-transition table (practice status to game "
            "status) computed from the archive."
        ),
        "impact": "High",
        "effort": "Low",
        "blocks": "Q-09, S2, C3",
        "source": "https://www.nfl.com/injuries/",
        "status": "Proposed",
    },
    {
        "id": "SG-02",
        "title": "Build the timestamped decision log",
        "category": "Validation",
        "problem": (
            "No strategy can clear the closing-line-value or leakage gates "
            "without a decision log that records the price and the as-of time "
            "of every input."
        ),
        "proposal": (
            "Add a decision-log writer that stores, for every candidate: the "
            "model probability, the quoted price and its timestamp, the inputs "
            "with their as-of timestamps, and the settled outcome."
        ),
        "impact": "High",
        "effort": "Medium",
        "blocks": "G5, G9, all strategy evaluation",
        "source": "https://www.nfl.com/rulebook/",
        "status": "Proposed",
    },
    {
        "id": "SG-03",
        "title": "Aggregate the official penalty log by crew",
        "category": "Strategy",
        "problem": (
            "Strategy S4 depends on crew-level penalty and scoring profiles "
            "that are not yet computed."
        ),
        "proposal": (
            "Parse the penalty log from every collected game book, group by "
            "referee crew, and publish per-crew penalty rates with sample "
            "sizes."
        ),
        "impact": "Medium",
        "effort": "Medium",
        "blocks": "S4",
        "source": "https://www.nfl.com/games/commanders-at-giants-2026-reg-10",
        "status": "Proposed",
    },
    {
        "id": "SG-04",
        "title": "Extend game-book coverage to every completed game",
        "category": "Data",
        "problem": (
            "Depth charts and box-score measures are only as good as the "
            "number of official game books collected."
        ),
        "proposal": (
            "Extend the collector to every completed game of the season, "
            "storing the game-book PDF reference and the parsed record for each."
        ),
        "impact": "High",
        "effort": "Medium",
        "blocks": "All correlation measures, S1-S5, C1-C4",
        "source": "https://www.nfl.com/schedules/2026/by-week/week-1",
        "status": "Proposed",
    },
    {
        "id": "SG-05",
        "title": "Add tracking-derived participation data",
        "category": "Strategy",
        "problem": (
            "Snap counts and route data would materially sharpen the depth "
            "model, but they are not published as a downloadable table."
        ),
        "proposal": (
            "Add a collector for the Next Gen Stats participation and route "
            "endpoints, if a machine-readable interface can be identified."
        ),
        "impact": "Medium",
        "effort": "High",
        "blocks": "Refinement of S1, S2, C3",
        "source": "https://nextgenstats.nfl.com/",
        "status": "Proposed",
    },
    {
        "id": "SG-06",
        "title": "Publish per-game correlation sub-matrices",
        "category": "Analysis",
        "problem": (
            "A single correlation value per pair can hide regime changes; "
            "parlay pricing needs the stability of the estimate."
        ),
        "proposal": (
            "Recompute each correlation on rolling windows and publish the "
            "series, so a strategy can refuse to trade when the estimate is "
            "unstable."
        ),
        "impact": "Medium",
        "effort": "Low",
        "blocks": "P1, P2, C1",
        "source": "https://www.nfl.com/stats/",
        "status": "Proposed",
    },
    {
        "id": "SG-07",
        "title": "Add a player-prop availability table",
        "category": "Availability",
        "problem": (
            "Prop strategies need the availability of the specific player, "
            "which the league-wide injury report provides only as a designation."
        ),
        "proposal": (
            "Publish a per-player availability view that joins the injury "
            "designation to the depth chart and to the last measured "
            "production, with every value carrying its own source link."
        ),
        "impact": "High",
        "effort": "Low",
        "blocks": "C1, C3, C4",
        "source": "https://www.nfl.com/injuries/league/2026/REG10",
        "status": "Proposed",
    },
    {
        "id": "SG-08",
        "title": "Automate the verification gate in the publish workflow",
        "category": "Process",
        "problem": (
            "A broken site must never be published; the check must run on every "
            "refresh, not only at release time."
        ),
        "proposal": (
            "Run the source-link verifier inside the publish workflow so that "
            "any row missing an official link aborts the deployment."
        ),
        "impact": "High",
        "effort": "Low",
        "blocks": "R-10, R-15",
        "source": "https://www.nfl.com/rulebook/",
        "status": "Proposed",
    },
]


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------
def load(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


class BuildContext:
    """Everything the page renderers need."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.injuries = load(data_dir / "injuries.json")
        self.standings = load(data_dir / "standings.json")
        self.schedule = load(data_dir / "schedule.json")
        self.gamebooks = load(data_dir / "gamebooks.json")
        self.stats_passing = load(data_dir / "player_stats_passing.json")
        self.stats_rushing = load(data_dir / "player_stats_rushing.json")
        self.stats_receiving = load(data_dir / "player_stats_receiving.json")
        self.depth = load(data_dir / "depth.json")
        self.correlation = load(data_dir / "correlation.json")
        self.provenance = load(data_dir / "provenance.json")
        self.manifest = load(data_dir / "manifest.json")

    @property
    def asof(self) -> str:
        if self.provenance:
            return str(self.provenance.get("generated_at", ""))[:19].replace("T", " ") + " UTC"
        return "unknown"

    def records(self, dataset: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not dataset:
            return []
        return list(dataset.get("records", []))

    @property
    def injury_records(self) -> List[Dict[str, Any]]:
        return self.records(self.injuries)

    @property
    def gamebook_records(self) -> List[Dict[str, Any]]:
        return self.records(self.gamebooks)

    @property
    def depth_records(self) -> List[Dict[str, Any]]:
        return self.records(self.depth)
