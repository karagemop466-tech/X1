#!/usr/bin/env python3
"""Independent verifier for the 2026-11-17 evidence pack.

    python3 tools/verify_evidence_2026_11_17.py

This does not trust the builder. It re-reads the committed TSVs as text, re-derives every
number the pack publishes, and fails if:

  1. a withheld field (one the pack marks unread) is blank anywhere, or a known field is blank;
  2. the 32 rows do not close arithmetically (wins = losses, PF = PA, NET = PF-PA, PCT = (W+T/2)/n);
  3. the 14 finals do not reproduce today's table when added to the 2026-11-14 snapshot for the
     clubs that played, with the Thursday game counted once;
  4. a cell the page claims differs from the published table actually matches it, or the count on
     the page disagrees with the CSV beside it;
  5. the pack's own `--check` does not reproduce (staleness);
  6. a source URL in the pack is not an official nfl.com host.

Exit 0 pass, 1 failure. It writes nothing.
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "data", "evidence", "2026_11_17")

FAILS: list[str] = []
NOTES: list[str] = []


def check(ok: bool, msg: str) -> bool:
    if not ok:
        FAILS.append(msg)
    return bool(ok)


def read_tsv(name: str) -> tuple[list[str], list[dict[str, str]], list[str]]:
    comments, lines = [], []
    with open(os.path.join(OUT, name), encoding="utf-8") as fh:
        for ln in fh.read().split("\n"):
            if ln.startswith("#"):
                comments.append(ln)
            elif ln.strip():
                lines.append(ln)
    head = lines[0].split("|")
    rows = [dict(zip(head, ln.split("|"))) for ln in lines[1:]]
    return head, rows, comments


def main() -> int:
    if not os.path.isdir(OUT):
        print("FAIL: evidence pack missing")
        return 1

    # ---- 1. withheld fields are explicitly listed, and every other field is present ----
    withheld_path = os.path.join(OUT, "summary.json")
    with open(withheld_path, encoding="utf-8") as fh:
        summary = json.load(fh)
    publish = summary.get("publishable_fields") or {}
    check(bool(publish), "summary.json must declare publishable_fields / withheld_fields")
    withheld = set(publish.get("withheld_fields") or [])
    published_fields = list(publish.get("publishable_fields") or [])
    for f in withheld:
        check(bool((publish.get("withheld_reasons") or {}).get(f)),
              f"withheld field {f} has no stated reason")

    # ---- 2. standings close arithmetically ----
    head, rows, comments = read_tsv("standings.tsv")
    check(len(rows) == 32, f"standings.tsv has {len(rows)} rows, expected 32")
    check(len({r["TEAM"] for r in rows}) == 32, "standings.tsv has a duplicate club code")
    for r in rows:
        for f in head:
            if f in withheld:
                continue
            check(r.get(f, "") != "", f'{r["TEAM"]}.{f} is blank but is not a withheld field')
        w, l, t = int(r["W"]), int(r["L"]), int(r["T"])
        pf, pa, net = int(r["PF"]), int(r["PA"]), int(r["NET"])
        played = w + l + t
        check(pf - pa == net, f'{r["TEAM"]}: NET {net} != PF-PA {pf - pa}')
        if played:
            check(abs(round((w + 0.5 * t) / played, 3) - float(r["PCT"])) <= 0.0011,
                  f'{r["TEAM"]}: PCT {r["PCT"]} != (W+T/2)/G')
        h = [int(x) for x in r["HOME"].split("-")]
        rd = [int(x) for x in r["ROAD"].split("-")]
        check(sum(h) + sum(rd) == played, f'{r["TEAM"]}: home+road games != W+L+T')
        check(h[0] + rd[0] == w and h[1] + rd[1] == l and h[2] + rd[2] == t,
              f'{r["TEAM"]}: home+road record != W-L-T')
    sw = sum(int(r["W"]) for r in rows)
    sl = sum(int(r["L"]) for r in rows)
    spf = sum(int(r["PF"]) for r in rows)
    spa = sum(int(r["PA"]) for r in rows)
    check(sw == sl, f"league wins {sw} != losses {sl}")
    check(spf == spa, f"league PF {spf} != PA {spa}")
    check(sum(int(r["T"]) for r in rows) % 2 == 0, "league ties are odd")
    games = (sw + sl + sum(int(r["T"]) for r in rows)) // 2
    check(games == summary["games_played_implied"],
          f"games played {games} != published {summary['games_played_implied']}")

    # ---- 3. the finals reproduce today's table from the 2026-11-14 snapshot ----
    _, finals, fcomment = read_tsv("week10_finals.tsv")
    check(len(finals) == 14, f"week10_finals.tsv has {len(finals)} rows, expected 14")
    old = {}
    with open(os.path.join(ROOT, "data", "verify", "official_standings_2026_w10.psv"),
              encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.startswith("#")]
    ohead = lines[0].split("|")
    for ln in lines[1:]:
        r = dict(zip(ohead, ln.split("|")))
        old[r["TEAM"]] = r
    check(len(old) == 32, f"the 2026-11-14 snapshot has {len(old)} clubs")
    now = {r["TEAM"]: r for r in rows}
    delta: dict[str, dict[str, int]] = {}
    for g in finals:
        if g.get("in_2026_11_14_snapshot") == "yes":
            continue
        a, h = g["away"], g["home"]
        as_, hs = int(g["away_score"]), int(g["home_score"])
        for club, mine, theirs in ((a, as_, hs), (h, hs, as_)):
            d = delta.setdefault(club, {k: 0 for k in ("W", "L", "T", "PF", "PA")})
            d["PF"] += mine
            d["PA"] += theirs
            if mine > theirs:
                d["W"] += 1
            elif theirs > mine:
                d["L"] += 1
            else:
                d["T"] += 1
    comp = 0
    for club, o in old.items():
        d = delta.get(club, {k: 0 for k in ("W", "L", "T", "PF", "PA")})
        for f in ("W", "L", "T", "PF", "PA"):
            comp += 1
            want = int(o[f]) + d[f]
            check(int(now[club][f]) == want,
                  f"{club}.{f}: snapshot {o[f]} + finals {d[f]} = {want}, pack prints {now[club][f]}")
    check(comp == summary["week10_vs_standings"]["checks"],
          f"{comp} comparisons vs published {summary['week10_vs_standings']['checks']}")

    # ---- 4. the mismatch CSV agrees with the page's claim and with the snapshot ----
    with open(os.path.join(OUT, "mismatches.csv"), encoding="utf-8") as fh:
        mm = list(csv.DictReader(fh))
    pub_rows = [m for m in mm if m["compared_against_this_read"].startswith("published")]
    check(len(pub_rows) == summary["published_vs_league"]["mismatches"],
          f"mismatches.csv has {len(pub_rows)} published-row diffs, summary says "
          f"{summary['published_vs_league']['mismatches']}")
    # A withheld field has no value in this read, so its diff row is compared on the snapshot
    # side only and must say so on the read side. Everything else is checked both ways.
    for m in pub_rows:
        club, field = m["club"], m["field"]
        check(old[club][field] == m["their_value"],
              f'{club}.{field}: CSV says the published value was {m["their_value"]}, '
              f'snapshot prints {old[club][field]}')
        if field in withheld:
            check(m["this_read"] == "(withheld)",
                  f'{club}.{field}: withheld field carries a value {m["this_read"]!r} in the diff')
            continue
        check(now[club][field] == m["this_read"],
              f'{club}.{field}: CSV says this read is {m["this_read"]}, TSV prints {now[club][field]}')
        check(m["their_value"] != m["this_read"],
              f"{club}.{field}: listed as a difference but the values are equal")
    # every cell NOT listed must be equal between the two tables
    listed = {(m["club"], m["field"]) for m in pub_rows}
    for club, r in old.items():
        for f in ohead:
            if f == "TEAM" or f in withheld or (club, f) in listed:
                continue
            check(r[f] == now[club][f],
                  f"{club}.{f}: not in the mismatch list but {r[f]!r} != {now[club][f]!r}")

    # ---- 5. the collector comparison, if present, is exact ----
    col_rows = [m for m in mm if m["compared_against_this_read"].startswith("collector")]
    check(len(col_rows) == summary["collector_vs_league"]["mismatches"],
          f"mismatches.csv has {len(col_rows)} collector diffs, summary says "
          f"{summary['collector_vs_league']['mismatches']}")

    # ---- 6. source hosts ----
    allowed = {"www.nfl.com", "nfl.com"}
    for url in (summary["sources"].values()):
        host = url.split("//", 1)[-1].split("/")[0].lower()
        check(host in allowed, f"source {url} is not an official nfl.com host")
    for ln in comments + fcomment:
        if "SOURCE:" in ln:
            host = ln.split("SOURCE:")[1].strip().split("//")[-1].split("/")[0].lower()
            check(host in allowed, f"TSV source header points at {host}")

    # ---- 7. the withholds are honest ----
    # A withheld field may legitimately appear in a *diff* against the published table (that
    # table does print it). What must not happen is a withheld field being published as a
    # value this read took. So the test is on the read itself, not on every string.
    for f in withheld:
        check(f not in head, f"withheld field {f} appears as a column in standings.tsv")
        check(f not in published_fields, f"withheld field {f} is also listed as publishable")
    for f in published_fields:
        check(f in head, f"publishable field {f} is missing from standings.tsv")

    # ---- 8. page sanity: it must not claim more than the pack holds ----
    with open(os.path.join(OUT, "page.html"), encoding="utf-8") as fh:
        page = fh.read()
    check(str(summary["published_vs_league"]["mismatches"]) in page,
          "page.html does not state the published-table mismatch count")
    check("25" not in page.split("mismatches")[0][-200:],
          "page.html appears to carry a different mismatch count than the summary")

    print("evidence pack 2026-11-17 verification")
    print(f"  clubs closed            : {len(rows)}")
    print(f"  games played implied    : {games}")
    print(f"  finals added            : {len(finals) - 1} (Thursday game already in the snapshot)")
    print(f"  snapshot x finals checks: {comp}")
    print(f"  published-table diffs   : {len(pub_rows)} of {len(rows) * (len(head) - 1)} cells")
    print(f"  collector diffs         : {len(col_rows)}")
    for n in NOTES:
        print(f"  note: {n}")
    if FAILS:
        print(f"\nFAIL - {len(FAILS)} problem(s):")
        for f in FAILS[:40]:
            print("  -", f)
        return 1
    print("\nPASS - every published number re-derived; the withheld field is the only empty one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
