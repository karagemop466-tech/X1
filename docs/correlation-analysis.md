# Correlation Analysis — Measured Values

All values computed by [`scripts/build_data.py`](https://github.com/karagemop466-tech/X1/blob/main/scripts/build_data.py) from nflverse `games.csv` (1999–2026 regular seasons with market lines, n=7,074 unless noted). No external values, no inference.

## Game-level correlation values

| Measure | Value | Interpretation | Source |
|---|---|---|---|
| corr(market spread, actual home margin) | **0.431** | the market line is a moderately strong margin predictor — the benchmark any own-line model must beat | [build_data.py](https://github.com/karagemop466-tech/X1/blob/main/scripts/build_data.py) |
| corr(actual margin, game total) | **0.017** | side and total are essentially uncorrelated | [build_data.py](https://github.com/karagemop466-tech/X1/blob/main/scripts/build_data.py) |
| corr(\|margin\|, game total) | **0.075** | close games are not systematically higher/lower scoring | [build_data.py](https://github.com/karagemop466-tech/X1/blob/main/scripts/build_data.py) |
| P(home covers) | 47.5% | baseline | [build_data.py](https://github.com/karagemop466-tech/X1/blob/main/scripts/build_data.py) |
| P(home covers \| game goes OVER) | 47.8% (Δ +0.3pp) | spread & total legs near-independent at game level | [build_data.py](https://github.com/karagemop466-tech/X1/blob/main/scripts/build_data.py) |
| Weekly home-cover variance ÷ binomial expectation | **0.99** (473 weeks, n≥8 games) | no slate-level overdispersion: **cross-game outcomes are effectively independent** — parlay pricing by multiplication is fair | [build_data.py](https://github.com/karagemop466-tech/X1/blob/main/scripts/build_data.py) |

## Why these numbers matter

1. **Parlays:** the variance ratio (0.99) empirically justifies treating different games as independent legs. If slate-level shocks (weather systems, refs, weeks) mattered, this ratio would exceed 1.0 — it does not.
2. **Same-game parlays:** the spread↔total Δ (+0.3pp) shows even the two markets inside one game are weakly coupled at the *game* level. Player-level coupling (QB↔WR etc.) is larger but **unmeasured** — blocked until play-by-play data exists ([props-parlays.html](props-parlays.html)).
3. **Own lines:** corr(spread, margin) = 0.431 quantifies how much information the market line already contains; any model claiming an edge must demonstrate |model − market| disagreements that survive the gates.

## Caveats

- All values are market-era regular-season aggregates; sub-period shifts are checked in Gate F, not here.
- Player-prop correlations: **no values published** — data blocked (OQ-4). Any number you see elsewhere until then is not from this system.
