# Round-3 brief — verbatim source of record

Captured 2026-11-15 by session `arena-9e5228c8-x1`. This file is the **verbatim** brief this round
answers. It is not edited after capture. `data/deck/brief_round3_sentences.tsv` splits it into
individual requirement sentences, and `tools/build_deck.py` **verifies that every sentence in the
TSV is a literal substring of this file** before it publishes anything. A typo, a paraphrase or an
invented line therefore fails the build instead of reaching the site.

Three parts, in the order they arrived.

---

## Part A — the requirement lines

NFL

The goal of this project is to collect, organize, and analyze utilizing a full list of requirements.  

Add a price-snapshot store that records opening and closing numbers for every market we originate

Add a verified results feed so backtests and ROI can be computed at all

Originate the side first, then the total, then the moneyline

Publish the model's fair line, the market line, and the difference as separate columns

Separate 'signal' from 'staking' in the leaderboard so a lucky staking run cannot mask a bad signal

Track the depth of the replacement, not just the fact of a replacement

Compute correlations only from officially sourced numbers and publish n with each value

Define a demotion gate that sends a live strategy back to paper

Pre-register every strategy; forbid backtest numbers from ever appearing on the leaderboard

Build the availability graph as a first-class dataset (who was expected to start, who actually did)

Do not model depth from jersey order; model it from playing time

Make the injury signal a surprise, never a level

Run the 32-team roster/IR sweep before any team-level model is trusted

Add a fixture-context feature set built only from published schedule facts

Store every model output as a probability plus its inputs, not just a pick

Compute and publish the "removal of luck" panel on the site dashboard

Add a two-sided "what would change our mind" field to every strategy entry

Price a line ourselves and publish the residual against the market, on a schedule, from day one

Turn the 136-game log into the pre-registered backtest corpus

Decide the price-data policy before any backtest is published

Store every injury-hub read with its clock time and publish the delta, never the level

Put a decision-readiness table on the landing page: one row per requirement, with the gate that blocks it and the number that would clear it

Transcribe the venue of every fixture from the official game centre and publish it

Publish the league's dated schedule announcement beside the live schedule page

Use official NFL Game Books for actual starters and game-day status; do not infer depth rank or snaps

Ingest game-level results to make the ratings opponent-aware

Add injury and personnel ablations instead of fixed penalties

Instead of subtracting a fixed number of points for a missing starter, test the same model with and without the personnel features and report the difference with uncertainty.

Add injury/depth ablations, not fixed penalties

Compare identical models with and without verified availability features using chronological holdouts.

Automate immutable multi-day availability snapshots

Capture the official report and club depth pages at least daily with retained hashes, so practice designations can be replayed as they were known. Today the site holds one capture, which cannot support backtesting.

Build immutable official availability snapshots

Scheduled capture of NFL injury reports, club depth pages and inactive evidence with raw hashes, timestamps and conflict flags

Capture official inactive lists and snap counts

Only 6 of 254 report rows carry a game designation, and no active list or snap share is captured. Without them a backup's replacement of a starter cannot be confirmed, only suspected.

Fix the two depth-parsing failures before widening coverage

The Texans publish depth as an image and the Packers prepend jersey numbers. Number stripping plus storing the raw string recovers the Packers rows; the Texans image needs an authorized structured source, not transcription by eye.

Model depth slots as groups, not a single starter

149 club/unit/position slots list more than one rank-1 player (three receivers at rank 1, three inside linebackers at rank 1). Treating column 1 as 'the starter' would fabricate a starter the club never named.

Treat roster turnover as a first-class data event

The Colts' Week 10 release documents two starting-receiver trades in the same article as its depth chart. Depth, availability and lineup evidence must be versioned against the last official roster event, not trusted as durable.

Start with a singles-only shadow baseline

Pre-register a simple team-strength model, freeze versions and record forecasts before kickoff.

Keep parlays and prop combos behind a joint-evidence gate

Multiplying marginal probabilities is invalid under dependence. A combo may only be ranked when a directly validated joint probability and the operator's void/push rules are both available.

Use proper-score leaderboard divisions

Separate singles, game parlays, same-game parlays and prop combos; rank eligible strategies by benchmark-relative skill with uncertainty.

Rank with proper scores and uncertainty, not win rate

Rank by benchmark-relative Brier skill with a game-cluster lower bound and a multiplicity adjustment for the number of trials. Raw win rate and short-run ROI cannot distinguish skill from variance.

