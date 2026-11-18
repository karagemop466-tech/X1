# Round 6 findings — PR #84 reconciliation and the defects found while verifying it

**Session:** `arena/6a4ba536-x1` · **Branch:** `arena/6a4ba536-x1` (from `main` @ `d80c5b3`) · **Date:** 2026-11-18 (UTC)
**Scope:** this file records what this session measured. Every value below is either read from a committed
official transcription or re-derived from one; nothing is inferred. Where a value could not be confirmed,
it says so.

---

## 1. What this round changed, and why

`main` carried one open PR (#84) that had been `CONFLICTING` for a day. It was not cosmetic: it is the change
that closes Week 10, taking the verified results feed from 137 settled games to 150, and it decides the
price-data policy the brief demanded *before* any backtest is published. The repository's own record
(`COORDINATION.md`, round 5) said the feed was closed; the artefact the site reads,
`data/results/results_feed_meta.json`, still said **14 of 2,232 verified, generated 2026-11-14**. Both could
not be true. This round resolved it by regenerating from the generator, not by editing a published number.

## 2. Independent verification of the closure claim

Before trusting either branch, the Week 10 fixture list was re-read from the official page on 2026-11-18:

* **Source:** <https://www.nfl.com/schedules/2026/by-week/week-10> (read 2026-11-18, chunks 0-1 of 2)
* **14 fixtures, all printed `Final`,** scores identical to the transcription in PR #84's pack:
  WAS 24–NYG 21 · NE 10–DET 35 · KC 35–ATL 13 · HOU 24–CLE 27 · MIN 30–GB 10 · MIA 22–IND 24 ·
  CAR 20–NO 17 · BUF 31–NYJ 12 · JAX 40–TEN 23 · LA 34–AZ 6 · SEA 21–LV 13 · SF 46–DAL 40 ·
  PIT 18–CIN 38 · LAC 23–BAL 20
* **Byes printed by the same page:** CHI, DEN, PHI, TB — 14 fixtures + 4 byes = 32 clubs, each once.

This is a third independent read of that page (two sessions transcribed it on 2026-11-17; this one on
2026-11-18). All three agree.

## 3. Defects found, and how each was fixed

### 3.1 The feed's own meta file described a superseded window (fixed)

`data/results/results_feed_meta.json` was generated 2026-11-14 by
`tools/build_results_feed_all_seasons.py`, which read only the 2026-11-14 evidence files and validated
against the 2026-11-14 standings. It reported `official_verified: 1`, `scheduled: 135`. The CSV beside it
held 14 official-verified rows. No gate compared the two, so the discrepancy shipped.

**Fix at the generator, not in the file.** That builder now also reads the dated 2026-11-17 pack and:

| Check | What it proves | Result |
|---|---|---|
| C1 | All 14 Week 10 finals in the dated pack equal the mirror's score for the same club pair | pass, 14/14 |
| C2 | The two official reads of Week 10 agree wherever both printed a score | pass, 1 fixture final in both; 13 final only on the later read, each named |
| C3 | Mirror arithmetic (scores sum to total; result = home − away) | pass |
| C4 | W-L-T recomputed from the feed reproduces the **2026-11-17** standings baseline | pass, 32/32 |
| C5 | The 2026-11-14 baseline vs today's feed | informational, 26 of 32 clubs differ — expected, that read predates the week's games |

The 2026-11-14 read is **kept**, not overwritten: it is a dated artefact and the delta between it and the
later read is evidence. The feed now reports `official_verified: 14`, `final: 2110`.

### 3.2 Check I3 measured a delta against a moving target (fixed)

`tools/verify_2026_11_17.py` check I3 publishes "the dated delta: published table (2026-11-14) vs official
page (2026-11-17)", but it read `data/nfl/injuries_week10.tsv` — the **live** table. The collector had
already republished that table at 347 rows, so on a fresh run the delta collapsed to `published_rows: 347,
rows_added: 0, cells_changed: 0`. The finding it exists to publish — 345 → 347 rows, 32 cells changed —
had disappeared from the record *because the defect had been fixed*, which is the one way a verification
artefact must never behave.

**Fix:** the 2026-11-14 transcription is now frozen at
`data/nfl/injuries_week10_2026_11_14.tsv`, extracted byte-for-byte from commit `ad1add5` (the commit that
published it). I3 measures the delta against that file and reports the live table's row count separately.
The finding is restored: **345 → 347 rows, 2 added, 0 removed, 32 cells changed**.

### 3.3 Two branches assigned the same flag ids to different findings (fixed)

PR #84 and `main` both defined `F-22`…`F-25`, with completely unrelated content:

| id | `main` (merged first) | PR #84 |
|---|---|---|
| F-22 | Week 10 injury table stale: 345 → 347 rows | mirror bytes moved between two fetches 21 min apart |
| F-23 | Week 10 standings stale: 130 fields, 26 clubs | two reads of one page printed different column sets |
| F-24 | no Week 11 injury report exists yet | ROI still describes a 137-game window |
| F-25 | one fetch contradicted its immediate repeat | a self-referencing console artefact |

Silently keeping one side would have deleted five published findings. **Fix:** `main`'s numbering stands
(it merged first); PR #84's five items keep their content byte-identically under `F-27`…`F-31`, and each
carries a `renumbered_on_integration` field naming what happened. The Flagged page renders from
`data/flags.json`, so the renumbering reaches the site without a hand-edited page.

### 3.4 Two sessions transcribed the same pages into the same paths (resolved by precedent)

Round 5 hit this exact collision and set the rule: `main`'s file keeps the canonical name, the other keeps
its own bytes under a session suffix, and a checker proves the two independent reads agree. Applied here:

* `official_standings_2026_11_17_473e08d5.tsv`, `official_w10_results_2026_11_17_473e08d5.tsv`, and the
  derived closure files carry the suffix; `main`'s files are byte-identical to what `main` already had.
* **New check** `tools/verify_2026_11_17_473e08d5.py`: **384 standings cells** (32 clubs × 12
  legend-defined columns) and **98 Week 10 cells** (14 fixtures × 7 fields), **0 mismatches**. The only
  difference is the club label `LA`/`ARZ` vs `LAR`/`AZ`, matched by alias and reported, never normalised
  away silently.

### 3.5 A merge artifact silently pointed two pages at the same data (fixed)

Both branches added module-level globals to `tools/build_site.py` with the same names (`PACK17`, `PROMO17`,
`W10_17`, `STAND17`). After the merge the closure page's assignment overwrote the verification page's, so
the verification page read the **closure** pack and died on `KeyError: 'counts'` — the build failed loudly,
which is the right outcome, but the fix is namespacing rather than picking a side. The closure page's
globals are now `CLOSE*`; the verification page keeps its own.

### 3.6 Two round-5 gates were pinned to the pre-closure corpus (fixed, derived not loosened)

`tools/verify_2026_11_17_dc96bc33.py` asserted `len(reads) == 137` and "exactly 13 Week 10 finals are
**not** in the log". Both were true before the promotion and both inverted when the 13 finals were promoted
into `data/results/_raw/reads.tsv`:

* the log is now 150 rows, and the 137 was really **136 games closed through Week 9 + the one Week 10
  Thursday game** already promoted, plus 14 fixtures = 150;
* the "13 added" is now **0 added, 14 present**.

Both expectations are now **derived and named** — `CLOSED_THROUGH_WEEK9 + WEEK10_FIXTURES`, and an
explicit pre/post-promotion state — rather than retyped to whatever makes the gate green. Deriving them
is what exposed the 136-versus-137 distinction.

## 4. Week 11: verified against PR-04 rather than duplicated

The next kickoff is **2026-11-19 8:15 PM ET** (IND@HOU, PRIME). Week 11 origination is already
pre-registered as **PR-04** (`docs/preregistration/PR-04-week11-escrow.md`, built by session
`arena-9d8c298c-x1`, rule frozen 2026-11-17). Building a second one would duplicate another session's
registered rule, so this round **verified** it instead:

| Verification | Method | Result |
|---|---|---|
| Slate completeness | 13 fixtures re-read from the official Week 11 page on 2026-11-18 vs the 13 in `data/lab/escrow/week11_forecasts_2026-11-17.csv` | identical (only the `AZ`/`ARI` label alias differs) |
| Bye accounting | 26 clubs playing + 6 byes (ATL, CLE, GB, LA, NE, SEA) | 32, no overlap |
| Model arithmetic | ratings, home edge and probability recomputed from the 150-game official corpus with PR-01's frozen `K=2.0, H=1.6, SIGMA=13.5` | **13/13 fixtures exact**, 0 mismatches on fair line and probability |
| Rest days | each club's last game (2026 schedule dates) to its own kickoff | **26/26 correct** |
| Pre-kickoff ordering | record stamped `2026-11-17T22:50:00Z`, first kickoff `2026-11-20T01:15:00Z` | ordering holds |

**One documentation defect fixed:** the `rest` lambda in `tools/lab/build_escrow.py` subtracts a UTC
kickoff date from a schedule date with no statement of which frame is intended, so a reader cannot tell
whether a 8:15 PM ET Monday kickoff (01:15Z Tuesday) counts as one day more. The behaviour is correct and
verified; a comment now states the frame. The rule text is untouched, so PR-04's hash still matches.

## 5. Week 11 injury report does not exist yet (confirmed independently)

`https://www.nfl.com/injuries/league/2026/reg11` re-read on 2026-11-18 still resolves to the **Week 10**
report: the page's own heading reads "Injuries - WEEK 10", its first card is WAS–NYG on THURSDAY,
NOVEMBER 12TH, and the week selector lists WEEK 1…WEEK 11 with WEEK 11 not selected. Flag F-24 already
records this from 2026-11-17; this is a second dated read confirming it is still true, and it means **no
Week 11 practice or game designation can be published today**. It is left blank.

## 6. What remains unverified, and what would clear it

| Item | State | What would clear it |
|---|---|---|
| Official price / closing line | **none exists** for 2026 in this repo; `market_line` and `residual` stay blank on all 84 price records and all 52 escrow rows | a licensed feed, or an owner decision to accept a named third-party source (Q-02) |
| Week 11 availability | not printed by the league yet (confirmed above) | the first capture where the selector selects WEEK 11 |
| Venue per fixture | the weekly schedule page prints no venue field (F-31) | one Game Center read per fixture |
| Snap counts / inactive lists | not captured anywhere in the repo | an official source; depth is still not modelled from playing time |
| Houston depth chart | published as an image; deliberately not transcribed | an authorised structured source |

## 7. Gates run this round

All pass on the merged tree: `scripts/verify_site.py` (175 pages), `scripts/check_site.py`,
`scripts/verify_research_site.py`, `tools/check_links.py` (176 files, 47,014 assertions),
`tools/verify_app.py`, `tools/verify_data.py`, `tools/verify_against_official.py`,
`tools/build_state_audit.py --check`, `tools/build_preregistration.py --check`,
`tools/verify_2026_11_16.py --check`, `tools/verify_2026_11_17.py --check`,
`tools/verify_2026_11_17_dc96bc33.py --check`, `tools/verify_2026_11_17_473e08d5.py`,
`tools/promote_week10_2026_11_17.py --check`, `tools/build_results_r3.py --check`,
`tools/build_snapshots.py --check`, `tools/build_origination.py --check`, `tools/build_round3.py --check`,
`tools/build_shadow_baseline.py --check`, `tools/build_next_decisions.py --check`,
`tools/verify_results_feed.py`, `tools/verify_stores.py`, `tools/verify_brief_coverage.py`.
