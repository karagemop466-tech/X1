#!/usr/bin/env python3
"""Build depth-slot groups, 32-club deficiency summary, and Week 11 Offense-vs-Defense Matchup Deficiency Matrix.

Addresses brief requirements:
  - Fix Packers jersey-number depth parsing failure (strip leading digits while retaining raw_player)
    and flag Houston Texans as unavailable_image_only (never transcribe an image by eye).
  - Model depth slots as groups, not a single starter (shared_position_group when multiple rank-1 slots
    exist at a (club, unit, position), shared_concatenated_cell when a cell names multiple players).
  - Represent shared and empty depth slots faithfully (synthesize explicit empty_depth_gap rows).
  - Per-team view across all 32 clubs: starters out/on-report, 2nd/3rd/4th-string replacements named,
    net injury count.
  - Interactive Offense vs. Defense Matchup Deficiency Matrix (1st-4th string) for all 13 Week 11
    official matchups, surfacing trench (OL vs EDGE/DL/LB) and coverage/backfield (WR/TE/RB vs CB/S/LB)
    mismatches from official sources only.

Usage:
    python3 tools/build_depth_matrix.py          # build JSON/CSV outputs under data/depth/
    python3 tools/build_depth_matrix.py --check  # rebuild in memory and fail if committed files are stale
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPTH_PATH = os.path.join(ROOT, "data", "pipeline", "depth_charts.json")
INJ_W11_PATH = os.path.join(ROOT, "data", "pipeline", "injuries.json")
INJ_W10_PATH = os.path.join(ROOT, "data", "nfl", "injuries_week10.tsv")
W11_SLATE_PATH = os.path.join(ROOT, "data", "lab", "reads", "2026-11-17", "week11_slate_2026-11-17.tsv")
CLUB_REG_PATH = os.path.join(ROOT, "data", "pipeline", "club_registry.json")
OUT_DIR = os.path.join(ROOT, "data", "depth")

SUFFIXES = {"Jr.", "Sr.", "II", "III", "IV", "V", "Jr", "Sr"}
INJ_TEAM_ALIAS = {"LAR": "LA", "ARZ": "AZ"}
HOU_URL = "https://www.houstontexans.com/team/depth-chart"
NFL_INJ_URL = "https://www.nfl.com/injuries/"
NFL_W11_SCHED_URL = "https://www.nfl.com/schedules/2026/by-week/week-11"

CLUB_NAMES = {
    "ATL": "Atlanta Falcons", "AZ": "Arizona Cardinals", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}

OFF_PASS_POS = {"WR", "TE"}
OFF_TRENCH_POS = {"LT", "LG", "C", "RG", "RT", "OT", "OG", "OL"}
OFF_BACK_POS = {"QB", "RB", "FB"}
DEF_COV_POS = {"CB", "S", "FS", "SS", "DB", "NB"}
DEF_TRENCH_POS = {"DE", "DT", "NT", "DL", "EDGE", "OLB", "LB", "ILB", "MLB"}


def strip_jersey(raw: str) -> tuple[str, str]:
    s = (raw or "").strip()
    m = re.match(r"^(\d+)\s+(.+)$", s)
    if m:
        return m.group(2).strip(), m.group(1)
    return s, ""


def split_concat_players(clean: str) -> list[str]:
    s = (clean or "").strip()
    if not s:
        return []
    tokens = s.split()
    if any(t[0].islower() for t in tokens if t):
        return [s]
    core = [t for t in tokens if t not in SUFFIXES]
    if len(core) < 4:
        return [s]
    parts = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens):
            name = [tokens[i], tokens[i + 1]]
            i += 2
            while i < len(tokens) and tokens[i] in SUFFIXES:
                name.append(tokens[i])
                i += 1
            parts.append(" ".join(name))
        else:
            parts.append(tokens[i])
            i += 1
    return parts


def read_w11_slate() -> tuple[list[dict], dict[str, dict]]:
    with open(W11_SLATE_PATH, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    rows = list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))
    games = []
    team_sched = {}
    for r in rows:
        if r["row_type"] == "game":
            games.append(r)
            team_sched[r["away"]] = {
                "game_id": r["game_id"], "opponent": r["home"], "home_away": "away",
                "is_bye": False, "matchup": f"{r['away']} @ {r['home']}",
                "date_et": r["date_et"], "time_et": r["time_et"], "network": r["network"],
                "game_url": r["game_url"],
            }
            team_sched[r["home"]] = {
                "game_id": r["game_id"], "opponent": r["away"], "home_away": "home",
                "is_bye": False, "matchup": f"{r['away']} @ {r['home']}",
                "date_et": r["date_et"], "time_et": r["time_et"], "network": r["network"],
                "game_url": r["game_url"],
            }
        elif r["row_type"] == "bye":
            team_sched[r["away"]] = {
                "game_id": r["game_id"], "opponent": "BYE", "home_away": "bye",
                "is_bye": True, "matchup": "BYE (Week 11)",
                "date_et": "", "time_et": "", "network": "",
                "game_url": NFL_W11_SCHED_URL,
            }
    return games, team_sched


def read_w10_injuries() -> list[dict]:
    with open(INJ_W10_PATH, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


def build_all() -> dict:
    dc_doc = json.load(open(DEPTH_PATH, encoding="utf-8"))
    dc_rows = dc_doc["rows"]
    inj11_doc = json.load(open(INJ_W11_PATH, encoding="utf-8"))
    inj11_rows = inj11_doc["rows"]
    inj10_rows = read_w10_injuries()
    w11_games, w11_team_sched = read_w11_slate()

    # Index injuries by (team, player)
    inj11_by_tp = {}
    inj11_by_team = defaultdict(list)
    for r in inj11_rows:
        t = INJ_TEAM_ALIAS.get(r["team_abbrev"], r["team_abbrev"])
        p = (r.get("player") or "").strip()
        inj11_by_tp[(t, p)] = r
        inj11_by_team[t].append(r)

    inj10_by_tp = {}
    inj10_by_team = defaultdict(list)
    for r in inj10_rows:
        t = INJ_TEAM_ALIAS.get(r["team"], r["team"])
        p = (r.get("player") or "").strip()
        inj10_by_tp[(t, p)] = r
        inj10_by_team[t].append(r)

    # Identify multi-slot rank-1 groups per (team, unit, position)
    rank1_slots_per_pos = defaultdict(set)
    by_slot = defaultdict(list)
    club_source_url = {}
    for r in dc_rows:
        t = r["team_abbrev"]
        pos = (r.get("position") or "").strip()
        club_source_url.setdefault(t, r.get("_source_url") or "")
        if r.get("depth") == 1:
            rank1_slots_per_pos[(t, r["unit"], pos)].add(r["slot"])
        by_slot[(t, r["unit"], pos, r["slot"])].append(r)
    club_source_url["HOU"] = HOU_URL

    # Build depth_groups_32 rows
    group_rows = []
    empty_gap_count_by_team = defaultdict(int)
    jersey_stripped_by_team = defaultdict(int)
    shared_concat_by_team = defaultdict(int)
    gb_raw_w10_joins = 0
    gb_stripped_w10_joins = 0

    for (t, unit, pos, slot), srows in sorted(by_slot.items()):
        srows_sorted = sorted(srows, key=lambda x: x["depth"])
        depths_present = {r["depth"]: r for r in srows_sorted}
        max_d = max(depths_present)
        is_multi_pos_group = len(rank1_slots_per_pos[(t, unit, pos)]) > 1
        slot_group_id = f"{t}:{unit}:{pos or 'UNLABELLED'}:S{slot}"
        src_url = srows_sorted[0].get("_source_url") or club_source_url.get(t, "")
        ret_at = srows_sorted[0].get("_retrieved_at") or dc_doc.get("generated_at", "")

        for d in range(1, max_d + 1):
            r = depths_present.get(d)
            if r is None:
                empty_gap_count_by_team[t] += 1
                group_rows.append({
                    "team_abbrev": t,
                    "team_name": CLUB_NAMES[t],
                    "unit": unit,
                    "position": pos,
                    "slot": slot,
                    "depth": d,
                    "slot_group_id": slot_group_id,
                    "slot_kind": "empty_depth_gap",
                    "raw_player": "",
                    "player_clean": "",
                    "members": "",
                    "members_count": 0,
                    "jersey_number": "",
                    "jersey_stripped": "false",
                    "position_label_missing": "true" if not pos else "false",
                    "w11_injury_status": "",
                    "w11_practice_status": "",
                    "w11_game_status": "",
                    "w10_game_status": "",
                    "source_url": src_url,
                    "retrieved_at": ret_at,
                })
                continue

            raw_p = (r.get("player") or "").strip()
            clean_p, jersey_no = strip_jersey(raw_p)
            if jersey_no:
                jersey_stripped_by_team[t] += 1
            if t == "GB":
                if (t, raw_p) in inj10_by_tp:
                    gb_raw_w10_joins += 1
                if (t, clean_p) in inj10_by_tp:
                    gb_stripped_w10_joins += 1

            members = split_concat_players(clean_p)
            if len(members) > 1:
                slot_kind = "shared_concatenated_cell"
                shared_concat_by_team[t] += 1
            elif is_multi_pos_group and d == 1:
                slot_kind = "shared_position_group"
            else:
                slot_kind = "standard"

            # Match W11 and W10 injuries across any member in this slot
            w11_hits = [inj11_by_tp[(t, m)] for m in members if (t, m) in inj11_by_tp]
            w10_hits = [inj10_by_tp[(t, m)] for m in members if (t, m) in inj10_by_tp]
            w11_prac = "; ".join(h.get("practice_status") or "" for h in w11_hits if h.get("practice_status"))
            w11_gs = "; ".join(h.get("game_status") or "" for h in w11_hits if h.get("game_status"))
            w11_inj = "; ".join(h.get("injuries") or "" for h in w11_hits if h.get("injuries"))
            w10_gs = "; ".join(h.get("game_status") or "" for h in w10_hits if h.get("game_status"))

            group_rows.append({
                "team_abbrev": t,
                "team_name": CLUB_NAMES[t],
                "unit": unit,
                "position": pos,
                "slot": slot,
                "depth": d,
                "slot_group_id": slot_group_id,
                "slot_kind": slot_kind,
                "raw_player": raw_p,
                "player_clean": clean_p,
                "members": " | ".join(members),
                "members_count": len(members),
                "jersey_number": jersey_no,
                "jersey_stripped": "true" if jersey_no else "false",
                "position_label_missing": "true" if not pos else "false",
                "w11_injury_status": w11_inj,
                "w11_practice_status": w11_prac,
                "w11_game_status": w11_gs,
                "w10_game_status": w10_gs,
                "source_url": src_url,
                "retrieved_at": ret_at,
            })

    # Explicit Houston Texans unavailable row (never transcribed from image)
    group_rows.append({
        "team_abbrev": "HOU",
        "team_name": CLUB_NAMES["HOU"],
        "unit": "",
        "position": "",
        "slot": 0,
        "depth": 0,
        "slot_group_id": "HOU:UNAVAILABLE_IMAGE_ONLY",
        "slot_kind": "unavailable_image_only",
        "raw_player": "",
        "player_clean": "",
        "members": "",
        "members_count": 0,
        "jersey_number": "",
        "jersey_stripped": "false",
        "position_label_missing": "true",
        "w11_injury_status": "",
        "w11_practice_status": "",
        "w11_game_status": "",
        "w10_game_status": "",
        "source_url": HOU_URL,
        "retrieved_at": dc_doc.get("generated_at", ""),
    })

    # Build slot lookup for replacements (2nd, 3rd, 4th string)
    slot_map = defaultdict(dict)
    for gr in group_rows:
        if gr["slot_kind"] != "unavailable_image_only" and gr["depth"] >= 1:
            slot_map[(gr["team_abbrev"], gr["unit"], gr["position"], gr["slot"])][gr["depth"]] = gr

    def slot_injury_severity(gr: dict) -> str:
        gs = (gr.get("w11_game_status") or "").lower()
        pr = (gr.get("w11_practice_status") or "").lower()
        if "out" in gs or "did not participate" in pr:
            return "OUT_OR_DNP"
        if "doubtful" in gs or "questionable" in gs or "limited" in pr:
            return "DOUBTFUL_Q_OR_LIMITED"
        if gr.get("w11_practice_status") or gr.get("w11_game_status"):
            return "FULL_PRACTICE_ON_REPORT"
        return "HEALTHY_NOT_LISTED"

    def find_replacement(t: str, unit: str, pos: str, slot: int) -> tuple[str, str]:
        dmap = slot_map.get((t, unit, pos, slot), {})
        for d in (2, 3, 4):
            cand = dmap.get(d)
            if cand and cand["player_clean"]:
                sev = slot_injury_severity(cand)
                if sev != "OUT_OR_DNP":
                    return f"{d}nd/rd/th" if False else f"{d}{'nd' if d==2 else 'rd' if d==3 else 'th'}", cand["player_clean"]
        for d in (2, 3, 4):
            cand = dmap.get(d)
            if cand and cand["player_clean"]:
                return f"{d}{'nd' if d==2 else 'rd' if d==3 else 'th'} (also on report)", cand["player_clean"]
        return "none_listed", ""

    # Build 32-team deficiency summary
    team_summary_rows = []
    for t in sorted(CLUB_NAMES):
        sched = w11_team_sched[t]
        w11_team_inj = inj11_by_team[t]
        w10_team_inj = inj10_by_team[t]
        w11_dnp = sum(1 for r in w11_team_inj if "did not participate" in (r.get("practice_status") or "").lower())
        w11_lim = sum(1 for r in w11_team_inj if "limited" in (r.get("practice_status") or "").lower())
        w11_full = sum(1 for r in w11_team_inj if "full" in (r.get("practice_status") or "").lower())
        w11_out = sum(1 for r in w11_team_inj if (r.get("game_status") or "").strip() == "Out")
        w11_dbt = sum(1 for r in w11_team_inj if (r.get("game_status") or "").strip() == "Doubtful")
        w11_q = sum(1 for r in w11_team_inj if (r.get("game_status") or "").strip() == "Questionable")
        w10_out = sum(1 for r in w10_team_inj if (r.get("game_status") or "").strip() == "Out")

        if t == "HOU":
            team_summary_rows.append({
                "team_abbrev": t,
                "team_name": CLUB_NAMES[t],
                "depth_status": "unavailable_image_only",
                "w11_matchup": sched["matchup"],
                "w11_is_bye": "true" if sched["is_bye"] else "false",
                "depth1_slots": "",
                "shared_rank1_pos_groups": "",
                "shared_concat_cells": "",
                "empty_depth_gaps": "",
                "jersey_stripped_rows": "",
                "w11_injuries_total": len(w11_team_inj),
                "w11_dnp_count": w11_dnp,
                "w11_limited_count": w11_lim,
                "w11_full_count": w11_full,
                "w11_out_count": w11_out,
                "w11_doubtful_count": w11_dbt,
                "w11_questionable_count": w11_q,
                "w11_starters_on_report": "",
                "w11_starters_out_or_dnp": "",
                "w11_offense_replacements": "",
                "w11_defense_replacements": "",
                "w10_injuries_total": len(w10_team_inj),
                "w10_out_count": w10_out,
                "flag": "HOU depth chart published as image only; depth/replacement cells left blank",
                "source_url": HOU_URL,
            })
            continue

        t_d1 = [r for r in group_rows if r["team_abbrev"] == t and r["depth"] == 1]
        t_shared_pos = sum(1 for (tt, u, p), sids in rank1_slots_per_pos.items() if tt == t and len(sids) > 1)
        starters_on_rep = 0
        starters_out_dnp = 0
        off_reps = []
        def_reps = []
        for r in t_d1:
            sev = slot_injury_severity(r)
            if sev != "HEALTHY_NOT_LISTED":
                starters_on_rep += 1
            if sev == "OUT_OR_DNP":
                starters_out_dnp += 1
            if sev in ("OUT_OR_DNP", "DOUBTFUL_Q_OR_LIMITED"):
                tier, rep_name = find_replacement(t, r["unit"], r["position"], r["slot"])
                desc = f"{r['position'] or '?'}: {r['player_clean']} ({r['w11_game_status'] or r['w11_practice_status']}) -> {tier} {rep_name or 'none listed'}"
                if r["unit"] == "Offense":
                    off_reps.append(desc)
                elif r["unit"] == "Defense":
                    def_reps.append(desc)

        team_summary_rows.append({
            "team_abbrev": t,
            "team_name": CLUB_NAMES[t],
            "depth_status": "verified_club_chart",
            "w11_matchup": sched["matchup"],
            "w11_is_bye": "true" if sched["is_bye"] else "false",
            "depth1_slots": len(t_d1),
            "shared_rank1_pos_groups": t_shared_pos,
            "shared_concat_cells": shared_concat_by_team[t],
            "empty_depth_gaps": empty_gap_count_by_team[t],
            "jersey_stripped_rows": jersey_stripped_by_team[t],
            "w11_injuries_total": len(w11_team_inj),
            "w11_dnp_count": w11_dnp,
            "w11_limited_count": w11_lim,
            "w11_full_count": w11_full,
            "w11_out_count": w11_out,
            "w11_doubtful_count": w11_dbt,
            "w11_questionable_count": w11_q,
            "w11_starters_on_report": starters_on_rep,
            "w11_starters_out_or_dnp": starters_out_dnp,
            "w11_offense_replacements": "; ".join(off_reps),
            "w11_defense_replacements": "; ".join(def_reps),
            "w10_injuries_total": len(w10_team_inj),
            "w10_out_count": w10_out,
            "flag": "GB leading jersey numbers stripped (raw_player preserved)" if t == "GB" else "",
            "source_url": club_source_url.get(t, NFL_INJ_URL),
        })

    # Build Week 11 Offense vs Defense Matchup Deficiency Matrix (1st-4th String)
    def lane_summary(team: str, unit: str, pos_set: set[str]) -> dict:
        if team == "HOU":
            inj_list = [r for r in inj11_by_team["HOU"] if (r.get("position") or "").strip() in pos_set]
            notes = [f"{r['player']} ({r['position']}, {r.get('game_status') or r.get('practice_status') or 'on report'})" for r in inj_list]
            return {
                "depth_status": "unavailable_image_only",
                "starters_total": "",
                "starters_affected": "",
                "worst_tier": "HOU_DEPTH_UNAVAILABLE",
                "detail": "; ".join(notes) if notes else "HOU depth unavailable (image-only); 0 lane injuries listed on W11 report",
                "source_url": HOU_URL,
            }
        slots = [
            r for r in group_rows
            if r["team_abbrev"] == team and r["unit"] == unit and r["depth"] == 1
            and r["position"] in pos_set and r["slot_kind"] != "empty_depth_gap"
        ]
        affected = []
        worst_rank = 1  # 1=starter clean, 2=starter limited/Q, 3=starter DNP/Out -> 2nd/3rd/4th string
        for r in slots:
            sev = slot_injury_severity(r)
            if sev == "OUT_OR_DNP":
                tier, rep = find_replacement(team, unit, r["position"], r["slot"])
                affected.append(f"{r['position']}: {r['player_clean']} ({r['w11_game_status'] or r['w11_practice_status']}) -> {tier} {rep or 'none'}")
                worst_rank = max(worst_rank, 3)
            elif sev == "DOUBTFUL_Q_OR_LIMITED":
                tier, rep = find_replacement(team, unit, r["position"], r["slot"])
                affected.append(f"{r['position']}: {r['player_clean']} ({r['w11_game_status'] or r['w11_practice_status']}) -> {tier} {rep or 'none'}")
                worst_rank = max(worst_rank, 2)
        tier_label = {1: "1st_string_clean", 2: "1st_string_limited_or_Q", 3: "replacement_2nd_to_4th_string_active"}[worst_rank]
        return {
            "depth_status": "verified_club_chart",
            "starters_total": len(slots),
            "starters_affected": len(affected),
            "worst_tier": tier_label,
            "detail": "; ".join(affected) if affected else "All listed 1st-string slots clear on W11 report",
            "source_url": club_source_url.get(team, NFL_INJ_URL),
        }

    LANES = [
        ("Passing_WR_TE_vs_CB_S", OFF_PASS_POS, DEF_COV_POS),
        ("Trench_OL_vs_Front7", OFF_TRENCH_POS, DEF_TRENCH_POS),
        ("Backfield_QB_RB_vs_Box", OFF_BACK_POS, DEF_TRENCH_POS | DEF_COV_POS),
    ]
    matrix_rows = []
    for g in w11_games:
        for off_team, def_team, side_label in ((g["away"], g["home"], "Away Off vs Home Def"),
                                               (g["home"], g["away"], "Home Off vs Away Def")):
            for lane_name, off_pos, def_pos in LANES:
                o_sum = lane_summary(off_team, "Offense", off_pos)
                d_sum = lane_summary(def_team, "Defense", def_pos)
                if "HOU" in (off_team, def_team):
                    mismatch_flag = "HOU_DEPTH_UNAVAILABLE"
                elif o_sum["worst_tier"] != "1st_string_clean" and d_sum["worst_tier"] != "1st_string_clean":
                    mismatch_flag = "BOTH_UNITS_DEPLETED"
                elif d_sum["worst_tier"] == "replacement_2nd_to_4th_string_active" and o_sum["worst_tier"] == "1st_string_clean":
                    mismatch_flag = "OFF_ADVANTAGE_DEF_BACKUP"
                elif o_sum["worst_tier"] == "replacement_2nd_to_4th_string_active" and d_sum["worst_tier"] == "1st_string_clean":
                    mismatch_flag = "DEF_ADVANTAGE_OFF_BACKUP"
                elif o_sum["worst_tier"] != "1st_string_clean" or d_sum["worst_tier"] != "1st_string_clean":
                    mismatch_flag = "WATCH_LIMITED_OR_Q"
                else:
                    mismatch_flag = "NO_STARTER_DEFICIENCY"

                matrix_rows.append({
                    "game_id": g["game_id"],
                    "matchup": f"{g['away']} @ {g['home']}",
                    "date_et": g["date_et"],
                    "time_et": g["time_et"],
                    "side": side_label,
                    "offense_team": off_team,
                    "defense_team": def_team,
                    "lane": lane_name,
                    "off_starters_total": o_sum["starters_total"],
                    "off_starters_affected": o_sum["starters_affected"],
                    "off_tier": o_sum["worst_tier"],
                    "off_detail": o_sum["detail"],
                    "def_starters_total": d_sum["starters_total"],
                    "def_starters_affected": d_sum["starters_affected"],
                    "def_tier": d_sum["worst_tier"],
                    "def_detail": d_sum["detail"],
                    "mismatch_flag": mismatch_flag,
                    "game_url": g["game_url"],
                    "off_source_url": o_sum["source_url"],
                    "def_source_url": d_sum["source_url"],
                })

    meta = {
        "generated_at": dc_doc.get("generated_at", ""),
        "injuries_w11_retrieved_at": inj11_doc.get("generated_at", ""),
        "sources": {
            "depth_charts": "data/pipeline/depth_charts.json (31 official club depth charts; HOU image-only unavailable)",
            "injuries_w11": NFL_INJ_URL,
            "injuries_w10": "https://www.nfl.com/injuries/league/2026/reg10",
            "schedule_w11": NFL_W11_SCHED_URL,
        },
        "counts": {
            "clubs_total": 32,
            "clubs_verified_depth": 31,
            "clubs_unavailable_image_only": 1,
            "depth_group_rows": len(group_rows),
            "gb_jersey_stripped_rows": jersey_stripped_by_team["GB"],
            "gb_w10_injury_joins_raw": gb_raw_w10_joins,
            "gb_w10_injury_joins_stripped": gb_stripped_w10_joins,
            "shared_rank1_position_groups": sum(1 for sids in rank1_slots_per_pos.values() if len(sids) > 1),
            "shared_concatenated_cells": sum(shared_concat_by_team.values()),
            "empty_depth_gap_rows": sum(empty_gap_count_by_team.values()),
            "w11_fixtures": len(w11_games),
            "w11_matrix_rows": len(matrix_rows),
            "w11_matrix_mismatch_alerts": sum(1 for r in matrix_rows if r["mismatch_flag"] in ("OFF_ADVANTAGE_DEF_BACKUP", "DEF_ADVANTAGE_OFF_BACKUP", "BOTH_UNITS_DEPLETED")),
        },
    }
    return {
        "meta": meta,
        "depth_groups": group_rows,
        "team_summary": team_summary_rows,
        "matrix_w11": matrix_rows,
    }


def write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def serialize_outputs(bundle: dict) -> dict[str, str]:
    meta = bundle["meta"]
    files = {}

    def dump_json(name: str, rows: list[dict]) -> str:
        return json.dumps({"meta": meta, "rows": rows}, indent=2, ensure_ascii=False) + "\n"

    def dump_csv(rows: list[dict]) -> str:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

    files["depth_groups_32.json"] = dump_json("depth_groups_32", bundle["depth_groups"])
    files["depth_groups_32.csv"] = dump_csv(bundle["depth_groups"])
    files["team_deficiency_summary.json"] = dump_json("team_deficiency_summary", bundle["team_summary"])
    files["team_deficiency_summary.csv"] = dump_csv(bundle["team_summary"])
    files["matchup_deficiency_matrix_w11.json"] = dump_json("matchup_deficiency_matrix_w11", bundle["matrix_w11"])
    files["matchup_deficiency_matrix_w11.csv"] = dump_csv(bundle["matrix_w11"])
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    bundle = build_all()
    rendered = serialize_outputs(bundle)
    os.makedirs(OUT_DIR, exist_ok=True)
    if args.check:
        stale = []
        for fname, content in rendered.items():
            p = os.path.join(OUT_DIR, fname)
            if not os.path.exists(p):
                stale.append(f"{fname} (missing)")
            else:
                cur = open(p, encoding="utf-8").read()
                if cur != content:
                    stale.append(f"{fname} (differs)")
        if stale:
            print("STALE data/depth/ outputs:", ", ".join(stale))
            return 1
        c = bundle["meta"]["counts"]
        print(f"CHECK OK: 32 clubs ({c['clubs_verified_depth']} verified + 1 HOU image-only), "
              f"GB joins {c['gb_w10_injury_joins_raw']}->{c['gb_w10_injury_joins_stripped']}, "
              f"W11 matrix {c['w11_matrix_rows']} rows ({c['w11_matrix_mismatch_alerts']} alerts)")
        return 0

    for fname, content in rendered.items():
        with open(os.path.join(OUT_DIR, fname), "w", encoding="utf-8") as fh:
            fh.write(content)
    c = bundle["meta"]["counts"]
    print(f"wrote data/depth/: {c['depth_group_rows']} depth rows, 32 team rows, {c['w11_matrix_rows']} W11 matrix rows")
    print(f"  GB jersey stripped: {c['gb_jersey_stripped_rows']} rows, W10 injury joins: {c['gb_w10_injury_joins_raw']} -> {c['gb_w10_injury_joins_stripped']}")
    print(f"  shared rank-1 position groups: {c['shared_rank1_position_groups']}, shared concat cells: {c['shared_concatenated_cells']}, empty gaps: {c['empty_depth_gap_rows']}")
    print(f"  W11 mismatch alerts (2nd-4th string active): {c['w11_matrix_mismatch_alerts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
