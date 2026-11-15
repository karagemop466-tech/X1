#!/usr/bin/env python3
"""Row-by-row comparison of the published Week 10 injury table against the
official NFL.com injury page as re-read on 2026-11-15 (session arena-ed8c600d-x1).

Inputs
  data/capture/2026_w10/official_nflcom_injuries_week10_transcription.psv  (official page, transcribed)
  data/nfl/injuries_week10.tsv                                              (published table)

Outputs
  data/capture/2026_w10/recapture_report.json
  data/capture/2026_w10/recapture_report.md

Rules
  * A row is matched on (game, team, player). Matches are compared on injury,
    practice_status and game_status. Blank means blank on the page.
  * Nothing is inferred. A row present on one side only is reported as such.
  * Exit status is 1 if any official row is missing from the published table or
    any field differs, so CI fails loudly rather than publishing a silent gap.
"""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL = ROOT / "data/capture/2026_w10/official_nflcom_injuries_week10_transcription.psv"
PUBLISHED = ROOT / "data/nfl/injuries_week10.tsv"
OUT_DIR = ROOT / "data/capture/2026_w10"
SOURCE_URL = "https://www.nfl.com/injuries/"

FIELDS = ["injury", "practice_status", "game_status"]


def read_official():
    rows = []
    for ln in OFFICIAL.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        parts = ln.split("|")
        if len(parts) != 7:
            raise SystemExit(f"official row has {len(parts)} fields, expected 7: {ln!r}")
        game, team, player, pos, injury, practice, status = parts
        rows.append({"game": game, "team": team, "player": player, "position": pos,
                     "injury": injury, "practice_status": practice, "game_status": status})
    return rows


