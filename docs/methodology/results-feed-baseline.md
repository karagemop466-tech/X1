# What the results feed is verified *against*

**Decision recorded 2026-11-17 by session `arena-473e08d5-x1` (task N-2), answering question Q-62 and
executing suggestion S-22.** One line, then the reasoning a reviewer needs to disagree with it:

> The verified results feed is reconciled against a **dated, frozen standings transcription**, never
> against the rolling collector register. The date is published with the claim.

## The two candidates

| | A — rolling baseline | B — dated baseline (**chosen**) |
|---|---|---|
| What the feed is checked against | `data/pipeline/standings.json`, rewritten by the collector on every refresh run | `data/verification/<date>/official_standings_<date>.tsv`, a hand transcription of the official standings page with its own read date |
| What "verified" means | "agrees with whatever the collector last fetched" | "reproduces the league's own numbers as printed on a named date" |
| Failure mode | coverage gaps disappear by redefinition: if the register moves, the feed is "consistent" again without a single new official read | coverage gaps are visible, but the baseline must be re-read and re-transcribed each time the feed is extended |
| Can a reader reproduce it | only with the collector's fetch history | yes: the file, the URL, the date, and the checker are all in the repository |

A's failure mode is the one that matters here, because it is silent. The feed and the register would be
two readings of the same page that happen to agree, and nothing in the repository would say which date
the agreement belonged to.

## What B costs, and how that cost is paid

Extending the feed under B is not an append. Four artefacts are coupled and move as one change or the
feed stops being arithmetically meaningful:

1. **the transcription** — the new official rows (`data/results/raw/official_results_2026_weekNN.psv`,
   `data/results/_raw/reads.tsv`);
2. **the row-count pin** — the feed builders assert the expected number of settled games
   (`tools/build_results_r3.py` `N_EXPECT`; `tools/build_results_feed_907c.py`);
3. **the standings baseline** — a new dated transcription covering through the last completed week;
4. **the mirror pin** — `data/raw/nflverse/games.csv` plus `data/raw_manifest.json`, because the
   third-party row-diff gate needs bytes that *contain* the new games.

Moving (1) alone was tried and rejected: the feed grew and 23 of 32 clubs immediately disagreed with the
standings it is validated against, i.e. the closure looked like 23 transcription errors. The gate was
right to fail; the baseline was the stale side.

The first closure executed this way is on disk as the worked example:
`data/verification/2026_11_17/` (Week 10 complete, 13 games appended, feed 137 → 150) with
`tools/verify_2026_11_17.py` as its checker.

## What each checker is allowed to read

| Check | Reads | Why that source |
|---|---|---|
| V7 / standings arithmetic | the dated transcription | the claim is "reproduces the page as printed on date X" |
| V6 | `data/pipeline/standings.json` | a *second, independent machine parse of the same page*: a disagreement is a parser defect, not a redefinition |
| V1–V5 | the dated evidence pack only | read integrity, cross-page record agreement, HOME+ROAD = W-L-T, league closure |
| V9 | `data/raw_manifest.json` vs the pinned file | the cross-check must be cited by bytes, not by URL: two fetches of the mirror 21 minutes apart on 2026-11-17 returned **different bytes**, the first without the Sunday scores |

`data/pipeline/standings.json` therefore keeps a role and loses an authority: it may *corroborate*, it
may never *set the baseline*. That is the answer to Q-63's first half as well — the dated files are
canonical, the register is a cache.

## Consequences the site has to live with

* **A frozen baseline freezes coverage.** Between closures the feed legitimately says "150 games" while
  the league has printed more. That is stated with its date rather than hidden, and the collector's
  refresh must not quietly re-baseline the feed to look current.
* **Every count needs a date next to it.** The landing page carried "137 settled games" for three days
  after the official page printed 14 Week 10 finals — the number was correct for its read and wrong as a
  present-tense claim. `tools/verify_app.py` now fails the build if the results page states a settled-game
  count that is not the row count of the feed it renders, and the feed rows carry their own `read_at`
    (`retrieved_at` per row, rendered in the page's *Retrieved* column).
* **Pre-kickoff records are not re-baselined.** `data/shadow/forecasts_pre_kickoff.csv` and the dated view
  `data/results/verified_results_2026.csv` stay exactly as written; a closure adds rows beside them and
  reports the drift, and `tools/grade_roi.py` names which feed file it graded against on every output row.
* **Joins are measured, not assumed.** The three sets spell two relocated clubs differently (`LA`/`LAR`,
  `ARI`/`AZ`/`ARZ`), so the closure joins fixtures on away + home + date with an explicit normalisation
  and fails if a fixture exists on one side only. `game_id` is never a join key across sources.

## Who may change this

The baseline date moves only in a commit that moves all four coupled artefacts and re-runs every results
gate in the same diff — reviewed as one change. Re-baselining the standings without new game rows (or the
reverse) is the shape that turns a coverage gap into an apparent data error, in either direction.
