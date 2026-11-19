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

---

# Executive Summary — third round addendum (2026-11-14, session `arena-600e6009-x1`)

The second-round addendum above is preserved as written. This round adds what it uniquely
produced; where the same requirement was built by a parallel round, both artefacts are kept and
labelled rather than one being dropped.

## What this round added

| Requirement | This round's artefact | Relationship to the second round's |
|---|---|---|
| Verified results feed | Third independent transcription of all 137 finals (`data/results/_raw/reads.tsv` → `tools/build_results_r3.py`), three checks per build: row diff vs the publishing mirror (137/137, 0 mismatches), standings arithmetic (32/32), source-URL audit | Cross-checks the T16/N2 feeds rather than replacing them |
| Signal metric (price-independent) | Model side pick vs official result: **84–49 (63.16%), z = 3.035, p = 0.0024, n = 133** (1 tie, 3 zero-line games excluded and named), baseline 0.50 stated because no price exists | Complementary: the round-2 ROI table grades against an assumed −110; this grade needs no price at all |
| Price-snapshot store | 84 records (14 games × side/total/moneyline × open/close) with a capture-status vocabulary (`recorded`, `pending_kickoff`, `captured_post_final`, `not_captured_before_kickoff`) — a stage missed in time keeps its status, never a borrowed value | Same requirement, stricter rule: every market cell blank (no mirror close), statuses published on `app/snapshots.html` |
| Origination order + three columns | 42 rows, sequences asserted to be exactly 1, 2, 3 per game (side → total → moneyline); fair / market / difference as separate columns, difference blank while market is | Coexists with `app/origination.html`; the assertion lives in `tools/build_origination.py --check` |
| Signal / staking split | Official-basis board (`data/leaderboard_signal_staking_official.json`): ST-11 populated on signal only (n = 133), staking columns blank by rule, `rank_basis = signal_only` | Complements the mirror-basis T18 board; both are on `app/leaderboard.html` |
| Replacement depth | Distribution view: 680 slots on the 2nd string, 8 on the 3rd, 0 on the 4th, plus 16 starters on the report whose club chart names no next man (F-15, left unfilled) | Complements the per-slot store on `app/replacement-depth.html` |
| Official-only correlations | Audit of all 988 published pairs: integer n on every value (n = 32), p present, hosts limited to `www.nfl.com`, violations = 0, re-run on every build (`tools/build_round3.py --check`) | Independent check over the same discipline the round-2 15-pair table applies |
| Demotion gate | Adopted round-2's G8 (six triggers, `docs/methodology/demotion-gate.md`) as the register of record — this round's proposed duplicate G8 was dropped in favour of the richer, active one | Nothing discarded: the stronger definition wins the path |
| Decision registers | **Q-19…Q-24** (price feed for the snapshot store, close capture job, G8 ratification, signal baseline, origination of record, results refresh), **S-13…S-18** (six reviewable proposals), **F-14…F-19** (post-hoc Thursday captures, 16 unnamed replacements, 3 zero-line games, the tie, ARI/AZ alias, two-model disagreement) | Root registers were untouched by the earlier rounds; these are additive |

## Still open after this round

- **Q-19 / Q-02** — no official price source: market lines, differences, CLV and ROI stay blank everywhere, by rule.
- **Q-21** — this round asked for explicit ratification of demotion thresholds; the register of record is round-2's G8 (D1–D6, `data/gates.json`), whose D4/D5 stay inactive until a price feed exists.
- **Q-23** — two in-repo models publish different Week 10 lines; neither is designated the origination of record yet (F-19).
- **Q-24 / S-17** — the results feed is verified but not yet re-read by the scheduled refresh.

## 10. Round 4 — decision readiness (2026-11-15, session `arena-fb9e0427-x1`)

**What this round added.** A decision-readiness register with **one row per requirement** (60 rows: the 53
rows of the 2026-11-14 register plus 7 brief items that register does not carry). Each row names the gate
that blocks it, the value measured now from a named repository file, and the number that would clear it.
It is on the landing page (`app/index.html`), and every row carries its evidence link. The data is in
`data/audit/readiness.json`, rebuilt by `tools/build_state_audit.py --check` in CI.

**Headline, measured this round.** The register is not a fair picture of the data:

| | Register (2026-11-14) | Round 4 (checked against the files) |
|---|---|---|
| met | 42 | **33** |
| partly met | 7 | **16** |
| in progress | 2 | 2 |
| open | 2 | **9** |

Nine register rows changed state, every one from **met** to **partly met**: the G1 threshold conflict (R-12), the missing cluster bound (R-14), one capture date with no retained series (R-15), 31 of 32 depth charts (R-16), no snap counts or inactive lists (R-17), the open injury re-capture (R-20), the price pairs (R-46), the official results (R-47) and the mirror market lines (R-49). The register text is unchanged, and the change is shown beside it, not written over it.

**The numbers that block the most rows.**

