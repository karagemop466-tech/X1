# Suggestions register (T7)

A dedicated section for suggestions so they can be reviewed and the best path chosen **before**
any change is implemented. Each suggestion carries: problem, proposal, effort, expected benefit,
dependencies, and a decision field the owner fills in.

Workflow: `proposed` → `under review` (owner) → `approved` / `rejected` / `deferred` → `implemented`.
Nothing is implemented while `proposed` unless it is pure documentation of verified facts.

| ID | Date | Suggestion | Problem it solves | Effort | Expected benefit | Dependencies | Decision |
|---|---|---|---|---|---|---|---|
| SG-01 | 2026-11-14 | Weekly automated refresh: scheduled job (Actions cron) re-fetches official pages + nflverse and regenerates CSVs/site | Data goes stale every week (this snapshot is W10) | M | Site always current; no manual input | Q1 pipeline decision; sandbox network limits | **proposed** |
| SG-02 | 2026-11-14 | Model v2: add QB-starter adjustment (from verified qb_map) + recency weighting | v1 has no edge; QB-blindness is the biggest visible gap (LAC@BAL, SEA@LV) | M | First credible positive-ROI candidate for S4/S5 | none — data already in-repo | **proposed (top pick)** |
| SG-03 | 2026-11-14 | Collect all 32 official club depth charts once, then weekly diffs | Enables true 2nd/3rd-string deficiency scoring (owner requirement) | M–L | Unlocks S1/S2 strategies and the deficiency metric | Q3 | **proposed** |
| SG-04 | 2026-11-14 | Historical injury-report archive (NFL.com weekly reports 2019–2026) joined to results | Quantify injury/deficiency signal instead of asserting it | M | Evidence-based S2 gate; validates or kills the thesis | network access / licensing | **proposed** |
| SG-05 | 2026-11-14 | Timestamped odds store (`data/odds/`) for CLV scoring | CLV is the most luck-resistant signal; needs bet-time + close-time lines | M | Reward integrity; gates measurable | Q6 provider decision | **proposed** |
| SG-06 | 2026-11-14 | Bet policy defaults: max 3-leg parlays; no cross-sport; same-game legs must declare φ; props combos capped at 3 | Correlation risk control | S | Prevents tail-risk blowups | owner approval | **proposed** |
| SG-07 | 2026-11-14 | Bankroll defaults: 1 unit = 1% of bankroll; max 5 units/day; stop-loss 15 units/month | Luck-proof risk posture | S | Survival until edges are proven | owner approval | **proposed** |
| SG-08 | 2026-11-14 | Per-team dashboard pages (records, injury load flags, ratings, upcoming line) | Faster decision-making per game | M | One-stop team view | site build already generates from CSVs | **proposed** |
| SG-09 | 2026-11-14 | Publish model versions: every fit change bumps `model_config.json` version and re-runs full backtest | Prevent silent methodology drift | S | Auditability; gates compare like-for-like | none | **proposed** |
| SG-10 | 2026-11-14 | Add a "verification changelog" page listing every data correction with before/after + source | Trust and reviewability | S | Owner can audit corrections | none | **proposed** |
| SG-11 | 2026-11-14 | Weekly "line vs market" review post: where X1 and market disagree ≥ 3 pts, with injury context | Turns model output into reviewable analysis | S | Ongoing edge research log | none | **proposed** |
| SG-12 | 2026-11-14 | Link COORDINATION.md status into the site (task board snapshot) | Visibility of parallel-session progress | S | Owner sees pipeline state | integration session policy | **proposed** |

## How to decide

1. Start with SG-02 (model v2) — biggest expected benefit, zero external dependencies.
2. Then SG-03 + SG-04 together — they unlock the owner's injury/depth requirement end-to-end.
3. SG-05 + SG-06 + SG-07 form the "live wagering integrity" bundle — decide as a set.
4. SG-01/SG-08/SG-09/SG-10/SG-11/SG-12 are operational polish; batch-approve when convenient.

Owner: mark decisions by editing the Decision column (or adding a note in the repo); the site's
Suggestions page mirrors this table verbatim with sources.
