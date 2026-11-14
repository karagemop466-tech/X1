---

# Executive Summary — second round addendum (2026-11-14, session `arena-1d3600f8-x1`)

The first-round summary above is preserved verbatim. Several of its "deliberately not published"
rows changed state this round — because the missing piece was built, not because the rule was
relaxed.

## What changed

| First round said | Second round state |
|---|---|
| No results feed; ROI not computable | **Verified results feed now exists**: 137 settled 2026 games (Weeks 1–10 through TNF), every row sourced to its official nfl.com game page, double-entry checked against the official standings — 32/32 clubs match on PF/PA and W-L-T, league totals 6,291 = 6,291, zero mirror disagreements. ROI is now computed from official outcomes (`data/results/roi_summary.csv`): **nothing is positive at the assumed −110**; model spread MAE 10.05 pts on verified results. |
| No price snapshots | **Price-snapshot store exists** (`data/price_snapshots/`): opening + closing capture slots for all 56 originated markets (14 games × side/total/moneyline), an append-only capture log, and a recorder tool. Opening quotes do not exist in any permitted source — blank and flagged (Q-02). Closing captures are the third-party mirror benchmark, labelled unverified on every row. |
| Correlation values not published | **15 official-only correlations published** with n, r, permutation p, Fisher CI and row-level official sources (`data/analysis/correlations_official.csv`). Mirror-based values remain visible but quarantined as non-official reference. |
| Leaderboard rankings withheld | The official-only board is still unranked (correct — no official prices yet), but the leaderboard now separates **signal from staking** (`data/leaderboard_signal_staking.csv`): final grade = min(signal, staking); 0 of 16 mirror-window strategies are rankable; a lucky staking run cannot mask a bad signal. |
| Depth tracking = starter vs backup | **Depth of the replacement is now tracked and published**: of 189 on-report starters, replacements sit at 2nd string (168), 3rd string (3), or unreadable (18, flagged, never inferred). Per-team, per-unit, per-status aggregates with sources (`data/analysis/replacement_depth.json`). |
| Demotion = one sentence | **Demotion gate G8 defined** (six mechanical triggers, action, re-entry, logging, authority; `data/gates.json`, `docs/methodology/demotion-gate.md`). D4/D5 switch on automatically when the price store gains captures. |

## The standing honest position

1. **The model is a screen, not a price.** On verified 2026 results nothing beats break-even at
   −110. This is published, not hidden.
2. **No official source publishes betting prices.** Every price cell is blank-and-flagged or
   labelled third-party. Q-02 (a licensed price feed) remains the single highest-leverage decision
   (suggestion S-A on the suggestion board).
3. **Nothing is ranked on luck.** The min(signal, staking) rule and the G8 demotion gate are wired;
   the board is honestly empty of promotable strategies.
4. **Verification is double-entry.** Every new feed is cross-checked against an independent official
   table; every table row on the site links to the page it came from (`tools/verify_app.py`: 5,784
   rows, 0 unsourced).

---

## 9. Round 2 — the eight new requirements (2026-11-14, session `arena-52aabfa8-x1`)

The owner's second brief added eight requirements (R-46 … R-53, quoted verbatim in
`docs/live-pipeline/project-brief-round2.md`). All eight shipped with an artifact, a
machine check and a page:

| # | Requirement | Artifact | Check |
|---|---|---|---|
| R-46 | Price-snapshot store (opening + closing, every market we originate) | `data/prices/price_history.csv` — 20,088 rows, 2,232 games × spread/total/moneyline × both snapshots; blanks carry flag codes | P1–P6 in `tools/build_price_history.py` |
| R-47 | Verified results feed for backtests/ROI | `data/results/verified_results.csv` — 2,232 rows, per-row verification tier (1 official-verified score, 13 officially-confirmed unplayed, 2,218 mirror-flagged) | C1–C4 in `tools/build_results_feed_all_seasons.py` |
| R-48 | Originate side → total → moneyline | `ORIGINATION_ORDER` pre-registered and asserted against the emitted column order in `code/build_lines.py` | write-time assertion |
| R-49 | Fair line / market line / difference as separate columns | `data/lines/originated_lines_2026_week10.csv` now carries all three for all three markets (moneyline difference in probability points, vig named) | column-order assertion; three-column publication on `app/origination.html` |
| R-50 | Signal separated from staking on the leaderboard | `signal_score` / `rank_signal` are the only rank key; `staking_score`, equity and drawdown are informational and structurally cannot enter it | `code/leaderboard.py` sort block; `app/leaderboard.html` |
| R-51 | Depth of the replacement tracked | already live: every deficiency row carries the 2nd/3rd/4th string of the replacement, sourced to the club chart | existing join verification |
| R-52 | Correlations only from official numbers, n with every value | 988-row official-only set, n = 32 on every row, all nfl.com sources, independently recomputed | `tools/verify_official_correlations.py` → 988/988, ledger `data/verify/official_correlations.csv` |
| R-53 | Demotion gate: live → paper | root register gate G8 (six triggers, supersedes this session's four-trigger draft D1) + pipeline G-13; automatic action, shadow-window re-promotion; closes Q-26 | rendered on both validation pages |

**Verification of this round:** every existing check still passes — `tools/verify_data.py`
(2,944 checks), `tools/check_links.py` (28,026 assertions), `scripts/verify_site.py`
(116 pages), `scripts/check_site.py`, `scripts/verify_research_site.py` (1,921 assertions),
`scripts/pipeline/verify_site.py`, `tools/verify_against_official.py` (2,183 cells,
0 mismatches), `tools/test_source_rule.py` (mutation caught), `scripts/verify_parlay.py`,
`tools/cross_check.py`, `tools/hub/build_hub.py`, `tools/verify_app.py` (23 pages,
5,942 rows, 0 unsourced), and the staleness guards for `index.html`/`pages/` and
`data/nfl/availability_derived.tsv`.

**New flags this round (all on the Flagged for Review page, none blocking):**
F-10 legacy `…_away` spread column names (values verified correct under both readings);
F-11 2,218 of 2,232 result rows are mirror-only (Q-04 stays open); F-12 the official
standings snapshot predates the Thursday Night game while the schedule page prints its
FINAL score (freshness, recorded as check C4); F-13 the correlations `method` text omits the
| r | < 0.99 redundancy cut (values verified, documentation gap); F-14 the strategy matrix
publishes no per-cell n (excluded from the R-52 set rather than guessed); F-15 opening and
closing prices use different published conventions (no CLV computed until normalisation is
a recorded decision).

**What still blocks real money numbers:** Q-02 (an owner-supplied price feed — no official
source publishes prices) and Q-04 (official box scores for every historical game). This
round mapped both gaps per row instead of hiding them; neither is closed by this round.