- **Official prices:** opening and closing spreads exist for **272 of 2,232** games, moneylines for **0**, and
  **0 of 20,088** rows come from an official source (`data/prices/price_history.csv`). The 2,232 games × 3
  markets = **6,696** official pairs needed.
- **Official results:** **14 of 2,232** results are officially verified; the rest rely on the third-party mirror.
  The 2026 feed was built on 2026-11-14, and on 2026-11-15 nfl.com shows the Patriots–Lions game as **Final
  (10–35)**, which the feed still lists as scheduled.
- **Injury captures:** the published table is **one** capture date (345 rows). Nothing retains a series. The
  injury file has one git commit, and daily captures from Wednesday to kickoff need **5 per game week**.
- **Depth:** **31 of 32** clubs parsed. The Houston chart is an image and is not parsed.
- **Strategy gate:** the one strategy that passes every gate has **398 bets**. `data/gates.json` requires **500**
  singles bets, and the README requires 100. The two registers disagree, and this is flagged, not resolved.
- **Gaps with no data at all:** no ablation, no game-cluster bound, no multiplicity adjustment, no NWS forecast,
  no roof designation, no reserve list, no inactive list, no snap count, and no random-picks control on any
  leaderboard run. Each is an open row with its measured count.

**Verified this round.** Four clubs (Commanders, Giants, Patriots, Lions; 44 players, 176 fields) were
compared against the live nfl.com injury page fetched on 2026-11-15, with **0 mismatches** against the
2026-11-14 table (`tools/spotcheck_injuries_r4.py`, `data/audit/round4_spotcheck_injuries.csv`). That is a spot
check of 4 of 28 clubs, not a re-verification. PR #49 (another session, merged as `4f361c9`) reported 16 differing rows
and 2 absent Ravens rows. This round recounted those numbers from its files (flag F4-06) but did not re-read the live page for them.

**Flagged, published, not changed.** The landing page quotes a spread MAE of 10.42 (model) and 9.73
(market). `data/lab/lines/model_report.json` publishes 10.741 and 9.792 over 3,165 games, and the figures
were not reproduced from `data/lab/lines/fair_lines.csv`. The text was left as found and is listed on the
Flagged for review page with both sources. The register also cites Q-09 for reward rules, but Q-09 is
"Market scope" in `data/questions.json`; rewards are Q-07 there and Q-20 in the decision register.

**Still open after this round (with the number that clears each).** Official prices (6,696 pairs, now 0);
official results (2,232 rows, now 14); daily injury captures (5 per game week, now 1 date); 32 of 32 depth
charts (now 31); a reward rule set (Q-07, not decided); a joint-probability calibration per combo family (3
families, now 0 files); and one G1 sample threshold that both registers state (they state 100 and 500 today).

---\n\n# Executive Summary — fourth round: session `arena/1aa2b47f-x1` review and release (2026-11-15)\n\nThis session took over the integrated branch (`arena/1aa2b47f-x1`, identical to `main` at `51d6e32`) and ran the offline verification the build cannot do against live official pages, because `nfl.com` and `operations.nfl.com` return connection failure from this sandbox (HTTP 000). No value was inferred and nothing was published that is not already in a committed official snapshot.\n\n## What this session verified (offline)\n\n| Check | Result |\n|---|---|\n| `tools/verify_data.py` | 2,944 integrity assertions — all pass |\n| `tools/check_links.py` | 159 files, 40,653 assertions — all links resolve, no orphans, every external host approved |\n| `scripts/verify_site.py` | 159 HTML pages — local links resolve, every data-table row carries an official source link |\n| Live official sources | `nfl.com`, `operations.nfl.com` unreachable (HTTP 000) — verification is against committed snapshots only |\n\n## Standing honest position (unchanged)\n\n1. **No official source publishes betting prices.** Every price, CLV, difference and ROI cell is blank and flagged (Q-02 / F-06). Q-02 is the single highest-leverage open decision.\n2. **Nothing is ranked on luck.** Signal is separated from staking; G8 demotes live→paper mechanically; the board is honestly empty of promotable strategies.\n3. **Depth is club self-report.** No league-wide official depth chart exists; several clubs print 'unofficial' (Q-05 / F-01).\n\n## Irregularities carried forward (none block release)\n\nFlags F-01…F-19 and defects D-01…D-03 remain on the Flagged for Review page with source links. Highest-signal open items: Q-02 (licensed price feed), Q-04 (licensed snap counts), Q-07 (reward funding/legality), R-02 (no LICENSE file). No new irregularity was introduced this session; no published value was changed.\n\n## Recommended owner actions (suggestions board, unchanged)\n\n- **S-13** — name the price feed (unblocks Q-19/Q-02 and every market column).\n- **S-17** — schedule the results-feed refresh (unblocks Q-24).\n- **S-16** — ratify the G8 demotion thresholds (Q-21).\n- **S-10** — second independent transcription pass on standings and injuries.\n- Add a `LICENSE` (R-02) before republishing any ingested NFL data.

---

## 11. Integration refresh — 2026-11-19 (session `arena/073589d1-x1`)

