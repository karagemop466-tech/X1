#!/usr/bin/env python3
"""Publish the 2026-11-15 read of the official NFL.com Week 10 injury report.

Session arena-79598415-x1 (requirement: "Re-capture and republish the Week 10 injury
tables"; integration request logged by arena-ed8c600d-x1 in COORDINATION.md).

Inputs
  data/capture/2026_w10/official_nflcom_injuries_week10_transcription.psv
      347 printed rows, transcribed from https://www.nfl.com/injuries/ on 2026-11-15
      (UTC) by session arena-ed8c600d-x1. Re-checked by this session field by field
      on the Monday LAC@BAL block, Arden Key (MIA@IND), and per-club counts for all 28 clubs.
  data/nfl/snapshots/injuries_week10_2026-11-14.tsv
      The previous published table (345 rows, retrieved 2026-11-14). Kept verbatim.

Outputs (both are rewritten on every run; the 2026-11-14 snapshot is never touched)
  data/nfl/snapshots/injuries_week10_2026-11-15.tsv   dated capture, same columns as before
  data/nfl/injuries_week10.tsv                        the published table, now == 2026-11-15

Rules
  * Every printed row is written; nothing is dropped and nothing is inferred.
  * Blank on the page means blank in the file.
  * player_url is kept from the previous table where the player was already present.
    The two rows that were absent before take the URL printed on the page for them:
    https://www.nfl.com/players/calais-campbell/ and https://www.nfl.com/players/ronnie-stanley/
  * Exits 1 if a printed row cannot be given a player_url, so nothing is published blind.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PSV = ROOT / "data/capture/2026_w10/official_nflcom_injuries_week10_transcription.psv"
OLD = ROOT / "data/nfl/snapshots/injuries_week10_2026-11-14.tsv"
NEW_SNAPSHOT = ROOT / "data/nfl/snapshots/injuries_week10_2026-11-15.tsv"
PUBLISHED = ROOT / "data/nfl/injuries_week10.tsv"
# Derived copies, regenerated from PUBLISHED so that no copy can silently disagree.
CONSOLE_PSV = ROOT / "data/verify/official_injuries_2026_w10.psv"   # read by tools/build_console.py
GAME_CSV = ROOT / "data/injuries_2026_week10.csv"                    # read by tools/cross_check.py
ANNEX_CSV = ROOT / "data/injuries/injuries_2026_week10.csv"          # annex copy with snapshot_date
PRACTICE_ABBR = {"Full Participation in Practice": "Full",
                 "Limited Participation in Practice": "Limited",
                 "Did Not Participate In Practice": "DNP"}

PRINTED_URL = {
    "Calais Campbell": "https://www.nfl.com/players/calais-campbell/",
    "Ronnie Stanley": "https://www.nfl.com/players/ronnie-stanley/",
}

HEADER = ["game", "team", "player", "position", "injury", "practice_status",
          "game_status", "player_url"]


def read_psv():
    rows = []
    for ln in PSV.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        parts = ln.split("|")
        if len(parts) != 7:
            raise SystemExit(f"official row has {len(parts)} fields, expected 7: {ln!r}")
        rows.append(parts)
    return rows


def read_tsv(path):
    lines = [l for l in path.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    header = lines[0].split("\t")
    return [dict(zip(header, l.split("\t"))) for l in lines[1:]]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    targets = [NEW_SNAPSHOT, PUBLISHED, GAME_CSV, ANNEX_CSV, CONSOLE_PSV]
    before = {t: t.read_bytes() if t.exists() else None for t in targets}
    status = _build()
    if status or not check:
        return status
    changed = [t.relative_to(ROOT).as_posix() for t in targets
               if before[t] != t.read_bytes()]
    for t in targets:  # --check must not leave the tree modified
        if before[t] is None:
            t.unlink(missing_ok=True)
        else:
            t.write_bytes(before[t])
    if changed:
        print("STALE: regenerated output differs from the committed copy:", *changed, sep="\n  ")
        return 1
    print("check: committed Week 10 injury copies match a fresh build")
    return 0


def _build():
    official = read_psv()
    previous = {(r["game"], r["team"], r["player"]): r for r in read_tsv(OLD)}
    out = []
    missing_url = []
    for game, team, player, pos, injury, practice, status in official:
        prev = previous.get((game, team, player))
        url = prev["player_url"] if prev else PRINTED_URL.get(player, "")
        if not url:
            missing_url.append(f"{game} {team} {player}")
        out.append({"game": game, "team": team, "player": player, "position": pos,
                    "injury": injury, "practice_status": practice,
                    "game_status": status, "player_url": url})
    if missing_url:
        print("FAIL: no player_url for:", *missing_url, sep="\n  ")
        return 1

    header_lines = [
        "# SOURCE: https://www.nfl.com/injuries/  (\"Official Latest NFL Injury Report for Players - Week 10 of the 2026 Season\")",
        "# Retrieved 2026-11-15 (UTC) by session arena-ed8c600d-x1 (transcription); published by arena-79598415-x1 via tools/build_w10_snapshot.py.",
        "# One row per player as PRINTED by NFL.com. Nothing added, nothing inferred. Blank = blank on the page.",
        "# Previous capture (2026-11-14, 345 rows): data/nfl/snapshots/injuries_week10_2026-11-14.tsv",
    ]
    text = "\n".join(header_lines) + "\n" + "\t".join(HEADER) + "\n"
    text += "".join("\t".join(r[h] for h in HEADER) + "\n" for r in out)

    NEW_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    NEW_SNAPSHOT.write_text(text, encoding="utf-8")
    PUBLISHED.write_text(text, encoding="utf-8")
    print(f"wrote {NEW_SNAPSHOT.relative_to(ROOT)} ({len(out)} rows)")
    print(f"wrote {PUBLISHED.relative_to(ROOT)} ({len(out)} rows)")
    write_derived(out)
    return 0


def _rows_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _annex_team(code):
    """The annex and console copies spell the Rams 'LA'; the published TSV spells it 'LAR'."""
    return "LA" if code == "LAR" else code


def write_derived(out):
    """Regenerate the three derived copies from the published rows."""
    # Game-level copy: game, game_day, kickoff, network and flag_codes come from the
    # previous copy. The two rows that were absent take the block printed for LAC@BAL.
    old = _rows_csv(GAME_CSV)
    cols = list(old[0].keys())
    by_key = {(r["team_abbr"], r["player"]): r for r in old}
    block = next(r for r in old if r["game"] == "LAC at BAL")
    lines = []
    for r in out:
        base = by_key.get((r["team"], r["player"]))
        if base is None:
            base = {c: "" for c in cols}
            for c in ("game", "game_day", "kickoff_et", "network"):
                base[c] = block[c]
            base["team_abbr"] = r["team"]
            base["player"] = r["player"]
        new = dict(base)
        new.update({"position": r["position"], "injury": r["injury"],
                    "practice_status": r["practice_status"],
                    "game_status": r["game_status"], "player_url": r["player_url"],
                    "source_url": "https://www.nfl.com/injuries/"})
        lines.append(new)
    with open(GAME_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\r\n")
        w.writeheader()
        w.writerows(lines)

    # Annex copy: week, team, player, position, injuries, practice_status, game_status,
    # player_page, report_source, snapshot_date.
    with open(ANNEX_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["week", "team", "player", "position", "injuries", "practice_status",
                    "game_status", "player_page", "report_source", "snapshot_date"])
        for r in out:
            w.writerow([10, _annex_team(r["team"]), r["player"], r["position"], r["injury"],
                        r["practice_status"], r["game_status"], r["player_url"],
                        "https://www.nfl.com/injuries/", "snapshot 2026-11-15"])

    # Console copy: the abbreviated pipe-delimited form the console builder reads.
    with open(CONSOLE_PSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="|", lineterminator="\n")
        w.writerow(["TEAM", "PLAYER", "POS", "INJURY", "PRACTICE", "GAMESTATUS"])
        for r in out:
            w.writerow([_annex_team(r["team"]), r["player"], r["position"], r["injury"],
                        PRACTICE_ABBR[r["practice_status"]] if r["practice_status"] else "",
                        r["game_status"]])
    print(f"wrote derived copies: {GAME_CSV.name}, {ANNEX_CSV.name}, {CONSOLE_PSV.name}")


if __name__ == "__main__":
    sys.exit(main())
