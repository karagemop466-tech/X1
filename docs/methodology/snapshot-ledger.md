# Methodology — immutable injury-report ledger (session `arena-c0461519-x1`)

**Owner requirement (brief, verbatim intent):** store every official injury-report read with its
clock time and publish the *delta*, never the *level*; capture the report daily from Wednesday to
kickoff so Questionable → Out changes and DNP → LP → FP practice trends can be seen; never let
"not listed" mean "available"; keep raw hashes so a practice designation can be replayed as it was
known.

## Why the existing pipeline is not enough

`python3 -m pipeline` (every 6 hours, `.github/workflows/data-refresh.yml`) **overwrites**
`data/pipeline/injuries.json` on each run. Before this ledger, no file in the repository kept a
second read of the official page, so a Week 10 designation could not be replayed as it was known on
Wednesday versus Saturday. The pipeline is unchanged by this session; it is a separate request
(see `COORDINATION.md`).

## What is stored

| Artefact | Path | Mutability |
|---|---|---|
| One JSON line per read | `data/ledger/injuries/ledger.jsonl` | append-only |
| Raw page bytes, gzipped (written only when the page content changes) | `data/ledger/injuries/raw/<UTC>_<sha12>.html.gz` | create-only, never rewritten |

Every ledger line carries:

| Field | Meaning |
|---|---|
| `captured_at_utc` | clock time of the read (UTC, seconds) |
| `source_url` / `final_url` | the official page requested (`https://www.nfl.com/injuries/`) and the URL after redirects |
| `http_status`, `error` | response code and any transport error |
| `bytes`, `sha256` | size and SHA-256 of the decoded page bytes (exact, for integrity) |
| `content_sha256` | SHA-256 with random UUIDs masked (used for change flags; see below) |
| `file`, `gzip_sha256` | the raw file holding those bytes and its own hash (null when the read failed) |
| `season`, `week`, `title` | read from the page's own `<title>` ("… Week N of the YYYY Season") |
| `flags` | change and conflict flags (below) |
| `prev_sha256` / `entry_sha256` | hash chain: each line commits to the line before it |
| `runner`, `tool` | GitHub Actions run id (or `local`) and the producing tool version |

### Flags

| Flag | Kind | Meaning |
|---|---|---|
| `first_capture` | info | first successful read of the ledger |
| `unchanged` | info | same week and same `content_sha256` as the previous read |
| `revised` | change | same week, different `content_sha256` — a designation, practice line or other content changed |
| `week_rollover` | change | the page now shows a different week or season |
| `http_error` | **fatal** | non-200 response or transport error |
| `empty_body` | **fatal** | fewer than 20,000 bytes returned |
| `schema_drift` | **fatal** | the page title no longer reads as an injury report with a week, or the text "Practice Status" is absent |

A fatal flag makes the scheduled run fail (the alarm). The failed read is still written as a
ledger line, so the outage is itself on the record.

### Why change detection masks UUIDs (a false positive found on live reads)

The official page embeds a fresh random UUID on every render (e.g. a carousel `data-jsonid`).
The first two live reads (ledger seq 1 and 2, 8 minutes apart) had the same length (399,862
characters) and differed in **28 characters, all inside one UUID**. A byte-level hash alone
would therefore report a change every read. Seq 2 was written with the byte-level rule and is
flagged `revised`; that line is **not** edited (the ledger is append-only), and it is a known
false positive. From seq 3 on, change flags use `content_sha256`, which masks UUIDs. A genuine
content change (for example a designation edited from Questionable to Out) still produces a new
`content_sha256` and a `revised` flag. The unit check run during the build: same page → `unchanged`;
one designation edited → `revised`; outage → `http_error`.

## Integrity checks (`python3 tools/snapshot_ledger.py verify`)

1. Every `prev_sha256` equals the previous line's `entry_sha256` (chain).
2. Every `entry_sha256` re-computes from its line (catches any edited field).
3. `seq` is contiguous.
4. Every raw file exists, its gzip hash matches, its decoded hash matches `sha256`, and its size
   matches `bytes`.

`tools/verify_stores.py` and `.github/workflows/verify.yml` run this on every push and pull request.
The mutation test used during build: changing one field of a line makes `verify` exit 1 (`entry_sha256 mismatch`).

## Schedule and storage

* Scheduled read every 4 hours UTC (`.github/workflows/injury-ledger.yml`, cron `17 */4 * * *`).
  Over a Wednesday–Sunday window that is at least one read per day, which is the brief's "daily
  from Wednesday to kickoff". Reads at the same content reuse one raw file, so storage grows with
  page **changes**, not with reads.
* Runs on a same-repository pull request read the page on the runner, verify the chain, and
  commit the result to the PR branch. Fork pull requests read and verify only.
* The **first live capture** came from a branch push, not a pull request: pull_request
  synchronize and reopen events did not start workflow runs for this branch in the build sandbox,
  so a temporary `push` trigger was added and removed again (see the irregularities in
  `COORDINATION.md`).

## What this does NOT do yet (honest limits)

* It does not parse the page into rows. The **delta** of designations (Questionable → Out, DNP → LP →
  FP) needs a parser pinned to the table's expected row count and fields. That parser is not built
  here; until it is, the ledger proves *that* the page changed and *when*, not *which* row changed.
* The sandbox used to build this cannot reach nfl.com (`curl` fails at TLS; only the fetch tool
  reaches it). The first real captures therefore come from the GitHub Actions runner, and are
  committed only after `verify` passes on the downloaded artifact.
* Week 1–9 archives are not in this ledger. The ledger starts at the first read.
* Hashes prove that the stored bytes did not change after capture. They do not prove that NFL
  published those bytes at that time; the capture time is the runner's clock.

## First capture (record)

| Item | Value |
|---|---|
| Ledger line | `seq 1`, `captured_at_utc 2026-11-15T18:21:05Z`, `http_status 200`, `bytes 399868` |
| Page title | "Official Latest NFL Injury Report for Players - Week 10 of the 2026 Season \| NFL.com" |
| Decoded SHA-256 | `fb7259efb662941c9cefbe180f5a5b7268e192604c2fdf3be75b66da4cc07d8c` |
| Raw file | `data/ledger/injuries/raw/20261115T182105Z_fb7259efb662.html.gz` |
| Captured by | GitHub Actions run `43746250190` (`runner` field), committed by `x1-bot` |
| Flags | `first_capture` (no fatal flag; "Practice Status" text present) |
| Spot-check (decoded raw vs official page) | Kerby Joseph (Knee, DNP, **Out**), Cade Mays (Ankle, DNP, **Out**), D.J. Reed (Hip, DNP, **Out**); Malik Harrison (Groin, LP, **Questionable**); Amon-Ra St. Brown (Rib, LP, **Questionable**) |

The spot-check reads the committed raw bytes; the designations match the official page as fetched
through the fetch tool at the same session. The full 345-row table is **not** parsed by this
ledger and is covered by the existing verifiers (`tools/verify_against_official.py`).

## Sources

* Official NFL injury report — https://www.nfl.com/injuries/ (the page the capture reads).
* Official NFL injury-report policy — https://www.nfl.com/news/competition-committee-approves-revisions-to-injury-report
  (cited in `pipeline/sources.py`; not re-read in this session).
