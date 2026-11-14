"""Pipeline orchestrator.

Fetches every dataset from an official source, verifies what it can, and writes
`data/*.json`. Designed to be run unattended by GitHub Actions: it never raises,
it reports, and it refuses to overwrite a good dataset with an empty one.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import htmlutil as H
from . import club_registry, model_correlation, repo_review
from . import parsers as P
from . import sources as S
from .http import fetch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def page_title(html: str) -> str:
    match = TITLE_RE.search(html or "")
    return H._squash(match.group(1)) if match else ""


# ------------------------------------------------------------------ io helpers
def read_json(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:  # noqa: BLE001
        return None


def write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False, sort_keys=False)
        handle.write("\n")


def verification_block(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    verified = sum(1 for r in rows if r.get("_verified"))
    unverified_cells = sum(len(r.get("_unverified") or []) for r in rows)
    flagged = [r for r in rows if not r.get("_verified")]
    by_flag: Dict[str, int] = {}
    for row in flagged:
        for flag in row.get("_flags") or ["unverified value"]:
            by_flag[flag] = by_flag.get(flag, 0) + 1
    return {
        "rows": len(rows),
        "rows_verified": verified,
        "rows_flagged": len(flagged),
        "unverified_cells": unverified_cells,
        "flagged_reasons": by_flag,
    }


def dataset(
    name: str,
    title: str,
    rows: List[Dict[str, Any]],
    columns: List[str],
    source: Dict[str, str],
    **extra: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "dataset": name,
        "title": title,
        "generated_at": now_iso(),
        "source": source,
        "columns": columns,
        "rows": rows,
        "verification": verification_block(rows),
    }
    payload.update(extra)
    return payload


def guard_write(path: str, payload: Dict[str, Any], report: Dict[str, Any], key: str) -> None:
    """Write unless the new run produced nothing while we already had rows."""
    previous = read_json(path)
    new_rows = payload.get("row_count", len(payload.get("rows", [])))
    if previous and new_rows == 0:
        report["datasets"][key] = {
            "status": "kept_previous",
            "reason": "this run produced 0 rows; previous verified data retained",
            "previous_rows": len(previous.get("rows", [])),
        }
        return
    write_json(path, payload)
    report["datasets"][key] = {
        "status": "written" if new_rows else "empty",
        "rows": new_rows,
    }


# -------------------------------------------------------------------- datasets
def build_standings(report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    result = fetch(S.STANDINGS_URL)
    if not result.ok:
        report["errors"].append({"dataset": "standings", "url": S.STANDINGS_URL, "error": result.error})
        return None
    doc = H.parse(result.body)
    parsed = P.parse_standings(doc, S.STANDINGS_URL, now_iso())
    rows = parsed["rows"]
    if not rows:
        report["errors"].append({"dataset": "standings", "url": S.STANDINGS_URL, "error": "0 rows parsed"})
        return None
    payload = dataset(
        "standings",
        "2026 NFL League Standings",
        rows,
        parsed["columns"],
        {
            "url": S.STANDINGS_URL,
            "label": "NFL.com — 2026 League Standings (regular season)",
            "org": "NFL",
        },
        season=2026,
        week=None,
        columns_officially_labelled=parsed["columns_officially_labelled"],
        consistency_check=parsed["consistency_check"],
        note=parsed["note"],
        tiebreak_source_url=S.TIEBREAK_URL,
    )
    guard_write(os.path.join(DATA_DIR, "standings.json"), payload, report, "standings")
    return payload


def team_index_from(standings: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    index: Dict[str, Dict[str, str]] = {}
    for row in (standings or {}).get("rows", []):
        abbrev = row.get("team_abbrev")
        slug = row.get("team_slug")
        if not abbrev or not slug:
            continue
        index[abbrev] = {
            "slug": slug,
            "name": row.get("team_name"),
            "nick": slug.split("-")[-1].capitalize(),
        }
    return index


def nick_map(index: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for abbrev, meta in index.items():
        out[(meta.get("nick") or "").lower()] = abbrev
        out[(meta.get("name") or "").lower()] = abbrev
    return out


def build_injuries(report, team_index, nicks) -> Optional[Dict[str, Any]]:
    result = fetch(S.INJURIES_URL)
    if not result.ok:
        report["errors"].append({"dataset": "injuries", "url": S.INJURIES_URL, "error": result.error})
        return None
    doc = H.parse(result.body)
    parsed = P.parse_injuries(doc, S.INJURIES_URL, team_index, nicks)
    rows = parsed["rows"]
    payload = dataset(
        "injuries",
        f"Official NFL Injury Report — Week {parsed.get('week')}, {parsed.get('season')}",
        rows,
        ["team_name", "player", "position", "injuries", "practice_status", "game_status",
         "game_date", "kickoff_et", "broadcast"],
        {
            "url": S.INJURIES_URL,
            "label": "NFL.com — Official NFL Injury Report (current week)",
            "org": "NFL",
        },
        season=parsed.get("season"),
        week=parsed.get("week"),
        tables_parsed=parsed.get("tables_parsed"),
        designation_policy_url=S.INJURY_POLICY_URL,
        note=(
            "Designations are the league's own: practice status is Did Not Participate / "
            "Limited Participation / Full Participation; game status is Out / Doubtful / "
            "Questionable. Blank cells mean the official page left the field empty."
        ),
    )
    guard_write(os.path.join(DATA_DIR, "injuries.json"), payload, report, "injuries")
    return payload


def build_club_registry(report, team_index) -> Dict[str, str]:
    """Read the league's own list of official club sites."""
    result = fetch(S.CLUB_REGISTRY_URL, retries=2)
    html = result.body if result.ok else None
    if not result.ok:
        report["errors"].append(
            {"dataset": "club_registry", "url": S.CLUB_REGISTRY_URL, "error": result.error}
        )
    log: List[Dict[str, object]] = []
    mapping = club_registry.resolve(html, log)
    report["club_registry"] = log or [{"source": "fallback list in pipeline/sources.py"}]
    by_abbrev: Dict[str, str] = {}
    for abbrev, meta in team_index.items():
        domain = S.club_domain(abbrev, mapping, meta.get("slug", ""))
        if domain:
            by_abbrev[abbrev] = domain
    return by_abbrev


