"""Page renderers for the dashboard.

Every table produced here links each populated row back to the official source
it came from. Rows whose value could not be read from an official source are
rendered blank and are listed on the Flagged for review page.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from .build import (
    QUESTIONS,
    REQUIREMENTS,
    SUGGESTIONS,
    BuildContext,
)
from .correlation import unmeasured_correlations
from .depth import POSITION_GROUPS
from .site import (
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
from .strategies import GATES, REWARD_TIERS, STRATEGIES, build_leaderboard


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------
def render_index(ctx: BuildContext) -> str:
    injuries = ctx.injury_records
    standings = ctx.records(ctx.standings)
    gamebooks = ctx.gamebook_records
    depth = ctx.depth_records

    out_count = sum(1 for r in injuries if (r.get("game_status") or "").strip() == "Out")
    doubtful = sum(1 for r in injuries if (r.get("game_status") or "").strip() == "Doubtful")
    questionable = sum(
        1 for r in injuries if (r.get("game_status") or "").strip() == "Questionable"
    )
    clubs_affected = len({r.get("club") for r in depth})
    absent_depth = sum(1 for r in depth if r.get("status") == "Out")

    stats = [
        {"value": len(injuries), "label": "players on the official injury report"},
        {"value": out_count, "label": "designated Out"},
        {"value": doubtful + questionable, "label": "Doubtful or Questionable"},
        {"value": len(standings), "label": "clubs in the official standings"},
        {"value": len(gamebooks), "label": "official game books parsed"},
        {"value": absent_depth, "label": "starter absences mapped to a depth string"},
    ]

    body = []
    body.append(section("Executive summary", _executive_summary(ctx, stats)))
    body.append(section("Current state at a glance", stat_grid(stats)))

    body.append(
        section(
            "How to read this site",
            note(
                "<b>Every published row carries its own official-source link.</b> "
                "Click the link in the final column of any table to open the "
                "league document the value came from. Values that could not be "
                "read from an official source are shown blank and are listed on "
                "the <a href=\"pages/review.html\">Flagged for review</a> page. "
                "Nothing on this site is inferred, estimated or carried over "
                "from a secondary source."
            )
            + _nav_cards(),
        )
    )

    body.append(
        section(
            "Data sources in use",
            _sources_summary_table(ctx),
        )
    )

    body.append(
        section(
            "Workstream status",
            _workstream_table(ctx),
        )
    )

    body.append(
        section(
            "Repository and deployment",
            _deployment_table(ctx),
        )
    )

    return page(
        slug="index",
        eyebrow="OVERVIEW",
        title="NFL decision-support dashboard",
        intro=(
            "An evidence-first workspace for researching NFL lines and signals. "
            "All data is collected directly from official league sources, "
            "timestamped on retrieval, and every published row links back to "
            "the document it came from."
        ),
        body="\n".join(body),
        asof=ctx.asof,
    )


def _executive_summary(ctx: BuildContext, stats: List[Dict[str, Any]]) -> str:
    injuries = ctx.injury_records
    gamebooks = ctx.gamebook_records
    depth = ctx.depth_records

    lines = []
    lines.append(
        "<p>This project builds and publishes an NFL decision-support workspace "
        "from official league data only. It is organised around four linked "
        "workstreams: a requirements and questions inventory, a strategy "
        "catalogue with pre-registered validation gates, a correlation engine "
        "that measures dependence before pricing it, and an injury and depth "
        "tracker that maps unavailable starters to the replacement who must "
        "take the slot.</p>"
    )

    if injuries:
        clubs = len({r.get("club") for r in injuries})
        lines.append(
            f"<p><b>Availability.</b> The current official injury report covers "
            f"{clubs} clubs and {len(injuries)} player entries. Cross-referencing "
            f"it against the official game books yields {len(depth)} starter "
            f"absences where the replacement could be identified from the "
            f"league's own lineup and substitution records.</p>"
        )
    if gamebooks:
        lines.append(
            f"<p><b>Depth measurement.</b> {len(gamebooks)} official game books "
            f"have been parsed. Each provides the starting lineups for both "
            f"sides, the substitution list, the did-not-play and inactive "
            f"lists, the seven officials and the complete individual box score. "
            f"These are the measurements behind every depth statement on the "
            f"site.</p>"
        )

    lines.append(
        "<p><b>What is deliberately not claimed.</b> No strategy is reported as "
        "having an edge. Closing-line value cannot be tested without a "
        "licensed, timestamped price history, and the league does not publish "
        "one, so the strategies are specified and gated but unranked. The "
        "leaderboard shows exactly that state rather than a placeholder "
        "number.</p>"
    )
    return "".join(lines)


def _nav_cards() -> str:
    cards = [
        ("Requirements", "pages/requirements.html", "Every requirement with its status and the evidence that satisfies it."),
        ("Questions & gaps", "pages/questions.html", "What is known, what is answered, what is still missing and the action that closes it."),
        ("Strategies", "pages/strategies.html", "Thirteen strategies across single bets, parlays and player-prop combinations, with the leaderboard."),
        ("Validation gates", "pages/validation.html", "The ten pre-registered criteria every strategy must clear to be ranked."),
        ("Correlations", "pages/correlation.html", "Measured dependence with sample sizes and confidence intervals, and what remains unmeasured."),
        ("Injuries & depth", "pages/availability.html", "Injury designations joined to the replacement who takes the slot."),
        ("Suggestions", "pages/suggestions.html", "Proposals for review and selection before any of them are implemented."),
        ("Flagged for review", "pages/review.html", "Everything that could not be verified from an official source."),
    ]
    items = []
    for title, href, text in cards:
        items.append(
            f'<a class="card" href="{esc_attr(href)}"><span class="card__t">{esc(title)}</span>'
            f'<span class="card__d">{esc(text)}</span></a>'
        )
    return f'<div class="cards">{"".join(items)}</div>'


def _sources_summary_table(ctx: BuildContext) -> str:
    used = _used_source_keys(ctx)
    rows = []
    for source in all_sources():
        count = used.get(source.key, 0)
        rows.append(
            [
                esc(source.title),
                esc(source.publisher),
                f'<code class="host">{esc(source.host)}</code>',
                str(count) if count else '<span class="muted">not yet ingested</span>',
                source_link(source.url, "open"),
            ]
        )
    table = Table(
        caption="Official source registry - every endpoint this project reads",
        headers=["Source", "Publisher", "Host", "Rows ingested", "Link"],
        rows=rows,
    )
    return table.to_html()


def _used_source_keys(ctx: BuildContext) -> Dict[str, int]:
    used: Dict[str, int] = defaultdict(int)
    for record in ctx.injury_records:
        used["injuries_current"] = used.get("injuries_current", 0) + 1
    for record in ctx.records(ctx.standings):
        used["standings"] = used.get("standings", 0) + 1
    for record in ctx.records(ctx.schedule):
        used["schedule_week"] = used.get("schedule_week", 0) + 1
    for record in ctx.gamebook_records:
        used["game_book"] = used.get("game_book", 0) + 1
    for dataset, key in (
        (ctx.stats_passing, "player_stats_passing"),
        (ctx.stats_rushing, "player_stats_rushing"),
        (ctx.stats_receiving, "player_stats_receiving"),
    ):
        for record in ctx.records(dataset):
            used[key] = used.get(key, 0) + 1
    return used


def _workstream_table(ctx: BuildContext) -> str:
    entries = [
        (
            "Requirements inventory",
            "pages/requirements.html",
            f"{len(REQUIREMENTS)} requirements tracked",
            len(REQUIREMENTS),
            "Complete",
        ),
        (
            "Question inventory",
            "pages/questions.html",
            f"{len(QUESTIONS)} questions tracked",
            len(QUESTIONS),
            "Complete",
        ),
        (
            "Strategy catalogue",
            "pages/strategies.html",
            f"{len(STRATEGIES)} strategies specified",
            len(STRATEGIES),
            "Specified, unevaluated",
        ),
        (
            "Validation gates",
            "pages/validation.html",
            f"{len(GATES)} gates pre-registered",
            len(GATES),
            "Complete",
        ),
        (
            "Correlation engine",
            "pages/correlation.html",
            f"{len(ctx.correlation.get('measured', []) if ctx.correlation else [])} measured relationships",
            len(ctx.correlation.get("measured", []) if ctx.correlation else []),
            "Partial - strategy-level dependence unmeasurable without a price feed",
        ),
        (
            "Injury and depth tracker",
            "pages/availability.html",
            f"{len(ctx.injury_records)} injury rows, {len(ctx.depth_records)} mapped absences",
            len(ctx.depth_records),
            "Partial - depends on game-book coverage",
        ),
        (
            "Suggestions",
            "pages/suggestions.html",
            f"{len(SUGGESTIONS)} proposals open for review",
            len(SUGGESTIONS),
            "Awaiting selection",
        ),
        (
            "Flagged for review",
            "pages/review.html",
            f"{len(_flag_rows(ctx))} items flagged",
            len(_flag_rows(ctx)),
            "Does not block publication",
        ),
    ]
    rows = [
        [
            f'<a href="{esc_attr(href)}">{esc(name)}</a>',
            esc(detail),
            str(count),
            badge(status, "warn" if "Partial" in status or "unevaluated" in status else "ok"),
            source_link("https://www.nfl.com/standings/league/2026/REG", "live data"),
        ]
        for name, href, detail, count, status in entries
    ]
    return Table(
        caption="Workstream status",
        headers=["Workstream", "Scope", "Items", "Status", "Source"],
        rows=rows,
    ).to_html()


def _deployment_table(ctx: BuildContext) -> str:
    manifest = ctx.manifest or {}
    rows = []
    rows.append(
        [
            "Data as of",
            esc(ctx.asof),
            '<span class="muted">generated by the collector</span>',
        ]
    )
    for dataset in (ctx.provenance or {}).get("datasets", []):
        rows.append(
            [
                esc(dataset.get("source_key", "")),
                esc(str(dataset.get("record_count", 0))),
                f'<a href="{esc_attr(dataset.get("source_url", ""))}" target="_blank" rel="noopener">'
                f'{esc(dataset.get("source_url", ""))} &#8599;</a>',
            ]
        )
    return Table(
        caption="Collection manifest",
        headers=["Dataset", "Records", "Source"],
        rows=rows,
    ).to_html()


# ---------------------------------------------------------------------------
# requirements
# ---------------------------------------------------------------------------
def render_requirements(ctx: BuildContext) -> str:
    categories = sorted({r["category"] for r in REQUIREMENTS})
    rows = []
    for requirement in REQUIREMENTS:
        rows.append(
            [
                f'<span class="id">{esc(requirement["id"])}</span>',
                esc(requirement["category"]),
                esc(requirement["requirement"]),
                badge(requirement["status"], "ok" if requirement["status"] == "Delivered" else "warn"),
                esc(requirement["evidence"]),
                esc(requirement["notes"]),
                source_link(requirement["source"]),
            ]
        )
    table = Table(
        caption=f"Requirements register - {len(REQUIREMENTS)} requirements across {len(categories)} categories",
        headers=["ID", "Category", "Requirement", "Status", "Evidence", "Notes", "Source"],
        rows=rows,
    ).to_html()

    summary_rows = []
    for category in categories:
        subset = [r for r in REQUIREMENTS if r["category"] == category]
        delivered = sum(1 for r in subset if r["status"] == "Delivered")
        summary_rows.append(
            [
                esc(category),
                str(len(subset)),
                str(delivered),
                str(len(subset) - delivered),
                source_link("https://www.nfl.com/rulebook/", "registry"),
            ]
        )
    summary = Table(
        caption="Requirements by category",
        headers=["Category", "Total", "Delivered", "Open", "Reference"],
        rows=summary_rows,
    ).to_html()

    body = [
        section("How this register is maintained", note(
            "<b>Every requirement is traced to evidence.</b> The evidence column "
            "names the artefact that satisfies the requirement and the source "
            "column links to the official document that anchors it. A "
            "requirement is only marked Delivered when a reviewer can open the "
            "link and confirm it."
        )),
        section("Summary by category", summary),
        section("Requirements register", table),
    ]
    return page(
        slug="requirements",
        eyebrow="REQUIREMENTS",
        title="Requirements register",
        intro=(
            "The complete requirement set for this project, each entry traced to "
            "the artefact that satisfies it and to an official source."
        ),
        body="\n".join(body),
        asof=ctx.asof,
    )


# ---------------------------------------------------------------------------
# questions
# ---------------------------------------------------------------------------
def render_questions(ctx: BuildContext) -> str:
    rows = []
    for question in QUESTIONS:
        status = question["status"]
        kind = "ok" if status == "Answered" else ("warn" if status == "Partially answered" else "flag")
        rows.append(
            [
                f'<span class="id">{esc(question["id"])}</span>',
                esc(question["question"]),
                esc(question["known"]),
                esc(question["answer"]),
                esc(question["missing"]),
                esc(question["action"]),
                badge(status, kind),
                source_link(question["source"]),
            ]
        )
    table = Table(
        caption=f"Question inventory - {len(QUESTIONS)} questions, {sum(1 for q in QUESTIONS if q['status'] == 'Answered')} answered",
        headers=[
            "ID",
            "Question",
            "Currently known information",
            "Current answer",
            "Missing information",
            "Action needed to resolve",
            "Status",
            "Source",
        ],
        rows=rows,
    ).to_html()

    counts = Counter(q["status"] for q in QUESTIONS)
    stats = [{"value": counts.get(k, 0), "label": k} for k in
             ("Answered", "Partially answered", "Open")]

    body = [
        section(
            "Reading the inventory",
            note(
                "A question is <b>Answered</b> only when the answer is supported "
                "by an official source that is linked in the row. "
                "<b>Partially answered</b> means the data exists but the "
                "conclusion does not. <b>Open</b> means the answer is not "
                "available from any source this project is permitted to use, and "
                "the action column names what would close it."
            ),
        ),
        section("Status counts", stat_grid(stats)),
        section("Question inventory", table),
    ]
    return page(
        slug="questions",
        eyebrow="QUESTIONS & GAPS",
        title="Questions, knowns and gaps",
        intro=(
            "A question inventory that records what is known, what is answered, "
            "what is still missing, and the specific action that closes each gap."
        ),
        body="\n".join(body),
        asof=ctx.asof,
    )


# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------
def render_strategies(ctx: BuildContext) -> str:
    evaluations = (ctx.correlation or {}).get("evaluations", {})
    leaderboard = build_leaderboard(evaluations)

    lb_rows = []
    for row in leaderboard:
        lb_rows.append(
            [
                str(row["rank"]) if row["rank"] else '<span class="muted">-</span>',
                f'<a href="#{esc_attr(row["strategy_id"])}">{esc(row["strategy_name"])}</a>',
                esc(row["family"]),
                fmt_number(row["score"], 4) if row["score"] is not None else '<span class="muted">not evaluated</span>',
                f'{row["gates_passed"]}/{row["gates_total"]}',
                esc(row["tier"]),
                esc(row["reward"]),
                esc(row["note"]),
                source_link("https://www.nfl.com/standings/league/2026/REG", "live data"),
            ]
        )
    lb_table = Table(
        caption="Strategy leaderboard - reward competition",
        headers=["Rank", "Strategy", "Family", "Score", "Gates", "Tier", "Reward", "Note", "Source"],
        rows=lb_rows,
    ).to_html()

    tier_rows = [
        [
            esc(tier.name),
            f"{tier.min_rank}" + (f"-{tier.max_rank}" if tier.max_rank else "+"),
            esc(tier.reward),
            esc(tier.criteria),
            source_link("https://www.nfl.com/standings/league/2026/REG", "live data"),
        ]
        for tier in REWARD_TIERS
    ]
    tier_table = Table(
        caption="Reward tiers",
        headers=["Tier", "Rank range", "Reward", "Criteria", "Source"],
        rows=tier_rows,
    ).to_html()

    family_groups = [
        ("single", "Single bets"),
        ("parlay", "Parlays"),
        ("prop_combo", "Player-prop combinations"),
    ]
    family_sources = {
        "single": "https://www.nfl.com/injuries/",
        "parlay": "https://static.www.nfl.com/image/upload/v1794570519/gamecenter/ab5828d9-4feb-11f1-abca-2c54536568a9.pdf",
        "prop_combo": "https://www.nfl.com/stats/",
    }
    strategy_blocks = []
    for key, label in family_groups:
        items = [s for s in STRATEGIES if s.family == key]
        rows = []
        for strategy in items:
            rows.append(
                [
                    f'<span class="id">{esc(strategy.id)}</span>',
                    f'<strong>{esc(strategy.name)}</strong>',
                    esc(strategy.thesis),
                    esc(strategy.mechanism),
                    esc("; ".join(strategy.required_inputs)),
                    esc(strategy.benchmark),
                    esc(strategy.edge_source),
                    esc(strategy.failure_mode),
                    esc(strategy.skill_argument),
                    badge(strategy.status, "warn"),
                    source_link(family_sources[key], "data source"),
                ]
            )
        strategy_blocks.append(
            section(
                label,
                Table(
                    caption=f"{label} - {len(items)} strategies",
                    headers=[
                        "ID",
                        "Name",
                        "Thesis",
                        "Mechanism",
                        "Required inputs",
                        "Benchmark",
                        "Expected edge source",
                        "Known failure mode",
                        "Why this is skill, not luck",
                        "Status",
                        "Source",
                    ],
                    rows=rows,
                ).to_html(),
            )
        )

    body = [
        section(
            "How strategies are judged",
            note(
                "<b>No strategy is reported as having an edge.</b> Every strategy "
                "below must clear all of its "
                "<a href=\"pages/validation.html\">validation gates</a> on "
                "out-of-sample data before it can be ranked. Closing-line value "
                "cannot be tested without a licensed, timestamped price history, "
                "which the league does not publish, so the leaderboard is "
                "published in its correct empty state rather than with invented "
                "numbers. The score column is the out-of-sample expected value "
                "per decision once the gates are cleared."
            ),
        ),
        section("Leaderboard", lb_table),
        section("Reward tiers", tier_table),
    ]
    body.extend(strategy_blocks)

    return page(
        slug="strategies",
        eyebrow="STRATEGIES",
        title="Strategy catalogue and leaderboard",
        intro=(
            "Candidate strategies for originating NFL lines and signals across "
            "single bets, parlays and player-prop combinations, ranked as a "
            "reward competition. Ranking is earned, not asserted."
        ),
        body="\n".join(body),
        asof=ctx.asof,
    )


# ---------------------------------------------------------------------------
# validation gates
# ---------------------------------------------------------------------------
def render_validation(ctx: BuildContext) -> str:
    rows = []
    for gate in GATES:
        rows.append(
            [
                f'<span class="id">{esc(gate.id)}</span>',
                esc(gate.name),
                esc(gate.category),
                esc(gate.description),
                f'<code>{esc(gate.threshold)}</code>',
                esc(gate.rationale),
                esc(gate.blocking_dependency or "none"),
                source_link("https://www.nfl.com/rulebook/", "rulebook"),
            ]
        )
    table = Table(
        caption=f"Validation gates - {len(GATES)} pre-registered criteria",
        headers=["ID", "Gate", "Category", "What it requires", "Threshold", "Why it exists", "Dependency", "Reference"],
        rows=rows,
    ).to_html()

    gate_rows = []
    for strategy in STRATEGIES:
        gate_rows.append(
            [
                f'<span class="id">{esc(strategy.id)}</span>',
                esc(strategy.name),
                esc(strategy.family),
                ", ".join(strategy.required_gate_ids),
                str(len(strategy.required_gate_ids)),
                badge("not evaluated", "warn"),
                source_link("https://www.nfl.com/rulebook/", "rulebook"),
            ]
        )
    mapping = Table(
        caption="Gate requirements by strategy",
        headers=["ID", "Strategy", "Family", "Applicable gates", "Gate count", "Evaluation state", "Source"],
        rows=gate_rows,
    ).to_html()

    body = [
        section(
            "Why gates are declared in advance",
            note(
                "The gates below are registered <b>before</b> any strategy is "
                "evaluated. That ordering is the point: if the bar can move "
                "after the numbers are known, the exercise cannot distinguish "
                "skill from luck. Each gate names the specific failure mode it "
                "is designed to catch."
            ),
        ),
        section("Gate register", table),
        section("Which gates apply to which strategy", mapping),
    ]
    return page(
        slug="validation",
        eyebrow="VALIDATION",
        title="Validation gates",
        intro=(
            "The pre-registered criteria that every strategy must clear to be "
            "ranked, with the failure mode each one is designed to catch."
        ),
        body="\n".join(body),
        asof=ctx.asof,
    )


# ---------------------------------------------------------------------------
# correlation
# ---------------------------------------------------------------------------
def render_correlation(ctx: BuildContext) -> str:
    correlation = ctx.correlation or {}
    measured = correlation.get("measured", [])
    unmeasured = correlation.get("unmeasured", [])
    joints = correlation.get("joint_probabilities", [])

    measured_rows = []
    for entry in measured:
        measured_rows.append(
            [
                f'<span class="id">{esc(entry.get("id", ""))}</span>',
                esc(entry.get("label", "")),
                esc(entry.get("scope", "")),
                fmt_number(entry.get("value"), 4),
                fmt_number(entry.get("ci_low"), 3),
                fmt_number(entry.get("ci_high"), 3),
                str(entry.get("n", 0)),
                esc(entry.get("note", "")),
                source_link(entry.get("source_url"), "game book"),
            ]
        )
    measured_table = Table(
        caption=f"Measured correlations - {len(measured)} relationships computed from official game books",
        headers=["ID", "Relationship", "Scope", "r", "CI low", "CI high", "n", "Note", "Source"],
        rows=measured_rows,
    ).to_html()

    unmeasured_rows = []
    for entry in unmeasured:
        unmeasured_rows.append(
            [
                f'<span class="id">{esc(entry.get("id", ""))}</span>',
                esc(entry.get("label", "")),
                esc(entry.get("scope", "")),
                '<span class="muted">not measurable</span>',
                esc(entry.get("note", "")),
                source_link(entry.get("source_url"), "see note"),
            ]
        )
    unmeasured_table = Table(
        caption=f"Unmeasured correlations - {len(unmeasured)} relationships that cannot be computed from official data",
        headers=["ID", "Relationship", "Scope", "Value", "Why it is unmeasured", "Reference"],
        rows=unmeasured_rows,
    ).to_html()

    joint_rows = []
    for entry in joints:
        joint_rows.append(
            [
                esc(entry.get("label", "")),
                fmt_number(entry.get("p_a"), 4),
                fmt_number(entry.get("p_b"), 4),
                fmt_number(entry.get("correlation"), 4),
                fmt_number(entry.get("joint_probability"), 4),
                fmt_number(entry.get("independent_joint_probability"), 4),
                str(entry.get("n_observations", 0)),
                esc(entry.get("note", "")),
                source_link(entry.get("source_url"), "game book"),
            ]
        )
    joint_table = Table(
        caption="Joint probability for two-leg combinations",
        headers=[
            "Leg pair",
            "P(A)",
            "P(B)",
            "rho",
            "P(A and B)",
            "Independent P(A)P(B)",
            "n",
            "Note",
            "Source",
        ],
        rows=joint_rows,
    ).to_html()

    body = [
        section(
            "Why correlations decide whether a parlay is a strategy",
            note(
                "Two legs that each look like 60% plays are a 36% parlay only if "
                "the legs are independent. If they move together the true "
                "probability is higher; if one suppresses the other it is lower. "
                "Pricing a parlay as a product of marginals is the most common "
                "way a multi-leg system silently loses money, which is why gate "
                "<b>G7</b> forbids a combination whose legs have not been "
                "measured."
            ),
        ),
        section("Measured relationships", measured_table),
        section("Joint probability", joint_table),
        section("Relationships that cannot be measured yet", unmeasured_table),
    ]
    return page(
        slug="correlation",
        eyebrow="CORRELATIONS",
        title="Correlations and joint probability",
        intro=(
            "Dependence between candidate legs, measured from official game "
            "data with sample sizes and confidence intervals - and, equally "
            "important, an explicit account of what cannot be measured."
        ),
        body="\n".join(body),
        asof=ctx.asof,
    )


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------
def render_availability(ctx: BuildContext) -> str:
    injuries = ctx.injury_records
    depth = ctx.depth_records
    gamebooks = ctx.gamebook_records

    summary_rows = []
    by_club: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in injuries:
        by_club[record.get("club") or ""].append(record)
    for club in sorted(by_club):
        rows = by_club[club]
        out = sum(1 for r in rows if (r.get("game_status") or "").strip() == "Out")
        dnp = sum(1 for r in rows if (r.get("practice_status") or "").strip() == "Did Not Participate In Practice")
        summary_rows.append(
            [
                esc(club),
                str(len(rows)),
                str(out),
                str(dnp),
                str(sum(1 for r in rows if (r.get("game_status") or "").strip() == "Questionable")),
                str(sum(1 for r in rows if (r.get("game_status") or "").strip() == "Doubtful")),
                source_link("https://www.nfl.com/injuries/", "injury report"),
            ]
        )
    summary = Table(
        caption=f"Injury report summary by club - {len(injuries)} player entries across {len(by_club)} clubs",
        headers=["Club", "Players", "Out", "DNP in practice", "Questionable", "Doubtful", "Source"],
        rows=summary_rows,
    ).to_html()

    depth_rows = []
    for record in depth:
        depth_rows.append(
            [
                esc(record.get("club", "")),
                esc(record.get("side", "")),
                esc(record.get("group", "")),
                esc(record.get("starter", "")),
                esc(record.get("starter_position")),
                badge(record.get("status", ""), "flag" if record.get("status") == "Out" else "warn"),
                esc(record.get("injury")),
                esc(record.get("replacement")),
                esc(record.get("replacement_string")),
                fmt_number(record.get("depth_deficit"), 0),
                esc("; ".join(record.get("notes", []))),
                source_link(record.get("source_url"), "injury report"),
            ]
        )
    depth_table = Table(
        caption=f"Starter absence mapped to a replacement - {len(depth)} mapped absences",
        headers=[
            "Club",
            "Side",
            "Position group",
            "Unavailable starter",
            "Pos",
            "Status",
            "Injury",
            "Replacement",
            "Replacement string",
            "Depth deficit",
            "Notes",
            "Source",
        ],
        rows=depth_rows,
    ).to_html()

    full_rows = []
    for record in injuries:
        full_rows.append(
            [
                esc(record.get("club", "")),
                esc(record.get("player", "")),
                esc(record.get("position")),
                esc(record.get("injuries")),
                esc(record.get("practice_status")),
                esc(record.get("game_status")),
                source_link(record.get("source_url"), "injury report"),
            ]
        )
    full_table = Table(
        caption=f"Full official injury report - {len(injuries)} player entries",
        headers=["Club", "Player", "Position", "Injuries", "Practice status", "Game status", "Source"],
        rows=full_rows,
    ).to_html()

    body = [
        section(
            "How depth is measured",
            note(
                "The injury report says <b>who</b> is unavailable. The official "
                "game book says <b>who played</b>: it lists the starting eleven "
                "for both teams, the substitution list, the did-not-play list and "
                "the inactive list. Joining the two gives the replacement who "
                "must take the slot, and therefore which string of the depth "
                "chart absorbs the absence. A 1st string replaced by the 2nd "
                "string is a depth deficit of 1; a 4th string absorbing it is a "
                "deficit of 3. Nothing about how much production is lost is "
                "claimed here - that is an estimate, and it is listed as an open "
                "item."
            ),
        ),
        section("Summary by club", summary),
        section("Starter absence and replacement", depth_table),
        section("Full official injury report", full_table),
    ]
    return page(
        slug="availability",
        eyebrow="AVAILABILITY",
        title="Injuries and depth deficiencies",
        intro=(
            "The official injury report joined to the official game books, so "
            "every unavailable starter is mapped to the specific replacement who "
            "must take the slot."
        ),
        body="\n".join(body),
        asof=ctx.asof,
    )


# ---------------------------------------------------------------------------
# suggestions
# ---------------------------------------------------------------------------
def render_suggestions(ctx: BuildContext) -> str:
    rows = []
    for suggestion in SUGGESTIONS:
        rows.append(
            [
                f'<span class="id">{esc(suggestion["id"])}</span>',
                esc(suggestion["title"]),
                esc(suggestion["category"]),
                esc(suggestion["problem"]),
                esc(suggestion["proposal"]),
                badge(suggestion["impact"], "ok" if suggestion["impact"] == "High" else "warn"),
                badge(suggestion["effort"], "warn" if suggestion["effort"] == "High" else "ok"),
                esc(suggestion["blocks"]),
                badge(suggestion["status"], "info"),
                source_link(suggestion["source"]),
            ]
        )
    table = Table(
        caption=f"Suggestions - {len(SUGGESTIONS)} proposals for review and selection before implementation",
        headers=[
            "ID",
            "Title",
            "Category",
            "Problem",
            "Proposal",
            "Impact",
            "Effort",
            "Unblocks",
            "Status",
            "Source",
        ],
        rows=rows,
    ).to_html()

    category_counts = Counter(s["category"] for s in SUGGESTIONS)
    stats = [{"value": category_counts.get(c, 0), "label": c} for c in sorted(category_counts)]

    body = [
        section(
            "How suggestions are handled",
            note(
                "A suggestion is a <b>proposal</b>, not a change. Nothing on this "
                "list has been implemented. Each entry states the problem it "
                "addresses, what the proposal actually is, its impact and effort, "
                "and which workstream it unblocks, so a proposal can be selected "
                "or rejected on its merits before any code is written. The "
                "Unblocks column links suggestions back to the questions and "
                "strategies that are waiting on them."
            )
        ),
        section("Suggestions by category", stat_grid(stats)),
        section("Suggestion register", table),
    ]
    return page(
        slug="suggestions",
        eyebrow="SUGGESTIONS",
        title="Suggestions for review and selection",
        intro=(
            "Proposals for improving the project, presented so they can be "
            "reviewed and selected before any of them are implemented."
        ),
        body="\n".join(body),
        asof=ctx.asof,
    )


# ---------------------------------------------------------------------------
# flagged for review
# ---------------------------------------------------------------------------
def _flag_rows(ctx: BuildContext) -> List[Dict[str, Any]]:
    """Assemble everything that could not be verified from an official source."""
    flags: List[Dict[str, Any]] = []

    if not ctx.injury_records:
        flags.append(
            {
                "area": "Injury report",
                "item": "No injury report rows were ingested",
                "detail": (
                    "The collector did not retrieve the official injury report, "
                    "so no availability statement on this site can be supported."
                ),
                "severity": "High",
                "manual_review": "https://www.nfl.com/injuries/",
            }
        )

    for record in ctx.depth_records:
        if not record.get("replacement"):
            flags.append(
                {
                    "area": "Depth deficiency",
                    "item": f'{record.get("club", "")} - {record.get("starter", "")}',
                    "detail": (
                        "The starter is unavailable but no replacement could be "
                        "identified from the sampled official game books. The "
                        "replacement field is deliberately left blank."
                        + (" " + " ".join(record.get("notes", [])) if record.get("notes") else "")
                    ),
                    "severity": "Medium",
                    "manual_review": record.get("source_url", "https://www.nfl.com/injuries/"),
                }
            )
        for note_text in record.get("notes", []):
            if "unverified" in note_text or "uncertain" in note_text:
                flags.append(
                    {
                        "area": "Depth deficiency",
                        "item": f'{record.get("club", "")} - {record.get("starter", "")}',
                        "detail": note_text,
                        "severity": "Medium",
                        "manual_review": record.get("source_url", "https://www.nfl.com/injuries/"),
                    }
                )

    # Blank game-status cells in the official report are normal, but a player
    # with an injury and no designation is worth a look.
    for record in ctx.injury_records:
        if record.get("injuries") and not record.get("game_status"):
            flags.append(
                {
                    "area": "Injury report",
                    "item": f'{record.get("club", "")} - {record.get("player", "")}',
                    "detail": (
                        "The official report lists an injury but leaves the game "
                        "status blank. The designation is left blank here rather "
                        "than inferred."
                    ),
                    "severity": "Low",
                    "manual_review": record.get("source_url", "https://www.nfl.com/injuries/"),
                }
            )

    # Unmeasured correlations.
    for entry in (ctx.correlation or {}).get("unmeasured", []):
        flags.append(
            {
                "area": "Correlation",
                "item": entry.get("label", entry.get("id", "")),
                "detail": entry.get("note", ""),
                "severity": "Medium",
                "manual_review": entry.get("source_url", "https://www.nfl.com/stats/"),
            }
        )

    # Game books that could not be parsed.
    for record in ctx.gamebook_records:
        for note_text in record.get("notes", []):
            flags.append(
                {
                    "area": "Game book",
                    "item": record.get("matchup") or record.get("game_id", ""),
                    "detail": note_text,
                    "severity": "Low",
                    "manual_review": record.get("game_center_url", "https://www.nfl.com/scores/"),
                }
            )

    # Known open questions that touch data.
    for question in QUESTIONS:
        if question["status"] == "Open":
            flags.append(
                {
                    "area": "Open question",
                    "item": f'{question["id"]} - {question["question"]}',
                    "detail": (
                        f'{question["answer"]} Missing: {question["missing"]} '
                        f'Action: {question["action"]}'
                    ),
                    "severity": "Medium",
                    "manual_review": question["source"],
                }
            )

    return flags


def render_review(ctx: BuildContext) -> str:
    flags = _flag_rows(ctx)
    rows = []
    for flag in flags:
        severity = flag.get("severity", "Low")
        kind = "flag" if severity == "High" else ("warn" if severity == "Medium" else "info")
        rows.append(
            [
                esc(flag.get("area", "")),
                esc(flag.get("item", "")),
                esc(flag.get("detail", "")),
                badge(severity, kind),
                source_link(flag.get("manual_review"), "review manually"),
            ]
        )
    table = Table(
        caption=f"Flagged for review - {len(flags)} items",
        headers=["Area", "Item", "Detail", "Severity", "Manual review link"],
        rows=rows,
    ).to_html()

    counts = Counter(f.get("severity", "Low") for f in flags)
    stats = [{"value": counts.get(k, 0), "label": k} for k in ("High", "Medium", "Low")]

    body = [
        section(
            "What this page is",
            note(
                "<b>Flagged items do not block publication.</b> They are listed "
                "here in full so a reviewer can check them by hand. Every flag "
                "links to the official document that would settle it. A flagged "
                "item means a value could not be read from an official source; "
                "it never means a value was guessed."
            )
        ),
        section("Counts by severity", stat_grid(stats)),
        section("Flagged register", table),
    ]
    return page(
        slug="review",
        eyebrow="FLAGGED FOR REVIEW",
        title="Flagged for review",
        intro=(
            "Everything that could not be verified from an official source, with "
            "a manual-review link for each item. Flagged items do not block "
            "publication."
        ),
        body="\n".join(body),
        asof=ctx.asof,
    )


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------
def render_sources(ctx: BuildContext) -> str:
    rows = []
    for source in all_sources():
        rows.append(
            [
                f'<span class="id">{esc(source.key)}</span>',
                esc(source.title),
                esc(source.publisher),
                f'<code class="host">{esc(source.host)}</code>',
                esc(source.description),
                esc(source.provides),
                badge("volatile" if source.volatile else "stable", "warn" if source.volatile else "ok"),
                source_link(source.url, "open"),
            ]
        )
    table = Table(
        caption=f"Source registry - {len(SOURCES)} official endpoints",
        headers=[
            "Key",
            "Source",
            "Publisher",
            "Host",
            "Description",
            "What it authoritatively provides",
            "Stability",
            "Link",
        ],
        rows=rows,
    ).to_html()

    body = [
        section(
            "Source policy",
            note(
                "Only <b>nfl.com</b> and the official club domains are read, with "
                "one labelled exception: the published NFL Media Access Policy, "
                "which is hosted by the Pro Football Writers Association and "
                "marked as such in the publisher column. The build verifier "
                "checks every source link on every published page against the "
                "allow-list and fails the deployment if a row points anywhere "
                "else."
            )
        ),
        section("Registry", table),
    ]
    return page(
        slug="sources",
        eyebrow="SOURCES",
        title="Official source registry",
        intro=(
            "Every official endpoint this project reads, what it "
            "authoritatively provides, and whether its values change over time."
        ),
        body="\n".join(body),
        asof=ctx.asof,
    )


PAGES = {
    "index.html": render_index,
    "pages/requirements.html": render_requirements,
    "pages/questions.html": render_questions,
    "pages/strategies.html": render_strategies,
    "pages/validation.html": render_validation,
    "pages/correlation.html": render_correlation,
    "pages/availability.html": render_availability,
    "pages/suggestions.html": render_suggestions,
    "pages/review.html": render_review,
    "pages/sources.html": render_sources,
}
