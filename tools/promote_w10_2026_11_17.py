#!/usr/bin/env python3
"""Close the Week 10 results gap (S-22 / Q-62) — one coordinated, guarded commit.

What this does, and only this:

  1. Re-fetches the fingerprinted nflverse/nfldata `games.csv` mirror through `api.github.com`
     (the only GitHub host reachable from this sandbox), records the old and new SHA-256, and
     updates `data/raw_manifest.json`. The mirror is a CROSS-CHECK, never a published source.
  2. Appends to `data/results/_raw/reads.tsv` every Week 10 game that the newest dated official
     read prints as `Final` and that the corpus does not already hold. Rows are taken from the
     dated verification pack (`data/verification/2026_11_17/official_w10_results_2026_11_17.tsv`),
     which is itself a line-by-line transcription of https://www.nfl.com/schedules/2026/by-week/week-10.
  3. Refuses to write anything if a score it is about to append disagrees with the mirror row for
     the same fixture, or if the fixture is already in the corpus with a different score.

It does not touch the site, the registers, or any published table. After it runs, the builders
(`tools/build_results_r3.py` and friends) decide whether the corpus is admissible.

Usage:
  python3 tools/promote_w10_2026_11_17.py            # refresh mirror + extend the corpus
  python3 tools/promote_w10_2026_11_17.py --dry-run  # print exactly what would change
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READS = os.path.join(ROOT, "data", "results", "_raw", "reads.tsv")
PACK = os.path.join(ROOT, "data", "verification", "2026_11_17", "official_w10_results_2026_11_17.tsv")
MIRROR_DIR = os.path.join(ROOT, "data", "raw", "nflverse")
MIRROR = os.path.join(MIRROR_DIR, "games.csv")
MANIFEST = os.path.join(ROOT, "data", "raw_manifest.json")
MIRROR_URL = "https://api.github.com/repos/nflverse/nfldata/contents/data/games.csv"
READ_AT = "2026-11-17"
CLUB_TO_SLUG = {}          # filled from teams.csv below
# nflverse spells Arizona "ARI"; the Rams abbreviation in the 2026 mirror is "LA" (older seasons use "LAR"),
# so the lookup tries the alias table and then the alternative spelling rather than assuming one.
ABBR_ALIAS = {"AZ": "ARI"}
ALT_ABBR = {"LA": "LAR", "LAR": "LA"}


def read_tsv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


def nickname_table() -> dict:
    """Club code -> the nickname reads.tsv has always used ("Patriots", not "NE").

    Inverse of the mapping tools/build_results_r3.py applies, built from the same committed club
    list, so the appended rows are spelled the same way as the 137 rows already in the file.
    """
    back = {"SF": "49ers"}
    with open(os.path.join(ROOT, "data", "raw", "nflverse", "teams.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") == "2026" and r.get("full"):
                back[r["team"]] = r["full"].split()[-1]
    return back


def sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="reuse the fetched mirror copy in /tmp/mirror/games.csv")
    args = ap.parse_args(argv)

    # ---- 1. mirror ---------------------------------------------------------
    old_sha = sha256_file(MIRROR)
    tmp = "/tmp/mirror/games.csv"
    if not args.skip_fetch or not os.path.exists(tmp):
        req = urllib.request.Request(MIRROR_URL, headers={"Accept": "application/vnd.github.raw+json",
                                                           "User-Agent": "X1-verification"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
        os.makedirs("/tmp/mirror", exist_ok=True)
        with open(tmp, "wb") as fh:
            fh.write(body)
    new_sha = sha256_file(tmp)
    new_bytes = os.path.getsize(tmp)
    print(f"mirror games.csv  old sha256 {old_sha}")
    print(f"                  new sha256 {new_sha}  ({new_bytes} bytes)")

    # the mirror must be a superset-in-time of the old one: never accept a mirror that lost scores
    old_rows = list(csv.DictReader(open(MIRROR, encoding="utf-8")))
    new_rows = list(csv.DictReader(open(tmp, encoding="utf-8")))
    def scored(rows):
        return {r["game_id"]: (r["away_score"], r["home_score"]) for r in rows
                if r.get("season") == "2026" and r.get("game_type") == "REG" and (r.get("home_score") or "").strip()}
    s_old, s_new = scored(old_rows), scored(new_rows)
    lost = [g for g in s_old if g not in s_new]
    disagree = [g for g in s_old if g in s_new and s_old[g] != s_new[g]]
    if lost or disagree:
        raise SystemExit(f"ABORT: mirror regressed. lost={lost[:5]} disagree={disagree[:5]}")
    print(f"mirror monotonic  ok (2026 REG scored rows {len(s_old)} -> {len(s_new)}; "
          f"lost {len(lost)}, disagreed {len(disagree)})")

    # ---- 2/3. corpus -------------------------------------------------------
    existing = read_tsv(READS)
    by_slug = {r["game_slug"]: r for r in existing}
    pack = read_tsv(PACK)

    nick_for_note = nickname_table()
    mirror_by_id = {}
    for r in new_rows:
        if r.get("season") == "2026" and r.get("game_type") == "REG":
            mirror_by_id[r["game_id"]] = r

    add, notes = [], []
    for r in pack:
        if r["status"] != "Final":
            notes.append(f"{r['game_id']}: pack says {r['status']!r} -> stays out of the corpus")
            continue
        slug = r["game_url"].rstrip("/").split("/")[-1]
        if slug in by_slug:
            cur = by_slug[slug]
            if (cur["away_score"], cur["home_score"], cur["date"]) != (r["away_score"], r["home_score"], r["date_et"]):
                raise SystemExit(f"ABORT: {r['game_id']} is already in reads.tsv with a DIFFERENT score "
                                 f"({cur['away_score']}-{cur['home_score']} vs {r['away_score']}-{r['home_score']})")
            notes.append(f"{r['game_id']}: already in reads.tsv at {cur['away_score']}-{cur['home_score']} "
                         f"(read {cur.get('read_at') or '2026-11-14'}) — no double counting")
            continue
        away_abbr, home_abbr = r["away"], r["home"]
        def mid(a, h):
            return f"2026_10_{ABBR_ALIAS.get(a, a)}_{ABBR_ALIAS.get(h, h)}"
        mkeys = [mid(away_abbr, home_abbr),
                 mid(ALT_ABBR.get(away_abbr, away_abbr), home_abbr),
                 mid(away_abbr, ALT_ABBR.get(home_abbr, home_abbr))]
        m = next((mirror_by_id.get(k) for k in mkeys if mirror_by_id.get(k)), None)
        if m is None:
            raise SystemExit(f"ABORT: {r['game_id']} has no mirror row to cross-check (tried {mkeys}); "
                             f"refusing to publish a row the second source cannot be located for")
        if (m["away_score"], m["home_score"]) != (r["away_score"], r["home_score"]):
            raise SystemExit(f"ABORT: {r['game_id']} official {r['away_score']}-{r['home_score']} "
                             f"vs mirror {m['away_score']}-{m['home_score']} — a disagreement is a flag, not an append")
        if m["gameday"] != r["date_et"]:
            raise SystemExit(f"ABORT: {r['game_id']} date official {r['date_et']} vs mirror {m['gameday']}")
        nick = nickname_table()

        def nickname(abbr: str) -> str:
            # nflverse spells Arizona "ARI" and (in older seasons) the Rams "LAR"; the club code the
            # official page prints is "AZ"/"LA". Try the code, then the mirror's spelling.
            for k in (abbr, ABBR_ALIAS.get(abbr, ""), ALT_ABBR.get(abbr, "")):
                if k and k in nick:
                    return nick[k]
            raise SystemExit(f"ABORT: no nickname in the committed club list for club code {abbr!r}")

        add.append({"week": "10", "away": nickname(away_abbr), "home": nickname(home_abbr),
                    "away_score": r["away_score"], "home_score": r["home_score"],
                    "date": r["date_et"], "game_slug": slug, "read_at": READ_AT})
    print(f"rows to append    {len(add)}   (pack finals {sum(1 for r in pack if r['status']=='Final')})")
    for n in notes:
        print("   -", n)

    if not add:
        print("corpus already closed; nothing to append")

    # ---- write -------------------------------------------------------------
    header = "week\taway\thome\taway_score\thome_score\tdate\tgame_slug\tread_at"
    out_lines = [header]
    for r in existing:
        read_at = r.get("read_at") or "2026-11-14"
        out_lines.append("\t".join([r["week"], r["away"], r["home"], r["away_score"], r["home_score"],
                                    r["date"], r["game_slug"], read_at]))
    for a in add:
        out_lines.append("\t".join([a["week"], a["away"], a["home"], a["away_score"], a["home_score"],
                                     a["date"], a["game_slug"], a["read_at"]]))
    text = "\n".join(out_lines) + "\n"
    if args.dry_run:
        print(f"DRY RUN: reads.tsv would become {len(out_lines)-1} rows ({len(add)} appended)")
        return 0

    with open(READS, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"reads.tsv         {len(existing)} -> {len(out_lines)-1} rows")

    os.replace(tmp, MIRROR)
    with open(MIRROR, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    man = json.load(open(MANIFEST, encoding="utf-8"))
    for e in man:
        if e.get("name") == "games.csv":
            e["bytes"] = new_bytes
            e["sha256"] = new_sha
            e["status"] = "refreshed"
            e["retrieved_at"] = READ_AT
            e["previous_sha256"] = old_sha
            e["url"] = MIRROR_URL
            e["rows"] = len(rows)
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=2)
        fh.write("\n")
    print(f"mirror installed  {MIRROR} ({new_bytes} bytes, {len(rows)} rows) + manifest updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