def build_depth_charts(report, team_index, club_domains=None) -> Optional[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    sources_seen: List[Dict[str, Any]] = []
    for abbrev, meta in sorted(team_index.items()):
        attempts: List[Dict[str, Any]] = []
        best = None
        for path in S.DEPTH_CHART_PATHS:
            domain = (club_domains or {}).get(abbrev) or S.club_domain(
                abbrev, None, meta.get("slug", "")
            )
            if not domain:
                attempts.append({"url": None, "error": "no official club domain for this team"})
                break
            url = f"https://www.{domain}{path}"
            if not url:
                attempts.append({"url": None, "error": "no club domain configured"})
                break
            result = fetch(url, retries=3, backoff=3.0, sleep=1.2)
            if not result.ok:
                attempts.append({"url": url, "error": result.error})
                continue
            title = page_title(result.body)
            doc = H.parse(result.body)
            parsed = P.parse_depth_chart(doc, url, abbrev, meta.get("name") or abbrev)
            attempts.append(
                {"url": url, "status": result.status, "title": title,
                 "tables": len(doc.tables), "rows": len(parsed["rows"])}
            )
            if "depth chart" in title.lower() and parsed["rows"]:
                best = (url, title, parsed)
                break
            time.sleep(1.0)
        if best is None:
            report["errors"].append(
                {"dataset": "depth_charts", "team": abbrev, "attempts": attempts}
            )
            sources_seen.append(
                {"team_abbrev": abbrev, "url": "", "rows": 0, "page_title": "",
                 "attempts": attempts, "status": "unavailable"}
            )
            continue
        url, title, parsed = best
        rows.extend(parsed["rows"])
        sources_seen.append(
            {"team_abbrev": abbrev, "url": url, "rows": len(parsed["rows"]),
             "page_title": title, "attempts": attempts, "status": "ok"}
        )
    payload = dataset(
        "depth_charts",
        "Official Club Depth Charts (starters through 4th string)",
        rows,
        ["team_name", "unit", "position", "depth", "player"],
        {
            "url": "https://www.nfl.com/teams/",
            "label": "Official club sites (one depth chart per team)",
            "org": "Club",
        },
        season=2026,
        per_team_sources=sources_seen,
        note=(
            "Depth order is read left to right exactly as each club prints it: column 1 is "
            "the starter, column 2 the 2nd string, and so on. Where a club leaves a column "
            "empty the position simply has no listed player at that depth."
        ),
    )
    guard_write(os.path.join(DATA_DIR, "depth_charts.json"), payload, report, "depth_charts")
    return payload


def build_team_stats(report, team_index) -> Optional[Dict[str, Any]]:
    tables: List[Dict[str, Any]] = []
    for spec in S.TEAM_STAT_CATEGORIES:
        url = S.team_stat_url(spec["side"], spec["category"])
        result = fetch(url, retries=2)
        if not result.ok:
            report["errors"].append({"dataset": "team_stats", "url": url, "error": result.error})
            continue
        doc = H.parse(result.body)
        parsed = P.parse_team_stats(doc, url, spec["label"], team_index)
        if not parsed.get("rows"):
            report["errors"].append({"dataset": "team_stats", "url": url, "error": "0 rows parsed"})
            continue
        tables.append(
            {
                "id": f"{spec['side']}_{spec['category']}",
                "title": spec["label"],
                "source_url": url,
                "source_label": f"NFL.com — 2026 Team Stats, {spec['label']}",
                "source_org": "NFL",
                "columns": parsed["columns"],
                "columns_officially_labelled": parsed["columns_officially_labelled"],
                "header_raw": parsed.get("header_raw"),
                "rows": parsed["rows"],
            }
        )
    rows = [row for table in tables for row in table["rows"]]
    payload = dataset(
        "team_stats",
        "2026 NFL Team Stats (official)",
        rows,
        [],
        {
            "url": S.team_stat_url("offense", "passing"),
            "label": "NFL.com — 2026 Team Stats",
            "org": "NFL",
        },
        season=2026,
        tables=tables,
        row_count=len(rows),
        note=(
            "NFL.com prints these stat tables without a text header row, so column meaning "
            "cannot be confirmed from the source. Values are published exactly as printed, "
            "with positional column labels, and the whole table set is flagged for review."
        ),
    )
    guard_write(os.path.join(DATA_DIR, "team_stats.json"), payload, report, "team_stats")
    return payload


# ------------------------------------------------------- derived: deficiencies
STATUS_WEIGHT = {"out": 3, "doubtful": 2, "questionable": 1}


def _status_rank(status: Optional[str]) -> int:
    return STATUS_WEIGHT.get((status or "").strip().lower(), 0)


def build_deficiency(report, depth_payload, injury_payload, team_index):
    if not depth_payload or not injury_payload:
        report["errors"].append({"dataset": "deficiency", "error": "missing depth chart or injury input"})
        return None

    injury_by_player: Dict[str, Dict[str, Any]] = {}
    for row in injury_payload.get("rows", []):
        key = (row.get("team_abbrev"), (row.get("player") or "").strip().lower())
        injury_by_player[key] = row

    by_slot: Dict[Any, List[Dict[str, Any]]] = {}
    for row in depth_payload.get("rows", []):
        by_slot.setdefault(
            (row.get("team_abbrev"), row.get("unit"), row.get("position"), row.get("slot")), []
        ).append(row)

    rows: List[Dict[str, Any]] = []
    for (abbrev, unit, position, slot), entries in sorted(
        by_slot.items(),
        key=lambda kv: (str(kv[0][0]), str(kv[0][1]), str(kv[0][2]), kv[0][3] or 0),
    ):
        entries = sorted(entries, key=lambda r: r.get("depth") or 99)
        starter = entries[0] if entries else None
        if not starter:
            continue
        starter_key = (abbrev, (starter.get("player") or "").strip().lower())
        starter_inj = injury_by_player.get(starter_key)
        starter_status = (starter_inj or {}).get("game_status")
        starter_practice = (starter_inj or {}).get("practice_status")

        replacement = None
        replacement_status = None
        for candidate in entries[1:]:
            key = (abbrev, (candidate.get("player") or "").strip().lower())
            inj = injury_by_player.get(key)
            status = (inj or {}).get("game_status")
            if _status_rank(status) >= 3:  # OUT -> keep walking down the chart
                continue
            replacement = candidate
            replacement_status = status
            break
        if replacement is None and len(entries) > 1:
            replacement = entries[1]
            replacement_status = (
                injury_by_player.get(
                    (abbrev, (replacement.get("player") or "").strip().lower()), {}
                ).get("game_status")
            )

        severity = _status_rank(starter_status)
        flags: List[str] = []
        if severity >= 2 and replacement is None:
            flags.append("no replacement printed on the official depth chart")
        if severity >= 2 and replacement is not None and (replacement.get("depth") or 2) >= 3:
            flags.append(
                f"starter out/doubtful — {replacement.get('depth')} string backup is next up"
            )
        if starter_inj is None:
            flags.append("starter does not appear on the current official injury report")

        values = {
            "team_abbrev": abbrev,
            "team_name": team_index.get(abbrev, {}).get("name"),
            "unit": unit,
            "position": position,
            "slot": slot,
            "starter": starter.get("player"),
            "starter_game_status": starter_status,
            "starter_practice_status": starter_practice,
            "replacement": (replacement or {}).get("player"),
            "replacement_depth": (replacement or {}).get("depth"),
            "replacement_game_status": replacement_status,
            "depth_listed": len(entries),
            "severity": severity,
        }
        source_urls = [starter.get("_source_url")]
        if replacement is not None:
            source_urls.append(replacement.get("_source_url"))
        if starter_inj is not None:
            source_urls.append(starter_inj.get("_source_url"))
        row = P.make_row(
            values,
            source_url=starter.get("_source_url") or "",
            source_label="Official club depth chart + NFL.com official injury report",
            source_org="Club + NFL",
            flags=flags,
            allow_blank={"starter_game_status", "starter_practice_status", "replacement",
                         "replacement_depth", "replacement_game_status"},
        )
        row["_source_urls"] = [u for u in dict.fromkeys(source_urls) if u]
        row["_flagged_for_attention"] = severity > 0
        rows.append(row)

    rows.sort(key=lambda r: (-(r.get("severity") or 0), str(r.get("team_abbrev")), str(r.get("position"))))
    payload = dataset(
        "deficiency",
        "Lineup deficiency watch: starters down, backup who has to replace them",
        rows,
        ["team_name", "unit", "position", "slot", "starter", "starter_game_status",
         "starter_practice_status", "replacement", "replacement_depth",
         "replacement_game_status", "severity"],
        {
            "url": S.INJURIES_URL,
            "label": "Derived from official club depth charts + NFL.com injury report",
            "org": "Derived",
        },
        season=2026,
        severity_scale={"out": 3, "doubtful": 2, "questionable": 1, "not listed": 0},
        note=(
            "Derived, not scraped: the starter is column 1 of the club's own depth chart and "
            "the replacement is the next column whose player is not listed Out on the "
            "official injury report. Every row links to both official sources."
        ),
    )
    guard_write(os.path.join(DATA_DIR, "deficiency.json"), payload, report, "deficiency")
    return payload


# ----------------------------------------------------------------------- probe
def build_probe(report) -> Dict[str, Any]:
    probe: Dict[str, Any] = {"generated_at": now_iso(), "urls": []}
    for url in S.PROBE_URLS:
        result = fetch(url, retries=1)
        entry: Dict[str, Any] = {
            "url": url,
            "ok": result.ok,
            "status": result.status,
            "error": result.error,
        }
        if result.ok:
            doc = H.parse(result.body)
            entry["title"] = page_title(result.body)
            entry["table_count"] = len(doc.tables)
            entry["tables"] = [
                {
                    "rows": len(t["rows"]),
                    "cols": max((len(r) for r in t["rows"]), default=0),
                    "header": t.get("header"),
                    "first_row": [H.cell_text(c) for c in t["rows"][0]] if t["rows"] else [],
                }
                for t in doc.tables[:4]
            ]
        probe["urls"].append(entry)
    write_json(os.path.join(DATA_DIR, "_probe.json"), probe)
    return probe


# ------------------------------------------------------------------------ main
def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv or [])
    only = argv[0] if argv else None

    report: Dict[str, Any] = {
        "generated_at": now_iso(),
        "branch_note": "pipeline run",
        "datasets": {},
        "errors": [],
    }

    standings = build_standings(report)
    team_index = team_index_from(standings)
    nicks = nick_map(team_index)
    report["teams_resolved"] = sorted(team_index)

    injuries = build_injuries(report, team_index, nicks)
    club_domains = build_club_registry(report, team_index)
    depth = build_depth_charts(report, team_index, club_domains)
    stats = build_team_stats(report, team_index)
    deficiency = build_deficiency(report, depth, injuries, team_index)

    # Derived datasets. These read the freshly written files above, so a failed
    # upstream fetch degrades them instead of producing numbers from thin air.
    for builder in (model_correlation.main, repo_review.main):
        try:
            builder()
            report["datasets"][builder.__module__.split(".")[-1]] = {"status": "written"}
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(
                {"dataset": builder.__module__, "error": f"{type(exc).__name__}: {exc}"}
            )

    if only in (None, "probe"):
        build_probe(report)

    report["finished_at"] = now_iso()
    write_json(os.path.join(DATA_DIR, "_run_report.json"), report)
    print(json.dumps(report, indent=1)[:4000])
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
