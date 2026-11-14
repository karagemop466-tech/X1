# Demotion gate — how a live strategy is sent back to paper

**Register:** `data/gates.json` → gate **G8** · **Status:** defined, thresholds proposed,
awaiting owner ratification (question **Q-21**) · **Proposed by:** session
`arena-600e6009-x1`, round 3.

Every other gate decides whether a strategy may *enter* the leaderboard. G8 is the only gate
that decides when a strategy must **leave**. It exists because the leaderboard's whole premise
is that only selectively skilled strategies get rewarded — and a strategy can be selectively
skilled once and not later. Without an exit rule, a past result keeps earning on reputation.

---

## Why an exit rule has to be pre-registered

A demotion rule written *after* a strategy has gone live is not a rule, it is a negotiation.
The thresholds below are therefore proposed in full, in public, before any strategy is live.
They may be edited now, while nothing depends on them; after ratification they may only be
changed with the change recorded and dated, never applied backwards to rescue a position.

## The triggers (any one, evaluated on every scheduled gate re-run)

| # | Trigger | Rationale |
|---|---|---|
| 1 | Rolling **z < 1.0** over the most recent 100 graded bets | The signal has stopped being distinguishable from a coin flip on recent form. |
| 2 | **Two consecutive** scheduled gate re-runs fail any blocking gate G0–G7 | The strategy no longer clears the bar it cleared to get in. |
| 3 | **Median max drawdown > 25%** of bankroll while live (G5 breach in production) | Risk control that exists only in backtest is not risk control. |
| 4 | **Mean CLV ≤ 0** over a 50-bet window | If our price is systematically worse than the closing number, we are the noise. |

Rolling windows (100 bets / 50 bets) are deliberate: they make the gate respond to *current*
skill rather than to the lifetime average that got the strategy promoted, while still being
wide enough that a single bad weekend cannot trigger a demotion on its own.

## The action

On any trigger:

1. The strategy's status flips **live → paper** immediately.
2. Staking stops — no further exposure while it is under review.
3. The demotion is published on the leaderboard and the flagged page with the trigger that
   fired, the window, and the numbers at demotion time.
4. Re-entry requires a **fresh registered window** that passes G0–G7 again. The old sample
   does not count toward the new window. A strategy may cycle live → paper more than once;
   each cycle is recorded.

## What the gate does *not* do

- It does not touch the signal columns. Demotion is a **status** change; the measured signal
  history stays published, because a demoted strategy's record is evidence about the gate as
  much as about the strategy.
- It does not react to ROI alone. ROI is signal × staking × price; a staking pattern can move
  ROI without the signal changing, which is exactly why the leaderboard ranks on the signal
  group only. Trigger 4 (CLV) and triggers 1–2 (signal z, gate re-run) are the signal-side
  checks; trigger 3 (drawdown) is the risk-side check.
- It does not fire today. No strategy is live, and the thresholds above are proposals until
  Q-21 is answered. The gate is installed so that promotion has a defined exit before it has
  a defined entry.

## Where it is enforced

| Artefact | Role |
|---|---|
| `data/gates.json` → G8 | The register entry: triggers, action, cadence, ratification status |
| `app/validation.html` | Published gate card (root register G8, labelled separately from the research-lab numbering) |
| `app/leaderboard.html` | Signal/staking split the gate protects; demotions appear here |
| `tools/build_round3.py` | Asserts no staking value can enter the signal ranking |
| Question **Q-21** | Owner ratification of the four thresholds |

## Relationship to the other registers

Three gate registers live in this repository and they are numbered independently:

- **`data/gates.json` (root)** — G0–G8, the owner's register; G8 is this demotion gate.
- **Research-lab gates** (G1–G8 in the methodology note `validation-gates.md`) — pre-registered
  entry conditions for scoring: sample, leakage, significance, economics, baselines, luck
  robustness, parameter stability, non-redundancy.
- **Pipeline gates** (`data/pipeline/gates.json`, G-01…G-14) — the live-pipeline's own
  machine-checked set.

Same letters, different registers — each page that shows them says which register it is
reading. G8-in-the-root-register is the demotion gate; the research lab's G8 is
non-redundancy.
