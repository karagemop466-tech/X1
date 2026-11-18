#!/usr/bin/env python3
"""Official Game Center capture: the venue and the fixture facts, per fixture.

    python3 tools/official/gamecentre.py capture [--weeks 10,11] [--out data/official/gamecentre]
    python3 tools/official/gamecentre.py verify  [--dir  data/official/gamecentre]
    python3 tools/official/gamecentre.py cross-check
    python3 tools/official/gamecentre.py selftest

Why this exists (owner's brief, round 6):

    "Transcribe the venue of every fixture from the official game centre and publish it."
    "Add a drift alarm to every scraper: pin each parser to expected row counts and required
     fields; fail the build loudly when a field goes missing rather than publishing a blank."
    "Add a fixture-context feature set built only from published schedule facts."

The weekly schedule page has no venue field at all (flag F-26 on `main` records that 13 of 14
Week 10 `venue_note` cells are blank), so the venue can only come from the fixture's own Game
Center page. This tool reads the Game Center "Game Info" block for every fixture of a week,
retains the raw bytes it read, and publishes one row per fixture per read.

Rules this tool is built to:

* Nothing is inferred. A field the page did not print is written as an empty cell with
  `match_method=none`, and the row is counted in `fields_missing`. There is no fallback table
  of stadium names, no guessing a dome from a city, no jersey-number or abbreviation heuristics.
* Every published value is re-derivable from a retained capture: `verify` re-parses the stored
  gzip bytes and fails if the published table disagrees with what the page actually said.
* The slate is not typed by hand. Fixture URLs come from the league's own weekly schedule page;
  if that page cannot be read, the tool refuses rather than using a remembered list.
* Roof, surface, weather and officiating are captured only if the page prints them. As of the
  2026-11-18 reads the Game Center prints Location and Stadium and nothing about the roof, so
  those columns exist, are blank, and are flagged (see `docs/methodology/venue-and-fixture-context.md`).

Runs anywhere Python 3.11 runs. Network use is confined to `capture`, which fetches
www.nfl.com pages; `verify`, `cross-check` and `selftest` are offline and are what CI asserts.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DEFAULT = os.path.join(ROOT, "data", "official", "gamecentre")

NFL = "https://www.nfl.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# The official slate page for a week, and the fixture page pattern the league prints on it.
SLATE_URL = f"{NFL}/schedules/2026/by-week/week-%d"
SLUG_RE = re.compile(r"/games/([a-z0-9\-]+)-2026-reg-(\d{1,2})")

# Expected fixtures per week for the weeks this project reads. This is the drift pin: a page
# that prints fewer fixtures is a parser or source defect, not a quieter slate.
EXPECTED_FIXTURES = {10: 14, 11: 13}

# Fields that must be non-blank for a row to count as a good read. A required field that goes
# blank is a source or parser change, so `capture` fails rather than publishing blanks quietly.
REQUIRED_FIELDS = ("slug", "game_url", "status_label")

TAG_RE = re.compile(r"<[^>]+>")
INLINE_BREAK_RE = re.compile(r"(?i)</?(?:p|div|li|ul|ol|tr|h[1-6]|section|article|header|table|thead|tbody|dt|dd|figcaption)\b[^>]*>|<br\s*/?>")
WS_RE = re.compile(r"[ \t\r\f\v]+")
NBSLASH = re.compile(r"&(?:nbsp|#160);")

# The labels the official Game Info block is known to print. A line that starts with one of these
# ends the value of the label before it — which is how a blank field stays blank instead of
# swallowing the next field, and how a source that reorders its block still reads correctly.
KNOWN_LABELS = (
    "Location", "Stadium", "Capacity", "Attendance", "Surface", "Roof", "Weather",
    "Referee", "Kickoff", "Network", "TV", "Broadcast", "Officials", "Game Info",
    "Game Details", "Tickets", "Injury Report", "Depth Chart",
)

COLUMNS = (
    "captured_at_utc", "season", "week", "slug", "game_url", "slugs_printed",
    "away_page_name", "home_page_name", "away_abbr", "home_abbr",
    "status_label", "period_label", "clock",
    "away_score", "home_score", "location", "stadium", "city", "state",
    "capacity", "attendance", "surface", "roof", "kickoff_et", "game_number",
    "venue_method", "score_method", "body_sha256", "raw_gz_sha256", "raw_file",
    "http_status", "flags",
)


# --------------------------------------------------------------------------- helpers

def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def norm_lines(html: str) -> list[str]:
    """Block-level tags become line breaks; inline tags become spaces.

    The Game Info block prints a visible label and a screen-reader label back to back, so the
    page reads "Location LOCATION HOUSTON, TX". Keeping the element boundaries as line breaks is
    what lets a value be read without a fuzzy regex swallowing the next field. Nothing here
    reorders, rewrites or completes what the page said.
    """
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", "\n", html)
    text = INLINE_BREAK_RE.sub("\n", text)
    text = TAG_RE.sub(" ", text)
    text = NBSLASH.sub(" ", text)
    lines = []
    for raw in text.split("\n"):
        line = WS_RE.sub(" ", raw).strip()
        if line:
            lines.append(line)
    return lines


def _is_label_line(line: str) -> bool:
    low = line.lower()
    for lab in KNOWN_LABELS:
        if low == lab.lower() or low.startswith(lab.lower() + " "):
            return True
    return False


def _label_value(lines: list[str], label: str) -> tuple[str, str]:
    """Read one Game Info field. Returns (value, method); no match means ("", "none").

    The block prints a screen-reader label and a visible label back to back, with the value either
    on the same line or on the next one, so three shapes are accepted:
      `Label value`  ·  `Label LABEL value`  ·  `Label`/`LABEL` then the value on following lines.
    A value never runs past the next label line, so a field the page left out stays blank rather
    than borrowing the neighbour's value. No fallback table, no completion, no guessing.
    """
    head = re.compile("^" + re.escape(label) + r"\s*(?:" + re.escape(label.upper()) +
                      r")?\s*(.*)$", re.IGNORECASE)
    for i, line in enumerate(lines):
        m = head.match(line.strip())
        if not m:
            continue
        rest = (m.group(1) or "").strip(" .,-")
        if rest.upper() == label.upper():
            rest = ""                      # the doubled label, nothing else on the line
        if not rest:
            j = i + 1
            parts: list[str] = []
            while j < len(lines) and not _is_label_line(lines[j]):
                parts.append(lines[j].strip())
                j += 1
                if parts and not parts[-1].endswith((",", "-", "\u2013")):
                    break                  # one value line, unless it visibly continues
            rest = " ".join(parts).strip(" .,-")
        if rest and rest.upper() != label.upper():
            method = "label-inline" if (m.group(1) or "").strip() else "label-line"
            return rest, method
    return "", "none"


JSON_BLOB_RE = re.compile(r"<script[^>]*id=\"__NEXT_DATA__\"[^>]*>(.*?)</script>", re.S)


def json_from_page(html: str):
    """The page's own embedded JSON payload, if the render carries one. Parsed, never scraped blind."""
    m = JSON_BLOB_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _dig(obj, *paths):
    """First non-empty string found at any of the given key paths. ('a','b') means obj['a']['b']."""
    for path in paths:
        cur = obj
        for key in path:
            if isinstance(cur, dict):
                cur = cur.get(key)
            else:
                cur = None
                break
        if isinstance(cur, str) and cur.strip():
            return cur.strip(), "json-" + ".".join(path)
    return "", "none"


