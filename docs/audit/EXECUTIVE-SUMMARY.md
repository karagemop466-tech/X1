# Executive summary — session `arena/9cc1eaac-x1`

**Snapshot:** 2026-11-14 · **NFL season 2026, Week 10** · **Branch:** `arena/9cc1eaac-x1`
**Live site:** <https://karagemop466-tech.github.io/X1/>
**This round's brief page:** `pages/executive-brief.html`

---

## 1. Headline

Every published Week 10 value is correct. **2,183 cells were diffed cell by cell against a fresh
independent transcription of the official NFL pages: 0 mismatches, 4 of 4 tables clean.**

The problems this round found are therefore *not wrong numbers*. They are three things that make a
correct table misleading:

| What was wrong | Why it mattered | State |
|---|---|---|
| A **five-club** depth pilot was reported as the count of starters ruled out | It is a floor, not a total. The real number across the 31 clubs already in the repository is **31**, not **6** | fixed |
| The **live-pipeline tree (15 pages)** was linked from nothing | Reachable only by typing the URL; the reachability check skipped the tree | fixed |
| `tools/check_links.py` **failed with 111 errors on `main`** | The `verify-site` workflow had been red for 13 hours | fixed |

---

## 2. What was verified, and how

A third transcription of the official pages was made in this session
(`audit/official_snapshot_2026_w10.py`) and diffed against every published table by
`tools/verify_against_official.py`. This is deliberately *not* a comparison of two files written by
the same sessions — `tools/cross_check.py` already does that, and it cannot catch a shared misread.

| Table | Rows | Cells compared | Mismatches | Official source |
|---|---|---|---|---|
| Standings | 32 | 384 | **0** | <https://www.nfl.com/standings/division/2026/REG> |
| Week 10 schedule | 14 | 70 | **0** | <https://www.nfl.com/schedules/2026/REG/week/10/> |
| Week 10 byes | 4 | 4 | **0** | same schedule page |
| Week 10 injury report | 345 | 1,725 | **0** | <https://www.nfl.com/injuries/league/2026/reg10> |
| **Total** | | **2,183** | **0** | |

Two notes a reviewer should see rather than discover:

- The official standings page prints **`LA`** for the Rams; `data/nfl/standings.tsv` prints **`LAR`**.
  Both spellings are printed by an official page, so no value is wrong — but a join that ignores the
  alias silently drops the Rams. Recorded as **A-08**.
- The standings page prints **LAST 5** for all 32 clubs. The published file carries the column
  header and **no values**. That is available-but-unpublished, not wrong, so it is reported
  separately from a mismatch. Recorded as **A-09**.

**This closes flag I-17**, which recorded that 301 of 345 injury rows had never been re-checked by a
second reader. All 345 are now verified.

---

## 3. The finding that changes a decision

The repository contains **1,813 club-depth-chart entries across 31 of 32 clubs**
(`data/pipeline/depth_charts.json`, every row linking its own club page). The site's injury page
used a **five-club pilot** of that same data.

Running the identical join across the full collection:

| Measure | Five-club pilot | Full 31-club join |
|---|---|---|
| Clubs covered | 5 | **31** (Houston excluded: its chart page returns no parsable table) |
| Injured players joined | — | 255 of 345 |
| Players first-listed at their position | 35 | **162** |
| **First-listed players ruled Out** | **6** | **31** |
| Depth 2–4 players Out or Doubtful | — | 17 |

Neither number is false. The pilot is a **floor presented as a total**, and a decision taken on "6
starters out" would be a decision taken on roughly a fifth of the evidence. The full join is now
published on `pages/availability.html` with the pilot kept beneath it as a labelled subset.

**The decision this needs (Q-19):** should the full join be the permanent presentation? The
recommendation, its cost and how to reverse it are on the suggestions board as **B-01**. It needs one
line from you, not a build.

---

## 4. What is still not known, and why it matters

Seven questions block a defensible decision. Three are P0:

1. **Q-19 — evidence window.** Five clubs or thirty-one? (Above.)
2. **Q-02 — which line is the benchmark.** Four site trees currently measure results against three
   different references, so their ROIs are not comparable with each other. No leaderboard can rank
   strategies measured with different rulers.
3. **Q-05 — what counts as a starter.** The league publishes no depth chart. Every "2nd-string"
   claim rests on a definition the owner has to accept, because clubs label their own charts
   *unofficial* — Detroit and Green Bay print the word.

Two more matter for anything that pays out: **Q-20** (reward rules and legality — no money should
move before this is written and checked) and **Q-21** (there is no market prop price anywhere in
the repository, so no prop strategy can be priced).

The remaining open items — 38 in total — are in one table on `pages/review-queue.html`, each with a
source link. Previously four documents carried four different flag counts (6, 12, 17, 34).

---

## 5. The honest state of the strategy work

- **One of sixteen** pre-registered strategies passes all eight validation gates out of sample.
- That one is measured against a **third-party closing line carried in a community mirror**
  (`nflverse/nfldata`), not a league feed — the league publishes no prices. It is therefore
  conditional on the benchmark being acceptable, which is exactly Q-02.
- The originated-line model **underperforms** the market benchmark on spread error
  (MAE 10.42 vs 9.73 over 2021–2026). It is published as a screen, not a pricing model.
- **No reward can be paid**, because the reward rules do not exist and their legality has not been
  checked.

None of that is a reason to stop. It is the reason the gates exist: a project that cannot say
"fifteen of sixteen failed" is not measuring anything.

---

## 6. Requirements

All **45** requirements in the brief are assessed on `pages/requirements.html` against something
that can be opened and checked: **34 met, 7 partly met, 2 open, 2 in progress.**

**4 requirements were reassessed downward** from the earlier register, which is the most useful
number on that page. The pattern is consistent: a capability exists as a documented method but
cannot produce a number without a licensed feed, and the earlier register recorded the method as
the requirement being met.

---

## 7. What to do next, in order

| Order | Action | Why this order | Cost |
|---|---|---|---|
| 1 | Accept or reject **B-01** (publish the full join) | Already built and verified; changes a reported number from a floor to a count | one line |
| 2 | Accept **B-02** (run the official-diff in CI) | One workflow step stops a bad read from ever shipping again | one line |
| 3 | Choose the benchmark for **Q-02** | Until then no leaderboard result means anything | a decision |
| 4 | Write the reward rules (**Q-20**) before anything pays out | The only failure mode here that cannot be undone | legal advice |

Everything else on the suggestions board is cheaper to defer than to do.

---

## 8. Irregularities published for review

Ten findings are on `pages/executive-brief.html`; all 38 open items are on
`pages/review-queue.html`. Four are worth your attention specifically:

- **A-05** — four registers produced four different counts of "flagged items". Now one queue.
- **A-06** — the landing page claimed the repository publishes no computed values. Four trees
  publish them. The wording was true of one tree and false of the whole.
- **A-07** — the same number appears with a different level of caveat depending on which tree you
  open. Fixing it needs the badge decision (**B-07**).
- **A-09** — a column header with no values in it.

None of these blocks publication. All of them are visible.

---

*Every claim above is reproducible: `python3 tools/verify_against_official.py`,
`python3 tools/build_audit_registers.py`, `python3 tools/check_links.py`,
`python3 scripts/verify_site.py`. Nothing in this document is inferred; where a value is unknown it
is named as unknown.*
