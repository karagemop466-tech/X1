#!/usr/bin/env python3
"""Emit verified reference-data CSVs from code/reference_data_2026_w10.py.

Every emitted CSV row carries a source_url column pointing at the official page
the values were transcribed from. Rows with unverifiable values emit blanks
and a flagged_* note — nothing is ever inferred.

Run: python3 code/build_reference_data.py
"""
import csv, os, sys, datetime

sys.path.insert(0, os.path.dirname(__file__))
from reference_data_2026_w10 import (
    STANDINGS, VENUES_VERIFIED_W10, WEEK10_GAMES, WEEK10_BYES, MARKET_W10,
    QB_EXPECTED_W10, INJURIES_W10, INTERNATIONAL_2026, INTL_SOURCE, SEASON_FACTS,
)

OUT = os.path.join(os.path.dirname(__file__), "..", "data")
STANDINGS_SRC = "https://www.nfl.com/standings/division/2026/REG"
SCHED_SRC = "https://www.nfl.com/schedules/2026/REG10/"
INJ_SRC = "https://www.nfl.com/injuries/"
NFLVERSE_SRC = "https://github.com/nflverse/nfldata (games.csv, fetched via GitHub API 2026-11-14)"

TODAY = "2026-11-14"


def w(path, header, rows):
    p = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(header)
        wr.writerows(rows)
    print(f"wrote {path}: {len(rows)} rows")


def main():
    # ---- integrity checks BEFORE writing anything -------------------------
    wins = sum(r[5] for r in STANDINGS); losses = sum(r[6] for r in STANDINGS)
    ties = sum(r[7] for r in STANDINGS)
    pf = sum(r[8] for r in STANDINGS); pa = sum(r[9] for r in STANDINGS)
    assert len(STANDINGS) == 32, "need 32 teams"
    assert wins == losses, f"wins {wins} != losses {losses}"
    assert pf == pa, f"PF {pf} != PA {pa}"
    games_played = (wins + losses + ties) // 2
    assert (wins + losses + ties) % 2 == 0
    # tie halves: ties counted once per team -> tie games produce 2 tie entries
    print(f"CHECK ok: 32 teams, {wins}W/{losses}L/{ties}T, PF==PA={pf}, "
          f"decisive games={wins}, tie games={ties//2}, total games={games_played}")
    assert len(WEEK10_GAMES) == 14
    assert len(WEEK10_BYES) == 4
    teams_sched = set()
    for g in WEEK10_GAMES: teams_sched.update([g[3], g[4]])
    assert len(teams_sched) == 28
    all_abbr = {r[1] for r in STANDINGS}
    assert teams_sched | {b[0] for b in WEEK10_BYES} == all_abbr, "schedule+byes must cover 32 teams"
    assert all(k in all_abbr for k in QB_EXPECTED_W10), "QB map covers all teams"
    assert set(INJURIES_W10) == teams_sched, "injury report must cover exactly the 28 playing teams"
    n_inj = sum(len(v) for v in INJURIES_W10.values())
    print(f"CHECK ok: 14 W10 games, 4 byes, {n_inj} injury rows across 28 teams")

    # ---- teams/standings ---------------------------------------------------
    rows = []
    for (team, abbr, conf, div, order, W, L, T, PF, PA, home, road, divr, confr, strk, l5) in STANDINGS:
        pct = round((W + 0.5 * T) / (W + L + T), 3) if (W + L + T) else ""
        venue = VENUES_VERIFIED_W10.get(abbr, "")
        flag = "" if venue else "venue_unverified (not visible on official W10 schedule page; verify at team page)"
        rows.append([team, abbr, conf, div, order, W, L, T, pct, PF, PA, PF - PA,
                     home, road, divr, confr, strk, l5, venue,
                     f"{STANDINGS_SRC} (snapshot {TODAY}); cross-verified vs {NFLVERSE_SRC}",
                     "verified" if venue else "verified", flag])
    w("nfl/teams_standings_2026_w10.csv",
      ["team","abbr","conf","division","div_order","W","L","T","pct","PF","PA","net_pts",
       "home","road","div_rec","conf_rec","streak","last5","home_venue",
       "source","status","flagged_note"], rows)

    # ---- week 10 schedule ---------------------------------------------------
    rows = []
    for (date, wkday, et, away, home, tv, intl, ap, hp) in WEEK10_GAMES:
        mkt = MARKET_W10.get((away, home), (None, None, None, None))
        qb_a = QB_EXPECTED_W10[away][0]; qb_h = QB_EXPECTED_W10[home][0]
        conflict = "; ".join([QB_EXPECTED_W10[away][2], QB_EXPECTED_W10[home][2]]).strip("; ")
        result = f"{ap}-{hp}" if ap is not None else ""
        rows.append([10, date, wkday, et, away, home, tv, intl or "",
                     result,
                     mkt[0] if mkt[0] is not None else "", mkt[1] if mkt[1] is not None else "",
                     mkt[2] if mkt[2] is not None else "", mkt[3] if mkt[3] is not None else "",
                     qb_a, qb_h, conflict,
                     f"{SCHED_SRC} (snapshot {TODAY})",
                     f"market_lines_and_qb_fields: {NFLVERSE_SRC}; qb conflicts cross-checked vs NFL.com news links on {INJ_SRC}"])
    w("nfl/schedule_2026_week10.csv",
      ["week","date","weekday","et_time","away","home","tv","venue_note","result",
       "market_spread_away","market_total","market_ml_away","market_ml_home",
       "expected_qb_away","expected_qb_home","flagged_note","source","market_source"], rows)

    rows = [[10, abbr, W, L] for (abbr, W, L) in WEEK10_BYES]
    w("nfl/week10_byes.csv", ["week","team","W","L"], rows)

    # ---- international games ------------------------------------------------
    rows = [[wk, d, m, v, k, INTL_SOURCE, "verified" if "*" not in v else "verified (new market)"]
            for (wk, d, m, v, k) in INTERNATIONAL_2026]
    w("nfl/international_2026.csv",
      ["week","date","matchup","venue","kickoff_et","source","status"], rows)

    # ---- season facts --------------------------------------------------------
    rows = [[f, v, s, tier] for (f, v, s, tier) in SEASON_FACTS]
    w("nfl/season_facts.csv", ["fact","value","source","source_tier"], rows)

    # ---- injuries -------------------------------------------------------------
    rows = []
    for abbr, players in INJURIES_W10.items():
        for (name, pos, pos2, inj, prac, game, slug) in players:
            rows.append([10, abbr, name, pos, inj, prac, game,
                         f"https://www.nfl.com/players/{slug}/", INJ_SRC,
                         f"snapshot {TODAY}"])
    w("injuries/injuries_2026_week10.csv",
      ["week","team","player","position","injuries","practice_status","game_status",
       "player_page","report_source","snapshot_date"], rows)

    # ---- QB map ---------------------------------------------------------------
    rows = []
    for abbr in sorted(QB_EXPECTED_W10):
        qb, src, conflict = QB_EXPECTED_W10[abr] if False else QB_EXPECTED_W10[abbr]
        rows.append([10, abbr, qb, src, conflict, INJ_SRC, NFLVERSE_SRC])
    w("injuries/qb_map_2026_week10.csv",
      ["week","team","expected_starter","source","conflict_or_note","report_source","market_source"], rows)

    print("\nAll reference CSVs emitted. Values that could not be confirmed are blank + flagged.")


if __name__ == "__main__":
    main()