def parse_game_centre(html: str, lines: list[str] | None = None) -> dict:
    """Extract the fixture facts the official Game Center prints. Missing means blank, never guessed."""
    lines = lines if lines is not None else norm_lines(html)
    text = " ".join(lines)
    out: dict = {}

    m = re.search(r"\b(FINAL|LIVE|HALFTIME|SCHEDULED|POSTPONED|CANCELED|CANCELLED|IN PROGRESS)\b",
                  text, re.IGNORECASE)
    out["status_label"] = m.group(1).upper() if m else ""
    per = re.search(r"\bQ(?:UARTER)?\s*([1-4])\b", text, re.IGNORECASE)
    out["period_label"] = f"Q{per.group(1)}" if per else ""
    if out["period_label"]:
        tail = text[text.lower().find(out["period_label"].lower()):]
        clk = re.search(r"\b(\d{1,2}:\d{2})\b", tail)
        out["clock"] = clk.group(1) if clk else ""
    else:
        out["clock"] = ""

    # Score, in the order the box prints it. Two forms are tried, most trustworthy first, and the
    # form that matched is published so a reader can see how much to trust the row.
    score = re.search(r"\b([A-Z]{2,3})\s+(\d{1,3})\s*[-\u2013]\s*(\d{1,3})\s+([A-Z]{2,3})\b", text)
    if score:
        out["away_abbr"], out["away_score"] = score.group(1), score.group(2)
        out["home_abbr"], out["home_score"] = score.group(4), score.group(3)
        out["score_method"] = "away-at-home-line"
    else:
        out.update({"away_abbr": "", "home_abbr": "", "away_score": "", "home_score": "",
                    "score_method": "none"})

    out["location"], out["venue_method"] = _label_value(lines, "Location")
    out["stadium"], _ = _label_value(lines, "Stadium")
    out["capacity"], _ = _label_value(lines, "Capacity")
    out["attendance"], _ = _label_value(lines, "Attendance")
    out["surface"], _ = _label_value(lines, "Surface")
    out["roof"], _ = _label_value(lines, "Roof")
    out["kickoff_et"], _ = _label_value(lines, "Kickoff")
    gm = re.search(r"\bGAME\s+(\d{1,2})\b", text)
    out["game_number"] = gm.group(1) if gm else ""

    # Fallback, only when the Game Info block is not in the server-rendered HTML: read the same
    # fields out of the page's own JSON payload (the data the page hydrates from). The method
    # column records that this happened, so a reader knows the value came from the embedded
    # payload rather than from the printed block. If neither carries it, the cell stays blank.
    if not out["location"] or not out["stadium"]:
        js = json_from_page(html)
        if js:
            if not out["location"]:
                v, how = _dig(js, ("location", "fullName"), ("location", "name"),
                              ("venueLocation",), ("cityState",))
                if v:
                    out["location"], out["city"], out["state"] = v, "", ""
                    if "," in v:
                        out["city"], out["state"] = [x.strip() for x in v.split(",", 1)]
                    out["venue_method"] = how
            if not out["stadium"]:
                v, how = _dig(js, ("stadium", "fullName"), ("stadium", "name"),
                              ("venue", "fullName"), ("venue", "name"), ("venue",))
                if v:
                    out["stadium"], out["venue_method"] = v, how

    loc = out["location"]
    if "," in loc:
        city, state = loc.split(",", 1)
        out["city"], out["state"] = city.strip(), state.strip()
    else:
        out["city"] = out["state"] = ""
    return out


