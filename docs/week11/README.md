# Week 11 official injury report: reads, deltas and freshness

Session `arena-2d1ba329-x1` (branch `arena/2d1ba329-x1`). Published as
[`app/week11.html`](../../app/week11.html).

## What it does

1. **Keeps every read.** `tools/snapshot_ledger.py` (the scheduled `injury-ledger` job) stores the
   exact bytes of the official NFL.com injury page at each run, with the UTC capture time, an
   append-only hash chain, and change flags. Nothing here replaces that store.
2. **Parses the stored bytes, never a network copy.** `tools/week11/build_week11.py` reads
   `data/ledger/injuries/raw/*.html.gz`, re-checks each file against the ledger line
   (`gzip_sha256`, exact-byte `sha256`, and the UUID-masked `content_sha256`), then parses the
   matchup strips, the club sub-titles and the club tables.
3. **Fails loudly on drift.** A table whose headers are not exactly
   `Player | Position | Injuries | Practice Status | Game Status`, a row without five cells, a
   player cell without its profile link, a name mismatch, a matchup strip without a club table, or
   an unknown practice or game-status string stops the build. Nothing is mapped or guessed.
4. **Publishes deltas, not levels.** `data/week11/deltas.tsv` lists only what changed between
   consecutive reads whose content differs: a designation, practice status, or a row or club that
   appeared or disappeared. The latest level is in `data/week11/latest_read.tsv`, one row per
   listing, with the source URL on every row.
5. **Treats absence as absence.** A club shown in a matchup strip with no table in the read is a
   coverage gap, shown as such. It is never read as healthy.

## Sources

| What | Link | Used for |
|---|---|---|
| NFL.com 2026 injury report (Week 11 page) | https://www.nfl.com/injuries/ | Every value. Title: "Official Latest NFL Injury Report for Players - Week 11 of the 2026 Season". |
| Stored raw captures (SHA-256 per file) | https://github.com/karagemop466-tech/X1/tree/main/data/ledger/injuries/raw | Byte-level evidence for each read. |
| Ledger (append-only, hash chain) | https://github.com/karagemop466-tech/X1/blob/main/data/ledger/injuries/ledger.jsonl | Capture time, hashes, flags. |
| GitHub Actions run history for the scheduled capture | https://github.com/karagemop466-tech/X1/actions/workflows/injury-ledger.yml | Evidence for the cadence observed below. |

## Results on the day of writing (2026-11-19)

- Week 11 captures in the ledger: **8 stored, 5 distinct content states** (the last one, 22:10 UTC, was added by the PR probe on this branch).
- Latest read: **2026-11-19 22:10:21 UTC**, **253 listings** in **24 clubs**. Those 24 clubs are in 12 games; the 13th game, CIN @ WAS, has no table.
- **CIN and WAS** (Monday, Nov 23 matchup) have no table in the latest read. They are listed as
  gaps. They are not treated as healthy.
- Earliest Week 11 reads (2026-11-18 07:35 and 17:18 UTC) cover only the Thursday game (IND and
  HOU). Designations for several players that later read as **Out** were **blank** in the 17:18
  read and filled in by 01:53 UTC. A blank cell is therefore "not published yet", never a clean
  bill of health.

## Verification performed

- `python3 tools/week11/build_week11.py --check` → committed outputs match the ledger.
- `python3 -m unittest tests.test_week11` → 6 tests pass. They pin the parser to the stored
  13:16 UTC capture: hashes, 26 strips, 13 games, 24 clubs with a table, 253 rows, CIN and WAS as
  gaps, a known blank-status row, and a deterministic full build.
- `python3 tools/verify_app.py` → links resolve; every data row is sourced or flagged.
- **Live cross-check (by eye, not automated).** The official page was read on 2026-11-19 at about
  21:59 UTC. For the Indianapolis (11 listings) and Houston (15 listings) tables, 25 of 26 rows
  agree with the 13:16 UTC stored read on player, position, injury, practice status and game status.
  The one difference (Charlie Heck) is confirmed by the 22:10 UTC stored read, below.
- The raw bytes of the 01:53 and 13:16 UTC reads differ only in page chrome: analytics script tags
  and a carousel identifier. The injury tables are identical. The ledger's `revised` flag therefore
  overstates change for these two reads.

## Charlie Heck: resolved as a change in the official report

- **13:16 UTC read (stored):** injury *Not injury related - personal matter*, game status *Questionable*.
- **Live page, read at about 21:59 UTC (fetch, by eye):** both cells blank.
- **22:10 UTC read (captured by the scheduled-style probe on the runner, stored and hash-checked):** both cells blank.
- The delta is published in `data/week11/deltas.tsv` (from 13:16 to 22:10 UTC).

The parser is not at fault. The report stopped printing that designation before 21:59 UTC. A blank game
status means the report prints no designation; it is **not** a clearance, and nothing here reads it as one.

## Irregularities for manual review

1. **Ledger freshness failed on `main` at the time of writing.** The last successful read was 8.7 h
   before the check (`tools/snapshot_ledger.py status --max-age-hours 6` → exit 1). GitHub's
   scheduled runs for `injury-ledger` on `main` were about 8 h and about 20 h old in the run history.
   The job is scheduled every 4 h, so the gaps suggest scheduled runs are being delayed or skipped. A manual
   `workflow_dispatch` from this session returned HTTP 403, so it could not be forced.
   Recommended action: check the Actions "schedule" settings and whether the cron is being
   dropped; consider a second independent trigger.
   Recovery seen on this branch: a pull-request probe read the page at 22:10:21 UTC and committed the
   line. The scheduled cadence itself is still unexplained.
2. **The change flag is over-sensitive.** `revised` fires on page-chrome changes. The
   field-level delta in `deltas.tsv` is the measure to use. Changing the ledger's change definition
   is a change to `tools/snapshot_ledger.py`, which belongs to the ledger owner, so it is not made here.
3. **Coverage gaps are real.** CIN and WAS have no table in the latest read. Whether the report
   omits them or they are awaiting publication cannot be told from one read. Not inferred.
4. **Week 10 tables are still the published injury tables.** `injuries.html` and the landing still
   describe Week 10. This page is Week 11 only. Replacing the Week 10 table is outside this claim.
5. **The week is fixed in code.** `WEEK = 11` in `tools/week11/build_week11.py`. The next week needs
   that constant changed; the builder does not detect the week on its own.

## What this does not claim

- No probability, forecast, model, or designation-to-play-rate estimate. Designation reliability is
  a separate, unclaimed task (see the brief's item on measuring designation reliability).
- No snap counts, inactive lists, or game-day starters. Those need a different official source
  and are not in the injury report.
- No claim about any player's participation beyond what the stored read printed.

## Reproduce

```bash
python3 tools/snapshot_ledger.py verify --dir data/ledger/injuries
python3 tools/week11/build_week11.py          # rewrites data/week11/*
python3 tools/build_app.py                    # rewrites app/ (includes app/week11.html)
python3 -m unittest tests.test_week11
```
