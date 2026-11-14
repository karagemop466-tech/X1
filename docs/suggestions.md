# Suggestions — For Review Before Implementation

Purpose: the decision-making improvement suggestions raised during this session, collected so a reviewer can **choose the best path before any change is implemented**. Nothing here is implemented; each suggestion needs a decision (approve / modify / reject) recorded in [COORDINATION.md](https://github.com/karagemop466-tech/X1/blob/main/COORDINATION.md).

## Site & decision-making improvements

| ID | Suggestion | Why it improves decisions | Effort | Status |
|---|---|---|---|---|
| SG-01 | Add a weekly "Decision Digest" page: injuries that moved impact flags, model–market deltas > 2 pts, gate status changes — one page, five-minute read | Cuts review time; prevents missing material changes between weeks | M | proposed |
| SG-02 | Flag-impact ranking on the injuries page: sort teams by weighted availability loss (QB=5, OT/EDGE/CB=3, other starters=2) instead of alphabetical | Surfaces the injuries that actually move lines first | M | proposed |
| SG-03 | Show model line vs market line **with drift history** (Mon line → Thu line → close) per game once an odds feed exists (OQ-3) | Line movement is information; static snapshots hide it | M | proposed, blocked on OQ-3 |
| SG-04 | Every strategy page shows gate status chips (passed / provisional / failed / not run) | Makes "skill vs luck" status impossible to miss | S | proposed |
| SG-05 | Brier-score calibration tracker per strategy (predicted % vs actual %) | Calibration is the clearest luck-removal signal available weekly | M | proposed |
| SG-06 | Unverified-value policy on every table: blank cells keep a "why blank" tooltip/footnote | Prevents silent guessing; keeps audit trail obvious | S | implemented (flag page + blanks) |
| SG-07 | Ledger-first betting records: every pick logged (time, line, book, rationale, strategy ID) **before** kickoff; no retroactive entries | Time-stamped pre-commitment is the core anti-luck, anti-hindsight control | M | proposed |
| SG-08 | Kill-switch rule: any strategy whose rolling 30-pick CLV < −5% or Brier drift > 0.02 is auto-suspended pending review | Limits damage from decaying edges | S | proposed |
| SG-09 | Correlation-aware parlay builder: block combos whose measured correlation exceeds the cap (proposed 0.35) until re-approved | Parlay risk concentrates through correlation, not leg count | M | proposed, blocked on prop data (OQ-4) |
| SG-10 | Second-session independent verification pass (task T8 on the board) before each weekly publish | Two independent verifications catch transcription errors like ESPN status-vs-comment mismatches | S | proposed |
| SG-11 | Automate the weekly cycle with GitHub Actions (nflverse refresh → pipeline → site) after one successful manual-vs-automated comparison | Removes transcription risk and latency | M | proposed |
| SG-12 | Publish negative results (e.g., backup-QB no-edge after bias removal) as first-class entries | Prevents re-testing dead ideas and bias toward flashy signals | S | implemented |

## Process principles this session recommends adopting

1. **No edge without CLV.** A strategy is only promoted to "validated" after beating the closing line on ≥100 logged picks (see gates).
2. **Correlation is measured, never assumed** — at game level we measured it (variance ratio 0.99); at player level it stays blocked until data exists.
3. **Blank beats wrong.** Unverifiable values stay blank and flagged.
4. **Every table row cites its source.** Verified values link to official pages; computed values link to the computing script.
5. **Weekly cadence:** data refresh → flags → model lines → picks logged pre-kickoff → scoring after close → digest.
