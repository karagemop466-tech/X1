# Correlation report (computed, deterministic)

All values computed by `code/build_lines.py` from nflverse game results + market lines embedded in games.csv. No external claims.

| Metric | Value | n | 95% CI / detail | Meaning |
|---|---|---|---|---|
| game_margin_vs_game_total_pearson_r | 0.02 | 1496 | 95% CI (-0.031, 0.071) | same-game: higher-scoring games & margin relationship |
| same_game_favorite_cover_vs_over_phi | -0.023 | 1496 | 95% CI (-0.073, 0.028); P(over|fav covers)=0.473 vs P(over)=0.485 | same-game parlay correlation (market lines, 2021-2026) |
| model_spread_error_vs_total_error_r | 0.025 | 1779 | 95% CI (-0.022, 0.071) | same-game model errors |
| cross_game_same_week_residual_r | 0.001 | 12585 | 95% CI (-0.017, 0.018) | independence check across games in same week |

Parlay risk control: same-game spread/total legs carry phi ≈ -0.023 — joint probability must be adjusted, naive multiplication understates risk by roughly the difference between P(over|fav covers)=0.473 and P(over)=0.485.
Cross-game residual correlation r ≈ 0.001 (n=12585 pairs) supports treating different games as near-independent when building multi-game parlays.