def read_published():
    lines = [l for l in PUBLISHED.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        cells = ln.split("\t")
        if len(cells) != len(header):
            raise SystemExit(f"published row has {len(cells)} cells, expected {len(header)}: {ln!r}")
        d = dict(zip(header, cells))
        rows.append({"game": d["game"], "team": d["team"], "player": d["player"],
                     "position": d["position"], "injury": d["injury"],
                     "practice_status": d["practice_status"], "game_status": d["game_status"]})
    return rows


def key(r):
    return (r["game"], r["team"], r["player"])


def main():
    off = read_official()
    pub = read_published()

    off_idx, pub_idx = {}, {}
    dup_off = [k for k, c in Counter(key(r) for r in off).items() if c > 1]
    dup_pub = [k for k, c in Counter(key(r) for r in pub).items() if c > 1]
    for r in off:
        off_idx[key(r)] = r
    for r in pub:
        pub_idx[key(r)] = r

    missing_in_published = [off_idx[k] for k in off_idx if k not in pub_idx]
    extra_in_published = [pub_idx[k] for k in pub_idx if k not in off_idx]
    field_diffs = []
    for k in off_idx:
        if k in pub_idx:
            for f in FIELDS:
                if off_idx[k][f] != pub_idx[k][f]:
                    field_diffs.append({"game": k[0], "team": k[1], "player": k[2], "field": f,
                                        "official": off_idx[k][f], "published": pub_idx[k][f]})

    per_game_off = Counter(r["game"] for r in off)
    per_game_pub = Counter(r["game"] for r in pub)
    games = sorted(set(per_game_off) | set(per_game_pub))
    per_game = [{"game": g, "official_rows": per_game_off.get(g, 0),
                 "published_rows": per_game_pub.get(g, 0)} for g in games]

    # Team-level: clubs with zero official rows, zero published rows
    teams_off = Counter(r["team"] for r in off)
    teams_pub = Counter(r["team"] for r in pub)
    teams = sorted(set(teams_off) | set(teams_pub))
    per_team = [{"team": t, "official_rows": teams_off.get(t, 0), "published_rows": teams_pub.get(t, 0)}
                for t in teams]

    # Summary counts printed on the published page (app/injuries.html, 2026-11-14 capture)
    page_claims = {"Out": 66, "Questionable": 84, "Doubtful": 10, "no game status": 185}
    official_summary = {
        "Out": sum(1 for r in off if r["game_status"] == "Out"),
        "Questionable": sum(1 for r in off if r["game_status"] == "Questionable"),
        "Doubtful": sum(1 for r in off if r["game_status"] == "Doubtful"),
        "no game status": sum(1 for r in off if r["game_status"] == ""),
    }
    rows_with_any_mismatch = len({(d["game"], d["team"], d["player"]) for d in field_diffs})
    game_status_blank_official = sum(1 for r in off if r["game_status"] == "")
    game_status_blank_published = sum(1 for r in pub if r["game_status"] == "")

    sha = hashlib.sha256(OFFICIAL.read_bytes()).hexdigest()
    report = {
        "session": "arena-ed8c600d-x1",
        "source_url": SOURCE_URL,
        "official_capture_file": str(OFFICIAL.relative_to(ROOT)),
        "official_capture_sha256": sha,
        "official_capture_note": "SHA-256 of the session's transcription file. The fetch tool does not expose raw page bytes, so this is a hash of the transcription, not of the HTTP response.",
        "published_file": str(PUBLISHED.relative_to(ROOT)),
        "official_rows": len(off),
        "published_rows": len(pub),
        "games_official": len(per_game_off),
        "games_published": len(per_game_pub),
        "clubs_official": len(teams_off),
        "clubs_published": len(teams_pub),
        "duplicate_keys_official": dup_off,
        "duplicate_keys_published": dup_pub,
        "missing_in_published": missing_in_published,
        "extra_in_published": extra_in_published,
        "field_mismatches": field_diffs,
        "rows_with_any_field_mismatch": rows_with_any_mismatch,
        "summary_counts_official": official_summary,
        "summary_counts_printed_on_published_page": page_claims,
        "blank_game_status_official": game_status_blank_official,
        "blank_game_status_published": game_status_blank_published,
        "per_game": per_game,
        "per_club": per_team,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "recapture_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md = []
    md.append("# Week 10 official injury report — row-level re-capture check\n")
    md.append(f"Source: {SOURCE_URL} (NFL.com, read 2026-11-15 UTC by session `arena-ed8c600d-x1`).\n")
    md.append(f"Official transcription SHA-256: `{sha}`\n")
    md.append(f"- Official rows: **{len(off)}** across {len(per_game_off)} games and {len(teams_off)} clubs")
    md.append(f"- Published rows (`data/nfl/injuries_week10.tsv`): **{len(pub)}** across {len(per_game_pub)} games and {len(teams_pub)} clubs")
    md.append(f"- Official rows missing from published table: **{len(missing_in_published)}**")
    md.append(f"- Published rows not on official page: **{len(extra_in_published)}**")
    md.append(f"- Field mismatches on matched rows (injury / practice / game status): **{len(field_diffs)}** cells in **{rows_with_any_mismatch}** rows")
    md.append(f"- Summary counts, official page vs. counts printed on the published page: {official_summary} vs {page_claims}\n")
    md.append("## Per game\n\n| Game | Official rows | Published rows |\n|---|---:|---:|")
    for g in per_game:
        md.append(f"| {g['game']} | {g['official_rows']} | {g['published_rows']} |")
    md.append("\n## Per club\n\n| Club | Official rows | Published rows |\n|---|---:|---:|")
    for t in per_team:
        md.append(f"| {t['team']} | {t['official_rows']} | {t['published_rows']} |")
    if missing_in_published:
        md.append("\n## Missing from published table\n\n| Game | Club | Player | Injury | Practice | Game status |\n|---|---|---|---|---|---|")
        for r in missing_in_published:
            md.append(f"| {r['game']} | {r['team']} | {r['player']} | {r['injury']} | {r['practice_status']} | {r['game_status']} |")
    if extra_in_published:
        md.append("\n## Published but not on official page\n\n| Game | Club | Player |\n|---|---|---|")
        for r in extra_in_published:
            md.append(f"| {r['game']} | {r['team']} | {r['player']} |")
    if field_diffs:
        md.append("\n## Field mismatches\n\n| Game | Club | Player | Field | Official | Published |\n|---|---|---|---|---|---|")
        for d in field_diffs:
            md.append(f"| {d['game']} | {d['team']} | {d['player']} | {d['field']} | {d['official']} | {d['published']} |")
    (OUT_DIR / "recapture_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"official rows={len(off)} published rows={len(pub)} "
          f"missing={len(missing_in_published)} extra={len(extra_in_published)} "
          f"field_mismatches={len(field_diffs)} dup_off={len(dup_off)} dup_pub={len(dup_pub)}")
    bad = missing_in_published or extra_in_published or field_diffs or dup_off or dup_pub
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
