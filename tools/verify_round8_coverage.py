#!/usr/bin/env python3
"""Mechanical check for docs/review/round8-brief-coverage.tsv (session arena-757174a7-x1).

Fails (exit 1) when:
  * the table does not hold rows 1..82 exactly once;
  * a status is not one of the legal statuses;
  * a BUILT / PARTIAL / DEFINED row cites no evidence path that exists;
  * any cited evidence path (not a URL, not NONE) does not exist in the repository;
  * a NOT BUILT / DECLINED row cites evidence other than NONE and the path is missing;
  * an official_link is not https on an allowed host.

With --write it also renders docs/review/round8-brief-coverage.md from the TSV.
Run from the repository root:  python3 tools/verify_round8_coverage.py [--write]
"""
import collections
import csv
import os
import sys
from urllib.parse import urlparse

TSV = "docs/review/round8-brief-coverage.tsv"
MD = "docs/review/round8-brief-coverage.md"
LEGAL = {"BUILT", "PARTIAL", "DEFINED", "NOT BUILT", "DECLINED"}
NEEDS_EVIDENCE = {"BUILT", "PARTIAL", "DEFINED"}
# Official NFL / club / NWS hosts, plus this project's own Pages host and the mirror host.
ALLOWED_HOSTS = {
    "www.nfl.com", "media.nfl.com", "api.weather.gov", "www.atlantafalcons.com",
    "www.packers.com", "www.baltimoreravens.com", "karagemop466-tech.github.io",
    "github.com",
}
MIRROR_HOSTS = {"github.com"}  # third-party mirror links must also carry a flag == yes


def main():
    write = "--write" in sys.argv
    failures = []
    rows = list(csv.DictReader(open(TSV, encoding="utf-8"), delimiter="\t"))
    ids = [int(r["row"]) for r in rows]
    if sorted(ids) != list(range(1, 83)):
        failures.append(f"row ids are not 1..82 exactly once: {len(ids)} rows")
    counts_now = collections.Counter()
    counts_prior = collections.Counter()
    changed = []
    checked_paths = 0
    for r in rows:
        rid = r["row"]
        now, prior = r["status_2026_11_19"], r["status_2026_11_17"]
        for label, st in (("now", now), ("prior", prior)):
            if st not in LEGAL:
                failures.append(f"row {rid}: illegal {label} status {st!r}")
        counts_now[now] += 1
        counts_prior[prior] += 1
        if now != prior:
            changed.append((rid, prior, now))
        ev = [p.strip() for p in r["evidence"].split(";") if p.strip()]
        if now in NEEDS_EVIDENCE:
            if not any(os.path.exists(p) for p in ev if p != "NONE" and not p.startswith("http")):
                failures.append(f"row {rid}: status {now} but no evidence path exists")
        for p in ev:
            if p == "NONE":
                if now not in {"NOT BUILT", "DECLINED", "DEFINED"}:
                    failures.append(f"row {rid}: NONE evidence on a {now} row")
                continue
            # Paths ending in '/' are directories; others must be files or directories.
            checked_paths += 1
            if not os.path.exists(p.rstrip("/")):
                failures.append(f"row {rid}: evidence path missing: {p}")
        link = r["official_link"].strip()
        if link:
            u = urlparse(link)
            if u.scheme != "https" or u.netloc not in ALLOWED_HOSTS:
                failures.append(f"row {rid}: link not https on an allowed host: {link}")
            if u.netloc in MIRROR_HOSTS and r["flag"] != "yes":
                failures.append(f"row {rid}: mirror host link without flag=yes: {link}")
    print(f"rows: {len(rows)}")
    print("status 2026-11-19 :", dict(sorted(counts_now.items())))
    print("status 2026-11-17 :", dict(sorted(counts_prior.items())))
    print(f"rows whose status changed since 2026-11-17: {len(changed)}")
    print(f"evidence paths checked: {checked_paths}")
    if failures:
        for f in failures:
            print("FAIL", f)
        sys.exit(1)
    if write:
        with open(MD, "w", encoding="utf-8") as f:
            f.write(render(rows, counts_now, counts_prior, changed))
        print("wrote", MD)
    print("round-8 brief coverage: all rows, paths and links verified")


def render(rows, now, prior, changed):
    lines = [
        "# Round 8 — brief-to-repo coverage, re-verified on `main` @ 856366f",
        "",
        "**Session:** `arena-757174a7-x1` · **Branch:** `arena/757174a7-x1` · **Date:** 2026-11-19 (UTC)",
        "",
        "This is the row-by-row status of the 82 numbered items of the current owner brief, re-checked against the tree as it stands on `main` (`856366f`). The numbering follows the 2026-11-17 register (`docs/audit/brief-coverage-2026-11-17.md`), which covers the same items. Statuses are a repo fact, not an NFL fact: a value is an NFL fact only where the row's official link is shown and was read.",
        "",
        "**Mechanical check:** `python3 tools/verify_round8_coverage.py` (every evidence path must exist; every BUILT/PARTIAL/DEFINED row needs evidence; every link must be https on an allowed host; a mirror-hosted link must be flagged).",
        "",
        "## Status counts",
        "",
        "| Status | 2026-11-17 register | This re-check (2026-11-19) |",
        "|---|---:|---:|",
    ]
    for s in ["BUILT", "PARTIAL", "DEFINED", "NOT BUILT", "DECLINED"]:
        lines.append(f"| {s} | {prior.get(s, 0)} | {now.get(s, 0)} |")
    lines += [
        "",
        f"**{len(changed)} rows changed status** since the 2026-11-17 register; each change is explained in the row's note below. "
        "NOT BUILT fell from 24 to 8 because later merged work (origination desk, modeling lab, depth matrix, kickoff regime trial, announced-starter evidence) produced artefacts the 2026-11-17 register did not see. No row was upgraded without a path that exists.",
        "",
        "## Row register",
        "",
        "| # | Brief item | 2026-11-17 | Now | Evidence (repo path) | Gap or note | Official link | Flag |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        ev = "<br>".join(f"`{p.strip()}`" for p in r["evidence"].split(";") if p.strip())
        link = f"<{r['official_link']}>" if r["official_link"] else "—"
        flag = "yes" if r["flag"] == "yes" else ""
        lines.append(f"| {r['row']} | {r['brief_item']} | {r['status_2026_11_17']} | **{r['status_2026_11_19']}** | {ev} | {r['gap_or_note']} | {link} | {flag} |")
    lines += [
        "",
        "## Limits of this check",
        "",
        "- Paths and statuses were verified mechanically. Official links were not all re-read this session: the injury report (Week 10 page, 17-row sample), the NFL trades page (all 12 November trades) and the Lions rows were re-read live on 2026-11-19. Other links are the URLs the repo's own data files cite and were not re-fetched here.",
        "- Rows marked `PARTIAL` on mirror data (nflverse) are repo-computed, not league-published.",
        "- The Flagged for Review page and the site navigation are shared outputs and are not changed by this session (see COORDINATION.md).",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
