# Strategy Research — Generating Our Own Lines and Useful Signals

## 1. Philosophy: separating skill from luck

- **Skill** = a repeatable decision process whose expected value is positive **after** accounting for price (the vig) and measured before outcomes are known.
- **Luck** = outcome variance. A coin-flip bettor at -110 will win 8+ of 10 weekends regularly; only sample size and closing-line behavior distinguish them from an edge bettor.
- Luck removal levers (enforced by the [validation gates](validation-gates.html)): minimum sample sizes, closing-line value (CLV) as the primary metric, calibration scoring, stability across sub-periods, and multiple-testing control when screening signals.

## 2. Own-line origination pipeline (v0 implemented)

| Step | What happens | Status |
|---|---|---|
| 1. Power ratings | Elo (K=20, MOV-weighted, HFA 1.75 pts) trained on every regular-season game 1999→present, updated chronologically | ✅ built — `scripts/build_data.py` |
| 2. Convert to lines | spread = (Elo diff + HFA) × 0.026 pts/Elo | ✅ built |
| 3. Injury overlay | Weekly report (source-linked) drives position-group impact flags; QB situations documented | ✅ flags built; **quantified overlay pending** (needs depth charts, OQ-5) |
| 4. Weather overlay | Historical wind/roof baselines computed; per-game forecasts pending | ⏳ OQ-6 |
| 5. Totals model | **Not built** — field left blank everywhere; no values inferred | ⏳ flagged |
| 6. Price comparison | Model fair spread vs market line → "edge" candidates | ✅ built, **informational only until gates pass** |
| 7. Gate review | Only strategies that pass gates become bettable | ✅ defined |

## 3. Signal catalog (evidence-first)

Each signal lists: definition, computed evidence (linked to the computing script), current gate status. **Descriptive ≠ bettable**: nothing here is bettable until gates pass.

| ID | Signal | Computed evidence (1999–2026) | Gate status |
|---|---|---|---|
| S1 | Road favorites outperform home favorites ATS | road fav cover 51.5% (n=2,510) vs home fav 46.9% (n=4,564) | descriptive; needs out-of-sample + CLV |
| S2 | Wind ≥ 10 mph outdoors depresses scoring | over rate 44.7% (n=1,805) vs 48.9% all | descriptive |
| S3 | Rest spot: road team off bye vs short-week home | road side covers 56.8% (n=287), z≈2.3 | provisional — multiple-testing caveat (17 bins screened) |
| S4 | Backup QB teams | cover 49.8% (n=2,156) after removing look-ahead bias | **no edge — do not bet** (worked example in gates doc) |
| S5 | Injury-driven overlays (QB missing, OL/EDGE/CB depth) | flags built weekly; value quantification pending depth-chart data | blocked on OQ-5 |
| S6 | Market efficiency baseline | favorites cover 48.5% overall; weekly variance ratio 0.99 | context, not a signal |
| S7 | Totals in division rematches at low totals | over 49.3% (n=773) — no meaningful deviation | **no edge — do not bet** |

## 4. Week 10 model vs market (v0, informational)

Full table on [lines-model.html](lines-model.html). Largest disagreements: BUF@NYJ (model −16.2 vs market −8.5), JAX@TEN (−15.5 vs −10.5), SF@DAL (−7.5 vs −4.5). Until gates pass, these disagreements mean "model is crude" — the market (a synthesis of thousands of priced opinions) is the benchmark we must *beat*, not ignore.

## 5. Bet-type handling

- **Single bets**: the default. Every pick logged pre-kickoff with line, book, and strategy ID ([ledger spec](leaderboard.html)).
- **Parlays**: allowed only between games; cross-game legs treated as independent per measured variance ratio (0.99). Correlation caps in [props-parlays.html](props-parlays.html). No same-game parlays until player-level correlations are measured.
- **Player props / prop combos**: blocked until play-by-play data exists (OQ-4). Fair lines need usage rates; guessing is prohibited.

## 6. What would make the model bettable (the runway)

1. Totals model built (scoring-rate based) — removes the biggest current gap.
2. Injury overlay quantified with named backups (OQ-5) and historical injury data (blocked in sandbox — discovery in OQ-4/Q5).
3. Walk-forward backtest 2015–2025 with gates applied; then out-of-sample paper picks logged weekly with CLV.
4. Leaderboard entry after gates pass; rewards per approved policy.
