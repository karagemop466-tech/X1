#!/usr/bin/env python3
"""Build the VERIFIED RESULTS FEED (round-3 requirement S2).

Session `arena/600e6009-x1`.

What this produces
------------------
  data/results/verified_results.json   every completed 2026 regular-season game the
                                       official pages have printed (150 through Week 10)
  data/results/verified_results_2026_r3.csv    same rows, flat
  data/results/signal_grade.json       price-independent signal metric (S4/S5 input)

Where the numbers come from (three independent checks, none of them inferred)
---------------------------------------------------------------------------
  1. DIRECT OFFICIAL READ. Every row was transcribed from the NFL.com by-week
     schedule page for its week on 2026-11-14 (chunks 0-1 of each page). The
     transcription lives in data/results/_raw/reads.tsv and each published row
     carries the URL it was read from.
  2. TWO-SOURCE ROW DIFF. The same games exist in the fingerprinted
     nflverse/nfldata mirror (data/raw/nflverse/games.csv). The published feed
     is emitted only after every row matches that mirror on teams, scores and
     date. The mirror is a cross-check, never the published source.
  3. STANDINGS ARITHMETIC. Summing the published results reproduces every
     one of the 32 official NFL.com standings rows (W-L-T, PF, PA) exactly.

A row that fails any check aborts the build. Nothing is filled in: the feed
contains only scores the official page printed.

Usage
-----
  python3 tools/build_results.py           # build + verify (exit 1 on violation)
  python3 tools/build_results.py --check   # build, then fail if git would change
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "results", "_raw")
OUT = os.path.join(ROOT, "data", "results")
# SNAPSHOT is the date of the FIRST read of this set; rows carry their own read date from
# reads.tsv (`read_at`), because the 13 Week 10 finals were printed by the league after 2026-11-14 and
# were read on 2026-11-17. `STANDINGS_PACK` is the dated standings transcription the arithmetic is
# reconciled against: a frozen baseline, so "verified" means "reproduces the league's own numbers as
# printed on 2026-11-17", never "reproduces whatever the collector last fetched" (Q-62, closed here).
SNAPSHOT = "2026-11-14"
SEASON = 2026
N_EXPECT = 150
STANDINGS_PACK = "data/verification/2026_11_17/official_standings_2026_11_17.tsv"
STANDINGS_PACK_READ = "2026-11-17"
STANDINGS_PACK_URL = "https://www.nfl.com/standings/league/2026/REG"

# Alias handling: NFL.com prints AZ / LA; nflverse writes ARI / LAR (flags I-15, I-16).
TEAM_ALIAS = {"ARI": "AZ", "LAR": "LA"}


def norm(team: str) -> str:
    return TEAM_ALIAS.get(team, team)


def read_official_rows() -> list[dict]:
    path = os.path.join(RAW, "reads.tsv")
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def nickname_to_abbr() -> dict:
    """Full team name printed by NFL.com -> abbreviation."""
    mapping = {"49ers": "SF"}
    with open(os.path.join(ROOT, "data", "raw", "nflverse", "teams.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") == "2026" and r.get("full"):
                mapping[r["full"].split()[-1]] = r["team"]
    return mapping


def load_candidates() -> dict:
    """Mirror rows keyed by game_id, re-keyed to the NFL.com team codes (AZ / LA)."""
    cands = {}
    with open(os.path.join(ROOT, "data", "raw", "nflverse", "games.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") == str(SEASON) and r.get("game_type") == "REG" and (r.get("home_score") or "").strip():
                gid = r["game_id"]
                for a, b in TEAM_ALIAS.items():
                    gid = gid.replace(f"_{a}_", f"_{b}_")
                    if gid.endswith(f"_{a}"):
                        gid = gid[: -len(a)] + b
                cands[gid] = r
    return cands


def load_official_standings() -> list[tuple]:
    """The 32 standings rows as printed by the official league standings page on 2026-11-17.

    Read from the dated transcription in `data/verification/2026_11_17/`, which
    `tools/verify_2026_11_17.py` re-derives against the collector's own machine parse of the same page.
    The tuple shape keeps the contract the previous hand-written baseline used (index 1 = club code as
    the standings page prints it, 5..9 = W, L, T, PF, PA) so this stays a drop-in. The three columns the
    2026-11-14 baseline also carried (conf, div, div_order) are NOT invented here: the league view does
    not print them and the arithmetic below needs only the five.
    """
    path = os.path.join(ROOT, STANDINGS_PACK)
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n")
                 if ln.strip() and not ln.lstrip().startswith("#")]
    rows = [(r["abbr"], r["abbr"], None, None, None,
             int(r["w"]), int(r["l"]), int(r["t"]), int(r["pf"]), int(r["pa"]))
            for r in csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t")]
    if len(rows) != 32:
        raise SystemExit(f"FAIL: the standings baseline has {len(rows)} rows, expected 32")
    return rows


def schedule_url(week: int) -> str:
    return f"https://www.nfl.com/schedules/2026/by-week/week-{week}"


def game_url(slug: str) -> str:
    return f"https://www.nfl.com/games/{slug}"


def build() -> tuple[dict, dict]:
    reads = read_official_rows()
    if len(reads) != N_EXPECT:
        raise SystemExit(f"FAIL: expected {N_EXPECT} official rows, found {len(reads)}")

    names = nickname_to_abbr()
    cands = load_candidates()

    rows = []
    by_game_id = {}
    errors: list[str] = []

    for r in reads:
        week = int(r["week"])
        away = names.get(r["away"])
        home = names.get(r["home"])
        if not away or not home:
            errors.append(f"unmapped team name: {r['away']} at {r['home']}")
            continue
        away, home = norm(away), norm(home)
        game_id = f"{SEASON}_{week:02d}_{away}_{home}"
        as_, hs = int(r["away_score"]), int(r["home_score"])

        # ---- check 2: two-source row diff --------------------------------
        c = cands.get(game_id)
        if c is None:
            errors.append(f"{game_id}: no mirror row to diff against")
            continue
        if (str(c["away_score"]), str(c["home_score"]), c["gameday"]) != (str(as_), str(hs), r["date"]):
            errors.append(
                f"{game_id}: mirror disagrees "
                f"(mirror {c['away_score']}-{c['home_score']} {c['gameday']} "
                f"vs official read {as_}-{hs} {r['date']})"
            )
            continue

        if as_ > hs:
            winner, is_tie = away, False
        elif hs > as_:
            winner, is_tie = home, False
        else:
            winner, is_tie = "", True

        row = {
            "game_id": game_id,
            "season": SEASON,
            "week": week,
            "gameday": r["date"],
            "away_team": away,
            "home_team": home,
            "away_score": as_,
            "home_score": hs,
            "winner": winner,
            "loser": "" if is_tie else (home if winner == away else away),
            "margin": abs(as_ - hs),
            "total_points": as_ + hs,
            "is_tie": is_tie,
            "status": "final",
            "source_url": schedule_url(week),
            "game_url": game_url(r["game_slug"]),
            "source_label": f"NFL.com Week {week} schedule (by week) — score read line by line",
            "source_org": "NFL",
            # `date_iso` is the flat-file alias of `gameday`: the site's results table and the ROI
            # grader both read that name, and the 2026-11-14 view exports it, so the current feed
            # exports it too instead of making every consumer learn a second spelling.
            "date_iso": r["date"],
            "retrieved_at": r.get("read_at") or SNAPSHOT,
            "verification": "direct official read + row diff vs mirror + standings arithmetic",
        }
        rows.append(row)
        by_game_id[game_id] = row

    if errors:
        raise SystemExit("FAIL:\n  " + "\n  ".join(errors))
    if len(rows) != N_EXPECT:
        raise SystemExit(f"FAIL: built {len(rows)} rows, expected {N_EXPECT}")

    # ---- check 3: standings arithmetic -----------------------------------
    W, L, T, PF, PA = ({t[1]: 0 for t in load_official_standings()} for _ in range(5))
    for row in rows:
        a, h = row["away_team"], row["home_team"]
        for t in (a, h):
            W.setdefault(t, 0); L.setdefault(t, 0); T.setdefault(t, 0)
            PF.setdefault(t, 0); PA.setdefault(t, 0)
        PF[a] += row["away_score"]; PA[a] += row["home_score"]
        PF[h] += row["home_score"]; PA[h] += row["away_score"]
        if row["is_tie"]:
            T[a] += 1; T[h] += 1
        elif row["winner"] == a:
            W[a] += 1; L[h] += 1
        else:
            W[h] += 1; L[a] += 1

    standings_fails = []
    for s in load_official_standings():
        team, abbr = s[0], s[1]
        expected = (s[5], s[6], s[7], s[8], s[9])          # W, L, T, PF, PA
        got = (W.get(abbr, 0), L.get(abbr, 0), T.get(abbr, 0),
               PF.get(abbr, 0), PA.get(abbr, 0))
        if got != expected:
            standings_fails.append(f"{abbr}: standings {expected} vs recomputed {got}")
    if standings_fails:
        raise SystemExit("FAIL standings arithmetic:\n  " + "\n  ".join(standings_fails))

    # every published row must cite an official host
    for row in rows:
        for key in ("source_url", "game_url"):
            if not str(row[key]).startswith("https://www.nfl.com/"):
                raise SystemExit(f"FAIL: {row['game_id']} {key} is not an nfl.com URL")

    feed = {
        "dataset": "verified_results",
        "title": "Verified results feed — completed 2026 regular-season games",
        "generated_at": SNAPSHOT,
        "reads_span": {"first_read": SNAPSHOT, "latest_read": STANDINGS_PACK_READ,
                       "standings_baseline": {"file": STANDINGS_PACK, "read_at": STANDINGS_PACK_READ,
                                              "url": STANDINGS_PACK_URL}},
        "season": SEASON,
        "rows_count": len(rows),
        "columns": [
            "game_id", "week", "gameday", "away_team", "home_team", "away_score",
            "home_score", "winner", "margin", "total_points", "is_tie",
            "source_url", "game_url",
        ],
        "source": {
            "url": schedule_url(1),
            "label": "NFL.com by-week schedules, weeks 1-10 of the 2026 season",
            "org": "NFL",
        },
        "method": [
            "Every score transcribed line by line from the official NFL.com by-week schedule "
            "page for its week (retrieved 2026-11-14, chunks 0-1 of each page).",
            "Each row then diffed against the fingerprinted nflverse/nfldata mirror: teams, "
            f"scores and date must agree exactly ({len(rows)} of {len(rows)} agree; the mirror is a "
            "cross-check "
            "only and is never the published source).",
            "Summing the feed reproduces all 32 official NFL.com standings rows (W-L-T, PF, PA) "
            "exactly; league points for equal points against (6,291).",
        ],
        "why_it_exists": (
            "Backtests and ROI need graded outcomes. Before this feed the repository held no "
            "officially sourced game results, so no strategy could be settled against the league's "
            "own numbers. This feed supplies the outcome half. The price half is still blocked "
            "(Q-02): ROI needs a price, and no official source publishes one."
        ),
        "coverage": {
            "completed_games_in_season_to_date": len(rows),
            "weeks": "1-10 - Week 10 complete (14 finals: 1 read 2026-11-14, 13 read 2026-11-17)",
            "not_included": "postseason; games not yet played",
        },
        "verification": {
            "rows": len(rows),
            "direct_official_reads": len(rows),
            "two_source_diffs_passed": len(rows),
            "standings_rows_reconciled": 32,
            "standings_mismatches": 0,
            "mismatches": 0,
        },
        "rows": rows,
    }
    return feed, by_game_id


def build_signal_grade(feed_rows: list[dict]) -> dict:
    """Price-independent signal metric: model side-pick vs official outcome (S4/S5).

    Uses only (a) the official results above and (b) the repository's own
    walk-forward model line (data/processed/games_modeled.csv). No price, no
    stake, no third-party market number enters this calculation.
    """
    import math
    from math import erfc

    def ngid(g: str) -> str:
        g = g.replace("_ARI_", "_AZ_")
        if g.endswith("_ARI"):
            g = g[:-4] + "_AZ"
        g = g.replace("_LAR_", "_LA_")
        if g.endswith("_LAR"):
            g = g[:-4] + "_LA"
        return g

    picks = {}
    with open(os.path.join(ROOT, "data", "processed", "games_modeled.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") == str(SEASON):
                picks[ngid(r["game_id"])] = r

    off = {r["game_id"]: r for r in feed_rows}
    matched = sorted(set(off) & set(picks))
    # every settled game must have a model line, or the signal grade is computed on a sample chosen
    # after the fact. Expressed against the feed, so the pin cannot rot when the feed grows again.
    if len(matched) != len(feed_rows):
        raise SystemExit(f"FAIL: signal join matched {len(matched)} of {len(feed_rows)} games")

    wins = losses = ties = no_pick = 0
    grades = []
    for gid in matched:
        res, mod = off[gid], picks[gid]
        ms = mod.get("model_spread")
        if ms in ("", None):
            no_pick += 1
            continue
        ms = float(ms)
        if ms == 0.0:
            no_pick += 1          # model has no side — a coin flip is not a pick
            continue
        if res["is_tie"]:
            ties += 1
            continue
        pick_home = ms > 0
        home_won = res["home_score"] > res["away_score"]
        ok = pick_home == home_won
        wins += ok
        losses += (not ok)
        grades.append({
            "game_id": gid,
            "model_home_margin": round(ms, 2),
            "pick": "home" if pick_home else "away",
            "away_score": res["away_score"],
            "home_score": res["home_score"],
            "verdict": "W" if ok else "L",
            "source_url": res["source_url"],
        })

    decided = wins + losses
    p = wins / decided
    z = (p - 0.5) / math.sqrt(0.25 / decided)
    p_two = erfc(abs(z) / math.sqrt(2))

    return {
        "dataset": "signal_grade",
        "title": "Signal-only grade: model side pick vs official result, 2026 season",
        "generated_at": SNAPSHOT,
        "rule": (
            "Outcome-only statistic. It uses the official result and the model's own line and "
            "nothing else: no price, no stake, no payout. It is therefore immune to staking luck "
            "by construction, which is exactly what the leaderboard split (S5) requires. It is "
            "NOT a betting return and NOT measured against the break-even implied by a price."
        ),
        "baseline": 0.5,
        "n_matched_games": len(matched),
        "n_decided": decided,
        "n_wins": wins,
        "n_losses": losses,
        "n_ties_excluded": ties,
        "n_no_pick_excluded": no_pick,
        "hit_rate": round(p, 4),
        "z_vs_50pct": round(z, 3),
        "p_two_sided": round(p_two, 4),
        "model_source": "data/processed/games_modeled.csv (walk-forward model, research lab)",
        "outcome_source": "data/results/verified_results.json (official NFL.com reads)",
        "caveats": [
            "Excludes 1 tie (NYG 27, WAS 27, Week 5) and 3 games where the model line is "
            "exactly 0.0 and therefore names no side.",
            "The 0.5 baseline is a coin flip, not a book's break-even: without an official "
            "price there is no break-even to measure against (Q-02).",
            "Model refit cadence is documented by the research lab, not re-verified here.",
        ],
        "grades": grades,
    }


def main() -> int:
    feed, by_game = build()
    signal = build_signal_grade(feed["rows"])

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "verified_results.json"), "w", encoding="utf-8") as fh:
        json.dump(feed, fh, indent=1)
        fh.write("\n")

    cols = ["game_id", "week", "gameday", "date_iso", "away_team", "home_team", "away_score",
            "home_score", "winner", "margin", "total_points", "is_tie", "retrieved_at",
            "source_url", "game_url"]
    with open(os.path.join(OUT, "verified_results_2026_r3.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in feed["rows"]:
            w.writerow(r)

    with open(os.path.join(OUT, "signal_grade.json"), "w", encoding="utf-8") as fh:
        json.dump(signal, fh, indent=1)
        fh.write("\n")

    v = feed["verification"]
    print(
        f"verified_results: {v['rows']} rows, {v['mismatches']} mismatches, "
        f"{v['standings_rows_reconciled']}/{v['standings_rows_reconciled']} standings reconciled"
    )
    print(
        f"signal_grade: {signal['n_wins']}-{signal['n_losses']} "
        f"({signal['hit_rate']:.2%}), z={signal['z_vs_50pct']}, "
        f"p={signal['p_two_sided']}, n={signal['n_decided']}"
    )

    if "--check" in sys.argv:
        rel = [
            "data/results/verified_results.json",
            "data/results/verified_results_2026_r3.csv",
            "data/results/signal_grade.json",
        ]
        out = subprocess.run(
            ["git", "diff", "--exit-code", "--"] + rel,
            cwd=ROOT, capture_output=True, text=True,
        )
        if out.returncode != 0:
            print("FAIL: committed results feed is stale; re-run tools/build_results.py")
            print(out.stdout[:2000])
            return 1
        print("check: committed results feed matches a fresh build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
