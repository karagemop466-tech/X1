"""Strategy catalogue, validation gates and the leaderboard competition.

The design goal is *selective skill*: a strategy only earns a reward if it
demonstrably beats the null hypothesis out of sample, survives a multiple-testing
correction, and does not depend on a small number of lucky outcomes.

Contents
--------
``ValidationGate``
    A pre-registered pass/fail criterion. Gates are declared *before* a
    strategy is evaluated so the bar cannot move after the fact.
``Strategy``
    A candidate strategy: what it claims, what data it needs, which gates
    apply, and what its current evaluation state is.
``Leaderboard``
    The competition: scoring, tie-breaking, eligibility (only gate-passing
    strategies can be ranked) and reward tiers.

Nothing in this module reports a performance number unless one was actually
computed from data. Strategies that have not been evaluated are ``unevaluated``
and score nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# validation gates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationGate:
    """A pre-registered criterion a strategy must clear to be ranked."""

    id: str
    name: str
    description: str
    #: ``statistical`` | ``sample`` | ``calibration`` | ``risk`` | ``robustness`` | ``conduct``
    category: str
    #: Human-readable threshold, e.g. ``"p < 0.05"``.
    threshold: str
    #: Why the gate exists - what failure mode it is designed to catch.
    rationale: str
    #: If the gate cannot currently be evaluated, say why.
    blocking_dependency: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "threshold": self.threshold,
            "rationale": self.rationale,
            "blocking_dependency": self.blocking_dependency,
        }


GATES: List[ValidationGate] = [
    ValidationGate(
        id="G1",
        name="Minimum sample size",
        description=(
            "The strategy must be evaluated on a pre-declared minimum number of "
            "independent betting decisions."
        ),
        category="sample",
        threshold="n >= 300 settled decisions",
        rationale=(
            "Below roughly 300 decisions a strategy cannot be distinguished from "
            "noise at conventional confidence levels, regardless of the headline "
            "return."
        ),
    ),
    ValidationGate(
        id="G2",
        name="Out-of-sample evaluation only",
        description=(
            "All reported performance must come from data that was not used to "
            "select, tune or modify the strategy."
        ),
        category="statistical",
        threshold="100% of reported results from a held-out period",
        rationale=(
            "In-sample results measure how well a strategy fitted its own history, "
            "which is the definition of overfitting."
        ),
    ),
    ValidationGate(
        id="G3",
        name="Multiple-testing correction",
        description=(
            "When many strategies are tested, the family-wise error rate must be "
            "controlled across the whole family, not per strategy."
        ),
        category="statistical",
        threshold="White's Reality Check or Benjamini-Hochberg FDR <= 0.05",
        rationale=(
            "Testing dozens of strategies and reporting the winners guarantees an "
            "apparent edge even when none exists."
        ),
    ),
    ValidationGate(
        id="G4",
        name="Probability calibration",
        description=(
            "Stated probabilities must match observed frequencies, not merely be "
            "directionally correct."
        ),
        category="calibration",
        threshold="Brier score beats the base-rate model; calibration slope 0.9-1.1",
        rationale=(
            "A strategy that is well ranked but badly calibrated will still lose "
            "money at real prices."
        ),
    ),
    ValidationGate(
        id="G5",
        name="Closing-line value",
        description=(
            "The strategy must beat the closing line, not merely beat the opening "
            "line or its own average price."
        ),
        category="statistical",
        threshold="Positive CLV over a rolling 100-decision window",
        rationale=(
            "Beating a stale price is an execution artefact. Beating the closing "
            "price is evidence of information the market does not have."
        ),
    ),
    ValidationGate(
        id="G6",
        name="Bankroll and drawdown limits",
        description=(
            "The strategy must survive a defined adverse path without breaching "
            "the bankroll floor."
        ),
        category="risk",
        threshold="Maximum drawdown <= 20%; no single decision risks > 2% of bankroll",
        rationale=(
            "A positive-expectation strategy with an unacceptable drawdown "
            "profile will not be followed, and therefore will not compound."
        ),
    ),
    ValidationGate(
        id="G7",
        name="Correlation cap on combined legs",
        description=(
            "Multi-leg structures must measure the dependence between legs and "
            "price them jointly."
        ),
        category="risk",
        threshold="No two legs with |rho| >= 0.35 without a joint model",
        rationale=(
            "Treating correlated legs as independent is the most common way a "
            "parlay engine silently loses money."
        ),
    ),
    ValidationGate(
        id="G8",
        name="Stability across sub-periods",
        description=(
            "The edge must not depend on one season, one opponent class or one "
            "market regime."
        ),
        category="robustness",
        threshold="Positive in at least 3 of 4 rolling sub-periods",
        rationale=(
            "A single good regime is usually a coincidence, a rule change, or a "
            "market inefficiency that has already been arbitraged away."
        ),
    ),
    ValidationGate(
        id="G9",
        name="No lookahead or leakage",
        description=(
            "Every input used to make a decision must have been publicly "
            "available at decision time."
        ),
        category="conduct",
        threshold="Timestamp audit passes on 100% of decisions",
        rationale=(
            "The single largest source of fake backtest performance is using "
            "information that was not knowable when the bet was placed."
        ),
        blocking_dependency=(
            "Requires a timestamped decision log with input as-of timestamps."
        ),
    ),
    ValidationGate(
        id="G10",
        name="Reproducible provenance",
        description=(
            "Every published result must be regenerable from a pinned data "
            "snapshot and a versioned code revision."
        ),
        category="conduct",
        threshold="Run manifest published with each evaluation",
        rationale=(
            "An unreproducible result cannot be reviewed, and an unreviewable "
            "result cannot be trusted."
        ),
    ),
]


def gates_by_id() -> Dict[str, ValidationGate]:
    return {gate.id: gate for gate in GATES}


# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------


@dataclass
class Strategy:
    """A candidate strategy in the competition."""

    id: str
    name: str
    family: str  # "single" | "parlay" | "prop_combo"
    thesis: str
    mechanism: str
    required_inputs: List[str]
    required_gate_ids: List[str]
    #: What the strategy must beat to be useful.
    benchmark: str
    #: Where the strategy's edge is expected to come from.
    edge_source: str
    #: The known failure mode.
    failure_mode: str
    #: Why this is expected to be skill rather than luck.
    skill_argument: str
    #: Current state: unevaluated | in_validation | validated | rejected
    status: str = "unevaluated"
    evaluation: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "family": self.family,
            "thesis": self.thesis,
            "mechanism": self.mechanism,
            "required_inputs": self.required_inputs,
            "required_gate_ids": self.required_gate_ids,
            "benchmark": self.benchmark,
            "edge_source": self.edge_source,
            "failure_mode": self.failure_mode,
            "skill_argument": self.skill_argument,
            "status": self.status,
            "evaluation": self.evaluation,
            "notes": self.notes,
        }


STRATEGIES: List[Strategy] = [
    Strategy(
        id="S1",
        name="Availability-adjusted team strength",
        family="single",
        thesis=(
            "A team's true strength changes when starters are unavailable, and "
            "the market prices the injury report with a lag and an error term."
        ),
        mechanism=(
            "Adjust an Elo-style team rating by the expected on-field value of "
            "each unavailable starter, using the replacement's measured "
            "contribution from official game books. Then compare the adjusted "
            "projected margin to the offered spread."
        ),
        required_inputs=[
            "Official weekly injury report (practice + game status)",
            "Official game book lineups and box scores",
            "Team points for/against history",
            "Timestamped market prices",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G8", "G9", "G10"],
        benchmark="Closing spread",
        edge_source=(
            "The public injury report is published before the market fully "
            "prices it, and depth quality is not observable in the headline "
            "designation."
        ),
        failure_mode=(
            "Injuries are already priced in by the time the line moves; the "
            "adjustment adds noise without signal."
        ),
        skill_argument=(
            "The signal is a documented, timestamped public input combined with "
            "an independently measured replacement value, evaluated out of sample."
        ),
    ),
    Strategy(
        id="S2",
        name="Replacement-tier mismatch",
        family="single",
        thesis=(
            "The market treats 'starter out' and '3rd string replaces starter' as "
            "equivalent, but the expected production gap differs by an order of "
            "magnitude."
        ),
        mechanism=(
            "Quantify, from official game books, how a position group's output "
            "changes when the depth index of the replacement increases. Combine "
            "that measured gap with the specific injury designations for the "
            "week and test whether the market's spread adjustment matches."
        ),
        required_inputs=[
            "Official injury report",
            "Official game book lineups and box scores",
            "Timestamped market prices",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G8", "G9", "G10"],
        benchmark="Closing spread",
        edge_source=(
            "Designation tells you who is out; the depth chart tells you how "
            "much production is actually lost."
        ),
        failure_mode=(
            "Replacement effects are position- and scheme-specific, and a "
            "league-wide average may be too blunt."
        ),
        skill_argument=(
            "Uses only league-published inputs and a measured, not assumed, "
            "replacement effect."
        ),
    ),
    Strategy(
        id="S3",
        name="Situational weather and surface total",
        family="single",
        thesis=(
            "Game-day weather and stadium surface measurably affect scoring, and "
            "the adjustment is not fully reflected in the total."
        ),
        mechanism=(
            "Use the official game book's weather block (temperature, humidity, "
            "wind, wind chill, roof status, surface) as features in a points-"
            "distribution model, then compare the model total to the market total."
        ),
        required_inputs=[
            "Official game book weather records",
            "Official game book box scores",
            "Venue records",
            "Timestamped market prices",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G8", "G9", "G10"],
        benchmark="Closing total",
        edge_source=(
            "Forecasts available before the game carry more information than "
            "the conditions recorded at kickoff."
        ),
        failure_mode=(
            "Weather explains little of the total relative to team strength, so "
            "the edge may be too small to cover the vig."
        ),
        skill_argument=(
            "A measurable physical input with a documented directional effect, "
            "tested against a naive baseline."
        ),
    ),
    Strategy(
        id="S4",
        name="Officiating crew profile",
        family="single",
        thesis=(
            "Referee crews differ measurably in penalty rate and scoring "
            "composition, and the market does not price the crew."
        ),
        mechanism=(
            "Build a per-crew profile of penalty counts and scoring composition "
            "from official game books (each book lists all seven officials and "
            "the full penalty log), then model the total and the margin against "
            "crew identity."
        ),
        required_inputs=[
            "Official game book officials and penalty logs",
            "Official game book box scores",
            "Timestamped market prices",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G8", "G9", "G10"],
        benchmark="Closing total and spread",
        edge_source=(
            "Crew assignment is published in advance and is public information "
            "that most price makers do not model."
        ),
        failure_mode=(
            "Crew sample sizes are small and personnel change, so the profile "
            "may not persist across seasons."
        ),
        skill_argument=(
            "Fully deterministic public input with a measurable outcome "
            "relationship and a natural out-of-sample split."
        ),
    ),
    Strategy(
        id="S5",
        name="Offensive line continuity",
        family="single",
        thesis=(
            "Loss of a starting offensive lineman has a different effect than "
            "loss of a skill position, and the distinction is measurable."
        ),
        mechanism=(
            "Use the official game book to measure rushing and passing "
            "performance by offensive line configuration, then flag games where "
            "multiple starting linemen are unavailable."
        ),
        required_inputs=[
            "Official injury report",
            "Official game book lineups",
            "Official game book box scores",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G8", "G9", "G10"],
        benchmark="Closing total",
        edge_source=(
            "Multi-lineman absences are rare and are not decomposed in the "
            "market's injury adjustment."
        ),
        failure_mode=(
            "Low frequency of multi-lineman absences makes the sample thin."
        ),
        skill_argument=(
            "Derived from official lineup data with a clear causal mechanism."
        ),
    ),
    Strategy(
        id="P1",
        name="Same-game parlay with measured dependence",
        family="parlay",
        thesis=(
            "A same-game parlay priced as independent legs systematically "
            "mis-prices either direction, depending on the true correlation."
        ),
        mechanism=(
            "Estimate the correlation between the candidate legs from official "
            "game-level data, price the combination with a bivariate model, and "
            "only take it when the joint probability exceeds the offered price "
            "by more than the modelled error."
        ),
        required_inputs=[
            "Official game book box scores",
            "Official injury report",
            "Timestamped market prices for each leg",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"],
        benchmark="Offered parlay price",
        edge_source=(
            "Bookmakers price parlay legs with a vig stack; an explicitly "
            "correlated model can find legs where the joint price is too low."
        ),
        failure_mode=(
            "The correlation may be unstable across seasons, and joint pricing "
            "errors can exceed the mis-pricing being exploited."
        ),
        skill_argument=(
            "Dependence is measured rather than assumed, and the strategy "
            "declines to trade when it cannot be measured."
        ),
    ),
    Strategy(
        id="P2",
        name="Correlation-screened cross-game parlay",
        family="parlay",
        thesis=(
            "Most cross-game parlay legs are near-independent; the rare "
            "positively correlated pair is mis-priced by a product assumption."
        ),
        mechanism=(
            "Screen candidate legs by measured residual correlation (for example "
            "two teams in the same division, or two quarterbacks in the same "
            "game), and reject any pair whose correlation is high enough that "
            "the product assumption fails."
        ),
        required_inputs=[
            "Official game book box scores",
            "Timestamped market prices",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"],
        benchmark="Offered parlay price",
        edge_source=(
            "Explicit screening removes legs whose independence assumption "
            "fails, which is where naive parlay stacking loses money."
        ),
        failure_mode=(
            "The residual edge after paying the vig stack may be smaller than "
            "the modelling error."
        ),
        skill_argument=(
            "The strategy earns reward for declining to bet, which only pays if "
            "the dependence model is correct."
        ),
    ),
    Strategy(
        id="P3",
        name="Game-script conditional leg",
        family="parlay",
        thesis=(
            "Second-half legs conditioned on the first half have different value "
            "than static first-half props."
        ),
        mechanism=(
            "Condition the second-half model on the observed first-half score "
            "margin, which is known before the second-half prop resolves."
        ),
        required_inputs=[
            "Official game book play-by-play",
            "Official game book box scores",
            "Timestamped market prices",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"],
        benchmark="Offered first-half and second-half prices",
        edge_source=(
            "Game script is observable in real time and changes the second-half "
            "distribution materially."
        ),
        failure_mode=(
            "Live execution introduces latency and price staleness that may "
            "exceed the modelled edge."
        ),
        skill_argument=(
            "Conditional probability is a direct consequence of the model, "
            "auditable against the play-by-play."
        ),
    ),
    Strategy(
        id="C1",
        name="Player-prop pair within one game",
        family="prop_combo",
        thesis=(
            "A quarterback's volume and a receiver's volume are correlated "
            "within a game, so pricing them as independent mis-states both the "
            "probability and the price."
        ),
        mechanism=(
            "Use official game book box scores to measure the within-game "
            "correlation between a passer and his primary target, then model the "
            "combination jointly."
        ),
        required_inputs=[
            "Official game book box scores",
            "Official injury report for availability",
            "Timestamped market prices",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"],
        benchmark="Offered SGP price",
        edge_source=(
            "Same-game player props are priced with an independence assumption "
            "that is visibly wrong when the passer is favoured to throw more."
        ),
        failure_mode=(
            "Correlation depends on script and is unstable for individual "
            "player pairs."
        ),
        skill_argument=(
            "Depends on a measurable within-game relationship and refuses to "
            "price pairs whose correlation is not established."
        ),
    ),
    Strategy(
        id="C2",
        name="Team-total component pair",
        family="prop_combo",
        thesis=(
            "Rush and pass components of a team total are negatively correlated, "
            "so a two-leg over/under pair is mis-priced relative to the sum."
        ),
        mechanism=(
            "Model the joint distribution of a team's rushing and passing "
            "production from official box scores and price the pair jointly."
        ),
        required_inputs=[
            "Official game book box scores",
            "Timestamped market prices",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"],
        benchmark="Offered team-total and component prices",
        edge_source=(
            "The two components are mechanically substitutable, which creates a "
            "structural negative correlation the market treats as independent."
        ),
        failure_mode=(
            "The joint distribution is heavy tailed and the tail behaviour is "
            "where the pricing error usually lives."
        ),
        skill_argument=(
            "Uses a structural dependence that can be verified directly from "
            "official box scores."
        ),
    ),
    Strategy(
        id="C3",
        name="Availability-adjusted prop combination",
        family="prop_combo",
        thesis=(
            "A back-up's prop price does not fall by the same amount as the "
            "starter's prop price rises."
        ),
        mechanism=(
            "From official game books, measure the historical production of a "
            "replacement at each position group and re-price the prop "
            "combination."
        ),
        required_inputs=[
            "Official injury report",
            "Official game book box scores",
            "Timestamped market prices",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"],
        benchmark="Offered prop prices",
        edge_source=(
            "Prop markets react to the designation but not to the measured "
            "replacement output."
        ),
        failure_mode=(
            "Prop prices move fast; the window between the report and the price "
            "may be short."
        ),
        skill_argument=(
            "Ties the prop price to the same official depth measurement used in "
            "the single-bet strategies."
        ),
    ),
    Strategy(
        id="C4",
        name="Scoring-prop and team-total pair",
        family="prop_combo",
        thesis=(
            "A scoring prop and the team total carry different information, and "
            "their joint distribution is not the product of their marginals."
        ),
        mechanism=(
            "Model scoring-prop probability conditional on projected team "
            "scoring distribution from official box scores."
        ),
        required_inputs=[
            "Official game book box scores",
            "Timestamped market prices",
        ],
        required_gate_ids=["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"],
        benchmark="Offered SGP price",
        edge_source=(
            "Bookmaker SGP pricing uses a marginals-only model, which is "
            "structurally mis-specified for scoring props."
        ),
        failure_mode=(
            "Scoring props have heavy right tails and thin samples for rare "
            "outcomes."
        ),
        skill_argument=(
            "The dependence is structural and can be verified from official "
            "scoring records."
        ),
    ),
]


def strategies_by_id() -> Dict[str, Strategy]:
    return {strategy.id: strategy for strategy in STRATEGIES}


# ---------------------------------------------------------------------------
# leaderboard
# ---------------------------------------------------------------------------
@dataclass
class RewardTier:
    """A reward band in the competition."""

    name: str
    min_rank: int
    max_rank: Optional[int]
    reward: str
    criteria: str


REWARD_TIERS: List[RewardTier] = [
    RewardTier(
        name="Proving ground",
        min_rank=1,
        max_rank=3,
        reward="50% of the monthly research budget",
        criteria=(
            "Cleared every applicable gate, positive out-of-sample return, and "
            "positive closing-line value over the full evaluation window."
        ),
    ),
    RewardTier(
        name="Validated",
        min_rank=4,
        max_rank=10,
        reward="25% of the monthly research budget",
        criteria=(
            "Cleared every applicable gate with a return that is not "
            "significantly different from zero."
        ),
    ),
    RewardTier(
        name="Provisional",
        min_rank=11,
        max_rank=25,
        reward="10% of the monthly research budget",
        criteria=(
            "Cleared the statistical gates and sample-size gate but failed "
            "robustness or risk gates."
        ),
    ),
    RewardTier(
        name="Not ranked",
        min_rank=26,
        max_rank=None,
        reward="Not eligible",
        criteria=(
            "Failed any blocking gate, or has not been evaluated out of sample."
        ),
    ),
]


@dataclass
class LeaderboardRow:
    """One row of the strategy leaderboard."""

    strategy_id: str
    strategy_name: str
    family: str
    rank: Optional[int]
    score: Optional[float]
    gates_passed: int
    gates_total: int
    tier: str
    reward: str
    status: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "family": self.family,
            "rank": self.rank,
            "score": self.score,
            "gates_passed": self.gates_passed,
            "gates_total": self.gates_total,
            "tier": self.tier,
            "reward": self.reward,
            "status": self.status,
            "note": self.note,
        }


def build_leaderboard(
    evaluations: Dict[str, Dict[str, Any]],
    *,
    min_gates_passed: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Rank strategies that have cleared their gates.

    ``evaluations`` maps strategy id to an evaluation record containing at
    minimum ``gates_passed`` (list of gate ids) and ``score``. Strategies
    without an evaluation are listed as unevaluated and are never ranked.
    """
    rows: List[LeaderboardRow] = []
    ranked: List[Tuple[float, Strategy, Dict[str, Any]]] = []

    for strategy in STRATEGIES:
        evaluation = evaluations.get(strategy.id)
        if not evaluation:
            rows.append(
                LeaderboardRow(
                    strategy_id=strategy.id,
                    strategy_name=strategy.name,
                    family=strategy.family,
                    rank=None,
                    score=None,
                    gates_passed=0,
                    gates_total=len(strategy.required_gate_ids),
                    tier="Not ranked",
                    reward="Not eligible",
                    status="unevaluated",
                    note=(
                        "No out-of-sample evaluation has been run. A strategy "
                        "cannot be ranked on an untested hypothesis."
                    ),
                )
            )
            continue

        passed = list(evaluation.get("gates_passed", []))
        total = len(strategy.required_gate_ids)
        score = evaluation.get("score")
        eligible = len(passed) >= total
        if min_gates_passed is not None:
            eligible = eligible and len(passed) >= min_gates_passed
        if eligible and score is not None:
            ranked.append((float(score), strategy, evaluation))
        else:
            rows.append(
                LeaderboardRow(
                    strategy_id=strategy.id,
                    strategy_name=strategy.name,
                    family=strategy.family,
                    rank=None,
                    score=score,
                    gates_passed=len(passed),
                    gates_total=total,
                    tier="Not ranked",
                    reward="Not eligible",
                    status="not_ranked",
                    note=(
                        f"Cleared {len(passed)} of {total} required gates."
                    ),
                )
            )

    ranked.sort(key=lambda item: (-item[0], item[1].id))
    for index, (score, strategy, evaluation) in enumerate(ranked, start=1):
        tier = _tier_for(index)
        rows.append(
            LeaderboardRow(
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                family=strategy.family,
                rank=index,
                score=score,
                gates_passed=len(evaluation.get("gates_passed", [])),
                gates_total=len(strategy.required_gate_ids),
                tier=tier.name,
                reward=tier.reward,
                status="ranked",
                note=evaluation.get("note", ""),
            )
        )

    rows.sort(key=lambda r: (r.rank is None, r.rank or 0, r.strategy_id))
    return [row.to_dict() for row in rows]


def _tier_for(rank: int) -> RewardTier:
    for tier in REWARD_TIERS:
        if tier.max_rank is None or rank <= tier.max_rank:
            return tier
    return REWARD_TIERS[-1]
