#!/usr/bin/env python3
"""Fixture-context features, built only from published schedule facts.

    python3 tools/official/fixture_context.py build
    python3 tools/official/fixture_context.py check      # rebuild and diff (CI staleness gate)

Owner's brief, round 6:

    "Add a fixture-context feature set built only from published schedule facts."

The rule that decides what this file is allowed to contain is that last clause. Every input is a
page the league published, read on a date, with its bytes retained somewhere in this repository:

  * the weekly slate pages (date, kickoff, network, opponent, printed record, status) as
    retained by the scheduled collector in `data/captures/payloads/week_schedule/**`;
  * the venue of each fixture as the fixture's own Game Center page printed it
    (`data/official/gamecentre/venue_register_latest.tsv`, plus the 2026-11-18 hand register for
    Week 10 at `data/nfl/venues_2026_week10.csv`);
  * the league's standings page for the record a club carried into the fixture.

What that rules out, and why it stays out: weather and roof (no official page in this repository
prints one per fixture — see the open question about the NWS overlay), player availability
(the injury ledger is a separate feature set), and any distance, elevation or time-zone number
computed from a stadium's coordinates, because the coordinates are not a published schedule fact.
Travel is therefore reported as what the two venues are called and whether the league printed the
same city, never as miles.

Deterministic: no clock reads, no randomness. Re-running reproduces the same bytes.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GC = os.path.join(ROOT, "data", "official", "gamecentre")
CAPTURES = os.path.join(ROOT, "data", "captures", "payloads", "week_schedule")
VENUES_W10 = os.path.join(ROOT, "data", "nfl", "venues_2026_week10.csv")
OUTDIR = os.path.join(ROOT, "data", "official", "fixture_context")
OUT = os.path.join(OUTDIR, "fixture_context_2026_w11.csv")

SEASON = 2026
TARGET_WEEK = 11
PRIOR_WEEK = 10

# Dated official reads already in the repository (each one a transcription of a specific page on a
# specific day, with its own provenance header). The slate read is the newer of the two Week 11
# sources, so it wins over the collector's 2026-11-16 payload; the Week 10 read supplies the prior
# fixture date for every club, which is what rest days and byes are computed from.
W11_READ = os.path.join(ROOT, "data", "lab", "reads", "2026-11-17", "week11_slate_2026-11-17.tsv")
W10_READ = os.path.join(ROOT, "data", "lab", "reads", "2026-11-17", "week10_finals.tsv")

COLUMNS = (
    "game_id", "week", "date_et", "kickoff_et", "network", "status_as_read",
    "away_abbr", "home_abbr", "away_record_slate", "home_record_slate",
    "away_rest_days", "home_rest_days", "away_short_week", "home_short_week",
    "away_bye_prior_week", "home_bye_prior_week",
    "away_prev_venue", "home_prev_venue", "venue_city_this_week", "venue_same_city_as_prev",
    "stadium", "stadium_source", "roof", "surface",
    "prime_time", "window_label", "international", "slate_source_url", "slate_read_at", "flags",
)


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def read_read_tsv(path):
    """A dated official read: `#` provenance lines, then one tab-separated table."""
    if not os.path.exists(path):
        return None, []
    with open(path, encoding="utf-8", newline="") as fh:
        body = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    rd = csv.DictReader(body, delimiter="\t")
    rows = list(rd)
    read_at = ""
    for r in rows:
        if r.get("read_at"):
            read_at = r["read_at"]
            break
    src = rows[0].get("source_url", "") if rows else ""
    return {"as_read_at": read_at, "source_url": src, "rows": rows,
            "file": os.path.relpath(path, ROOT)}, rows


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def latest_slate(week: int) -> dict | None:
    """The newest retained official weekly-slate read that carries rows for `week`."""
    best = None
    if not os.path.isdir(CAPTURES):
        return None
    for dirpath, _dirs, files in os.walk(CAPTURES):
        for f in files:
            if not f.endswith(".json"):
                continue
            path = os.path.join(dirpath, f)
            try:
                d = json.load(open(path, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            rows = [r for r in d.get("rows", []) if str(r.get("week")) == str(week)
                    or f"-reg-{week}" in (r.get("game_url") or "")]
            if not rows:
                continue
            stamp = d.get("as_read_at", "")
            if best is None or stamp > best["as_read_at"]:
                best = {"as_read_at": stamp, "source_url": rows[0].get("source_url", ""),
                        "rows": rows, "file": os.path.relpath(path, ROOT)}
    return best


def slug_of(url: str) -> str:
    """The fixture slug, with the season/week suffix removed so a slug from the slate page and a
    slug from the venue capture are the same key. The suffix carries no information the row does
    not already have: week and season are columns of both files."""
    m = re.search(r"/games/([a-z0-9\-]+)$", (url or "").rstrip("/"))
    return re.sub(r"-\d{4}-reg-\d+$", "", m.group(1)) if m else ""


def days_between(a: str, b: str):
    try:
        d1 = dt.date.fromisoformat(a)
        d2 = dt.date.fromisoformat(b)
    except (TypeError, ValueError):
        return ""
    return (d2 - d1).days


def load_venue_lookup() -> dict:
    """slug -> (stadium, location, source_url), from the retained Game Center capture and,
    for the closed week, the dated hand register. Blank when neither printed a venue."""
    look: dict[str, dict] = {}
    for r in read_tsv(os.path.join(GC, "venue_register_latest.tsv")):
        slug = re.sub(r"-\d{4}-reg-\d+$", "", r.get("slug", ""))
        if not slug:
            continue
        look[slug] = {"stadium": r.get("stadium", ""), "location": r.get("location", ""),
                      "roof": r.get("roof", ""), "surface": r.get("surface", ""),
                      "source": r.get("game_url", ""),
                      "method": r.get("venue_method", "")}
    for r in read_csv(VENUES_W10):
        slug = re.sub(r"-\d{4}-reg-\d+$", "", r.get("game_center_slug", ""))
        if slug and slug not in look:
            look[slug] = {"stadium": r.get("stadium_as_printed", ""),
                          "location": r.get("location_as_printed", ""),
                          "roof": "", "surface": "",
                          "source": r.get("game_center_url", ""), "method": "hand-read-2026-11-18"}
    return look


def club_of_slug(slug: str, pos: int) -> str:
    """The club name the league printed in the fixture URL. A string read, not a lookup: this
    project publishes the name as printed, and the abbreviation mapping lives in the slate rows."""
    parts = re.split(r"-at-", slug or "")
    if len(parts) != 2:
        return ""
    side = parts[0] if pos == 0 else parts[1]
    side = re.sub(r"-\d{4}-reg-\d+$", "", side)
    return side.replace("-", " ")


def build() -> tuple[list[dict], dict]:
    slate11, _ = read_read_tsv(W11_READ)
    slate10, _ = read_read_tsv(W10_READ)
    slate_src = {"week11": slate11 and slate11["file"], "week10": slate10 and slate10["file"]}
    if not slate11:
        slate11 = latest_slate(TARGET_WEEK)
        slate_src["week11"] = slate11 and slate11["file"]
    if not slate10:
        slate10 = latest_slate(PRIOR_WEEK)
        slate_src["week10"] = slate10 and slate10["file"]
    venues = load_venue_lookup()
    flags_summary = {"slate_11": slate_src["week11"] or "MISSING",
                     "slate_10": slate_src["week10"] or "MISSING",
                     "slate_11_read_at": (slate11 or {}).get("as_read_at", ""),
                     "slate_10_read_at": (slate10 or {}).get("as_read_at", ""),
                     "venue_lookup_rows": len(venues)}
    if not slate11:
        return [], flags_summary

    # prior fixture per club, from the Week 10 slate: date + venue city, as the slate printed them
    prev: dict[str, dict] = {}
    if slate10:
        w10_hand = {re.sub(r"-\d{4}-reg-\d+$", "", (r.get("game_center_slug") or "")): r
                    for r in read_csv(VENUES_W10)}
        for r in slate10["rows"]:
            if r.get("row_type") not in (None, "", "game") and r.get("row_type") != "game":
                continue
            slug = slug_of(r.get("game_url", ""))
            for side in ("away", "home"):
                club = (r.get(side) or "").strip()
                if not club:
                    continue
                hand = w10_hand.get(slug, {})
                v = venues.get(slug, {})
                prev[club] = {"date": r.get("date_et", ""),
                              "city": (v.get("location") or hand.get("location_as_printed") or ""),
                              "stadium": (v.get("stadium") or hand.get("stadium_as_printed") or "")}
        byes = sorted({(r.get("away") or "").strip() for r in slate10["rows"]
                       if (r.get("status") or "").strip().lower() in ("bye",) or r.get("row_type") == "bye"})
    else:
        byes = []

    rows = []
    for r in slate11["rows"]:
        if r.get("row_type") == "bye" or r.get("status") == "Bye" or not r.get("home"):
            continue
        slug = slug_of(r.get("game_url", ""))
        v = venues.get(slug, {})
        away, home = (r.get("away") or "").strip(), (r.get("home") or "").strip()
        date11 = r.get("date_et", "")
        pa, ph = prev.get(away, {}), prev.get(home, {})
        rest_a = days_between(pa.get("date", ""), date11)
        rest_h = days_between(ph.get("date", ""), date11)
        row = {
            "game_id": r.get("game_id", ""), "week": TARGET_WEEK,
            "date_et": date11, "kickoff_et": r.get("time_et", ""),
            "network": r.get("network", ""), "status_as_read": r.get("status", ""),
            "away_abbr": away, "home_abbr": home,
            "away_record_slate": r.get("away_record", ""), "home_record_slate": r.get("home_record", ""),
            "away_rest_days": rest_a, "home_rest_days": rest_h,
            "away_short_week": ("yes" if isinstance(rest_a, int) and rest_a <= 4 else
                                ("no" if isinstance(rest_a, int) else "")),
            "home_short_week": ("yes" if isinstance(rest_h, int) and rest_h <= 4 else
                                ("no" if isinstance(rest_h, int) else "")),
            "away_bye_prior_week": ("yes" if away in byes else "no") if byes or slate10 else "",
            "home_bye_prior_week": ("yes" if home in byes else "no") if byes or slate10 else "",
            "away_prev_venue": pa.get("stadium", ""), "home_prev_venue": ph.get("stadium", ""),
            "venue_city_this_week": v.get("location", ""),
            "venue_same_city_as_prev": (
                "yes" if v.get("location") and pa.get("city") and v["location"].upper() == pa["city"].upper()
                else ("no" if v.get("location") and pa.get("city") else "")),
            "stadium": v.get("stadium", ""), "stadium_source": v.get("source", ""),
            "roof": v.get("roof", ""), "surface": v.get("surface", ""),
            "prime_time": "", "international": "", "slate_source_url": slate11["source_url"],
            "slate_read_at": slate11["as_read_at"], "flags": "",
        }
        # "Prime time" is only a fact when the page labels the window. The slate prints a window
        # string per fixture ("Thursday Night Football, November 19th"), so the flag is read from
        # that label and never inferred from the kickoff clock: 4:25 PM games are not labelled
        # prime time by the league, and a model that decided they were would be inventing a
        # broadcast effect the schedule does not claim.
        note = (r.get("note") or "").strip()
        row["window_label"] = note
        low = note.lower()
        if any(w in low for w in ("thursday night", "sunday night", "monday night",
                                  "prime time", "international")):
            row["prime_time"] = "yes"
        elif note:
            row["prime_time"] = "no"
        else:
            row["prime_time"] = ""
        loc = (row["venue_city_this_week"] or "").upper()
        if loc:
            foreign = any(c in loc for c in (", ON", "MEXICO", "GERMANY", ", BC", "LONDON", "MUNICH", "BRAZIL", "SPAIN"))
            row["international"] = "yes" if foreign else "no"
        flags = []
        if not row["stadium"]:
            flags.append("venue-not-captured")
        if row["away_rest_days"] == "":
            flags.append("rest-days-unknown:away")
        if row["home_rest_days"] == "":
            flags.append("rest-days-unknown:home")
        if not row["roof"]:
            flags.append("roof-not-on-page")
        if not row["surface"]:
            flags.append("surface-not-on-page")
        row["flags"] = ";".join(flags)
        rows.append(row)
    return rows, flags_summary


def write(rows: list[dict], meta: dict) -> None:
    os.makedirs(OUTDIR, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS), extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(os.path.join(OUTDIR, "fixture_context_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, sort_keys=True)


def cmd_build(args) -> int:
    rows, inputs = build()
    meta = {"dataset": "fixture-context-2026-w11", "season": SEASON, "week": TARGET_WEEK,
            "rule": "published schedule facts only; a field no official page printed is blank",
            "rows": len(rows), "inputs": inputs,
            "counts": {
                "with_stadium": sum(1 for r in rows if r["stadium"]),
                "with_rest_days_away": sum(1 for r in rows if r["away_rest_days"] != ""),
                "with_rest_days_home": sum(1 for r in rows if r["home_rest_days"] != ""),
                "with_roof": sum(1 for r in rows if r["roof"]),
                "with_surface": sum(1 for r in rows if r["surface"]),
            }}
    if not rows:
        print("fixture context: no Week 11 slate capture found — nothing built (not an error; "
              "the capture has to run first)")
        write([], meta)
        return 1 if args.strict else 0
    write(rows, meta)
    print(f"fixture context: {len(rows)} fixtures, "
          f"{meta['counts']['with_stadium']} with a venue, "
          f"{meta['counts']['with_rest_days_away']}+{meta['counts']['with_rest_days_home']} rest-day cells")
    return 0


def cmd_check(args) -> int:
    before = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    rows, _ = build()
    meta = {"rebuilt": len(rows)}
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(COLUMNS), extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    if buf.getvalue() != before:
        print("FAIL: committed fixture-context table does not reproduce from its inputs")
        return 1
    print(f"PASS: fixture-context table reproduces ({meta['rebuilt']} rows)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--strict", action="store_true", help="exit non-zero when there is nothing to build")
    b.set_defaults(func=cmd_build)
    c = sub.add_parser("check")
    c.set_defaults(func=cmd_check)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
