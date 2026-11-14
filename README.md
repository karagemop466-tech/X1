# X1 — NFL Data, Verification & Decision System

Verified NFL data · original line origination · a skill-gated strategy leaderboard ·
decision-support analysis. Every table row on the site links its official source; values that
cannot be confirmed are **left blank and flagged — never inferred**.

**Live site:** https://karagemop466-tech.github.io/X1/ (GitHub Pages, deployed from `main`)

## What's in here

| Path | Contents |
|---|---|
| `site/` | The static dashboard (10 pages): overview, teams, schedule, injuries & depth, X1 lines, strategies & leaderboard, executive summary & open questions, suggestions, flagged-for-review, sources |
| `data/nfl/` | Verified reference data (standings, Week 10 schedule, international slate, season facts) — per-row source links |
| `data/injuries/` | Official Week 10 injury report (345 rows) + QB starter map with conflicts flagged |
| `data/lines/` | X1 originated lines, model config, leak-free backtest, threshold sweep, computed correlation report |
| `data/strategies/` | Strategy registry, validation gates, leaderboard, luck-reference arithmetic, bet-log template |
| `data/raw/nflverse/` | Source copies (nflverse/nfldata via GitHub API) + provenance README |
| `docs/` | Repo review, source registry & verification protocol, methodologies, executive summary, open-questions matrix, suggestions register |
| `code/` | Deterministic, stdlib-only builders: reference data → lines → leaderboard → site |

## Rebuild everything

```bash
python3 code/build_reference_data.py   # emits verified CSVs from transcribed official data
python3 code/build_lines.py            # fits ratings, backtests leak-free, originates Week 10 lines
python3 code/leaderboard.py            # grades bets, scores strategies, checks gates
python3 code/build_site.py             # regenerates the site from the CSVs
```

## Key verified facts (snapshot 2026-11-14)

- 2026 season, Week 10: 137/272 games played; byes CHI/DEN/PHI/TB; Munich game NE@DET;
  MNF LAC@BAL. Standings 32/32 cross-verified NFL.com ↔ nflverse (exact match).
- Record nine 2026 international games (operations.nfl.com): Melbourne, Rio, 3× London, Paris,
  Madrid, Munich, Mexico City.
- X1 v1 model: MAE ≈ 10.9 pts; **no betting edge vs market** (ROI −6.1%..−2.6%) — reported
  honestly; model v2 (QB-adjusted) is suggestion SG-02.
- Correlations (computed): same-game spread/total φ = −0.023 (n=1,496); margin-total r = 0.020;
  cross-game r = 0.001 (n=12,585). Prop correlations blocked on data (open question Q5).
- Luck arithmetic: a true 55% win-rate capper needs **991 bets** for 95% confidence — the
  leaderboard gates encode this so luck cannot be rewarded.

## Coordination

Parallel sessions read `COORDINATION.md` before any work: claim tasks, commit claims immediately,
keep scopes non-overlapping, rebase before push, and record sources/verification/irregularities
at completion. Shared outputs change only in the final integration session.

## House rules

1. Official sources only for verified values (see `docs/sources/sources.md` for tiers).
2. Unverifiable → blank + `Flagged for Review` (site page) — never filled in.
3. Conflicting sources are recorded, not silently resolved (see the QB map).
4. Market lines are benchmarks, not truth.
5. No betting recommendation anywhere on the site; strategies must pass gates first.
