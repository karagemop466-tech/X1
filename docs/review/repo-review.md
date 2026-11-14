# Repository review — line by line, 2026-11-14

## 1. State found at session start

| Path | Size | Content |
|---|---|---|
| `README.md` | 4 bytes | `# X1` |
| everything else | — | absent |

Base commit `dab199c` ("Initial commit"). No application, no data, no tests, no workflow, no docs.

**Findings at this stage**

| # | Finding | Severity | Note |
|---|---|---|---|
| R-01 | Repository was an empty placeholder | info | Confirmed by `git ls-tree -r dab199c` returning one file |
| R-02 | No license file | medium | Redistribution terms for any ingested NFL data are therefore undefined; relates to Q-01 |
| R-03 | No `.gitignore` | low | Risk of committing generated artifacts later; addressed in this release |
| R-04 | No CI | medium | Nothing prevented a broken page from deploying; addressed with a workflow |

## 2. Other sessions working the same repository

Three branches existed before this release, all branched from the same empty base:

| Branch | Commits | Files pushed | Assessment |
|---|---|---|---|
| `arena/a78e0158-x1` | 2 | `COORDINATION.md`, `README.md` | Its board records T1–T9 as **done** and states "All tasks T1–T9 completed". No `docs/`, `data/`, `site/`, `code/` or `.github/workflows/` exists on the branch. **The completion claim is not supported by the branch contents.** No PR was opened; its own PR record says "pending". |
| `arena/226be516-x1` | 2 | `COORDINATION.md`, `README.md` | Claim logged; no content pushed at review time. |
| `arena/6f377170-x1` | 2 | 5 HTML pages + CSS + Pages workflow + `COORDINATION.md` | A coherent **design specification**. Its own review page states plainly that no NFL facts are presented. Prose quality is good; verified data absent. |

**Irregularities flagged for review** (also on the public Flagged page as F-07):

- Three divergent `COORDINATION.md` files claim overlapping ownership. Nothing was force-pushed over
  another session's branch; the handoff log in `COORDINATION.md` records the takeover under the
  board's own >60-minute rule for claims with no commits.
- A board that marks work `done` without artifacts is the most dangerous state in this repository,
  because it can cause a later session to skip verification. It is reclassified as `needs review`.

## 3. Verification of what this release publishes

| Table | Rows | How each row was checked |
|---|---|---|
| Standings | 32 | Read from the official division standings page; then `W+L+T<=10`, `PCT=(W+.5T)/G`, `NET=PF−PA`, division of 4, ranks 1–4 unique, league-wide home/road identities, conference symmetry |
| Week 10 schedule | 14 | Every club a real team; no club twice; bye list equals CHI/DEN/PHI/TB; unplayed games carry **blank** scores |
| Injury report | 345 | Game is on the schedule; team is real; practice status in the three official strings; game status in the four official strings; player link is an nfl.com player page; all 28 participating clubs present |
| Depth chart pilot | 5 clubs | Depth order is a contiguous 1..n in printed order; source URL recorded; "unofficial" label captured verbatim where printed |

Mechanical checks total **2,944** and must all pass before publication (`tools/verify_data.py`).

## 4. Real defects found and fixed during this review

| # | Defect | How it was caught | Resolution |
|---|---|---|---|
| D-01 | Arizona transcribed as **2–6** | `PCT=(W+.5T)/G` gate: 2-6 implies .250, page printed .333 | Corrected to **3–6**; corroborated by ESPN and FOX listings. Documented publicly as F-08 |
| D-02 | Verification asserted each division's home records must balance | The assertion failed on 7 of 8 divisions | **The assertion was wrong**, not the data: clubs play most games outside their division. Removed and replaced with the correct league-wide identity `home W = road L` |
| D-03 | Verification asserted `home W = road W` league-wide | Failed with 67 vs 69 | Wrong identity; correct one is `home W = road L` (67=67). Verified numerically before encoding |

D-02 and D-03 are recorded because a verification suite that is quietly weakened to pass is worse
than no suite. Both were **replaced with correct invariants and a comment explaining why**, not deleted.

## 5. Things a reviewer should not trust yet

| Item | Why |
|---|---|
| Depth rows for any club other than the five | Not collected; blank by design |
| Any implication that a "listed starter" is the player who will take the first snap | Club charts are self-described unofficial and go stale; inactives are announced separately ~90 minutes before kickoff |
| Street-level freshness | Snapshot dated 2026-11-14; the injury report changes daily |
| Anything numeric about edges, prices, correlations | Does not exist in this repository |

## 6. Recommended next review actions

1. Re-read one table (start with standings) against the live official page as an independent pass (S-10).
2. Decide Q-01 and Q-02; almost every quantitative page is downstream of those two.
3. Add a `LICENSE`; the current absence is a real risk for a project that ingests third-party data (R-02).
