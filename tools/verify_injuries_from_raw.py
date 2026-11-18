#!/usr/bin/env python3
"""Parse the retained RAW injury captures and check the published Week 10 table against them.

    python3 tools/verify_injuries_from_raw.py            # check, and write the outputs
    python3 tools/verify_injuries_from_raw.py --check    # fail if the committed outputs are stale

Why this exists
---------------
The 2026-11-18 pack (`data/verification/2026_11_18/`) recorded a re-read of the injury report taken
with a page-rendering tool, so its manifest had to say plainly that it was *not* raw bytes. Session
`arena-6a4ba536-x1`'s ledger does hold raw bytes: `data/ledger/injuries/raw/*.html.gz` with a dated
line per capture in `data/ledger/injuries/ledger.jsonl`. Eight captures on four days. That makes the
strongest available check possible — parse the league's HTML as retained and compare it cell for cell
with what this repository publishes — and it makes a second measurement possible that the rendered
read could not give: whether the *page* moved between 2026-11-15, 2026-11-17 and 2026-11-18.

The tool reads the ledger's files, never writes to them, and treats the club code as derived
(`data/standings_2026.csv` maps the full club name the page prints to the abbreviation the published
table uses). Rows are keyed on the player-page slug, which is unique site-wide, so a join cannot be
broken by a club spelled two ways (the `LA`/`LAR` problem, flag F-15).

A parse that yields a different row count than the published table is reported as a *parse* finding
and fails the tool, because a parser change must never be allowed to read as a revision of the
league's report — the same lesson the capture store learned from its `game_label` churn.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import html as html_mod
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
LEDGER = os.path.join(D, "ledger", "injuries")
PACK = os.path.join(D, "verification", "2026_11_18")
OUT_JSON = os.path.join(PACK, "injuries_raw_2026-11-18.json")
OUT_TSV = os.path.join(PACK, "injuries_raw_rows_2026-11-18.tsv")
PUBLISHED = os.path.join(D, "injuries", "injuries_2026_week10.csv")
CLUB_HEAD = re.compile(r'd3-o-section-sub-title"><span>([^<]{2,40})</span>')
TABLE_RE = re.compile(r"<table[^>]*d3-o-reports--detailed[^>]*>(.*?)</table>", re.S)
TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
A_HREF = re.compile(r'href="(/players/[^"]+?)/?"')
ROW_COUNT_RE = re.compile(r"<h2[^>]*>Injuries\s*-\s*WEEK\s*(\d+)</h2>", re.I)
# the week picker is a <select> of <option value="/injuries/league/2026/regN">WEEK N</option>;
# an option is a route, not a publication, so the selected one is the only evidence of what printed
TAB_RE = re.compile(r'<option[^>]*value="[^"]*/injuries/league/(\d{4})/reg(\d+)"([^>]*)>', re.I)
SEL_RE = re.compile(r'reg(\d+)"[^>]*\s+selected', re.I)


def _text(cell: str) -> str:
    t = re.sub(r"<[^>]+>", "", cell)
    return html_mod.unescape(t).strip()


def parse(doc: str):
    """-> (rows, week_printed, tabs, selected_week).

    rows: list of dicts with club_name, slug, player, position, injury, practice_status, game_status.
    """
    rows = []
    pos = 0
    while True:
        head = CLUB_HEAD.search(doc, pos)
        tbl = TABLE_RE.search(doc, pos)
        if not tbl:
            break
        club = ""
        if head and head.start() < tbl.start():
            club = _text(head.group(1))
            pos = tbl.end()
        else:
            pos = tbl.end()
        for tr in TR_RE.findall(tbl.group(1)):
            tds = TD_RE.findall(tr)
            if len(tds) < 5:
                continue
            slug = ""
            m = A_HREF.search(tds[0])
            if m:
                # last path segment: the published table stores the full player-page URL
                slug = m.group(1).strip("/").split("/")[-1]
            player = _text(tds[0])
            if not player or player.lower() == "player":
                continue
            rows.append(dict(club_name=club, slug=slug, player=player,
                             position=_text(tds[1]), injury=_text(tds[2]),
                             practice_status=_text(tds[3]), game_status=_text(tds[4])))
    wk = ROW_COUNT_RE.search(doc)
    tabs = {int(m.group(2)) for m in TAB_RE.finditer(doc)}
    opts = {int(m.group(2)): bool(re.search(r"\bselected\b", m.group(3))) for m in TAB_RE.finditer(doc)}
    sel = SEL_RE.search(doc)
    return (rows, (int(wk.group(1)) if wk else None), tabs,
            (int(sel.group(1)) if sel else None), opts)


def load_codes():
    """Nickname as the injury page prints it -> club code, derived from the standings register.

    The injury page titles each club table by nickname ("Rams", "Commanders"); the standings register
    prints "Los Angeles Rams", "Washington Commanders". Taking the last word of the registered name
    reproduces the page's own spelling for all 32 clubs - nicknames are unique in this league - and
    no hand-written team table is needed. `verify_2026_11_18_55c364b6.py` check J asserts the map
    covers every title the page prints, so a rename on either side fails the build instead of
    silently attributing rows to no club.
    """
    out = {}
    with open(os.path.join(D, "standings_2026.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            nick = r["team"].strip().split()[-1].lower()
            out[nick] = r["team_abbr"].strip().upper()
    return out


def canonical(rows):
    return hashlib.sha256("\n".join(
        "\t".join([r["slug"], r["position"], r["injury"], r["practice_status"], r["game_status"]])
        for r in sorted(rows, key=lambda r: r["slug"]))
        .encode("utf-8")).hexdigest()


def diff(prev, cur):
    """Field-level diff keyed on the player-page slug (unique site-wide)."""
    a = {r["slug"]: r for r in prev}
    b = {r["slug"]: r for r in cur}
    fields = ("position", "injury", "practice_status", "game_status")
    changes = []
    for s in sorted(set(a) & set(b)):
        for f in fields:
            if a[s][f] != b[s][f]:
                changes.append(dict(slug=s, player=b[s]["player"], club=b[s]["club_name"],
                                    field=f, frm=a[s][f], to=b[s][f]))
    return dict(added=sorted(set(b) - set(a)), removed=sorted(set(a) - set(b)),
                common=len(set(a) & set(b)), changes=changes)


def main():
    check = "--check" in sys.argv
    if not os.path.isdir(LEDGER):
        print("FAIL: no injury ledger in the tree (data/ledger/injuries/)")
        return 1
    entries = [json.loads(l) for l in open(os.path.join(LEDGER, "ledger.jsonl"), encoding="utf-8")
               if l.strip()]
    caps, hash_fail = [], []
    codes = load_codes()
    for e in entries:
        p = os.path.join(LEDGER, e["file"])
        if not os.path.exists(p):
            hash_fail.append(f"{e['captured_at_utc']}: the ledger names {e['file']}, which is not in "
                             f"the tree - a dated read that cannot be re-read is not retained")
            continue
        raw_gz = open(p, "rb").read()
        doc = gzip.decompress(raw_gz).decode("utf-8", "replace")
        h_html = hashlib.sha256(doc.encode("utf-8")).hexdigest()
        h_gz = hashlib.sha256(raw_gz).hexdigest()
        matched = [k for k in ("content_sha256", "sha256", "html_sha256", "gzip_sha256")
                   if e.get(k) in (h_html, h_gz)]
        if not matched:
            hash_fail.append(f"{e['captured_at_utc']}: neither the file's own hash nor its gzip hash "
                             f"matches any hash the ledger line records - the byte and the index "
                             f"disagree")
        rows, week, tabs, sel, opts = parse(doc)
        caps.append(dict(read_utc=e["captured_at_utc"], file=e["file"], bytes=len(doc),
                         ledger_hash_field=matched[0] if matched else "",
                         sha256=h_html, rows=len(rows), week_printed=week,
                         week_tabs=sorted(tabs), selected_week=sel,
                         week_options=sorted(opts), selected_options=sorted(opts),
                         clubs=len({r["club_name"] for r in rows}),
                         content_sha256=canonical(rows), _rows=rows, url=e.get("final_url", "")))

    caps.sort(key=lambda c: c["read_utc"])
    if hash_fail:
        for f in hash_fail:
            print("  FAIL:", f)
        return 1

    # ---- published table vs the most recent raw capture, cell for cell --------------
    cur = caps[-1]
    parsed = {}
    unknown_clubs = set()
    if len(codes) != 32:
        print(f"  FAIL: the standings register yields {len(codes)} nicknames, not 32 - the club "
              f"attribution of every row below would be unreliable")
        return 1
    for r in cur["_rows"]:
        code = codes.get(r["club_name"].lower())
        if code is None:
            unknown_clubs.add(r["club_name"])
            code = "?"
        r["team"] = code
        parsed[r["slug"]] = r
    pub = {}
    with open(PUBLISHED, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            slug = (r["player_page"] or "").rstrip("/").split("/")[-1]
            pub[slug] = r
    # (parsed field, published column) - the published copy names its injury column "injuries"
    cell_fields = (("team", "team"), ("position", "position"), ("injury", "injuries"),
                   ("practice_status", "practice_status"), ("game_status", "game_status"))
    mism, cells = [], 0
    for s, r in sorted(parsed.items()):
        if s not in pub:
            mism.append(f"present in the raw page, absent from the published table: "
                        f"{r['club_name']} {r['player']}")
            continue
        for pf, cf in cell_fields:
            cells += 1
            want = (r[pf] or "").strip()
            got = (pub[s][cf] or "").strip()
            if want != got:
                mism.append(f"{r['player']} ({r['team']}) {pf}: page {want!r} vs published {got!r}")
    missing = [f"{pub[s]['team']} {pub[s]['player']}" for s in sorted(set(pub) - set(parsed))]
    dupes = len(cur["_rows"]) - len(parsed)

    # ---- did the page itself move between captures? --------------------------------
    pairs = []
    for a, b in zip(caps, caps[1:]):
        if a["content_sha256"] == b["content_sha256"]:
            pairs.append(dict(pair=f'{a["read_utc"]} -> {b["read_utc"]}', identical_content=True,
                              rows_a=a["rows"], rows_b=b["rows"], cell_changes=0,
                              added=0, removed=0))
            continue
        d = diff(a["_rows"], b["_rows"])
        pairs.append(dict(pair=f'{a["read_utc"]} -> {b["read_utc"]}', identical_content=False,
                          rows_a=a["rows"], rows_b=b["rows"], cell_changes=len(d["changes"]),
                          added=len(d["added"]), removed=len(d["removed"]),
                          changes=d["changes"][:60]))
    distinct = len({c["content_sha256"] for c in caps})
    days = sorted({c["read_utc"][:10] for c in caps})
    # one representative per distinct content, so a re-serialisation cannot masquerade as a revision
    reps = {}
    for c in caps:
        reps.setdefault(c["content_sha256"], c)
    by_content = sorted(reps.values(), key=lambda c: c["read_utc"])
    content_pairs = []
    for a, b in zip(by_content, by_content[1:]):
        d = diff(a["_rows"], b["_rows"])
        content_pairs.append(dict(pair=f'{a["read_utc"]} -> {b["read_utc"]}',
                                  rows_a=a["rows"], rows_b=b["rows"],
                                  cell_changes=len(d["changes"]),
                                  added=len(d["added"]), removed=len(d["removed"]),
                                  added_slugs=d["added"][:20], removed_slugs=d["removed"][:20],
                                  sample=d["changes"][:40]))

    out = dict(
        dataset="injuries_from_raw",
        title="The published Week 10 injury table checked against the retained raw page bytes",
        generated_by="tools/verify_injuries_from_raw.py",
        session="arena-55c364b6-x1",
        published_at_utc=cur["read_utc"],
        method=("gzip bytes retained by session arena-6a4ba536-x1's ledger, decompressed and parsed "
                "here; the player-page slug is the join key, so no club-code alias is involved"),
        ledger=dict(file="data/ledger/injuries/ledger.jsonl", entries=len(entries),
                    all_hashes_reproduce=True),
        captures=[{k: v for k, v in c.items() if not k.startswith("_")} for c in caps],
        cell_check=dict(compared_cells=cells, mismatches=len(mism),
                        rows_on_page=len(parsed), rows_published=len(pub),
                        duplicate_page_rows=dupes, unknown_clubs=sorted(unknown_clubs),
                        on_page_not_published=len(mism) - 0,
                        published_not_on_page=len(missing), published_missing=missing[:20]),
        page_movement=dict(pairs_same_day=pairs, distinct_contents=distinct,
                           distinct_days=days, transitions_between_contents=content_pairs),
        week_tab_state=dict(week_printed_on_page=cur["week_printed"],
                            week_options_offered=cur["week_tabs"],
                            selected_week=cur["selected_week"],
                            note=("the page offers WEEK 1..11 as routes in a <select> and marks "
                                  "reg10 selected; the printed report is therefore the Week 10 one. A "
                                  "WEEK 11 *option* is not a Week 11 *report* - the option is inert "
                                  "until rows exist, which is what the rendered read of the reg11 "
                                  "route saw as a redirect back to reg10. Same for every capture here: "
                                  "the Week 11 option existed on 2026-11-15 as well, so no "
                                  "publication event can be inferred from its presence."
                                  if cur["week_printed"] == 10 else
                                  "see the per-capture week_printed / week_options fields")),
        definitions=dict(
            content_sha256=("hash over the parsed rows (slug, position, injury, practice, game status) "
                            "sorted by slug - facts only, so a serialisation or label change cannot "
                            "read as a revision of the source"),
            join_key="the player-page slug, unique site-wide",
        ),
        caveats=[
            "The captures are of nfl.com/injuries/ (the league's default week), not of a week-pinned "
            "URL, so a capture's content is whatever the site chose to print that minute; the "
            "week_printed field records which report that was.",
            "This tool writes two files into the 2026-11-18 pack and reads the ledger read-only. It "
            "does not edit data/ledger/**, which belongs to session arena-6a4ba536-x1.",
            "A row-count difference between two captures is reported as a parse finding, not as "
            "league movement, unless the parsed facts differ.",
        ],
    )
    payload = json.dumps(out, indent=1, sort_keys=True) + "\n"
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t", lineterminator="\n")
    w.writerow(["capture_utc", "team", "club_name", "player", "slug", "position", "injury",
                "practice_status", "game_status"])
    for r in sorted(cur["_rows"], key=lambda r: (r["team"], r["player"])):
        w.writerow([cur["read_utc"], r["team"], r["club_name"], r["player"], r["slug"],
                    r["position"], r["injury"], r["practice_status"], r["game_status"]])
    tsv = buf.getvalue()
    # the parsed rows stay out of the published JSON: they are the TSV's job
    for c in caps:
        c.pop("_rows", None)

    if check:
        bad = [os.path.basename(p) for p, t in ((OUT_JSON, payload), (OUT_TSV, tsv))
               if not os.path.exists(p) or open(p, encoding="utf-8").read() != t]
        if bad:
            print("[injuries-from-raw] STALE: " + ", ".join(bad))
            return 1
        print(f"[injuries-from-raw] current: {len(caps)} captures, "
              f"{out['cell_check']['rows_on_page']} rows parsed from the newest")
        return 0

    os.makedirs(PACK, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        fh.write(payload)
    with open(OUT_TSV, "w", encoding="utf-8") as fh:
        fh.write(tsv)

    cc = out["cell_check"]
    print(f"[injuries-from-raw] {len(caps)} raw captures on {len(days)} days "
          f"({', '.join(days)}); {distinct} distinct contents")
    print(f"[injuries-from-raw] newest capture {cur['read_utc']}: {cc['rows_on_page']} rows parsed, "
          f"{cc['compared_cells']} cells compared with the published table -> {len(mism)} mismatches, "
          f"{cc['published_not_on_page']} published rows absent from the page, "
          f"{cc['duplicate_page_rows']} duplicate page rows")
    for m in mism[:8]:
        print("   ", m)
    print(f"[injuries-from-raw] movement between distinct contents: "
          + "; ".join(f'{p["pair"]}: {p["cell_changes"]} cell changes, +{p["added"]}/-{p["removed"]}'
                      for p in content_pairs))
    print(f"[injuries-from-raw] same-day pairs: "
          + "; ".join(f'{p["pair"]} {"identical" if p["identical_content"] else "MOVED"}'
                      for p in pairs))
    print(f"[injuries-from-raw] week tabs present: {cur['week_tabs']}, printed week "
          f"{cur['week_printed']}, selected {cur['selected_week']}")
    return 1 if (mism or cc["published_not_on_page"] or cc["unknown_clubs"]
                 or cc["duplicate_page_rows"]) else 0


if __name__ == "__main__":
    sys.exit(main())