Add durable snapshot storage and alerts

Store immutable captures outside the static site, monitor freshness and alert on source/schema changes.

Split the site into a public analysis layer and a private data layer

Keep the public site to derived analysis (indices, ratios, model output, links to the official page) and hold raw row-level data in a private store until the terms are read.

Add a per-team view: starters out, replacements named, net injury count

Quick team-level decision view

Add an announced-starter evidence field (not an inferred replacement)

The blank replacement columns are correct for the report page, but the NFL does publish dated starter changes for Lock, McCord and Brissett (VR-24, VR-25; VQ-05).

Add an official depth-chart register with date and source per row

Required to flag backups replacing starters on offense and defense

Calibrate what "Questionable" means empirically instead of using old percentages

Official text gives no percentages

Interactive Offense vs. Defense Matchup Deficiency Matrix (1st–4th String)

Surfaces immediate trench and coverage mismatches (e.g., WR1 facing promoted 2nd/3rd-string CB, or EDGE1 facing 2nd/3rd-string OT/LG) on one screen.

Flag stale depth rows against the official transactions log

Baltimore still publishes Lamar Jackson and Tyler Huntley at QB after both went on injured reserve and a replacement was traded in (VR-17, VR-26; VQ-07).

Point-in-Time Snapshot Ledger for Injuries, Depth Charts & Inactives

Prevents lookahead leakage when backtesting originated lines and preserves exact pre-kickoff replacement certainty.

Populate the three missing Lions game-status designations

Kerby Joseph, Cade Mays and D.J. Reed are published with a blank game-status cell while the official article lists all three as Out (VR-08, VR-12).

Re-capture and republish the Week 10 injury tables

Published counts are stale: 254 rows and 4 no-injury sections versus 279 rows and 2 sections live; Seattle and Cincinnati are shown as injury-free while listing 15 and 4 players (VR-04, VR-05, VR-06, VR-07).

Reject: deriving depth order from jersey number, experience or salary

Proposed shortcut for SG-05: infer starters from roster attributes on the official roster page.

Represent shared and empty depth slots faithfully

Seattle puts two players in one slot and Washington leaves a slot empty; both are currently indistinguishable from a ranked list (VR-21, VR-23; VQ-08).

Resolve the depth-order source before building the backup-deficiency feature

Evaluate two routes in order: (a) per-club official depth chart pages, verified club by club; (b) derive depth from snap counts if an official snap-count source exists. Do not build the feature until one route is verified for all 32 clubs.

Score injury-designation reliability before using it as a feature

Join several seasons of designations to the official inactive lists and measure the play rate per designation with confidence intervals. Only then decide whether the label becomes a model feature.

Snapshot the nfl.com injury report every Wed, Thu and Fri and keep a dated history

Lets us see Questionable→Out changes and practice trends (DNP→LP→FP)

Treat the injury report as a timestamped series, not a weekly snapshot

Capture the report daily from Wednesday to kickoff with the fetch timestamp, then measure how designations evolve.

Use snap counts as the starter proxy when the depth chart is unavailable

Gives a measurable starter/backup split

Add a control baseline (random picks; favorites only) to every leaderboard run

Separates skill from luck

Stadium Roof/Surface & NWS Hourly Wind/Precipitation Overlay

Prevents totals and passing-prop mispricing by coupling NWS forecast grids with official 90-minute stadium roof designations.

Two-Stage Skill Leaderboard (Proper-Score Qualification -> Prospective CLV/ROI Escrow)

Aligns incentives strictly with calibrated probabilistic skill (Brier Skill Score + Closing Line Value) over multi-week prospective samples.

Vig-Free Market Consensus vs. Originated Fair-Line Decomposition View

Separates true pricing divergence (origination alpha) from operator vig/margin before any bet structure is considered.

Publish a weekly 'what changed' diff instead of a static snapshot

Store each weekly snapshot and render a diff column (rank change, rating change, availability change).

Publish every model total twice until one wins

Keep both estimators visible with the gap column, and only collapse to one after a walk-forward comparison.

Add a drift alarm to every scraper

Pin each parser to expected row counts and required fields; fail the build loudly when a field goes missing rather than publishing a blank.

Capture the reserve list so 'not listed' never means 'available'

Malik Willis is absent from the weekly report because he is on injured reserve, not because he is healthy (VR-25; VQ-06).

