# Props & Parlays — Policy, Correlation Rules, and What Is Blocked

## 1. Current status of player props: BLOCKED (honest)

Generating **fair prop lines** (passing yards, rushing, receiving, TD scorer, etc.) requires player usage data: targets, carries, routes, air yards, team tendencies. That data lives in play-by-play / official stat feeds which are **not available in this environment** (nflverse release assets blocked from the sandbox — see [methodology](methodology.html), OQ-4).

Therefore:
- **No prop lines are published.** Fields that would need them are blank and flagged.
- **Player-level correlation values are not published** — they cannot be measured without play-level outcomes. Guessing correlation coefficients would violate the no-inference rule.
- Discovery options are logged in [open-questions.html](open-questions.html) Q4.

## 2. Parlay policy (game-level — supported by measured data)

Measured facts (computed, 1999–2026): weekly home-cover variance ratio **0.99** → outcomes across games behave like independent binomials; P(home cover | over) − P(home cover) = **+0.3pp** → spread and total legs are near-independent at game level.

Rules:
1. **Cross-game parlays only.** Pricing multiplies leg probabilities (justified by the measured independence).
2. **Correlation cap 0.35** (proposed): any two legs with measured correlation above the cap are rejected.
3. **No same-game parlays** until player-level correlations are measured from play-by-play data (classic priors — QB passing ↔ WR receiving positive, RB rushing ↔ WR receiving negative, team total ↔ player props positive — are **unverified hypotheses**, not inputs).
4. Parlay EV must clear the same threshold as singles; vig compounding is not an edge.
5. "Player prop bet combos" remain blocked until (1) prop fair lines exist and (2) same-game correlations are measured.

## 3. What is needed to unblock props

| Need | Source options | Verify by |
|---|---|---|
| Play-by-play 2026 | nflverse weekly pbp release (via GitHub Actions) | reconcile one week's totals vs official NFL gamebooks |
| Official player stats | NFL.com GSIS stat feeds / gamebooks | line-by-line box score check |
| Usage rates | derived from pbp (targets, carries) | cross-check vs team official reports |

Once unblocked: build per-prop fair lines from distributions, publish correlation matrix per game, then allow combos under the cap.
