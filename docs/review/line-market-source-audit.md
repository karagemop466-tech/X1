# Originated-lines market-source attribution audit

**Status: repository-level provenance correction published; no NFL odds source is verified here.**
Audited 2026-11-19 (UTC). The NFL Scores page was not fetched during this review; its existing link is identified only as a league score/results reference. This audit does not call mirror prices official, verify individual odds, or make any source-rights determination.

## What the code and output establish

1. `src/console/originate.py` builds each row's market side from `g["spread_line"]`, total from `g["total_line"]`, and moneyline from `g["home_moneyline"]` / `g["away_moneyline"]`. The same row assigns its provenance from `sources.get("nfldata_games")` and carries `source`, `source_url`, and `source_tier` into the generated CSV.
2. `src/console/sources.py` classifies `nfldata_games` as **`mirror`**, labels it `nflverse/nfldata games.csv`, and links to [the nflverse games.csv record](https://github.com/nflverse/nfldata/blob/master/data/games.csv). Its registry note states that the mirror does not publish a sportsbook identifier or line timestamp. The local `data/raw/nflverse/games.csv` hashes to `5a61d3121f2178ce81d43fe8894dfb666ac853f6acce20077cb4199410a4eb01`, while the registry records `60ea2f76bd2c539c3080b8efbb7863710284c9afe173b8399a1a1191bf03d5c8`. **Those hashes do not match.** The exact captured mirror version is unresolved; do not claim that this source file is fingerprint-verified. The repo itself does not establish a licensed book, quote time, or official NFL odds feed for these market values.
3. Before this correction, `tools/build_console.py` rendered the table's single Source cell with the official [NFL.com Scores](https://www.nfl.com/scores/) link and the computed model link, while omitting the market mirror link. That official scores page was not the source of the prices; the mixed source cell obscured the distinction.
4. The corrected `console/lines.html` now labels three sources separately: **market value source** (nflverse mirror), **official scores page** (results reference only), and **fair-line model** (computed). The generator fails closed if a populated market row's URL/tier does not match the mirror registry; it does not assert the hash match. Rows with no market value remain blank and show “no market value.” The unresolved hash discrepancy is linked as OD-F10.
5. The Desk's OD-F10 flag links the originator, source registry, console builder, mirror source and the NFL Scores results-reference page. It records both the prior attribution defect and the unverified capture hash.

## Verification and limits

- Rebuilt with `python3 tools/build_console.py`; the generator completed and reported 6,266 originated markets. All unrelated tracked pages/data regenerated as a side effect were restored; only the scoped `console/lines.html` output was retained, with its pre-existing navigation preserved.
- `python3 tools/verify_console.py`: 34 pages, 5,832 links, 3,323 data rows; every row sourced or explicitly marked, with no broken links.
- `python3 tools/origination_desk/build_site.py --check` passed, and `python3 tools/origination_desk/verify_desk.py` passed all 1,626 checks, including the OD-F10 source links.
- Whole-site checks passed after the changes: `tools/check_links.py` (211 files / 52,244 assertions), `scripts/verify_site.py` (211 HTML pages), and `tools/verify_deployed_tree.py` (219 assembled pages / 6,080 local links). The deployed-tree checker reported the same four pre-existing orphan pages recorded by the integration audit; no new orphans were introduced.
- No official NFL odds source was fetched or verified to validate the market prices. A link to NFL Scores does not remedy that gap. Until an authorized price source is established and evidence reviewed, treat mirror-derived market lines as third-party benchmarks only; do not treat them as official prices or publish an inferred verification status.

## Source links for manual review

- [nflverse/nfldata games.csv (mirror)](https://github.com/nflverse/nfldata/blob/master/data/games.csv)
- [NFL.com Scores (official scores/results reference, not odds)](https://www.nfl.com/scores/)
- [Repository market-line construction](https://github.com/karagemop466-tech/X1/blob/main/src/console/originate.py)
- [Repository source registry and evidence tiers](https://github.com/karagemop466-tech/X1/blob/main/src/console/sources.py)
- [Repository console page generator](https://github.com/karagemop466-tech/X1/blob/main/tools/build_console.py)
- [Published in-repository originated-lines page](../../console/lines.html)
- [Origination & Skill Desk flagged review page](../../origination-desk/decisions-flags.html)