Reject: ranking strategies by season-long ROI

Proposed alternative to SG-03: rank purely on realised return over the season.

Archive weekly injury reports for past seasons (for Q06)

Only way to test whether designations change outcomes

Pre-register each strategy (definition frozen before results are seen)

Prevents result-chasing

2026 Kickoff & Declared Onside-Kick Regime Priors Filter

Avoids systematic bias in originated game totals and 4th-quarter comeback win-probability curves.

Freeze a rule before it sees data (pre-registration)

Commit the rule text, the sample window and the gates to git before the evaluation window opens. The commit hash is the registration.

Split data into train, validation and final holdout seasons

Protects out-of-sample testing

---

## Part B — the site and research request

Make suggestions on how to improve the site to improve decision making and create a section dedicated for suggestions so someone can review suggestions and choose the best path before implementing any changes.

I want a clear list of questions, informations and answers that need to be addressed before any decision can be reasonably made based upon the information that we already have and do not have.  Suggestions need to be made to discover missing information.

I want to originate my own NFL lines.  Research and develop strategies for generating useful signals.  Treat it as a leaderboard competition that provides rewards for top performing strategies.  Look at single bet, parlays, player prop bet combos.   Each strategy must pass validation gates.   Determine correlation values.   Remove luck from the equation and build strategies that are selectively skill based.

The system should be tracking injuries and know any deficiencies in defenses such as 2nd,3rd or 4th string backups having to replace starters due to lineups.  Also same can be said for offenses using starters or backups.

Create an executive summary outlining important details.

## Part C — the operating instructions

There should be no manual input on my part. Work on your own to finish all tasks in this session. Work line by line, verify everything from official verified trusted sources, no hallucinations.

REPO WORK  Review the repo. Work line by line verifying from official verified trusted sources, and provide links for manual review. Flag any irregularities for review. No hallucinations.

SITE CREATION  Create a github page live site for this repo with a clean landing page and subpages organized by category. The UI should be clean, user friendly, simple, and easy to use, like a simple dashboard. It should contain all entries and findings in a simple, easy to read table format, and include any analysis and findings. Work line by line, verify everything, no hallucinations.

VERIFICATION  Verify line by line. Every table row must have a source link to an official site. If a value can't be confirmed from an official source, leave it blank and flag it as unverified. Never infer or fill in values.

PARALLEL SESSIONS  Multiple agent sessions may work on this repo at the same time, so coordinate to avoid conflicts and duplicate work. Before starting, read COORDINATION.md in the repo root (create it if it doesn't exist). It is the shared task board, listing each task, its status (unclaimed, in progress, done, needs review), the owning session ID, and the files it touches. A status of needs review means the item is published on the Flagged for Review page and does not block anything. Claim a task by writing your session ID and file scope there, then commit and push that claim immediately, and never start a task another session has claimed. Keep scopes non-overlapping: each session works on its own branch (or git worktree) named session-<id>/<task> and edits only the files in its claimed scope. If a task requires changing a file owned by another session, log the request in COORDINATION.md instead of editing it. Make small, frequent commits, and run git pull --rebase before every push. If you hit a merge conflict, stop, resolve it without discarding the other session's work, and log what happened. When a task is finished, record its sources, the verification performed, and any irregularities in COORDINATION.md and mark it done. Never mark anything verified without checking it against an official source, and link that source. Shared outputs, such as the table data and the site's index and navigation, are changed only by a final integration session once all other tasks are done. That session merges the branches, re-verifies the combined data line by line, confirms the site builds with no broken links, and publishes to GitHub Pages. If a session crashes or its claim is more than 60 minutes old with no commits, any other session may take over the task and note the handoff in the log.

PULL REQUEST AND MERGE  Do not stop to wait for my review. Work fully on your own from start to finish. When all tasks are done and the final integration session has verified the combined data and confirmed the site builds with no broken links, create a pull request from the integration branch to main with a summary of the changes, the sources used, and any flagged irregularities. Then merge the pull request without waiting for approval, confirm GitHub Pages deploys successfully, and record the PR link and merge result in COORDINATION.md. Flagged irregularities and unverified items do not block the merge. Publish them on a clearly labeled "Flagged for Review" page on the site, with the source links, so I can review them after the site is live and request changes. If the build, a check, or the deploy fails, fix the problem and retry until the site is live. Do not merge a broken site.
