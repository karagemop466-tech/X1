# Demotion gate G8 — live back to paper (T21)

**Session `arena-1d3600f8-x1` · 2026-11-14**

## What the owner asked for

> Define a demotion gate that sends a live strategy back to paper.

Before this gate existed, demotion was one sentence in the scoring rules ("two failed windows
demote; no sitting on old results"). G8 makes it operational, mechanical, and logged.

## Gate definition (machine-readable in `data/gates.json`, gate G8)

**Scope:** any strategy whose status is `live` (funded or paper-promoted).

**Triggers — any ONE demotes:**

| ID | Rule | Basis | Status |
|---|---|---|---|
| D1 | Two consecutive registered windows with negative flat-stake (signal-basis) ROI | signal block | active |
| D2 | Rolling 300 settled bets: hit rate below break-even with z ≤ −1.96 | signal block | active |
| D3 | Max drawdown > 25% of bankroll under the registered staking rule | staking block (live breach of G5) | active |
| D4 | Mean CLV negative over the last 100 settled bets | price-snapshot store | **inactive until a price feed exists (Q-02)** — recorded now so it cannot be forgotten |
| D5 | Brier skill score vs market-implied negative in two consecutive windows | G3 calibration in live | requires price feed (Q-02) |
| D6 | Any G0 provenance violation (lookahead, unlicensed input, unlogged settlement rule) | G0 | active, fires immediately |

**Action (what demotion does):**

* status `live → paper`, effective at the next settlement batch (immediately for D6);
* open live positions settle normally; new positions at paper stakes only;
* bankroll frozen: no additions or removals while demoted;
* leaderboard shows `demoted` with the trigger id; the strategy cannot rank in live leaderboards;
* every demotion is appended to `data/demotion_log.jsonl` (strategy, trigger, evidence, window,
  timestamp). The log is currently **empty — no strategy is live** (all 16 graded strategies are
  paper-only; see the signal/staking board).

**Re-entry (never automatic):**

1. one full shadow window at paper stakes;
2. pass gates G0–G7 again on the shadow window;
3. one clean live-probation window before restored standing;
4. the re-entry itself is recorded in the demotion log.

**Authority:** mechanical — triggers fire without discretion. A manual override requires an owner
note in `COORDINATION.md` with reasons.

## Why these triggers and not others

* D1/D2 catch **bad signal** (the quantity that matters) on the flat-stake basis, so a lucky
  staking run cannot postpone demotion — consistent with the signal/staking separation rule
  (final grade = min(signal, staking)).
* D3 catches **risk** even when the signal is fine.
* D4/D5 catch **market-decay** — the ways a strategy can keep winning bets while losing value.
  They are defined now and switch on the moment the price-snapshot store has real captures.
* D6 is the integrity tripwire: a provenance violation invalidates everything downstream, so it
  demotes immediately rather than at a window boundary.

## Relationship to the other gates

G8 is the only gate that **moves a strategy between states**; G0–G7 decide whether it may enter.
A demotion does not delete history: past windows stay on the board with their grades, and the
demotion entry is part of the strategy's permanent record.
