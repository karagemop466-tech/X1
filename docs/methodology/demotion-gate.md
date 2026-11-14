# Demotion gate — live back to paper

Session `arena/907c5baf-x1` · task N4 · 2026-11-14 · pre-registered policy

**Definition.** A live strategy is automatically returned to paper the moment any
trigger below fires. The full rule set, machine-readable, is
[`data/demotion_gate.json`](../../data/demotion_gate.json); it is rendered on the
Validation gates page (`app/validation.html`).

| ID | Trigger | Rule | Threshold status |
|---|---|---|---|
| G-D1.T1 | Two failed windows | two consecutive weekly review windows failing any gate passed at promotion | rule already published (EXECUTIVE-SUMMARY, validation-gates) |
| G-D1.T2 | Negative-edge evidence | rolling 50 live bets, flat-stake ROI < 0 with one-sided 90% bootstrap upper bound < 0 | **proposed default** (Q-26) |
| G-D1.T3 | CLV decay | last 50 priced bets, mean CLV < 0, one-sided p < 0.10 | **proposed default** (Q-26); needs price-store close captures (Q-31) |
| G-D1.T4 | Drawdown | peak-to-trough ≥ 25% of the strategy's allocation (unit = 1%) | **proposed default** (Q-26) |
| G-D1.T5 | Data-integrity breach | one proven wrong/contradicted input (a G1 failure found post-hoc) | rule; zero tolerance |

**Design intent.** The gate reads **signal metrics only** — flat-stake ROI, CLV, gate
failures. Staking is deliberately absent from the trigger logic, so a lucky staking run
can neither trigger nor prevent a demotion (consistent with the signal/staking split in
[`data/leaderboard_split.json`](../../data/leaderboard_split.json)). Demoting on a bare
losing streak would punish luck; requiring a confidence bound, CLV decay, or a breach
keeps the gate skill-based.

**Procedure on trigger.** No new live stakes; open positions settle normally from the
verified results feed; the strategy returns to the paper pool with its full history; the
leaderboard records the trigger id, window and date — entries are never deleted.

**Re-promotion.** A fresh pre-registered window (gate G2), no reuse of the old sample,
all eight promotion gates re-passed, and owner ratification (Q-25).

**Status.** T1 and T5 are boolean rules and need no thresholds. The numeric thresholds in
T2–T4 are **proposed defaults**: they are policy choices (not data values), labelled as
such everywhere they appear, and listed for ratification at decision **Q-26** on the
decision register.
