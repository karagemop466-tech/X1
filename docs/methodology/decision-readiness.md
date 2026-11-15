# Decision readiness — the gate, and the number that would clear it

**Requirement (owner's words, verbatim):**

> "Put a decision-readiness table on the landing page: one row per requirement, with the gate
> that blocks it and the number that would clear it"

**Built by:** `arena-73e6cbac-x1`, 2026-11-15. **Artefacts:** `data/readiness/decision_readiness.json`,
`data/readiness/decision_readiness.csv`, `pages/readiness.html`, and the table on `index.html`.
**Builder:** `tools/build_decision_readiness.py`. **Check:** `--check` (fails if the committed
register is stale). **Independent re-verification:** `tools/verify_2026_11_15.py`.

---

## 1. Why a status register was not enough

`data/pipeline/requirements.json` already carried all 53 requirements, each with a source quote and
a status sentence. That answers *"what did we say we did?"*. It does not answer the only question a
decision-maker has: **what would have to become true, and how would I know?**

The status register had three problems that a decision-readiness table has to fix:

| Problem in the status register | What the readiness register does instead |
|---|---|
| "Implemented" is a claim about work done, not about the evidence | Each row prints a **number computed at build time** from a file in this repository |
| No requirement named its blocking gate | Each row names a gate id from `data/gates.json` (G0–G8) or `data/pipeline/gates.json` (G-01…G-14) |
| The status text and the data could disagree without anyone noticing | 7 rows where they **do** disagree are printed side by side, with a note on the row |

The last point is the reason this page exists. It caught a real error on its first build — see §4.

---

## 2. The three columns, and where each value comes from

For every requirement the register publishes:

1. **The gate that blocks it.** Mapped explicitly in `GATE_FOR` in the builder — one line per
   requirement, auditable by eye. Two registers are used because the project has two: the strategy
   gauntlet (`G0`–`G8`) and the pipeline gates (`G-01`…`G-14`). A requirement with no numeric gate
   (a process or editorial step) is mapped to `—` and says so rather than inventing one.
2. **The number that would clear it.** A threshold, always numeric where a number exists, always
   traceable to the gate text or to the owner's brief. The formula that produced it is printed
   underneath it, so a reader can recompute it.
3. **The current value.** Recomputed on every build by `measure()`, which reads repository files and
   dated captures. Nothing is typed in by hand; nothing is recalled.

### The blank rule

A row whose current value cannot be computed is **left blank with the reason written out**, and the
reason is shown in the tooltip and in the full register. This follows the owner's standing rule:

> "If a value can't be confirmed from an official source, leave it blank and flag it as unverified.
> Never infer or fill in values."

21 of 53 rows are blank. None of them is silently blank: the builder **fails the build** if a blank
row has no stated reason, and fails if a numeric row has no source.

### The source-tier rule

Every row's source is classified into one of three tiers, and the tier is printed:

| Tier | Rows | Meaning |
|---|---|---|
| `official (nfl.com)` | 10 | the value is read from an official NFL page; the row links to it |
| `computed in this repository from official inputs` | 22 | computed at build time from a repository file whose own provenance that file states |
| `no numeric source required` | 21 | a process or editorial step; there is no number, and the row says so |

A computed row is **never** dressed up as an official one. Where the repository's own store is
third-party (nflverse), the underlying file says so and the note repeats it.

---

## 3. The gate mapping, in full

`GATE_FOR` maps requirement → gate. The counts per gate are published on the page. The largest
blockers by number of requirements are `G-01 Source gate` (11), `G-02 Pre-registration` (4),
`G-11 Closing line value` (4) and `G2 Skill above variance` (3).

Two mappings are worth calling out because they were **corrected during this build**:

| Requirement | First mapping | Corrected to | Why |
|---|---|---|---|
| R-09 leaderboard competition | G-14 multiple-comparisons | **G1 Sample size** | G1 sets a *different* threshold per division (singles 500, 2/3-leg 300, 3+ leg 400, props 500). The first draft applied a flat 500-bet bar to every division, which is not what the gate says. Corrected, 6 of 8 strategies meet their division's own bar. |
| R-08 useful signals | G-12 skill gate | **G2 Skill above variance** | G-12 is the pipeline-level *decision* gate; the binding arithmetic is G2's `z >= 1.96`. Measured: the largest observed z across 8 strategies is **+0.999**, so G2 is what actually blocks. |
| R-47 results feed | G-03 sample size | **G3 Calibration** | The results feed's job is to make calibration measurable, not to make the sample bigger. |

This is the value of writing the gate down: the first draft was wrong, the measurement exposed it,
and the correction is recorded here rather than quietly made.

---

## 4. What the first build caught

The first run of the builder returned `leaderboard_min_sample_gap = -2439` — a *negative* shortfall.
That is nonsense as a metric, and it was: one strategy holds 2,939 bets, comfortably above the 500
threshold, so subtracting 500 from it produces a meaningless negative "gap". The metric was wrong,
not the data.

**The correction changed the conclusion.** The site previously said no strategy has 500 bets.
The truth is that six of eight strategies clear G1 on their own division's threshold; what none of
them clears is **G2**, because the best z is +0.999 against a required 1.96. These are different
statements, and the second is the honest one.

The superseded metric was not deleted. It was replaced, and this note records what it said, so a
reviewer can see the change rather than take the final number on trust.

---

## 5. Independent re-verification, 2026-11-15

The published tables were captured 2026-11-14. This session re-read the official standings page on
2026-11-15 and diffed every published cell against a fresh transcription
(`data/verification/2026_11_15/official_standings_2026_11_15.tsv`).

**Result: 12 of 256 cells differ, across 2 of 32 clubs. The other 30 clubs are identical.**

| Club | Published (2026-11-14) | Official (2026-11-15) | Net pts |
|---|---|---|---|
| DET | 6-2-0, PF 222, PA 189, 4W | 7-2-0, PF 257, PA 199, 5W | +33 → +58 |
| NE | 5-4-0, PF 211, PA 207, 1L | 5-5-0, PF 221, PA 242, 2L | +4 → −21 |

Both differences are the one game that kicked off and finished between the two reads — the Munich
game, which the official Game Center reports as **New England 10 – Detroit 35, Final**, at
FC Bayern Munich Stadium.

The transcription is checked against its **own arithmetic** before it is used: `PCT = (W + T/2)/(W+L+T)`
and `NET PTS = PF − PA` are recomputed for all 32 rows, and the verifier exits non-zero rather than
publishing a diff from a transcription that fails its own sums.

The published table was **not** rewritten. It is a correct record of what was known before that game,
and the owner's point-in-time requirement depends on records like it staying intact. The difference is
published as flag **F-20**.

### A second hazard found while re-reading

At the same moment the page showed NE-DET as Final, it showed seven other games as *in progress with
the score reading 0-0*. A scraper that treats "a score is present" as "the game is final" would write
seven 0-0 results into the feed. Flagged as **F-21**, with the fix: settle on the page's explicit
`Final` status **and** a Game Book PDF existence check, never on the presence of a score.

---

## 6. What this page cannot tell you

- **It cannot price anything.** No row is a price.
- **It cannot confirm a starter.** The league publishes no depth chart; those rows are club
  self-reports and the clubs printing "unofficial" are named on the Flagged page.
- **It cannot settle an unfinished game.** The Week 10 injury table was re-captured on 2026-11-15 and
  16 rows differ from the 2026-11-14 capture. Both captures are dated; neither is declared wrong.
- **A green verdict is not a pass.** `gate partly met` means the measured value is non-zero, not that
  the gate is satisfied. Only `gate open` with a zero means the blocker is genuinely gone.

---

## 7. Reproducing

```bash
python3 tools/build_decision_readiness.py          # rebuild the register
python3 tools/build_decision_readiness.py --check  # fail if the committed register is stale
python3 tools/verify_2026_11_15.py                 # re-diff against the 2026-11-15 transcription
python3 tools/verify_2026_11_15.py --check         # fail if the committed diff is stale
python3 tools/build_site.py                        # regenerate index.html + pages/
python3 scripts/verify_site.py                     # the source-link rule every data row must pass
```

All five run in CI. The register cannot go stale without the build failing.

---

## 8. Sources

| Source | Used for | Tier |
|---|---|---|
| <https://www.nfl.com/standings/> | the live 2026-11-15 re-verification | official |
| <https://www.nfl.com/games/patriots-at-lions-2026-reg-10> | the Munich result behind both changed clubs | official |
| <https://www.nfl.com/schedules/2026/by-week/week-10> | the 0-0 in-progress hazard (F-21) | official |
| <https://www.nfl.com/injuries/> | injury counts, designation counts | official |
| `data/gates.json` | G0–G8 thresholds | the project's own register |
| `data/pipeline/gates.json` | G-01…G-14 thresholds and status | the project's own register |
| `data/pipeline/requirements.json` | the 53 requirements and their quotes | the project's own register |
| `docs/live-pipeline/project-brief.md` | the requirement's own wording | the owner's brief |
