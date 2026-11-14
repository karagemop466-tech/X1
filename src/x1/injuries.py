"""Injury tracking and depth-deficiency analysis.

Data used
---------
* Official NFL weekly injury report for the current week (league page,
  transcribed row by row into ``data/raw/official_injuries_w10_2026.csv``).
* Machine-readable transcription of the same reports for weeks 1-9 (nflverse
  injuries release) - used for the multi-week history and the measured effect
  of missing starters.
* Depth charts with an explicit depth tier - used to turn "this player is Out"
  into "this team must now start its third string at the position".
* Weekly roster statuses - used to confirm a replacement candidate is still
  on the team.

Two caveats are carried all the way to the published tables:

* the league does not publish depth tiers, so tiering is *derived* data;
* the available depth-chart snapshot is from the 2024 season, so every row
  states which season and week the tier came from.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import config

POSITION_GROUPS = {
    "QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "OL": "OL", "T": "OL", "G": "OL",
    "C": "OL", "DE": "DL", "DT": "DL", "NT": "DL", "LB": "LB", "OLB": "LB", "ILB": "LB",
    "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB", "DB": "DB", "K": "ST", "P": "ST", "LS": "ST",
}

GROUPS = ("QB", "RB", "WR", "TE", "DL", "LB", "DB", "OL")

OFFICIAL_FILE = "official_injuries_w10_2026.csv"


def position_group(position: str) -> str:
    return POSITION_GROUPS.get(str(position).upper(), "OTHER")


def load_injuries() -> pd.DataFrame:
    """Machine-readable injury history (weeks 1-9 of 2026)."""
    df = pd.read_csv(config.RAW_DIR / "injuries_2026.csv")
    df["position_group"] = df["position"].map(position_group)
    df["injury"] = df.apply(
        lambda r: ", ".join(
            [x for x in [r.get("report_primary_injury"), r.get("report_secondary_injury")]
             if isinstance(x, str) and x.strip()]
        ),
        axis=1,
    )
    df["status"] = df["report_status"].fillna("")
    df["source_url"] = df.apply(
        lambda r: f"https://www.nfl.com/injuries/league/{int(r['season'])}/reg{int(r['week'])}", axis=1
    )
    return df


def load_official_current() -> Optional[pd.DataFrame]:
    """Current-week official injury report (transcribed from nfl.com)."""
    path = config.RAW_DIR / OFFICIAL_FILE
    if not path.exists():
        return None
    df = pd.read_csv(path, keep_default_na=False)
    df = df.rename(columns={"player": "full_name"})
    df["position_group"] = df["position"].map(position_group)
    df["status"] = df["game_status"]
    df["injury"] = df["injury"]
    return df


def load_weekly_rosters() -> pd.DataFrame:
    df = pd.read_csv(config.RAW_DIR / "rosters_2026.csv")
    df["position_group"] = df["position"].map(position_group)
    return df


def load_depth_charts() -> pd.DataFrame:
    df = pd.read_parquet(config.RAW_DIR / "depth_charts.parquet")
    df = df.dropna(subset=["club_code", "full_name"])
    df["depth_team"] = pd.to_numeric(df["depth_team"], errors="coerce")
    df["position_group"] = df["position"].map(position_group)
    return df


def depth_snapshot(depth: pd.DataFrame) -> pd.DataFrame:
    """Most recent depth chart week for every team."""
    if depth.empty:
        return depth
    latest_week = depth.groupby("club_code")["week"].transform("max")
    return depth[depth["week"] == latest_week].copy()


def depth_tiers(depth: pd.DataFrame) -> Dict[str, Dict[str, List[Dict]]]:
    """team -> position group -> ordered list of {tier, player}."""
    out: Dict[str, Dict[str, List[Dict]]] = {}
    if depth.empty:
        return out
    for team, grp in depth.groupby("club_code"):
        by_group: Dict[str, List[Dict]] = {}
        for _, row in grp.iterrows():
            grp_name = str(row.get("position_group") or position_group(row.get("position", "")))
            by_group.setdefault(grp_name, []).append({
                "tier": int(row["depth_team"]) if pd.notna(row["depth_team"]) else None,
                "player": row.get("full_name"),
                "position": row.get("position"),
                "season": int(row["season"]) if pd.notna(row["season"]) else None,
                "week": int(row["week"]) if pd.notna(row["week"]) else None,
            })
        for grp_name, players in by_group.items():
            players.sort(key=lambda p: (p["tier"] if p["tier"] is not None else 99))
        out[team] = by_group
    return out


def current_injury_table(injuries: pd.DataFrame, week: int, official: Optional[pd.DataFrame] = None) -> List[Dict]:
    """Current-week injury rows (official transcription when available)."""
    rows: List[Dict] = []
    source = official if official is not None and len(official) else injuries[
        (injuries["week"] == week) & (injuries["status"] != "")
    ]
    if official is None or not len(official):
        week_val = week
    else:
        week_val = int(source["week"].iloc[0]) if len(source) else week
    order = {"Out": 0, "Doubtful": 1, "Questionable": 2}
    for _, r in source.iterrows():
        rows.append({
            "team": r["team"],
            "position": r["position"],
            "position_group": r["position_group"],
            "player": r["full_name"],
            "injury": r["injury"],
            "game_status": r["status"],
            "practice_status": r.get("practice_status", ""),
            "week": int(week_val),
            "source_url": r.get("source_url") or f"https://www.nfl.com/injuries/league/2026/reg{week}",
            "source_label": "NFL.com official injury report",
        })
    rows.sort(key=lambda r: (order.get(r["game_status"], 9), r["team"], r["position"]))
    return rows


def depth_deficiency_table(
    injuries: pd.DataFrame,
    depth: pd.DataFrame,
    rosters: pd.DataFrame,
    week: int,
    games: pd.DataFrame,
    official: Optional[pd.DataFrame] = None,
) -> List[Dict]:
    """Positions where the first string is unavailable and a deeper backup must start."""
    tiers = depth_tiers(depth_snapshot(depth))
    if official is not None and len(official):
        sel = official[official["status"].isin(["Out", "Doubtful"])]
        unavailable_all = official[official["status"].isin(["Out", "Doubtful"])]
    else:
        sel = injuries[(injuries["week"] == week) & (injuries["status"].isin(["Out", "Doubtful"]))]
        unavailable_all = sel

    # Which players are still on the active roster in the current week?
    active: Dict[str, set] = {}
    if len(rosters):
        wk = rosters[rosters["week"] == week]
        for team, grp in wk.groupby("team"):
            active[team] = set(grp["full_name"].dropna())

    out_rows: List[Dict] = []
    for _, r in sel.iterrows():
        team = r["team"]
        grp_name = r["position_group"]
        group_players = tiers.get(team, {}).get(grp_name, [])
        if not group_players:
            continue
        starters = [p for p in group_players if p["tier"] == 1]
        if not starters:
            continue
        starter = starters[0]
        if str(starter["player"]).strip() != str(r["full_name"]).strip():
            continue  # first string is healthy - no depth deficiency at this slot

        unavailable = set(unavailable_all[unavailable_all["team"] == team]["full_name"].dropna())
        roster_active = active.get(team, set())
        replacement = None
        for p in group_players:
            if p["tier"] == 1 or p["player"] in unavailable:
                continue
            if roster_active and p["player"] not in roster_active:
                continue  # no longer on the team - the chart is stale for this slot
            replacement = p
            break
        out_rows.append({
            "team": team,
            "position_group": grp_name,
            "starter": starter["player"],
            "starter_tier": 1,
            "starter_status": r["status"],
            "injury": r["injury"],
            "replacement": replacement["player"] if replacement else None,
            "replacement_tier": replacement["tier"] if replacement else None,
            "tier_gap": (replacement["tier"] - 1) if replacement else None,
            "depth_chart_season": starter["season"],
            "depth_chart_week": starter["week"],
            "source_url": r.get("source_url") or f"https://www.nfl.com/injuries/league/2026/reg{week}",
            "depth_source_url": "https://github.com/Beexly/Sports/blob/main/data/nflverse/hf_mikeysports_2025_depth_charts_zone1.parquet",
            "flag": "depth tier derived from a 2024 depth-chart snapshot",
        })
    out_rows.sort(key=lambda x: (-(x["tier_gap"] or 0), x["team"]))
    return out_rows


def injury_effect_on_covering(
    injuries: pd.DataFrame,
    games: pd.DataFrame,
    season: int = config.CURRENT_SEASON,
) -> List[Dict]:
    """Measured ATS impact of a position group losing its first string.

    Only games where exactly one side is missing an Out player are used, so the
    comparison is not contaminated by games where both sides are depleted.
    """
    played = games[(games["season"] == season) & games["home_score"].notna()].copy()
    rows: List[Dict] = []
    for grp in GROUPS:
        out_teams = injuries[
            (injuries["season"] == season)
            & (injuries["status"] == "Out")
            & (injuries["position_group"] == grp)
        ]
        team_weeks = set(zip(out_teams["team"], out_teams["week"]))
        if not team_weeks:
            continue
        margins = []
        for _, g in played.iterrows():
            week = int(g["week"])
            home_out = (g["home_team"], week) in team_weeks
            away_out = (g["away_team"], week) in team_weeks
            if home_out == away_out:
                continue
            if pd.isna(g["market_spread"]):
                continue
            side_margin = g["margin"] if away_out else -g["margin"]
            margins.append(side_margin + g["market_spread"])
        if not margins:
            continue
        arr = np.array(margins, dtype=float)
        rows.append({
            "position_group": grp,
            "games": int(len(arr)),
            "avg_ats_margin": float(arr.mean()),
            "ats_cover_rate": float((arr > 0).mean() + 0.5 * (arr == 0).mean()),
            "note": "Positive = the team missing the player still covered the spread.",
        })
    return rows


def injury_context_by_game(injuries: pd.DataFrame, games: pd.DataFrame,
                           season: int = config.CURRENT_SEASON) -> pd.DataFrame:
    """Per-game injury context (counts of Out players by position group)."""
    played = games[(games["season"] == season) & games["home_score"].notna()].copy()
    outs = injuries[(injuries["season"] == season) & (injuries["status"] == "Out")]
    counts = outs.groupby(["team", "week", "position_group"]).size().to_dict()
    rows = []
    for _, g in played.iterrows():
        week = int(g["week"])
        rec = {
            "game_id": g["game_id"],
            "season": season,
            "week": week,
            "gameday": g["gameday"],
            "away_team": g["away_team"],
            "home_team": g["home_team"],
            "market_spread": g["market_spread"],
            "market_total": g["market_total"],
            "margin": g["margin"],
        }
        for grp in GROUPS:
            rec[f"away_out_{grp}"] = int(counts.get((g["away_team"], week, grp), 0))
            rec[f"home_out_{grp}"] = int(counts.get((g["home_team"], week, grp), 0))
        rows.append(rec)
    return pd.DataFrame(rows)


def usage_depth_tiers(pstats26: pd.DataFrame, upto_week: int) -> Dict:
    """Depth tiers derived from 2026 usage (current, verifiable).

    For every team and offensive position group the players are ranked by the
    volume of work they have actually been given (pass attempts for quarterbacks,
    targets + carries for running backs and receivers).  Rank 1 is the first
    string, rank 2 the second string, and so on.  This replaces the much older
    published depth-chart snapshot for the groups where it can be derived.
    """
    tiers: Dict[str, Dict[str, List[Dict]]] = {}
    if pstats26 is None or not len(pstats26):
        return tiers
    df = pstats26[pstats26["week"] <= upto_week].copy()
    if df.empty:
        return tiers
    grp = df["position_group"]
    df["usage"] = np.where(
        grp == "QB",
        pd.to_numeric(df.get("attempts"), errors="coerce").fillna(0),
        pd.to_numeric(df.get("targets"), errors="coerce").fillna(0)
        + pd.to_numeric(df.get("carries"), errors="coerce").fillna(0),
    )
    team_col = "team" if "team" in df.columns else "recent_team"
    agg = (
        df.groupby([team_col, "position_group", "player_display_name"])
        .agg(usage=("usage", "sum"), games=("week", "nunique"))
        .reset_index()
    )
    agg = agg[agg["games"] >= 2]
    # Rank by games played first (a first string plays every week) and by
    # usage as the tiebreaker inside a position group.
    for (team, position), grp_df in agg.groupby([team_col, "position_group"]):
        offensive = position in ("QB", "RB", "WR", "TE")
        grp_df = grp_df.sort_values(
            ["usage", "games"] if offensive else ["games", "usage"], ascending=False
        ).reset_index(drop=True)
        entries = []
        if not offensive and len(grp_df) > 1:
            # Defensive groups have no usage signal; only accept an unambiguous
            # leader (strictly more games played than the next player).
            if grp_df.iloc[0]["games"] <= grp_df.iloc[1]["games"]:
                tiers.setdefault(team, {})[position] = []
                continue
        for rank, row in grp_df.iterrows():
            entries.append({
                "tier": int(rank + 1),
                "player": row["player_display_name"],
                "usage": float(row["usage"]),
                "games": int(row["games"]),
                "position": position,
            })
        tiers.setdefault(team, {})[position] = entries
    return tiers


def usage_deficiency_table(
    injuries: pd.DataFrame,
    depth: pd.DataFrame,
    rosters: pd.DataFrame,
    week: int,
    games: pd.DataFrame,
    official: Optional[pd.DataFrame],
    pstats26: Optional[pd.DataFrame],
) -> List[Dict]:
    """Depth deficiencies using 2026 usage tiers (falling back to the chart)."""
    if official is not None and len(official):
        sel = official[official["status"].isin(["Out", "Doubtful"])]
        unavailable_all = official[official["status"].isin(["Out", "Doubtful"])]
    else:
        sel = injuries[(injuries["week"] == week) & (injuries["status"].isin(["Out", "Doubtful"]))]
        unavailable_all = sel

    usage_weeks = int(pstats26["week"].max()) if pstats26 is not None and len(pstats26) else 0
    tiers = usage_depth_tiers(pstats26, usage_weeks) if usage_weeks else {}
    chart_tiers = depth_tiers(depth_snapshot(depth))

    rows: List[Dict] = []
    for _, r in sel.iterrows():
        team = r["team"]
        grp_name = r["position_group"]
        unavailable = set(unavailable_all[unavailable_all["team"] == team]["full_name"].dropna())
        group = tiers.get(team, {}).get(grp_name, [])
        method = "2026 usage tiers"
        chart_row = None
        if not group:
            group = chart_tiers.get(team, {}).get(grp_name, [])
            method = "2024 depth-chart snapshot (stale - no 2026 usage published for this group)"
            if group:
                chart_row = group[0]
        if not group:
            continue
        starter = group[0]
        if str(starter["player"]).strip() != str(r["full_name"]).strip():
            continue
        replacement = None
        for cand in group[1:]:
            if cand["player"] in unavailable:
                continue
            replacement = cand
            break
        rows.append({
            "team": team,
            "position_group": grp_name,
            "starter": starter["player"],
            "starter_tier": 1,
            "starter_status": r["status"],
            "injury": r["injury"],
            "replacement": replacement["player"] if replacement else None,
            "replacement_tier": replacement["tier"] if replacement else None,
            "tier_gap": (replacement["tier"] - 1) if replacement else None,
            "starter_evidence": (
                f"{starter.get('usage', 0):.0f} work units over {starter.get('games', 0)} games (weeks 1-{usage_weeks})"
                if "usage" in starter else
                f"depth-chart tier 1 (season {chart_row['season'] if chart_row else 'n/a'})"
            ),
            "method": method,
            "source_url": r.get("source_url") or f"https://www.nfl.com/injuries/league/2026/reg{week}",
            "depth_source_url": "https://github.com/Beexly/Sports/blob/main/data/nflverse/player_stats_weekly_archive.parquet",
        })
    rows.sort(key=lambda x: (-(x["tier_gap"] or 0), x["team"]))
    return rows


def depth_status_table(
    pstats26: pd.DataFrame,
    current: List[Dict],
    week: int,
    usage_week: Optional[int] = None,
) -> List[Dict]:
    """Full depth picture for the teams in the current injury report.

    Every position group of every team that appears in the current week's
    report is listed with its ranked players and the injury status of each one,
    so a reader can see exactly which string has to take over.
    """
    tiers = usage_depth_tiers(pstats26, usage_week or int(pstats26["week"].max()))
    status_by_player = {}
    for row in current:
        status_by_player[(row["team"], row["player"])] = {
            "game_status": row["game_status"],
            "injury": row["injury"],
            "practice_status": row["practice_status"],
            "source_url": row["source_url"],
        }
    rows: List[Dict] = []
    for team in sorted({r["team"] for r in current}):
        for grp_name, players in sorted(tiers.get(team, {}).items()):
            if not players:
                continue
            for entry in players[:4]:
                st = status_by_player.get((team, entry["player"]), {})
                rows.append({
                    "team": team,
                    "position_group": grp_name,
                    "tier": entry["tier"],
                    "player": entry["player"],
                    "games_played": entry.get("games"),
                    "work_units": entry.get("usage"),
                    "game_status": st.get("game_status") or "Not listed",
                    "injury": st.get("injury") or "",
                    "practice_status": st.get("practice_status") or "",
                    "must_start": bool(
                        entry["tier"] == 1 and st.get("game_status") in ("Out", "Doubtful")
                    ),
                    "source_url": st.get("source_url") or f"https://www.nfl.com/injuries/league/2026/reg{week}",
                })
    return rows


def injury_summary(injuries: pd.DataFrame, official: Optional[pd.DataFrame]) -> Dict:
    weeks = sorted(int(w) for w in injuries["week"].unique())
    summary = {
        "machine_readable_weeks": weeks,
        "machine_readable_last_week": max(weeks) if weeks else None,
        "rows": int(len(injuries)),
        "official_current_week_rows": int(len(official)) if official is not None else 0,
        "out_rows": int((injuries["status"] == "Out").sum()),
        "doubtful_rows": int((injuries["status"] == "Doubtful").sum()),
        "questionable_rows": int((injuries["status"] == "Questionable").sum()),
    }
    if official is not None and len(official):
        summary["official_teams"] = sorted(official["team"].unique().tolist())
        summary["official_out"] = int((official["status"] == "Out").sum())
        summary["official_questionable"] = int((official["status"] == "Questionable").sum())
        summary["official_doubtful"] = int((official["status"] == "Doubtful").sum())
    return summary