This section adds to the sections above; nothing above is edited. Every figure below is taken from a file in the repository or from the official page named beside it.

### What this session verified and changed

| Item | Result | Source / file |
|---|---|---|
| Baseline replay of the CI gates on `a1cca5c` | `verify.yml`: 53 of 53 steps pass. `pages.yml`: 21 of 21 pass. Run with GitHub's shell options (`bash -eo pipefail`). | `.github/workflows/verify.yml`, `.github/workflows/pages.yml` |
| Replay side effect | The replay rewrote 42 tracked generator outputs (timestamps and some counts). They were reverted and not committed. One count changed on replay: the capture-system page shows **8** captures committed and **15** on rebuild. The committed page is therefore stale against its own store. Logged, not fixed here. | `pages/capture-system.html`, `tools/` |
| **Week 11 official injury report captured** (read 2026-11-19 UTC, Thursday) | **253 player rows**, 2 "No Injuries Reported" sections (CIN, WAS), 26 clubs listed, 13 games. Designations: **9 Out, 6 Questionable**, all 15 in the Thursday IND–HOU game. Team row counts sum to 253. | <https://www.nfl.com/injuries/> · `data/capture/2026_w11/` · `week11/index.html` |
| Week 11 anomalies, kept as shown and flagged | Jaylen Waddle is listed under the Broncos; Mike Evans under the 49ers; two displayed names differ from their profile-link slugs (Dee Alford, Jacob Hummel). Club attribution was not checked against the roster pages. | `week11/index.html` (Irregularities section) |
| Week 11 gaps the page does not explain | Game Status is blank for every Sunday and Monday row. Six clubs (ATL, CLE, GB, LAR, NE, SEA) are not on the page, and byes are not stated there. A blank cell is **not** evidence of availability, and the repository does not treat it as one. | `week11/index.html` (What this read does not show) |
| Site checks after the change | `verify_site`, `verify_deployed_tree`, `check_links`, `check_site` and `verify_console` all pass. The Week 11 page is linked from the console landing and copied by the Pages build. | `tools/check_links.py`, `tools/verify_deployed_tree.py` |

### The standing position (unchanged by this session)

1. **No official source publishes betting prices.** Opening and closing prices stay blank or labelled third-party. A licensed price feed is still the single highest-leverage decision.
2. **The model is a screen, not a price.** No strategy is promotable. The leaderboard keeps signal and staking separate and applies the demotion gate. (The gate is defined in `docs/methodology/demotion-gate.md`.)
3. **Readiness, from the repo's own register** (`data/audit/readiness.json`, 60 rows): register status 42 met, 7 partly met, 2 in progress, 2 open, 7 not in the register.

### What this session could not do, and why

- **Daily Wednesday–Friday capture of the injury report, automated.** Not built. Bash in this sandbox cannot reach nfl.com (connection refused), so the capture is a fetch-tool transcription done by hand. Whether GitHub-hosted runners can reach nfl.com was not tested.
- **A second independent read of the Week 11 table.** Pending. The current file is a single-read transcription; its checks are internal (schema, vocabulary, row sums), not a cross-read.
- **Snap counts, official Game Books, inactive lists and depth-chart pages for all 32 clubs.** Not captured in this session. Depth order from jersey number, experience or salary stays rejected.
- **Historical injury reports for past seasons.** Not archived here. Without them, designation reliability cannot be measured.
- **Landing text LA-4** (the stale Week 10 "13/14 final" line) was requested on the coordination board and is **not** changed here. It is an integration item that needs the 2026-11-19 state of Week 10 confirmed from the official schedule page first.

### Questions that must be answered before a decision

| # | Question | Answer now | What would answer it |
|---|---|---|---|
| Q1 | Which price source is licensed for opening and closing lines? | None in the repository. No official source publishes prices. | A licensed odds-feed decision (Q-02). |
| Q2 | Is the Week 11 report complete for all 32 clubs? | 26 clubs listed, 6 absent, byes not stated on the page. | The official Week 11 schedule page and a second read of the report. |
| Q3 | Why are Sunday and Monday Game Status cells blank? | Blank in this read; the page does not say why. | Re-reads on the later report dates, compared row by row. |
| Q4 | Which club do Waddle and Evans belong to? | Shown under DEN and SF on the Week 11 page; not checked against roster pages. | The official roster pages for both clubs. |
| Q5 | Does a designation predict whether a player plays? | Not measured. No archived past-season reports in the repo. | Archived weekly reports plus official inactive lists, joined by player and game. |
| Q6 | Which source gives depth order for all 32 clubs? | Not resolved. Neither route is verified for all 32 clubs. | Per-club official depth-chart pages, or an official snap-count source (route a or b). |
| Q7 | Who will own the public/private data boundary? | Open. The boundary audit (PR #95, open) establishes no private store and no terms approval. | A written decision on what may be published. |

Suggestions for how to close these gaps are on the suggestion board (`suggestions/index.html`). Open pull requests from other sessions (#91, #92, #95, #96, #110, #113, #123) were not merged or changed here.
