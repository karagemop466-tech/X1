# X1 — NFL Line Origination & Strategy Lab

X1 originates its **own** NFL lines, tests strategies against a published
validation protocol, ranks them like a competition, removes luck from the
results, tracks injuries and depth shortages, and publishes every number with
the source that supports it.

The live site is published with GitHub Pages from `docs/`.

---

## What is here

| Path | What it holds |
|---|---|
| `src/x1/config.py` | Every threshold, gate definition, season split and payout assumption in one place. |
| `src/x1/sources.py` | The source registry: league-operated pages separated from community mirrors. |
| `src/x1/ingest.py` | Downloads the raw inputs through the GitHub API and fingerprints them with SHA-256. |
| `src/x1/prep.py` | Game normalisation, market helpers, walk-forward Elo and pre-game-only features. |
| `src/x1/model.py` | Walk-forward Poisson points model, line origination and market diagnostics. |
| `src/x1/strategies.py` | The pre-registered strategy library (spread, total, parlay families). |
| `src/x1/evaluation.py` | Walk-forward evaluation with per-season parameter re-selection. |
| `src/x1/gates.py` | The eight validation gates, bootstrap and randomisation tests. |
| `src/x1/correlation.py` | Strategy correlations, luck decomposition and parlay break-even maths. |
| `src/x1/leaderboard.py` | Leaderboard assembly and the reward formula. |
| `src/x1/props.py` | Player-prop line origination, calibration and prop-family correlations. |
| `src/x1/injuries.py` | Injury tracking, depth-tier derivation and measured injury effects. |
| `src/x1/content.py` | The requirement, question, suggestion and flagged-item registers. |
| `scripts/run_pipeline.py` | Runs the whole research pipeline and writes the processed tables. |
| `scripts/build_site.py` | Static site generator for `docs/`. |
| `data/raw_manifest.json` | Provenance for every input file: repository, path, size, SHA-256. |
| `data/processed/` | The tables that back every published number. |
| `COORDINATION.md` | The shared task board for parallel sessions. |

## Running it

```bash
pip install -r requirements.txt
python scripts/run_pipeline.py    # download, model, evaluate, gate, score
python scripts/build_site.py      # regenerate docs/
```

The pipeline is idempotent: raw inputs are cached and fingerprinted, and a
re-run reproduces the same tables.

## The validation protocol

A strategy earns reward **only** by passing all eight gates:

| Gate | Name | Threshold |
|---|---|---|
| G1 | Sample sufficiency | ≥ 100 settled out-of-sample bets |
| G2 | Out-of-sample integrity | Parameters chosen only from earlier seasons; no duplicate bets |
| G3 | Statistical significance | Bootstrap 95% CI lower bound > 0 **and** sign-flip permutation p ≤ 0.05 |
| G4 | Economic significance | ROI ≥ 2% per unit staked |
| G5 | Beats naive baselines | ROI above every always-on baseline on the same window |
| G6 | Luck robustness | Positive ROI after removing one-score games and blowouts |
| G7 | Parameter stability | ≥ 60% of neighbouring parameter values stay positive |
| G8 | Non-redundancy | Correlation with an accepted strategy ≤ 0.85 |

Reward: `1000 × ROI × min(1, bets / 300) × confidence`, where *confidence* is the
share of the bootstrap interval that stays above zero. A strategy that fails any
gate earns zero.

## Honesty rules the project follows

- Every table row links to the source that supports it.
- A value that cannot be confirmed from an official source is **left blank**
  and listed on the *Flagged for Review* page. Nothing is inferred or filled in.
- The market benchmark is a third-party closing line, because the league
  publishes no betting lines. That is stated wherever the benchmark is used.
- Depth tiers are derived from usage, because the league publishes no depth
  chart. Every derived row says so.
- Strategy parameters are re-selected each season from earlier seasons only.

## Licence

Research use. The bundled data files are third-party mirrors and keep their
own terms; see `src/x1/sources.py` for the full list.
