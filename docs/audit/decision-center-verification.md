# Decision Center — source and verification record

**Built:** 2026-11-19 (UTC) by `arena-34b79d69-x1` · **Branch:** `arena/34b79d69-x1`
**Scope:** the canonical suggestions/questions section at `/suggestions/`. This is a decision surface,
not a new NFL dataset. No value in it was recalled from memory or inferred from another value.

## Official pages re-read live (2026-11-19)

Each page below was fetched with the page-fetch tool in this session. The observation column
records only what that fetch returned. These are dated reads, **not** immutable captures: no raw
bytes or content hash were retained, and the section says so.

| ID | Official page | What the fetch printed | Flag raised | Used for |
|---|---|---|---|---|
| OR-1 | [NFL league standings 2026 REG](https://www.nfl.com/standings/league/2026/REG) | 32 club rows; Buffalo 8-1-0 first | DC-F2 (title placeholders) | DQ-01 |
| OR-2 | [NFL 2026 Week 10 schedule](https://www.nfl.com/schedules/2026/by-week/week-10) | 14 fixtures with finals, including WAS 24–NYG 21 and NE 10–DET 35; no price field | — | DQ-01, DQ-09, DQ-17, DS-02, DS-10, MI-01 |
| OR-3 | [NFL Week 10 injury report](https://www.nfl.com/injuries/league/2026/reg10) | Player / Position / Injuries / Practice Status / Game Status columns; three Detroit rows print Out | DC-F3 (title/heading week), DC-F4 (dated conflict) | DQ-03, DQ-04, DQ-07, DQ-18 |
| OR-4 | [2026 NFL Schedule Announced, 14 May 2026](https://media.nfl.com/football-information/2026/news/2026-nfl-schedule-announced) | 18-week, 272-game schedule; Week 10 NE at DET at FC Bayern Munich Stadium | — | DQ-09, DS-11, MI-09, MI-11 |
| OR-5 | [Game Center: Patriots at Lions, Week 10](https://www.nfl.com/games/patriots-at-lions-2026-reg-10) | Final 10–35; Location MUNICH; Stadium FC BAYERN MUNICH STADIUM; Game Book PDF link | DC-F5 (PDF CDN version drift) | DQ-05, DQ-16, DS-03, DS-10, MI-02, MI-04, MI-10 |

## Irregularities published, not corrected

| ID | What was found | Why it is not silently fixed |
|---|---|---|
| DC-F1 | Seven suggestion/question registers with different IDs and counts are published. | The owner has not chosen a canonical board. This section reconciles them for reading; it does not delete or overwrite any of them. |
| DC-F2 | The standings page's visible heading was `$year$ NFL $displayname$ Standings`. | A publisher-side format issue; correcting it here would misrepresent the source. |
| DC-F3 | The injury page title said Week 11 while its visible heading said Week 10. | Both strings are from the same official page at the same read; neither is discarded. |
| DC-F4 | The live injury page prints Out for Kerby Joseph, Cade Mays and D.J. Reed; the dated repository table prints blanks. | The repository table claims to be a frozen read. Amending it is a policy decision, not a transcription fix. |
| DC-F5 | The Game Book link's CDN version path changed between the 15 Nov memo and the 19 Nov read; the document UUID is unchanged. | No hashed PDF bytes were retained for either read, so a content difference cannot be ruled out. |

All five flags are non-blocking and are published on the section's Review log page. They are kept
in `data/suggestions/decision_center.json` rather than in the shared `data/flags.json`: that file
feeds several generated `flagged.html` pages owned by other scopes, and the board's rule 4 requires
a request to the integration owner instead of an unannounced edit.

## What this section deliberately does not claim

- It does not republish correlation coefficients, ROI figures, win rates or play-rate percentages
  computed from third-party mirrors as though they were official league values. Those numbers stay
  on their existing pages with their existing labels; this section points to the questions they
  cannot settle until official-only inputs exist.
- It does not assert that the NFL publishes betting lines, snap counts, an IR list, a roof table or
  an NWS forecast. None of those fields appeared in the five pages re-read here. They are recorded
  as missing inputs with source candidates, not as facts.
- It does not decide a path. All 18 suggestion rows remain `proposed — awaiting owner decision`,
  with blank Decision and Owner cells.
- It does not change any published NFL table. The only new NFL strings here are short observations
  copied from the five fetched pages and marked with their source.

## Verification performed

| Check | Result |
|---|---|
| `python3 tools/build_decision_center.py --check` | pass — all five pages reproduce byte for byte |
| `python3 tools/verify_decision_center.py` | pass — 754 assertions over 18 questions, 18 paths, 13 missing-input rows, 7 source boards, 5 flags and 5 official reads |
| `python3 scripts/verify_site.py` | pass — every `data-table` row carries an official https source link in its Source cell |
| `python3 tools/check_links.py` | pass — internal links resolve, external hosts approved, every page reachable |
| `python3 tools/verify_deployed_tree.py` | pass — the assembled upload tree has no broken links |

## How to maintain it

1. Edit `data/suggestions/decision_center.json` (or `official_reads.json` for a new dated read).
2. Run `python3 tools/build_decision_center.py`, then `tools/verify_decision_center.py --check`
   is the CI gate that catches a stale page.
3. To record a decision, fill only `decision` and `owner` on the relevant suggestion row with the
   path the owner chose and the date; rebuild. An empty cell remains visibly unverified.
