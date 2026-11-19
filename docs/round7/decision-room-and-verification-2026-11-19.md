# Round 7 — the Decision Room and the 2026-11-19 live verification

Session `arena/427c1843-x1`, branched from `main` @ `6f7df25`, 2026-11-19.

This file records what the round read, what it proved, what it could not prove, and where every
number can be checked. It is written for someone who wants to audit the round rather than use it.

---

## 1. What was read, and when

All official values were read on **2026-11-19** through a page-fetch tool (the sandbox's shell
network reaches `github.com` only; `www.nfl.com` is reachable through the fetch tool). Every
transcription records its source URL on every row and its read date in the file header.

| Source | URL | What it evidenced |
|---|---|---|
| League standings | <https://www.nfl.com/standings/league/2026/REG> | 32 club records, PF/PA, home/road, division, conference, streak |
| Week 10 schedule | <https://www.nfl.com/schedules/2026/by-week/week-10> | 14 finals with scores and both printed records |
| Week 11 schedule | <https://www.nfl.com/schedules/2026/by-week/week-11> | 13 fixtures (date, time, network, records) + 6 clubs on bye |
| Week 11 injury report | <https://www.nfl.com/injuries/league/2026/reg11> | 253 rows, 24 clubs, practice + game status |
| McCord / Willis article | <https://www.nfl.com/news/dolphins-place-qb-malik-willis-groin-on-injured-reserve-kyle-mccord-in-line-for-first-start> | A named starter replacement |
| Drew Lock article | <https://www.nfl.com/news/drew-lock-no-injury-designation-seahawks-raiders> | A head coach naming the starter |
| Brissett trade article | <https://www.nfl.com/news/ravens-complete-trade-for-cardinals-jacoby-brissett-deal-terms-revealed> | A trade — **not** a starter announcement |

## 2. What the pack proves

`python3 tools/verify_2026_11_19.py` rebuilds eight checks from the committed transcriptions. All
eight pass:

| Check | What it asserts | Result |
|---|---|---|
| A1 | NET = PF−PA, PCT = (W+T/2)/GP, HOME+ROAD = W-L-T for all 32 clubs | 96 / 96 |
| A2 | League closure: ΣW = ΣL = 149, ties even (2), ΣPF = ΣPA = 6 923, ΣNET = 0, 150 games implied | pass |
| A3 | Every record printed on the Week 11 page equals the standings page read the same day | 32 / 32 |
| A4 | Today's 32 standings rows and 14 Week 10 finals equal the 2026-11-18 pack field for field | 482 / 482 |
| A5 | Week 11 covers 32 clubs exactly once (13 × 2 + 6 byes); no fixture cell blank | pass |
| A6 | Week 11 fixture identity, date, time, network unchanged vs the frozen 2026-11-17 read | 91 / 91 |
| A7 | Week 11 injury report shape: 253 rows, 24 clubs, 16 designations, no duplicate player row, every game key present on the slate | pass |
| A8 | Every announced-starter row carries a non-empty quotation, a date and an nfl.com URL, and the named player is a row on the same day's report | 3 / 3 |

`--check` fails the CI job if the committed summary stops matching a fresh build.

## 3. What the round found

### 3.1 The multiplicity correction is the decisive number

16 strategies are scored. Exactly one clears p ≤ 0.05: `S_wind_under` (n = 398, hit 57.04 %,
flat ROI +11.53 %, CI [+2.2 %, +20.7 %], p = 0.0077). Corrected for a family of 16 the bar is
**p ≤ 0.003125**, and **none** clears it. At α = 0.05 with 16 independent tests you expect
**0.80 false positives** from chance alone.

`S_wind_under`'s luck-removed ROI is *higher* than its raw ROI (+13.04 %), which is weak evidence
the edge is not a lucky-win artefact. It is still not enough. Published on `room/luck.html` with the
arithmetic printed so it can be re-derived.

### 3.2 The published standings are 104 of 192 cells out of date

The site's standings table is a faithful **2026-11-14** read and `tools/verify_against_official.py`
confirms it matches *that day*. Compared with today's official page, **104 of 192 compared cells**
(32 clubs × 6 fields) differ, affecting **26 of 32 clubs** — every Week 10 result. The table is not
wrong; it is five days old and does not say so on the table.

Published as `F-R7-01` and measured on `room/stale.html`.

