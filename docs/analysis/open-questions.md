# Open questions — what must be answered before decisions (T7)

Decision-readiness matrix: every question that must be answered before a reasonable decision can
be made, what we already know (verified), what is missing, and the suggested action to discover it.
Status values: `open` (needs owner decision or data), `in-progress`, `answered`.

| # | Question | What we know (verified) | What we don't have | Suggested discovery action | Status |
|---|---|---|---|---|---|
| Q1 | What data can we trust automatically? | Standings/schedule/injuries cross-verified from official sources (32/32, 14/14, 9/9 matches); nflverse results match NFL.com exactly | A repeatable refresh pipeline (today: manual snapshots) | Add a weekly fetch script + Actions schedule; keep per-row provenance | open |
| Q2 | Which model improvements give the first real edge? | v1 (results-only) has no edge: ROI −6.1%..−2.6% at all thresholds; market RMSE 13.3 vs ours 13.9 | Quantified lift from QB-adjustment, recency weighting, situational features | Build model v2: QB starter adjustment (data already in qb_map), recency weights; re-run backtest; promote via gates | open |
| Q3 | Who is actually 2nd/3rd string on each team? | Official weekly injury reports (345 verified rows, W10 2026) | Official depth charts for all 32 teams (no league-wide official source; club PR releases have them) | One-time collection of all 32 club depth charts into `data/depth/` with per-row club links; then snap-count verification via official gamebooks | open — **highest-value unlock** (enables S1/S2 + deficiency score) |
| Q4 | How big is the backup-QB / injury-deficiency effect historically? | Market visibly prices QB news (e.g., LAC@BAL market line vs model without QB knowledge) | Historical injury-report archive joined to results | Archive NFL.com weekly reports (they exist per week, e.g. W9 2026); join to nflverse results 2019–2026; quantify | open |
| Q5 | Which player-prop combos are correlated? | Game-level correlations measured: same-game spread/total φ=−0.023; cross-game r=0.001 | Prop-level marginals and correlations (no official prop results feed in sandbox) | Obtain official league stat feeds (Next Gen Stats / GSIS via operations.nfl.com) or a licensed provider; compute per-market correlation matrix | open |
| Q6 | Where will live market odds come from? | nflverse per-game closing lines (2019+, secondary source) for backtests | A live, timestamped odds feed for CLV scoring and price comparison | Decide provider/subscription (or use NFL.com-adjacent public endpoints if licensing allows); store timestamped lines in `data/odds/` | open — **blocks CLV-based rewards** |
| Q7 | How is the reward pool funded and sized? | Reward mechanics defined (60/25/15 to top-3 official strategies) | Owner decision: pool size, currency, cadence | Owner decision required; no technical blocker | open — **owner decision** |
| Q8 | Which bets are allowed on the board? | Gates defined for singles, parlays (φ-adjusted), props | Owner policy: max parlay legs, prop-combo limits, bankroll cap | Owner decision; default proposal in suggestions SG-06 | open — owner decision |
| Q9 | How should the site grow? | Static site live with 10 pages, source-linked tables | Feature roadmap (filters, per-team pages, archive) | See suggestions register (SG-01..SG-08); owner picks | open |
| Q10 | What is the risk posture? | Luck math computed (991 bets to prove a 55% capper) | Units per bet, stop-loss, correlation caps at portfolio level | Owner decision; defaults proposed in suggestions SG-07 | open — owner decision |
| Q11 | Are the flagged roster moves real? | 12 irregularities flagged with sources (F1–F12) | Confirmation from club rosters/official transactions | Verify each flagged item against official club/transaction pages before using in models | in-progress |
| Q12 | BAL Week 10 starting QB? | Conflict documented (nflverse: Huntley; NFL.com news Nov 5: out for season; no QB on official W10 report; Lamar on IR) | Final answer (inactives publish ~90 min before Monday 8:15 PM ET kickoff) | Check official inactives Monday night; update qb_map | in-progress |

**Rule:** nothing on the site or in the models treats an open question as answered.
