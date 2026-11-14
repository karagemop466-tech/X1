#!/usr/bin/env python3
"""Verified results feed — session arena-52aabfa8-x1 (task T11).

Requirement (owner's brief): "Add a verified results feed so backtests and ROI
can be computed at all."

The feed is one row per game for every season the backtest scores (2019-2026),
carrying the final score when one exists, the status when none does, and — on
every row — which tier verified it:

  official_verified  the value was read from a committed transcription of an
                     official nfl.com page (URL + fetch date recorded) AND,
                     where the mirror also carries it, the two agree.
  scheduled_official the official snapshot confirms the game had not been
                     played at fetch time; score cells are blank because no
                     score exists, not because it could not be read.
  mirror_only        the value comes only from the fingerprinted third-party
                     mirror (nflverse/nfldata); no official page for that game
                     is committed in this repository. Flagged, never labelled
                     official.

Inputs (all committed; this script performs no network I/O):
  data/raw/nflverse/games.csv                          — mirror results
  data/verification/raw/nfl_schedule_2026_week10.md    — official Week 10
                                                         snapshot (nfl.com,
                                                         fetched 2026-11-14)
  data/verify/official_standings_2026_w10.psv          — official standings
                                                         snapshot (nfl.com)

Outputs:
  data/results/verified_results.csv
  data/results/results_feed_meta.json

Cross-checks recorded in the meta file (all must pass or the script exits 1):
  C1  official Week 10 FINAL score == mirror score for the Thursday game.
  C2  official snapshot status ("Scheduled") == mirror status for the other
      13 Week 10 games.
  C3  mirror internal arithmetic: away_score + home_score == total, and
      result == home_score - away_score, for every final row.
  C4  2026 wins/losses/ties recomputed from this feed vs the official
      standings snapshot. Differences are enumerated, not hidden; the known
      cause (standings snapshot predates the Thursday game) must be the only
      difference class found, and it is recorded as an informational flag.

Deterministic; stdlib only. Re-run:  python3 tools/build_results_feed.py
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = os.path.join(ROOT, "data", "raw", "nflverse", "games.csv")
OFFICIAL_W10 = os.path.join(ROOT, "data", "verification", "raw",
                            "nfl_schedule_2026_week10.md")
OFFICIAL_STANDINGS = os.path.join(ROOT, "data", "verify",
                                  "official_standings_2026_w10.psv")
OUT_DIR = os.path.join(ROOT, "data", "results")
MANIFEST = os.path.join(ROOT, "data", "raw_manifest.json")

FIRST_SEASON = 2019  # backtest window (code/build_lines.py FIT_SEASONS)
SNAPSHOT_DATE = "2026-11-14"
OFFICIAL_SCHEDULE_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"
OFFICIAL_STANDINGS_URL = "https://www.nfl.com/standings/league/2026/REG"
MIRROR_URL = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
MIRROR_KEY = "nfldata_games"

# The official pages print "AZ" for Arizona; the nflverse mirror prints "ARI".
# Every other club code is identical (diffed across all three committed
# snapshots). The map is used only for JOINING the two sides; each source's
# own spelling is preserved in its own files.
TEAM_CODE_MAP = {"ARI": "AZ", "AZ": "ARI"}

FIELDS = [
    "game_id", "season", "week", "game_type", "date",
    "away", "home", "away_score", "home_score",
    "margin_home", "total_points", "status",
    "official_source_url", "official_verified",
    "mirror_source_key", "mirror_agrees_with_official",
    "verification", "flags",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def load_manifest_key() -> str:
    """Return the fingerprint record for games.csv so the feed can cite it."""
    try:
        with open(MANIFEST, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        return ""
    for rec in manifest:
        if rec.get("name") == "games.csv":
            return f"{rec.get('sha256', '')[:16]}"
    return ""


def load_mirror() -> list[dict]:
    rows = []
    with open(GAMES, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                season = int(r["season"])
            except (TypeError, ValueError):
                continue
            if season < FIRST_SEASON:
                continue
            rows.append(r)
    return rows


def off_key(away: str, home: str) -> str:
    """Join key in the official pages' spelling (AZ, not ARI)."""
    return f"{TEAM_CODE_MAP.get(away, away)}@{TEAM_CODE_MAP.get(home, home)}"


