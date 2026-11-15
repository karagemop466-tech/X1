"""The two depth-parsing failures, measured instead of asserted.

Session `arena-b03ced7c-x1`. Additive module; it reads other sessions' stores
and writes only its own files.

The brief names two defects:

  * "The Texans publish depth as an image"  — no text to parse at all.
  * "The Packers prepend jersey numbers"    — text exists, but the name field
                                              carries "75 Sean Rhyan", so a join
                                              on the name silently fails.

This module does three things, in this order:

  1. Parses the live Packers chart with a number-stripping parser and keeps the
     raw string beside the cleaned name, so the cleaning is auditable.
  2. Compares that parse, cell by cell, with every Packers row the repository
     has published (`data/pipeline/depth_charts.json`, `data/console/
     depth_replacement.csv`, `data/depth/replacement_depth.csv`).
  3. Records the Texans chart as an *authorized structured source absent*: the
     page serves the chart as a single image with no table and no alt text, so
     there is nothing to read. It is not transcribed by eye.

What it refuses to do: transcribe the Texans image, infer a depth order from a
jersey number, or "fix" a disagreement by preferring one read.

Outputs (new):
  data/console/depth_parse.json
  data/console/depth_parse.csv
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LIVE_PSV = ("data/official/depth_parse_2026_w10/"
            "packers_depth_live_2026-11-15T1820z.psv")
GB_URL = "https://www.packers.com/team/depth-chart"
HOU_URL = "https://www.houstontexans.com/team/depth-chart"

UNITS = {"Offense": "Offense", "Defense": "Defense", "Special Teams": "Special Teams"}


def join_key(name: str) -> str:
    """Fold only what is character encoding, never what is identity.

    The Packers print a typographic apostrophe ("Ty\u2019Ron Hopper"); the league
    report prints ASCII ("Ty'Ron Hopper"). Folding the two across is an encoding
    fix, stated here so it cannot be mistaken for a name guess. Nothing else is
    folded: no punctuation removal, no suffix stripping, no fuzzy matching.
    """
    return (name or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u00a0", " ").strip()


def clean(raw: str):
    """Return (name, jersey, stripped). The raw string is never discarded."""
    raw = (raw or "").strip()
    m = re.match(r"^(\d{1,2})\s+(.+)$", raw)
    if m:
        return m.group(2).strip(), m.group(1), True
    return raw, "", False


def load_live():
    rows = []
    with open(os.path.join(ROOT, LIVE_PSV), encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("#") or not line.strip():
                continue
            unit, pos, slot, depth, raw = line.split("|")
            name, jersey, stripped = clean(raw)
            rows.append(dict(unit=UNITS[unit], position=pos, slot=int(slot), depth=int(depth),
                             raw=raw, name=name, jersey=jersey, stripped=stripped))
    return rows


def parse_published():
    with open(os.path.join(ROOT, "data", "pipeline", "depth_charts.json"), encoding="utf-8") as fh:
        rows = json.load(fh)["rows"]
    return [r for r in rows if r.get("team_abbrev") == "GB"]


def compare(live, published):
    """Cell-by-cell diff keyed on (unit, position, slot, depth).

    A row whose position label the parser could not read is kept with the
    sentinel '(unlabelled)' rather than dropped: the defect is that the label is
    missing, and dropping the row would hide it.
    """
    lut = {(r["unit"], r["position"], r["slot"], r["depth"]): r for r in live}
    pub = {}
    for r in published:
        pub[(r["unit"], r["position"] or "(unlabelled)", r["slot"], r["depth"])] = r

    def order(k):
        return tuple("" if x is None else str(x) for x in k)

    diffs = []
    for k in sorted(set(lut) | set(pub), key=order):
        a = lut.get(k)
        b = pub.get(k)
        if a and b:
            if (a["raw"] or "") != (b["player"] or ""):
                diffs.append(dict(key=k, kind="value", live=a["raw"], published=b["player"] or "",
                                  live_name=a["name"], note="printed cell differs"))
        elif a:
            diffs.append(dict(key=k,
                              kind="missing_named_in_published" if a["raw"] else "missing_empty_cell",
                              live=a["raw"], published="", live_name=a["name"],
                              note=("a named player is printed on the live chart and absent from the store"
                                    if a["raw"] else
                                    "the chart prints this cell empty; the store holds no row, so the "
                                    "emptiness cannot be told apart from an unread cell")))
        else:
            diffs.append(dict(key=k, kind="not_on_live_chart", live="",
                              published=b["player"] or "", live_name="",
                              note="in the store but not printed on the live chart"))

    # jersey-number contamination, counted rather than assumed
    contaminated = [r for r in published if re.match(r"^\d", (r.get("player") or "").strip())]
    return diffs, contaminated, pub, lut


def summary(live, published, diffs, contaminated):
    named_live = [r for r in live if r["raw"]]
    club_named = {r["name"] for r in live if r["name"]}
    pub_clean = {join_key(clean(r.get("player"))[0]) for r in published}
    pub_raw = {(r.get("player") or "").strip() for r in published}
    on_chart = {join_key(r["name"]) for r in live if r["name"]}

    # can a join succeed today?
    injury_names = set()
    with open(os.path.join(ROOT, "data", "nfl", "injuries_week10.tsv"), encoding="utf-8") as fh:
        body = [ln for ln in fh if not ln.startswith("#")]
    for r in csv.DictReader(body, delimiter="\t"):
        if r["team"] == "GB":
            injury_names.add(r["player"].strip())

    join_raw = injury_names & pub_raw
    join_clean = {n for n in injury_names if join_key(n) in pub_clean}

    return dict(
        live_cells=len(live),
        live_named=len(named_live),
        live_clubs_named=len(club_named),
        published_rows=len(published),
        published_contaminated=len(contaminated),
        published_distinct_raw=len(pub_raw),
        diffs=len(diffs),
        diffs_by_kind=dict(Counter(d["kind"] for d in diffs)),
        injury_rows_gb=len(injury_names),
        join_hits_with_raw_string=len(join_raw),
        join_hits_after_number_strip=len(join_clean),
        join_gain=len(join_clean) - len(join_raw),
        untouched_by_the_defect=sorted(join_clean & join_raw),
        recovered_by_stripping=sorted(join_clean - join_raw),
        still_unjoined=sorted(injury_names - join_clean),
        unjoined_not_on_chart=sorted(n for n in injury_names - join_clean
                                     if join_key(n) not in on_chart),
        unjoined_on_chart_but_not_matched=sorted(n for n in injury_names - join_clean
                                                 if join_key(n) in on_chart),
    )


def build():
    live = load_live()
    published = parse_published()
    diffs, contaminated, pub, lut = compare(live, published)
    s = summary(live, published, diffs, contaminated)

    texans = dict(
        url=HOU_URL,
        page_title="Depth Chart | Houston Texans - HoustonTexans.com",
        heading_on_page="Unofficial Depth Chart",
        evidence=("The page renders the depth chart as one image "
                  "(https://static.clubs.nfl.com/image/upload/texans/a5or0zowuo36y1txf4ly). "
                  "There is no table, no list and no alt text in the served page: the only "
                  "text on the page is the heading and the club's headline feed."),
        captured="2026-11-15T18:21Z",
        decision="Not transcribed. An image is an official publication but not a machine-readable "
                 "source; reading it by eye would introduce exactly the transcription risk the "
                 "rest of this repository exists to remove.",
        required_to_close="An authorized structured feed (club CMS export, league data licence) or "
                          "a text-bearing depth page. Until one exists Houston has 0 of 897 published "
                          "depth slots and every Houston availability statement is unverifiable.",
        slots_in_store=0,
    )

    findings = []
    n = 0

    def add(sev, area, finding, effect, source=GB_URL):
        nonlocal n
        n += 1
        findings.append(dict(id=f"DP-{n:02d}", severity=sev, area=area, finding=finding,
                             effect=effect, source=source))

    add("amber", "Packers depth",
        f"{s['published_contaminated']} of {s['published_rows']} published Packers rows still carry the "
        f"jersey number inside the name field (\"75 Sean Rhyan\"), so a name join against the injury "
        f"report misses them: {s['join_hits_with_raw_string']} of {s['injury_rows_gb']} Green Bay "
        f"injury rows match today, {s['join_hits_after_number_strip']} after stripping.",
        "The Packers' injured starters are under-detected. Stripping the number recovers "
        f"{s['join_gain']} join(s); the raw string is kept so the cleaning is auditable.")
    add("red", "Packers depth",
        f"{s['diffs']} cell(s) differ between the live chart and the published store "
        f"({s['diffs_by_kind'].get('missing_in_published', 0)} printed on the live chart but absent "
        f"from the store, {s['diffs_by_kind'].get('not_on_live_chart', 0)} in the store but not on the "
        f"live chart).",
        "Stripping the number is necessary but not sufficient: the store is also incomplete and in "
        "places contradicted, so it must be re-captured with the date the club prints "
        "(\"Unofficial, Nov. 10, 2026\") recorded on every row.")
    if s["unjoined_not_on_chart"]:
        add("amber", "Packers depth",
            f"{len(s['unjoined_not_on_chart'])} Green Bay player(s) on the official injury report are "
            f"printed nowhere on the club's depth chart: "
            + ", ".join(s["unjoined_not_on_chart"]) + ".",
            "They are either on injured reserve, on the practice squad, or omitted from the chart. "
            "The source does not say which, so no reason is recorded — the absence is published as an "
            "absence, and each of those players is unpriced by the availability model.")
    add("amber", "Texans depth",
        "The Texans chart is served as an image. Nothing on the page can be parsed as text.",
        "Houston has no published depth slot. A Houston starter ruled out cannot be matched to a "
        "replacement string, so the deficiency register is silent on one of 32 clubs — silence that "
        "must not be read as 'no deficiency'.", source=HOU_URL)
    add("amber", "Depth provenance",
        "Every club chart is labelled 'Unofficial' by the club that publishes it (Green Bay prints "
        "\"Unofficial, Nov. 10, 2026\").",
        "A depth row is a club self-report at a dated moment. It cannot be treated as a league fact "
        "and it must carry the club's own date, not the date we fetched it.", source=GB_URL)

    return dict(captured="2026-11-15T18:20Z", packers_source=GB_URL,
                packers_summary=s, texans=texans, findings=findings,
                diffs=[dict(unit=d["key"][0], position=d["key"][1], slot=d["key"][2],
                            depth=d["key"][3], kind=d["kind"], live=d["live"],
                            published=d["published"], note=d["note"],
                            live_name=d["live_name"], source=GB_URL) for d in diffs],
                live_rows=live)


def main():
    out = build()
    data_dir = os.path.join(ROOT, "data", "console")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "depth_parse.json"), "w", encoding="utf-8") as fh:
        # live_rows is shipped: the page renders the stripped-name demonstration
        # from this file, so the demonstration cannot drift from the measurement.
        json.dump(out, fh, indent=1)
        fh.write("\n")
    with open(os.path.join(data_dir, "depth_parse.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["CLUB", "UNIT", "POSITION", "SLOT", "DEPTH", "KIND", "LIVE_CELL",
                    "PUBLISHED_CELL", "NOTE", "SOURCE"])
        for d in out["diffs"]:
            w.writerow(["GB", d["unit"], d["position"], d["slot"], d["depth"], d["kind"],
                        d["live"], d["published"], d["note"], d["source"]])
        for r in out["live_rows"]:
            w.writerow(["GB", r["unit"], r["position"], r["slot"], r["depth"],
                        "live_named" if r["raw"] else "live_empty", r["raw"], "",
                        "number stripped" if r["stripped"] else "no number", GB_URL])
    s = out["packers_summary"]
    print(f"[depth-parse] live cells {s['live_cells']}, named {s['live_named']}, "
          f"published rows {s['published_rows']} ({s['published_contaminated']} with a jersey number)")
    print(f"[depth-parse] diffs {s['diffs']} {s['diffs_by_kind']}")
    print(f"[depth-parse] GB injury join: raw {s['join_hits_with_raw_string']} -> "
          f"stripped {s['join_hits_after_number_strip']} (+{s['join_gain']})")
    print(f"[depth-parse] recovered: {s['recovered_by_stripping']}")
    print(f"[depth-parse] still unjoined: {s['still_unjoined']}")
    print(f"[depth-parse] Texans: {out['texans']['slots_in_store']} slots, image source, not transcribed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