### 3.3 Week 11 availability is readable now, and mostly is not a game designation

253 rows, 24 clubs, 12 of the 13 fixtures. Only **16 rows** carry a game status (9 Out, 7
Questionable) and every one belongs to **IND or HOU**, the two clubs playing tonight. The other 22
clubs have practice participation and nothing else, because that is where the league's week stands
on a Thursday. An injury *signal* cannot be built from this page alone, and no claim that it can is
published.

### 3.4 Two of the owner's three named starters clear the evidence bar; one does not

The brief said the league "does publish dated starter changes for Lock, McCord and Brissett".

* **McCord** — the article states "second-year quarterback Kyle McCord will fill in, beginning Sunday
  on the road against the Indianapolis Colts", dated to the Week 10 window. Qualifies.
* **Lock** — "Drew Lock has no injury designation and will start Sunday …, coach Mike Macdonald said
  Friday." A head coach on the record. Qualifies.
* **Brissett** — the article evidences a **trade**, not a named starter. Lamar Jackson's IR
  placement makes Brissett the presumptive starter, and that presumption is exactly what the brief's
  own rule forbids publishing as fact. **Left blank**, recorded as `F-R7-07`.

### 3.5 The Lions game-status defect the brief describes is already closed

The brief lists "Kerby Joseph, Cade Mays and D.J. Reed are published with a blank game-status cell".
In the published Week 10 table (`data/nfl/injuries_week10.tsv`) all three now read **Out**:
<https://www.nfl.com/injuries/league/2026/reg10>. The defect was real and has been corrected; it is
not re-opened here.

## 4. Defects fixed this round

| ID | Defect | Evidence | Fix |
|---|---|---|---|
| F-R7-06 | Every page's navigation printed an ampersand as its raw HTML escape sequence | 94 occurrences across 29 files; the label `Requirements &amp; status` was passed through `esc()` | Fixed at `tools/build_site.py`; `verify_output()` now fails the build on any double-escaped entity in a generated page |
| — | The landing page said "347 injury rows verified" without a date, and "Five trees" when nine are published | `index.html` | Counted and dated: "week-10 injury rows verified … snapshot 2026-11-14", heading changed to "Every tree, one evidence rule", room added |

## 5. Irregularities published, not resolved

| ID | Item | Why it is not resolved |
|---|---|---|
| F-R7-03 | The Week 11 report lists **Jaylen Waddle (WR) under DEN** | Waddle's own player page and the rest of the same read place him with MIA, and the MIA block does not list him. This may be a publisher error; the row is transcribed as printed and no value is moved between clubs. |
| F-R7-04 | The frozen 2026-11-17 Week 11 read keys the Cardinals fixture `2026_11_ARZ_KC` while printing the club `AZ` | Normalised for comparison and counted (1 alias); displayed values unchanged. |
| F-R7-05 | Eight rows print a name that differs from the player-page slug | e.g. BUF "Dee Alford" → `/players/deaundre-ford/`, SF "Dre Greenlaw" → `dre-greenlaw-x9042`. Listing them stops a join on the slug from being silently wrong. |

## 6. What was deliberately **not** published

* **No depth rank for any player.** The league publishes no league-wide depth chart, club charts are
  self-published and inconsistent, and no official snap-count feed is licensed. Depth is recorded as
  gap **M-04**, not filled in.
* **No correlation value on `room/correlation.html`.** The repository's correlation values are
  computed from a third-party line benchmark, so they cannot satisfy the "officially sourced only"
  rule for that page. They stay on the line desk, where the benchmark is named on every row.
* **No Week 11 line.** Origination for the week is covered by a registered, frozen escrow
  (`data/lab/escrow/week11_forecasts_2026-11-17.csv`); a second implementation would be a duplicate.
* **No inferred starters.** Only the two dated, quoted statements in §3.4.

## 7. Reproduction

```bash
python3 tools/verify_2026_11_19.py       # rebuild + verify all eight checks
python3 tools/verify_2026_11_19.py --check   # committed summary must match a fresh build
python3 tools/build_room.py              # regenerate room/ from repository files
python3 tools/build_room.py --check      # room/ must be current
python3 tools/build_site.py              # regenerate index.html + pages/ (fails on double-escapes)
python3 tools/check_links.py             # 193 files, 47 692 assertions, every internal link
```

Both new steps are wired into `.github/workflows/verify.yml` (append-only).