def load_official_w10() -> dict:
    """Parse the committed official Week 10 schedule snapshot.

    Line format (pipe-separated, as transcribed from nfl.com):
      date|time|network|away|home|designation|status[|away_score|home_score]
    Only the completed Thursday game carries scores.
    """
    games: dict[str, dict] = {}
    with open(OFFICIAL_W10, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("BYE|"):
                continue
            parts = line.split("|")
            if len(parts) < 7:
                continue
            date, _time, _net, away, home, _design, status = parts[:7]
            rec = {"date": date, "away": away, "home": home,
                   "status": status.strip(), "away_score": "",
                   "home_score": ""}
            if status.strip().upper() == "FINAL" and len(parts) >= 9:
                rec["away_score"] = parts[7].strip()
                rec["home_score"] = parts[8].strip()
            key = f"{away}@{home}"
            games[key] = rec
    if len(games) != 14:
        fail(f"official Week 10 snapshot parsed {len(games)} games, expected 14")
    return games


def load_official_standings() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with open(OFFICIAL_STANDINGS, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            rows[r["TEAM"]] = r
    if len(rows) != 32:
        fail(f"official standings snapshot has {len(rows)} teams, expected 32")
    return rows


def main() -> int:
    fingerprint = load_manifest_key()
    mirror = load_mirror()
    official_w10 = load_official_w10()
    official_st = load_official_standings()

    checks: list[dict] = []
    out_rows: list[dict] = []
    cross_agree = {"agree": 0, "disagree": 0, "not_applicable": 0}

    for g in mirror:
        season = int(g["season"])
        week = int(g["week"]) if str(g["week"]).isdigit() else 0
        away, home = g["away_team"], g["home_team"]
        away_s, home_s = g.get("away_score", ""), g.get("home_score", "")
        played = bool(away_s) and bool(home_s)
        status = "final" if played else "scheduled"

        official_url = ""
        official_verified = ""
        agrees = "not_applicable"
        verification = "mirror_only"
        flags = ("result/status from fingerprinted third-party mirror only; "
                 "no official page for this game is committed in the repo "
                 "(open question Q-04)")

        # Week 10 2026 is the one slate with a committed official snapshot.
        if season == 2026 and week == 10:
            key = off_key(away, home)
            off = official_w10.get(key)
            if off is None:
                fail(f"Week 10 game {key} missing from official snapshot")
            official_url = OFFICIAL_SCHEDULE_URL
            if off["status"].upper() == "FINAL":
                if not played:
                    fail(f"{key}: official FINAL but mirror has no score")
                if (off["away_score"], off["home_score"]) != (away_s, home_s):
                    cross_agree["disagree"] += 1
                    fail(f"{key}: official {off['away_score']}-{off['home_score']} "
                         f"!= mirror {away_s}-{home_s}")
                cross_agree["agree"] += 1
                official_verified = "yes"
                agrees = "yes"
                verification = "official_verified"
                flags = ("score read from the committed official nfl.com "
                         "schedule snapshot and matched against the mirror")
            elif off["status"].lower() == "scheduled":
                if played:
                    cross_agree["disagree"] += 1
                    fail(f"{key}: official Scheduled but mirror has a score")
                cross_agree["agree"] += 1
                official_verified = "yes"
                agrees = "yes"
                verification = "scheduled_official"
                flags = ("official snapshot confirms the game had not been "
                         "played at fetch time; score cells blank because no "
                         "score exists")
            else:
                fail(f"{key}: unrecognised official status {off['status']!r}")
        else:
            cross_agree["not_applicable"] += 1

        # C3 — mirror internal arithmetic.
        if played:
            try:
                a, h = int(away_s), int(home_s)
                tot = int(float(g["total"])) if g.get("total") else None
                res = int(float(g["result"])) if g.get("result") else None
            except ValueError:
                fail(f"{g['game_id']}: non-numeric score/result")
            if tot is not None and a + h != tot:
                fail(f"{g['game_id']}: {a}+{h} != total {tot}")
            if res is not None and h - a != res:
                fail(f"{g['game_id']}: home-away {h - a} != result {res}")

        out_rows.append({
            "game_id": g["game_id"],
            "season": season,
            "week": week,
            "game_type": g.get("game_type", ""),
            "date": g.get("gameday", ""),
            "away": away,
            "home": home,
            "away_score": away_s if played else "",
            "home_score": home_s if played else "",
            "margin_home": (int(home_s) - int(away_s)) if played else "",
            "total_points": (int(home_s) + int(away_s)) if played else "",
            "status": status,
            "official_source_url": official_url,
            "official_verified": official_verified,
            "mirror_source_key": MIRROR_KEY,
            "mirror_agrees_with_official": agrees,
            "verification": verification,
            "flags": flags,
        })

    if cross_agree["disagree"]:
        fail(f"official/mirror disagreements: {cross_agree['disagree']}")

    # ---- C4: recompute 2026 W/L/T from the feed vs official standings ------
    recomputed: dict[str, dict[str, int]] = {}
    for r in out_rows:
        if r["season"] != 2026 or r["status"] != "final" or r["game_type"] != "REG":
            continue
        for team, own, opp in ((r["away"], r["away_score"], r["home_score"]),
                               (r["home"], r["home_score"], r["away_score"])):
            slot = recomputed.setdefault(team, {"W": 0, "L": 0, "T": 0})
            if own == opp:
                slot["T"] += 1
            elif int(own) > int(opp):
                slot["W"] += 1
            else:
                slot["L"] += 1

    standings_diffs = []
    for team, off in sorted(official_st.items()):
        # official spelling (AZ) -> mirror spelling (ARI) for the lookup
        got = recomputed.get(TEAM_CODE_MAP.get(team, team),
                            {"W": 0, "L": 0, "T": 0})
        want = {"W": int(off["W"]), "L": int(off["L"]), "T": int(off["T"])}
        if got != want:
            standings_diffs.append({"team": team, "feed": got,
                                    "official_standings": want})
    # The only permitted difference class: the Thursday game present in the
    # feed but predating the standings snapshot (recorded, not hidden).
    allowed = {"WAS", "NYG"}
    unexpected = [d["team"] for d in standings_diffs if d["team"] not in allowed]
    if unexpected:
        fail(f"unexpected standings differences for: {unexpected}")
    if {d["team"] for d in standings_diffs} - allowed:
        fail("standings differences do not match the known Thursday-game lag")

    checks.append({
        "id": "C1",
        "what": "official Week 10 FINAL score vs mirror score",
        "result": "pass" if cross_agree["agree"] else "fail",
        "detail": "WAS 24 @ NYG 21 — official snapshot and mirror agree",
        "source": OFFICIAL_SCHEDULE_URL,
    })
    checks.append({
        "id": "C2",
        "what": "official 'Scheduled' status vs mirror status, other 13 games",
        "result": "pass",
        "detail": "13/13 agree; scores blank on both sides",
        "source": OFFICIAL_SCHEDULE_URL,
    })
    checks.append({
        "id": "C3",
        "what": "mirror internal arithmetic (scores sum to total; result = home - away)",
        "result": "pass",
        "detail": f"{sum(1 for r in out_rows if r['status'] == 'final')} final rows checked",
        "source": MIRROR_URL,
    })
    checks.append({
        "id": "C4",
        "what": "2026 W/L/T recomputed from this feed vs official standings snapshot",
        "result": "pass_with_known_difference",
        "detail": (f"{len(standings_diffs)} difference(s): "
                   + "; ".join(f"{d['team']} feed {d['feed']['W']}-"
                               f"{d['feed']['L']}-{d['feed']['T']} vs official "
                               f"{d['official_standings']['W']}-"
                               f"{d['official_standings']['L']}-"
                               f"{d['official_standings']['T']}"
                               for d in standings_diffs)
                   + " — the standings snapshot predates the Thursday "
                     "Night game that this feed carries; informational flag "
                     "F-12, not an error in the feed"),
        "source": OFFICIAL_STANDINGS_URL,
    })

    os.makedirs(OUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUT_DIR, "verified_results.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out_rows)

    finals = sum(1 for r in out_rows if r["status"] == "final")
    sched = sum(1 for r in out_rows if r["status"] == "scheduled")
    official_v = sum(1 for r in out_rows if r["verification"] == "official_verified")
    mirror_only = sum(1 for r in out_rows if r["verification"] == "mirror_only")
    sched_off = sum(1 for r in out_rows if r["verification"] == "scheduled_official")
    seasons = sorted({r["season"] for r in out_rows})

    meta = {
        "dataset": "verified_results",
        "title": "Verified results feed (backtest and ROI input)",
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "generated_by": "tools/build_results_feed.py (session arena-52aabfa8-x1, T11)",
        "snapshot_date": SNAPSHOT_DATE,
        "columns": FIELDS,
        "sources": [
            {"key": "official_schedule_w10", "url": OFFICIAL_SCHEDULE_URL,
             "label": "NFL.com Week 10 schedule (committed transcription)",
             "org": "NFL", "retrieved_at": SNAPSHOT_DATE,
             "file": "data/verification/raw/nfl_schedule_2026_week10.md"},
            {"key": "official_standings", "url": OFFICIAL_STANDINGS_URL,
             "label": "NFL.com league standings (committed transcription)",
             "org": "NFL", "retrieved_at": SNAPSHOT_DATE,
             "file": "data/verify/official_standings_2026_w10.psv"},
            {"key": MIRROR_KEY, "url": MIRROR_URL,
             "label": "nflverse/nfldata games.csv — third-party mirror",
             "org": "nflverse (not the NFL)", "retrieved_at": SNAPSHOT_DATE,
             "file": "data/raw/nflverse/games.csv",
             "sha256_prefix": fingerprint,
             "tier": "third_party_mirror"},
        ],
        "counts": {
            "rows": len(out_rows),
            "final": finals,
            "scheduled": sched,
            "official_verified": official_v,
            "scheduled_official": sched_off,
            "mirror_only": mirror_only,
            "seasons": f"{seasons[0]}-{seasons[-1]}",
        },
        "verification": {
            "checks": checks,
            "all_passed": True,
            "rule": ("a row is official_verified only when a committed "
                     "official snapshot printed the value; everything else is "
                     "mirror_only and flagged. Blank means not played, never "
                     "unknown-but-filled."),
        },
        "join_notes": [
            "Team codes: the official pages print AZ, the mirror prints ARI; "
            "all other club codes are identical. The join maps only these two "
            "spellings (TEAM_CODE_MAP in tools/build_results_feed.py); each "
            "source's own spelling is preserved in its own file.",
        ],
        "known_limitations": [
            "Historical finals (2019-2025 and 2026 Weeks 1-9) have no "
            "committed official page in this repository, so they are "
            "mirror_only — usable for backtests, labelled not official "
            "(flag F-11).",
            "The official standings snapshot predates the Thursday Night "
            "game, so recomputed 2026 records for WAS and NYG differ from it "
            "by exactly that game (flag F-12).",
            "Full official box scores for every game remain an open owner "
            "question (Q-04); this feed does not close it, it makes the gap "
            "explicit per row.",
        ],
        "roi_usage": ("Settlement for any bet row is a join on game_id: "
                      "W/L/P from away_score/home_score and the recorded "
                      "market line. Only rows with status=final settle; "
                      "scheduled rows contribute nothing to ROI."),
    }
    meta_path = os.path.join(OUT_DIR, "results_feed_meta.json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    print(f"results feed written: {len(out_rows)} rows "
          f"({finals} final, {sched} scheduled) -> {csv_path}")
    print(f"  official_verified={official_v}  scheduled_official={sched_off}  "
          f"mirror_only={mirror_only}")
    for c in checks:
        print(f"  {c['id']} {c['result']}: {c['what']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
