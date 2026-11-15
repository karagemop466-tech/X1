# Week 10 (2026) official NFL.com injury report — dated re-capture (session arena-ed8c600d-x1)

| Item | Value |
|---|---|
| Source | https://www.nfl.com/injuries/ (NFL.com, "Official Latest NFL Injury Report for Players - Week 10 of the 2026 Season") |
| Read on | 2026-11-15 (UTC), through the fetch tool, chunks 0–7 of 8 |
| Games / clubs / rows on page | 14 / 28 / 347 |
| Method | Transcription by the session, one line per printed row, pipe-delimited. `tools/verify_w10_recapture.py` compares it to `data/nfl/injuries_week10.tsv` by key (game, club, player). |
| Limit | Bash cannot reach nfl.com from the sandbox (TLS failure), so the raw HTTP bytes are not retained. The SHA-256 in the report is of the transcription, not the response. |

## Files

- `official_nflcom_injuries_week10_transcription.psv` — the 347 rows as read.
- `recapture_report.md` / `recapture_report.json` — the comparison (generated; do not edit by hand).

## Result

- 345 published rows vs 347 on the page. Two Ravens rows are missing from the published table (Calais Campbell, Ronnie Stanley).
- 16 rows differ on at least one of injury / practice status / game status: 15 Monday LAC@BAL rows and Arden Key (MIA@IND).
- The other 12 of 14 games match cell for cell.
- Summary counts on the page: the published page's printed counts (66 Out / 84 Questionable / 10 Doubtful / 185 no status) do not match the current page (70 / 90 / 11 / 176).

The published table is a 2026-11-14 snapshot and is labelled as one. It was not overwritten. Changing it is an integration-session decision, logged in COORDINATION.md as a flagged item.

Run: `python3 tools/verify_w10_recapture.py` (exit 1 while the published table differs from the page).