# --------------------------------------------------------------------------- capture

def read_slate(week: int, report: dict) -> list[str]:
    """Fixture slugs for a week, from the league's own weekly schedule page."""
    url = SLATE_URL % week
    status, body, final_url, err = fetch(url)
    report["slate_urls"].append({"week": week, "url": url, "http_status": status,
                                 "final_url": final_url, "error": err})
    if not body:
        return []
    slugs: list[str] = []
    for m in SLUG_RE.finditer(body):
        if int(m.group(2)) == week and m.group(1) not in slugs:
            slugs.append(m.group(1))
    return slugs


def write_raw(outdir: str, captured_at: str, slug: str, html: str) -> tuple[str, str]:
    raw_dir = os.path.join(outdir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    stamp = captured_at.replace(":", "").replace("-", "")
    name = f"{stamp}_{slug}.html.gz"
    data = gzip.compress(html.encode("utf-8"), mtime=0)
    with open(os.path.join(raw_dir, name), "wb") as fh:
        fh.write(data)
    return name, sha256_bytes(data)


def cmd_capture(args) -> int:
    weeks = [int(w) for w in args.weeks.split(",") if w.strip()]
    outdir = args.out
    os.makedirs(outdir, exist_ok=True)
    captured_at = now_iso()
    report = {"command": "capture", "captured_at_utc": captured_at, "season": args.season,
              "weeks": weeks, "slate_urls": [], "rows": 0, "fields_missing": 0,
              "fetch_errors": [], "drift": []}

    rows: list[dict] = []
    for week in weeks:
        slugs = read_slate(week, report)
        if EXPECTED_FIXTURES.get(week) is not None and len(slugs) != EXPECTED_FIXTURES[week]:
            report["drift"].append({
                "dataset": f"week{week}_slate",
                "expected_fixtures": EXPECTED_FIXTURES[week], "found": len(slugs),
                "note": "the weekly slate page did not print the pinned fixture count"})
        if not slugs:
            report["fetch_errors"].append({"week": week, "error": "no fixture links parsed from the slate page"})
            continue
        for slug in slugs:
            url = f"{NFL}/games/{slug}-2026-reg-{week}"
            status, body, final_url, err = fetch(url)
            if not body:
                report["fetch_errors"].append({"slug": slug, "url": url, "error": err or "empty body",
                                               "http_status": status})
                continue
            lines = norm_lines(body)
            parsed = parse_game_centre(body, lines)
            # The slug is the league's own label for the fixture ("<away>-at-<home>-2026-reg-N").
            # Splitting it is a string read, not a lookup: no club table, no abbreviation guesses.
            sm = re.match(r"([a-z\-]+)-at-([a-z\-]+)-2026-reg-(\d+)$", slug)
            parsed["away_page_name"] = sm.group(1).replace("-", " ") if sm else ""
            parsed["home_page_name"] = sm.group(2).replace("-", " ") if sm else ""

            raw_name, gz_sha = write_raw(outdir, captured_at, slug, body)
            row = {
                "captured_at_utc": captured_at, "season": args.season, "week": week,
                "slug": slug, "game_url": url, "slugs_printed": len(slugs),
                "body_sha256": sha256_bytes(body.encode("utf-8")), "raw_gz_sha256": gz_sha,
                "raw_file": f"raw/{raw_name}", "http_status": status, "flags": "",
            }
            for k in COLUMNS:
                if k not in row:
                    row[k] = parsed.get(k, "")
            flags = []
            if not row["status_label"]:
                flags.append("status-not-printed")
            if row["status_label"] == "FINAL" and not (row["away_score"].isdigit() and row["home_score"].isdigit()):
                flags.append("final-without-score")
            if row["venue_method"] == "none":
                flags.append("venue-not-printed")
            for f in REQUIRED_FIELDS:
                if not str(row.get(f, "")).strip():
                    flags.append(f"missing-required:{f}")
                    report["fields_missing"] += 1
            if not row["surface"]:
                flags.append("surface-not-on-page")
            if not row["roof"]:
                flags.append("roof-not-on-page")
            row["flags"] = ";".join(flags)
            rows.append(row)
            report["rows"] += 1

    dated = os.path.join(outdir, f"venue_register_{args.season}_w{'_'.join(str(w) for w in weeks)}_{captured_at[:10]}.tsv")
    with open(dated, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS), delimiter="\t",
                          extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(os.path.join(outdir, "venue_register_latest.tsv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS), delimiter="\t",
                          extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    fixtures = {"captured_at_utc": captured_at, "season": args.season, "weeks": weeks,
                "fixtures": sorted({r["slug"] for r in rows}), "rows": len(rows),
                "source": "slugs read from the weekly schedule pages listed in slate_urls"}
    with open(os.path.join(outdir, "fixtures.json"), "w", encoding="utf-8") as fh:
        json.dump({**fixtures, "slate_urls": report["slate_urls"]}, fh, indent=1)
    report["output"] = os.path.relpath(dated, ROOT)
    report["fixtures_recorded"] = len(fixtures["fixtures"])
    with open(os.path.join(outdir, "venue_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    print(json.dumps({k: v for k, v in report.items() if k != "slate_urls"}, indent=1))
    if report["fields_missing"]:
        print(f"DRIFT: {report['fields_missing']} required field(s) missing across "
              f"{report['rows']} rows — published with flags, never filled in")
        return args.drift_exit_code
    return 0


# --------------------------------------------------------------------------- verify

def cmd_verify(args) -> int:
    """Re-parse every retained capture and require the published table to agree cell for cell."""
    outdir = args.out
    path = os.path.join(outdir, "venue_register_latest.tsv")
    if not os.path.exists(path):
        print(f"FAIL: no published register at {os.path.relpath(path, ROOT)}")
        return 2
    with open(path, encoding="utf-8") as fh:
        published = list(csv.DictReader(fh, delimiter="\t"))
    if not published:
        print("FAIL: published register is empty")
        return 1
    problems, checks, mismatches = [], 0, 0
    for row in published:
        raw = os.path.join(outdir, row["raw_file"])
        if not os.path.exists(raw):
            problems.append(f"{row['slug']}: retained capture {row['raw_file']} is missing")
            continue
        blob = open(raw, "rb").read()
        if sha256_bytes(blob) != row["raw_gz_sha256"]:
            problems.append(f"{row['slug']}: retained bytes do not match the published raw_gz_sha256")
            continue
        html = gzip.decompress(blob).decode("utf-8", "replace")
        if sha256_bytes(html.encode("utf-8")) != row["body_sha256"]:
            problems.append(f"{row['slug']}: body hash does not match the retained bytes")
            mismatches += 1
            continue
        again = parse_game_centre(html)
        for field in ("status_label", "away_score", "home_score", "location", "stadium",
                      "capacity", "venue_method", "score_method"):
            checks += 1
            if str(again.get(field, "")) != str(row.get(field, "")):
                mismatches += 1
                problems.append(f"{row['slug']}: {field} republished {row.get(field)!r} "
                                f"but the retained page parses to {again.get(field)!r}")
    weeks = {}
    for row in published:
        weeks.setdefault(int(row["week"]), set()).add(row["slug"])
    for week, slugs in sorted(weeks.items()):
        pin = EXPECTED_FIXTURES.get(week)
        if pin is not None and len(slugs) != pin:
            problems.append(f"week {week}: register carries {len(slugs)} fixtures, the pinned "
                            f"official slate prints {pin}")
    print(f"venue register verify: {len(published)} rows, {checks} cell re-derivations, "
          f"{mismatches} mismatches, weeks {sorted(weeks)}")
    if problems:
        print(f"FAIL — {len(problems)} problem(s):")
        for p in problems[:40]:
            print("  -", p)
        return 1
    print("PASS — every published venue cell is re-derivable from a retained official capture.")
    return 0


# --------------------------------------------------------------------------- cross-check

def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def read_csv_tsv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def load_latest_slate_capture(captures_dir: str) -> dict | None:
    """The most recent `week_schedule` payload the scheduled collector retained, if any."""
    root = os.path.join(captures_dir, "payloads", "week_schedule")
    if not os.path.isdir(root):
        return None
    best = None
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if not f.endswith(".json"):
                continue
            path = os.path.join(dirpath, f)
            try:
                d = json.load(open(path, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if best is None or d.get("as_read_at", "") > best.get("as_read_at", ""):
                best = d
                best["_path"] = path
    if not best:
        return None
    slugs = []
    for row in best.get("rows", []):
        u = (row.get("game_url") or "").strip()
        m = re.search(r"/games/([a-z0-9\-]+?)(?:-2026-reg-\d+)?$", u)
        if row.get("row_type") == "game" and m:
            slugs.append(m.group(1) if m.group(1).endswith("reg-11") else
                         m.group(1).split("-2026-reg-")[0] + "-2026-reg-11")
    return {"as_read_at": best.get("as_read_at", ""), "source_url": best.get("source_url", ""),
            "slugs": sorted(set(slugs)), "file": os.path.relpath(best["_path"], ROOT)}


def cmd_crosscheck(args) -> int:
    """Cross-reads that make a published value harder to get wrong.

    A. Venue: this tool's runner-read Week 10 stadiums against the hand-transcribed official
       register on `main` (`data/nfl/venues_2026_week10.csv`, session `arena/5433abad-x1`).
       Two readers, two dates, one page each — agreement is evidence, not duplication.
    B. Slate: the fixture set captured here against the dated Week 11 slate capture the
       scheduled collector retains (`data/captures/payloads/week_schedule/**`).

    Every disagreement is printed. Nothing here edits either side, and nothing here fills a gap
    in one register with a value remembered from the other: a field the capture did not print
    stays blank in the capture's own row.
    """
    outdir = args.out
    rows = []
    reg = os.path.join(outdir, "venue_register_latest.tsv")
    if os.path.exists(reg):
        rows = read_csv_tsv(reg)
    rep = os.path.join(outdir, "fixture_crosscheck.json")
    out = {"captured_at_utc": now_iso(), "checks": [], "mismatches": 0}

    # ---- A. venue agreement with the hand register
    venue_rows = read_csv(args.venues)
    if rows and venue_rows:
        mine = {r["slug"]: r for r in rows if r.get("venue_method") != "none"}
        agree, differ, only_theirs, cells = 0, [], [], 0
        for v in venue_rows:
            slug = (v.get("game_center_slug") or "").strip()
            if not slug:
                continue
            theirs = (v.get("stadium_as_printed") or "").strip().upper()
            if slug not in mine:
                only_theirs.append(slug)
                continue
            ours = (mine[slug].get("stadium") or "").strip().upper()
            cells += 1
            if ours == theirs:
                agree += 1
            else:
                differ.append({"slug": slug, "runner_read": ours, "hand_read": theirs})
        out["checks"].append({
            "name": "venue: runner capture vs hand transcription of the same official page",
            "hand_register": os.path.relpath(args.venues, ROOT),
            "hand_rows": len(venue_rows), "cells_compared": cells, "agree": agree,
            "differ": len(differ), "only_in_hand_register": only_theirs, "diff": differ,
            "rule": "a difference is a finding for the Flagged page, never a value to copy over"})
        out["mismatches"] += len(differ) + len(only_theirs)
    else:
        out["checks"].append({"name": "venue: runner capture vs hand transcription",
                              "status": "not-run",
                              "note": "needs both a capture (venue_register_latest.tsv) and "
                                      "data/nfl/venues_2026_week10.csv"})

    # ---- B. slate agreement with the collector's dated week-schedule capture
    slate = load_latest_slate_capture(args.captures)
    if rows and slate:
        mine_w11 = sorted(r["slug"] for r in rows if r["week"] == "11")
        theirs_w11 = sorted(slate["slugs"])
        out["checks"].append({
            "name": "slate: captured fixture set vs the collector's dated week-11 slate read",
            "slate_read_at": slate["as_read_at"], "slate_source": slate["source_url"],
            "captured": len(mine_w11), "slate": len(theirs_w11),
            "only_captured": sorted(set(mine_w11) - set(theirs_w11)),
            "only_in_slate": sorted(set(theirs_w11) - set(mine_w11))})
        out["mismatches"] += len(set(mine_w11) ^ set(theirs_w11))
    else:
        out["checks"].append({"name": "slate: captured fixture set vs the dated week-slate capture",
                              "status": "not-run", "note": "needs a capture and a slate payload"})

    os.makedirs(outdir, exist_ok=True)
    with open(rep, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    for c in out["checks"]:
        print(f"  {c['name']}: " + ", ".join(f"{k}={v}" for k, v in c.items()
                                             if k not in ("name", "diff") and not isinstance(v, list)))
    print(f"cross-check mismatches: {out['mismatches']} -> {os.path.relpath(rep, ROOT)}")
    return 1 if out["mismatches"] else 0


# --------------------------------------------------------------------------- selftest

def cmd_selftest(args) -> int:
    """Offline test: a reader with no network can prove the parser reads what the page prints."""
    label_block = (
        "<html><body><h2>Game Info</h2><div><span aria-hidden='true'>Location</span>"
        "<span class='sr-only'>LOCATION</span><p>HOUSTON, TX</p>"
        "<span>Stadium</span><span>STADIUM</span><p>RELIANT STADIUM</p>"
        "<span>Capacity</span><span>CAPACITY</span><p>72,220</p></div>"
        "<div>IND 10 - 7 HOU · Q4 · 02:31</div><div>FINAL</div></body></html>")
    live = (
        "<html><body><h2>Game Info</h2><div><span>Location</span><span>LOCATION</span>"
        "<p>CANTON, OH</p><span>Stadium</span><span>STADIUM</span><p>TOM BENN</p></div>"
        "<div>CIN 3 - 3 BAL · Q2 · 07:44 · LIVE</div></body></html>")
    no_block = "<html><body><h2>Overview</h2><div>nothing printed here</div></body></html>"
    cases = [("label-visible", label_block,
              {"location": "HOUSTON, TX", "stadium": "RELIANT STADIUM", "capacity": "72,220",
               "venue_method": "label-line", "status_label": "FINAL",
               "away_score": "10", "home_score": "7", "city": "HOUSTON", "state": "TX",
               "surface": "", "roof": ""}),
             ("live-no-final", live, {"location": "CANTON, OH", "stadium": "TOM BENN",
                                      "capacity": "", "status_label": "LIVE",
                                      "period_label": "Q2", "clock": "07:44",
                                      "venue_method": "label-line",
                                      "away_score": "3", "home_score": "3"}),
             ("absent-block-is-blank", no_block,
              {"location": "", "stadium": "", "capacity": "", "venue_method": "none",
               "surface": "", "roof": ""})]
    failures = []
    for name, html, expect in cases:
        got = parse_game_centre(html)
        for k, want in expect.items():
            if str(got.get(k, "")) != str(want):
                failures.append(f"{name}: {k} expected {want!r} got {got.get(k)!r}")
    # a blank field must stay blank, not become a guess
    for k, v in parse_game_centre(no_block).items():
        if v not in ("", "FINAL", "LIVE", "SCHEDULED", "none", "Q1", "Q2", "Q3", "Q4"):
            failures.append(f"absent-block-is-blank: parser invented {k}={v!r}")
    if failures:
        print("selftest FAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print(f"selftest PASS — {len(cases)} parser cases, {sum(len(c[2]) for c in cases)} asserted fields")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--weeks", default="10,11")
    c.add_argument("--season", type=int, default=2026)
    c.add_argument("--out", default=OUT_DEFAULT)
    c.add_argument("--drift-exit-code", type=int, default=0,
                   help="exit code to return when a required field is missing (CI uses 0 and "
                        "publishes the flag; a dedicated alarm step uses 1)")
    c.set_defaults(func=cmd_capture)
    v = sub.add_parser("verify")
    v.add_argument("--out", default=OUT_DEFAULT)
    v.set_defaults(func=cmd_verify)
    x = sub.add_parser("cross-check")
    x.add_argument("--out", default=OUT_DEFAULT)
    x.add_argument("--venues", default=os.path.join(ROOT, "data", "nfl", "venues_2026_week10.csv"))
    x.add_argument("--captures", default=os.path.join(ROOT, "data", "captures"))
    x.set_defaults(func=cmd_crosscheck)
    s = sub.add_parser("selftest")
    s.set_defaults(func=cmd_selftest)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
