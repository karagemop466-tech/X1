#!/usr/bin/env python3
"""Promote the 2026-11-17 official Week 10 read into the three transcription inputs the results feeds
read. Session arena-473e08d5-x1, closing S-22 / Q-62.

Why a generator and not a hand edit
-----------------------------------
The Week 10 finals were transcribed ONCE, by hand, from the official page, into
`data/verification/2026_11_17/official_w10_results_2026_11_17.tsv`. This tool derives every downstream
append from that one transcription, so three copies of the same number cannot disagree by typing. It is
idempotent: run it again and it writes nothing new.

What it appends (and never rewrites)
------------------------------------
  data/results/raw/official_results_2026_week10.psv      tools/build_results.py  (the N2 feed)
  data/results/_raw/reads.tsv                            tools/build_results_r3.py (the r3 feed + signal grade)
  data/verify/raw/nfl_scores_2026_official_promotions_2026_11_17.psv
                                                          tools/build_results_feed_907c.py (the settlement feed)

The PSV and the TSV gain rows; the third file is a *promotion overlay*: the original 2026-11-14 read of
`data/verify/raw/nfl_scores_2026_official.psv` stays on disk unchanged, with its thirteen Week 10 fixtures
printed as SCHEDULED and scoreless, because that is what the page said that day. The overlay carries the
score with its own read date. A backtest that joins the overlay sees what was knowable when, which is the
point-in-time property the brief asks for ("Point-in-Time Snapshot Ledger ... prevents lookahead leakage").

Read-date column
----------------
`reads.tsv` gains an eighth column, `read_at`. For the 137 rows already committed the value is
`2026-11-14`, which is the date recorded in every one of their source files (`retrieved` in the week PSVs,
`data/results/raw/week_0*.md`). For the promoted rows it is `2026-11-17`. No row's date is invented.

Nickname derivation, checked rather than assumed
------------------------------------------------
`reads.tsv` spells clubs the way the official page prints them in the result link
("Commanders at Giants"). That spelling is recovered from the fixture's own official slug, and before
anything is written the tool proves the rule on all 137 committed rows: if slug-derived nicknames do not
reproduce the existing file exactly, the tool aborts instead of appending.

Usage
  python3 tools/promote_week10_2026_11_17.py            # append (idempotent)
  python3 tools/promote_week10_2026_11_17.py --check    # fail if a re-run would change anything
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "data", "verification", "2026_11_17")
READS = os.path.join(ROOT, "data", "results", "_raw", "reads.tsv")
WEEK_PSV = os.path.join(ROOT, "data", "results", "raw", "official_results_2026_week10.psv")
SCORES_PSV = os.path.join(ROOT, "data", "verify", "raw", "nfl_scores_2026_official.psv")
PROMO_PSV = os.path.join(ROOT, "data", "verify", "raw",
                         "nfl_scores_2026_official_promotions_2026_11_17.psv")

PRIOR_READ = "2026-11-14"
THIS_READ = "2026-11-17"
# the standings page prints AZ where the fixture tables and the mirror use ARI (repo flags I-15/I-16);
# the week PSVs and reads.tsv keep the nflverse-style code, so one alias is applied on the way out.
CODE_FOR_PSV = {"AZ": "ARI"}
# The three transcription sets do not spell the two relocated clubs the same way: the Week 10 PSV writes
# LA/ARI, data/verify/raw/nfl_scores_2026_official.psv writes LAR/ARI. A join across them has to normalise
# first, or a fixture silently fails to promote. Measured, not assumed: the 2026-11-14 read printed
# 2026_10_LAR_ARI while the pack row is 2026_10_LA_ARZ, and the promotion file keys on the OLD spelling.
CANON = {"LAR": "LA", "ARZ": "ARI", "AZ": "ARI", "WSH": "WAS"}


def pair(code: str) -> str:
    return CANON.get(CODE_FOR_PSV.get(code, code), CODE_FOR_PSV.get(code, code))


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


def nick_from_slug(slug: str, side: int) -> str:
    """'commanders-at-giants-2026-reg-10' -> 'Commanders' (side 0) / 'Giants' (side 1)."""
    parts = slug.split("-")
    if len(parts) < 3 or parts[1] != "at":
        raise SystemExit(f"ABORT: game slug {slug!r} is not of the form <away>-at-<home>-...")
    return parts[2 * side].capitalize()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    pack = read_tsv(os.path.join(PACK, "official_w10_results_2026_11_17.tsv"))
    if len(pack) != 14:
        raise SystemExit(f"ABORT: the 2026-11-17 pack has {len(pack)} rows, expected 14")
    finals = [r for r in pack if r["status"] == "Final"]
    if len(finals) != 14:
        raise SystemExit(f"ABORT: {len(finals)} finals, expected 14 (a Week 10 game is not printed Final)")

    # ---- prove the nickname rule on the 137 rows already committed ------------------------------
    with open(READS, encoding="utf-8") as fh:
        existing = list(csv.DictReader(fh, delimiter="\t"))
    mismatches = []
    for r in existing:
        for side, field in ((0, "away"), (1, "home")):
            want = nick_from_slug(r["game_slug"], side)
            if want != r[field]:
                mismatches.append(f"{r['game_slug']}: file says {r[field]!r}, slug rule gives {want!r}")
    if mismatches:
        raise SystemExit("ABORT: the slug->nickname rule does not reproduce reads.tsv; refusing to append\n  "
                         + "\n  ".join(mismatches[:10]))
    print(f"nickname rule reproduces {len(existing)} committed reads.tsv rows exactly (0 exceptions)")

    # ---- the rows to add ------------------------------------------------------------------------
    new_psv = []
    for r in finals:
        away = CODE_FOR_PSV.get(r["away"], r["away"])
        home = CODE_FOR_PSV.get(r["home"], r["home"])
        gid = f"2026_10_{away}_{home}"
        slug = r["game_url"].rsplit("/", 1)[-1]
        new_psv.append({
            "week": "10", "game_id": gid, "game_date": r["date_et"], "away": away,
            "away_score": r["away_score"], "home": home, "home_score": r["home_score"],
            "status": "FINAL", "game_url": r["game_url"],
            "schedule_url": r["source_url"], "retrieved": THIS_READ,
            "_slug": slug, "_pack_game_id": r["game_id"],
        })

    # ---- 1. the week PSV -------------------------------------------------------------------------
    psv_cols = ["week", "game_id", "game_date", "away", "away_score", "home", "home_score",
                "status", "game_url", "schedule_url", "retrieved"]
    with open(WEEK_PSV, encoding="utf-8", newline="") as fh:
        psv_rows = list(csv.DictReader(fh, delimiter="|"))
    have = {r["game_id"] for r in psv_rows}
    add_psv = [r for r in new_psv if r["game_id"] not in have]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=psv_cols, delimiter="|", lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in psv_rows + add_psv:
        w.writerow(r)
    psv_text = buf.getvalue()

    # ---- 2. reads.tsv, with the read_at column ---------------------------------------------------
    reads_cols = ["week", "away", "home", "away_score", "home_score", "date", "game_slug", "read_at"]
    read_rows = []
    for r in existing:
        row = {c: r[c] for c in reads_cols if c in r}
        row["read_at"] = r.get("read_at") or PRIOR_READ
        read_rows.append(row)
    have_slugs = {r["game_slug"] for r in existing}
    add_reads = [r for r in new_psv if r["_slug"] not in have_slugs]
    for r in add_reads:
        read_rows.append({"week": "10", "away": nick_from_slug(r["_slug"], 0),
                          "home": nick_from_slug(r["_slug"], 1), "away_score": r["away_score"],
                          "home_score": r["home_score"], "date": r["game_date"],
                          "game_slug": r["_slug"], "read_at": THIS_READ})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=reads_cols, delimiter="\t", lineterminator="\n")
    w.writeheader()
    for r in read_rows:
        w.writerow(r)
    reads_text = buf.getvalue()

    # ---- 3. the promotion overlay for the settlement feed ---------------------------------------
    promo_cols = ["game_id", "pack_game_id", "away", "away_score", "home", "home_score", "gameday",
                  "status", "superseded_status", "superseded_away_score", "superseded_home_score",
                  "read_at", "prior_read_at", "game_url", "week_url"]
    with open(SCORES_PSV, encoding="utf-8") as fh:
        scores = []
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = line.split("|")
            scores.append(dict(zip(["week", "game_id", "away", "away_score", "home", "home_score",
                                    "gameday", "status", "game_url", "week_url"], p)))
    prior_open = {}
    for r in scores:
        if r["status"] == "FINAL":
            continue
        p = r["game_id"].split("_")
        prior_open[(pair(p[2]), pair(p[3]))] = r
    promo_rows = []
    for r in finals:
        away = CODE_FOR_PSV.get(r["away"], r["away"])
        home = CODE_FOR_PSV.get(r["home"], r["home"])
        gid = f"2026_10_{away}_{home}"
        p = prior_open.get((pair(r["away"]), pair(r["home"])))
        if p is None:
            continue          # already FINAL in the 2026-11-14 read (the TNF game): nothing to promote
        promo_rows.append({"game_id": p["game_id"], "pack_game_id": gid,
                           "away": away, "away_score": r["away_score"],
                           "home": home, "home_score": r["home_score"], "gameday": r["date_et"],
                           "status": "FINAL", "superseded_status": p["status"],
                           "superseded_away_score": p["away_score"], "superseded_home_score": p["home_score"],
                           "read_at": THIS_READ, "prior_read_at": PRIOR_READ,
                           "game_url": r["game_url"], "week_url": r["source_url"]})
    buf = io.StringIO()
    buf.write("# Promotion overlay - 2026-11-17 read of https://www.nfl.com/schedules/2026/by-week/week-10\n")
    buf.write("# One row per Week 10 fixture that the 2026-11-14 read of\n")
    buf.write("# data/verify/raw/nfl_scores_2026_official.psv printed as SCHEDULED. The older file is not\n")
    buf.write("# edited: it is the point-in-time record of what was knowable on 2026-11-14, when a blank\n")
    buf.write("# score was correct. This overlay carries the score with its own read date so a backtest can\n")
    buf.write("# join 'what the page printed' to 'when we read it'. Written by\n")
    buf.write("# tools/promote_week10_2026_11_17.py from data/verification/2026_11_17/; re-running it\n")
    buf.write("# reproduces this file byte for byte.\n")
    w = csv.DictWriter(buf, fieldnames=promo_cols, delimiter="|", lineterminator="\n")
    w.writeheader()
    for r in promo_rows:
        w.writerow(r)
    promo_text = buf.getvalue()

    targets = [(WEEK_PSV, psv_text), (READS, reads_text), (PROMO_PSV, promo_text)]
    changed = [(p, t) for p, t in targets if not os.path.exists(p) or open(p, encoding="utf-8").read() != t]
    if args.check:
        if changed:
            for p, _ in changed:
                print(f"STALE: {os.path.relpath(p, ROOT)} is not what the 2026-11-17 pack derives")
            return 1
        print(f"CHECK OK: {len(existing)} + {len(add_reads)} reads rows, {len(psv_rows)} + {len(add_psv)} "
              f"week-10 psv rows, {len(promo_rows)} promotion rows - the appends are exactly what the "
              f"dated pack derives")
        return 0
    for p, t in changed:
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(t)
        print(f"wrote {os.path.relpath(p, ROOT)}")
    if not changed:
        print("nothing to write - already promoted")
    print(f"week10 psv: {len(psv_rows)} -> {len(psv_rows) + len(add_psv)} rows; "
          f"reads.tsv: {len(existing)} -> {len(read_rows)} rows; promotions: {len(promo_rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
