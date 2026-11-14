"""Strategy library.

Every strategy is expressed as a *generator* that produces a list of bets from a
game frame.  A bet is one row:

    game_id, season, week, market, side, line, odds, outcome, profit

``profit`` is in units of one (e.g. +0.91 for a -110 winner, -1 for a loser,
0 for a push).

Parameter selection is walk-forward: for every evaluation season the strategy
parameters are re-chosen using *only* games from earlier seasons, then the
strategy is applied to the evaluation season.  Nothing that happened in the
evaluation season can influence the parameters used in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import config


# --------------------------------------------------------------------------
# Bet helpers
# --------------------------------------------------------------------------
def american_to_decimal(odds: float) -> float:
    if pd.isna(odds):
        return 1.0 + 100.0 / (-config.ODDS_MISSING)
    odds = float(odds)
    if odds < 0:
        return 1.0 + 100.0 / (-odds)
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / (-config.ODDS_MISSING)


def profit_units(outcome: float, odds: float) -> float:
    """Profit in units for a bet at the given American odds."""
    if outcome == 0.5:
        return 0.0
    dec = american_to_decimal(odds)
    return (dec - 1.0) if outcome > 0.5 else -1.0


def _pick_odds(row: pd.Series, market: str, side: str) -> float:
    """Price for a side, falling back to the documented default when absent."""
    if market == "spread":
        col = "home_spread_odds" if side == "home" else "away_spread_odds"
        val = row.get(col, np.nan)
    elif market == "total":
        col = "over_odds" if side == "over" else "under_odds"
        val = row.get(col, np.nan)
    elif market == "moneyline":
        col = "home_moneyline" if side == "home" else "away_moneyline"
        val = row.get(col, np.nan)
    else:
        val = np.nan
    if val is None or pd.isna(val):
        return float(config.ODDS_MISSING)
    return float(val)


def _bet_row(row: pd.Series, market: str, side: str, line: float, strategy: str, **meta) -> Dict:
    """Build one settled bet from a game row.

    For spread bets ``line`` is the *market* spread expressed from the home
    team's perspective (positive = home favoured), which is how the source
    dataset documents it.  The line shown to the bettor is derived from it:

        home line = -market_spread        away line = +market_spread

    so the home side covers when ``margin > market_spread`` and the away side
    covers when ``margin < market_spread`` (push on equality).
    """
    if market == "spread":
        margin = row["margin"]
        market_line = float(line)
        side_line = -market_line if side == "home" else market_line
        if side == "home":
            outcome = 1.0 if margin > market_line else (0.5 if margin == market_line else 0.0)
        else:
            outcome = 1.0 if margin < market_line else (0.5 if margin == market_line else 0.0)
        line = side_line
    elif market == "total":
        tp = row["total_points"]
        if side == "over":
            outcome = 1.0 if tp > line else (0.5 if tp == line else 0.0)
        else:
            outcome = 1.0 if tp < line else (0.5 if tp == line else 0.0)
    elif market == "moneyline":
        outcome = 1.0 if row["home_win"] > 0.5 else (0.5 if row["home_win"] == 0.5 else 0.0)
        if side == "away":
            outcome = 1.0 - outcome
    else:
        raise ValueError(f"unsupported market {market}")
    odds = _pick_odds(row, market, side)
    return {
        "game_id": row["game_id"],
        "season": int(row["season"]),
        "week": int(row["week"]),
        "gameday": row["gameday"],
        "market": market,
        "side": side,
        "line": float(line),
        "odds": odds,
        "outcome": outcome,
        "profit": profit_units(outcome, odds),
        "strategy": strategy,
        "away_team": row["away_team"],
        "home_team": row["home_team"],
        **{k: v for k, v in meta.items()},
    }


# --------------------------------------------------------------------------
# Strategy definitions
# --------------------------------------------------------------------------
@dataclass
class Strategy:
    key: str
    name: str
    family: str
    description: str
    param_grid: List[Dict] = field(default_factory=list)
    build: Optional[Callable[[pd.DataFrame, Dict], List[Dict]]] = None
    default_params: Dict = field(default_factory=dict)
    source_keys: List[str] = field(default_factory=list)

    def generate(self, frame: pd.DataFrame, params: Dict) -> List[Dict]:
        if self.build is None:
            return []
        return self.build(frame, params)


def _played(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame[frame["home_score"].notna()].copy()
    return df[df["market_spread"].notna() | df["market_total"].notna()]


# --- Spread family -------------------------------------------------------
def build_fade_favourite(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Bet the underdog whenever the market line is at least ``min_line``."""
    min_line = params["min_line"]
    max_line = params.get("max_line", 99.0)
    out = []
    for _, row in _played(frame).iterrows():
        line = row["market_spread"]
        if pd.isna(line) or abs(line) < min_line or abs(line) > max_line:
            continue
        side = "away" if line > 0 else "home"      # underdog takes the points
        out.append(_bet_row(row, "spread", side, line, "S_fade_favourite",
                             edge_bucket=f"{min_line}-{max_line}"))
    return out


def build_fade_favourite_band(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Bet the underdog only inside a specific spread band."""
    lo, hi = params["min_line"], params["max_line"]
    out = []
    for _, row in _played(frame).iterrows():
        line = row["market_spread"]
        if pd.isna(line) or not (lo <= abs(line) < hi):
            continue
        side = "away" if line > 0 else "home"
        out.append(_bet_row(row, "spread", side, line, "S_fade_band",
                             edge_bucket=f"{lo}-{hi}"))
    return out


def build_home_dog(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Bet the home team whenever it is the underdog."""
    out = []
    for _, row in _played(frame).iterrows():
        line = row["market_spread"]
        if pd.isna(line) or line >= 0:
            continue
        out.append(_bet_row(row, "spread", "home", line, "S_home_dog"))
    return out


def build_model_edge_spread(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Bet the side our originated line says is worth more than the market."""
    min_edge = params["min_edge"]
    out = []
    for _, row in _played(frame).iterrows():
        line = row["market_spread"]
        delta = row.get("spread_delta", np.nan)
        if pd.isna(line) or pd.isna(delta) or abs(delta) < min_edge:
            continue
        side = "home" if delta > 0 else "away"
        out.append(_bet_row(row, "spread", side, line, "S_model_spread",
                             model_line=row.get("model_spread"), delta=float(delta)))
    return out


def build_rest_edge(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Bet the side with materially more rest than the market line implies."""
    min_rest = params["min_rest"]
    out = []
    for _, row in _played(frame).iterrows():
        rest = row.get("rest_diff", np.nan)
        line = row["market_spread"]
        if pd.isna(rest) or pd.isna(line) or rest < min_rest:
            continue
        out.append(_bet_row(row, "spread", "home", line, "S_rest_home"))
    return out


def build_elo_momentum(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Bet the side whose Elo moved further than the market line implies."""
    min_delta = params["min_delta"]
    out = []
    for _, row in _played(frame).iterrows():
        elo_delta = row.get("elo_diff_home", np.nan)
        line = row["market_spread"]
        if pd.isna(elo_delta) or pd.isna(line):
            continue
        # convert Elo edge to an expected point difference (rough scale: 25 Elo ~ 1 pt)
        implied_pts = elo_delta / 25.0
        edge = implied_pts - line
        if abs(edge) < min_delta:
            continue
        side = "home" if edge > 0 else "away"
        out.append(_bet_row(row, "spread", side, line, "S_elo_momentum",
                             edge_pts=float(edge)))
    return out


def build_qb_change(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Bet against a team forced to start a different quarterback.

    The signal is detected purely from the published game records: a team whose
    starting quarterback differs from the quarterback who started its previous
    game.  No injury data is required, so the signal is testable over the full
    history.
    """
    out = []
    df = _played(frame).sort_values(["gameday", "game_id"]).copy()
    last_home_qb: Dict[str, str] = {}
    last_away_qb: Dict[str, str] = {}
    for _, row in df.iterrows():
        h, a = row["home_team"], row["away_team"]
        hq, aq = row.get("home_qb_name"), row.get("away_qb_name")
        changed_home = bool(hq) and (h in last_home_qb) and (last_home_qb[h] != hq)
        changed_away = bool(aq) and (a in last_away_qb) and (last_away_qb[a] != aq)
        if changed_home and not changed_away:
            out.append(_bet_row(row, "spread", "away", row["market_spread"],
                                 "S_qb_change_home", note="home QB changed"))
        elif changed_away and not changed_home:
            out.append(_bet_row(row, "spread", "home", row["market_spread"],
                                 "S_qb_change_home", note="away QB changed"))
        if hq:
            last_home_qb[h] = hq
        if aq:
            last_away_qb[a] = aq
    return out


# --- Total family --------------------------------------------------------
def build_under_band(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    lo, hi = params["min_total"], params["max_total"]
    out = []
    for _, row in _played(frame).iterrows():
        line = row["market_total"]
        if pd.isna(line) or not (lo <= line < hi):
            continue
        out.append(_bet_row(row, "total", "under", line, "S_under_band"))
    return out


def build_over_band(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    lo, hi = params["min_total"], params["max_total"]
    out = []
    for _, row in _played(frame).iterrows():
        line = row["market_total"]
        if pd.isna(line) or not (lo <= line < hi):
            continue
        out.append(_bet_row(row, "total", "over", line, "S_over_band"))
    return out


def build_model_edge_total(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    min_edge = params["min_edge"]
    out = []
    for _, row in _played(frame).iterrows():
        line = row["market_total"]
        delta = row.get("total_delta", np.nan)
        if pd.isna(line) or pd.isna(delta) or abs(delta) < min_edge:
            continue
        side = "over" if delta > 0 else "under"
        out.append(_bet_row(row, "total", side, line, "S_model_total",
                             model_line=row.get("model_total"), delta=float(delta)))
    return out


def build_wind_under(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Under when the outdoor game is windy."""
    min_wind = params["min_wind"]
    out = []
    for _, row in _played(frame).iterrows():
        line = row["market_total"]
        roof = str(row.get("roof", ""))
        wind = row.get("wind_mph", np.nan)
        if pd.isna(line) or roof in ("dome", "closed"):
            continue
        if pd.isna(wind) or wind < min_wind:
            continue
        out.append(_bet_row(row, "total", "under", line, "S_wind_under",
                             wind=float(wind)))
    return out


def build_cold_under(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Under when the outdoor game is cold (the classic 'cold weather under')."""
    max_temp = params["max_temp"]
    out = []
    for _, row in _played(frame).iterrows():
        line = row["market_total"]
        roof = str(row.get("roof", ""))
        temp = row.get("temp_f", np.nan)
        if pd.isna(line) or roof in ("dome", "closed"):
            continue
        if pd.isna(temp) or temp > max_temp:
            continue
        out.append(_bet_row(row, "total", "under", line, "S_cold_under",
                             temp=float(temp)))
    return out


def build_dome_under(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Under in roofed stadiums - no weather, no kickoff winds."""
    min_total = params["min_total"]
    out = []
    for _, row in _played(frame).iterrows():
        line = row["market_total"]
        roof = str(row.get("roof", ""))
        if pd.isna(line) or roof not in ("dome", "closed") or line < min_total:
            continue
        out.append(_bet_row(row, "total", "under", line, "S_dome_under"))
    return out


# --- Parlay family -------------------------------------------------------
def _pair_parlays(legs: pd.DataFrame, strategy: str, same_game: bool) -> List[Dict]:
    """Pair single legs into 2-leg parlays, at most one pair per game/week."""
    if legs.empty:
        return []
    legs = legs.copy()
    legs["week_key"] = legs["season"].astype(str) + "_" + legs["week"].astype(str)
    used_games = set()
    out: List[Dict] = []
    for wk, grp in legs.groupby("week_key"):
        grp = grp.sort_values("edge", ascending=False)
        taken: List[pd.Series] = []
        for _, a in grp.iterrows():
            for b in taken:
                if not same_game and a["game_id"] == b["game_id"]:
                    continue
                if a["game_id"] in used_games or b["game_id"] in used_games:
                    continue
                d1, d2 = american_to_decimal(a["odds"]), american_to_decimal(b["odds"])
                joint = a["outcome"] * b["outcome"]
                if joint == 1.0:
                    profit = d1 * d2 - 1.0
                elif joint == 0.25:
                    profit = (d1 - 1.0) * 0.5 + (d2 - 1.0) * 0.5
                elif joint == 0.0:
                    profit = -1.0
                else:
                    profit = 0.0
                out.append({
                    "game_id": f"{a['game_id']}|{b['game_id']}",
                    "season": int(a["season"]),
                    "week": int(a["week"]),
                    "gameday": a["gameday"],
                    "market": "parlay",
                    "side": "parlay",
                    "line": np.nan,
                    "odds": float(np.round((d1 * d2 - 1.0) * 100)),
                    "outcome": float(joint),
                    "profit": float(profit),
                    "strategy": strategy,
                    "away_team": f"{a['away_team']}@{b['away_team']}",
                    "home_team": f"{a['home_team']}@{b['home_team']}",
                    "leg1": f"{a['strategy']}:{a['side']}{a['line']}",
                    "leg2": f"{b['strategy']}:{b['side']}{b['line']}",
                    "edge": float(a.get("edge", 0) + b.get("edge", 0)),
                })
                used_games.add(a["game_id"])
                used_games.add(b["game_id"])
                taken.append(b)
                break
            else:
                if len(taken) < 1:
                    taken.append(a)
                    continue
    return out


def build_parlay_spread_total(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Two-leg parlay: one model-spread leg + one model-total leg."""
    spread_bets = build_model_edge_spread(frame, {"min_edge": params["min_edge"]})
    total_bets = build_model_edge_total(frame, {"min_edge": params["min_edge"]})
    legs = pd.DataFrame(spread_bets + total_bets)
    if legs.empty:
        return []
    legs["edge"] = [abs(b.get("delta", 0.0)) for b in spread_bets + total_bets]
    return _pair_parlays(legs, "P_spread_total", same_game=False)


def build_parlay_same_game(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Same-game parlay: model spread edge + model total edge."""
    spread_bets = build_model_edge_spread(frame, {"min_edge": params["min_edge"]})
    total_bets = build_model_edge_total(frame, {"min_edge": params["min_edge"]})
    sb = {b["game_id"]: b for b in spread_bets}
    tb = {b["game_id"]: b for b in total_bets}
    out = []
    for gid, a in sb.items():
        b = tb.get(gid)
        if b is None:
            continue
        d1, d2 = american_to_decimal(a["odds"]), american_to_decimal(b["odds"])
        joint = a["outcome"] * b["outcome"]
        if joint == 1.0:
            profit = d1 * d2 - 1.0
        elif joint == 0.25:
            profit = (d1 - 1.0) * 0.5 + (d2 - 1.0) * 0.5
        elif joint == 0.0:
            profit = -1.0
        else:
            profit = 0.0
        out.append({
            "game_id": gid,
            "season": int(a["season"]),
            "week": int(a["week"]),
            "gameday": a["gameday"],
            "market": "parlay",
            "side": "parlay",
            "line": np.nan,
            "odds": float(np.round((d1 * d2 - 1.0) * 100)),
            "outcome": float(joint),
            "profit": float(profit),
            "strategy": "P_same_game",
            "away_team": a["away_team"],
            "home_team": a["home_team"],
            "leg1": f"spread:{a['side']}{a['line']}",
            "leg2": f"total:{b['side']}{b['line']}",
            "edge": float(abs(a.get("delta", 0)) + abs(b.get("delta", 0))),
        })
    return out


def build_parlay_fade_under(frame: pd.DataFrame, params: Dict) -> List[Dict]:
    """Two-leg parlay: underdog side + under a mid-range total."""
    fade = build_fade_favourite(frame, params)
    under = build_under_band(frame, params)
    legs = pd.DataFrame(fade + under)
    if legs.empty:
        return []
    legs["edge"] = [0.0] * len(legs)
    return _pair_parlays(legs, "P_fade_under", same_game=False)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------
def registry() -> List[Strategy]:
    return [
        Strategy(
            key="S_fade_favourite",
            name="Fade the favourite (any line >= threshold)",
            family="spread",
            description="Bet the underdog whenever the market spread is at least the threshold.",
            param_grid=[{"min_line": m} for m in (3.5, 5.0, 6.5, 7.0, 7.5, 9.0, 10.0, 13.5)],
            default_params={"min_line": 7.5},
            build=build_fade_favourite,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_fade_band",
            name="Fade the favourite (spread band)",
            family="spread",
            description="Bet the underdog inside a chosen spread band.",
            param_grid=[{"min_line": lo, "max_line": hi} for lo, hi in
                        ((3.0, 5.0), (4.0, 7.0), (5.0, 7.0), (6.0, 9.0), (7.0, 10.0), (9.0, 99.0))],
            default_params={"min_line": 5.0, "max_line": 7.0},
            build=build_fade_favourite_band,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_home_dog",
            name="Home underdog against the spread",
            family="spread",
            description="Bet the home team in every game where the market makes it the underdog.",
            param_grid=[{}],
            default_params={},
            build=build_home_dog,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_model_spread",
            name="Originated line vs market spread",
            family="spread",
            description="Bet the side where our originated spread differs from the market spread.",
            param_grid=[{"min_edge": e} for e in config.SPREAD_EDGE_THRESHOLDS],
            default_params={"min_edge": 1.0},
            build=build_model_edge_spread,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_rest_home",
            name="Rest advantage (home side)",
            family="spread",
            description="Bet the home team when it has a rest advantage over the visitor.",
            param_grid=[{"min_rest": r} for r in (2, 3, 4)],
            default_params={"min_rest": 3},
            build=build_rest_edge,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_elo_momentum",
            name="Elo momentum vs market spread",
            family="spread",
            description="Bet the side whose Elo edge is larger than the market spread implies.",
            param_grid=[{"min_delta": d} for d in (0.5, 1.0, 1.5, 2.0, 3.0)],
            default_params={"min_delta": 1.0},
            build=build_elo_momentum,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_qb_change",
            name="Backup starting quarterback (bet against the team)",
            family="spread",
            description="Bet against the team whose starting quarterback changed from the previous game.",
            param_grid=[{}],
            default_params={},
            build=build_qb_change,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_under_band",
            name="Under a total band",
            family="total",
            description="Bet the under for market totals inside a chosen band.",
            param_grid=[{"min_total": lo, "max_total": hi} for lo, hi in
                        ((38.0, 42.0), (40.0, 44.0), (42.0, 46.0), (43.0, 47.0), (44.0, 48.0),
                         (45.0, 49.0), (46.0, 52.0), (48.0, 99.0))],
            default_params={"min_total": 44.0, "max_total": 48.0},
            build=build_under_band,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_over_band",
            name="Over a total band",
            family="total",
            description="Bet the over for market totals inside a chosen band.",
            param_grid=[{"min_total": lo, "max_total": hi} for lo, hi in
                        ((35.0, 40.0), (38.0, 42.0), (40.0, 44.0), (42.0, 46.0), (44.0, 48.0))],
            default_params={"min_total": 38.0, "max_total": 42.0},
            build=build_over_band,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_model_total",
            name="Originated total vs market total",
            family="total",
            description="Bet the side where our originated total differs from the market total.",
            param_grid=[{"min_edge": e} for e in config.TOTAL_EDGE_THRESHOLDS],
            default_params={"min_edge": 1.0},
            build=build_model_edge_total,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_wind_under",
            name="Wind - under",
            family="total",
            description="Bet the under in outdoor games with sustained wind.",
            param_grid=[{"min_wind": w} for w in (8.0, 10.0, 12.0, 14.0, 16.0)],
            default_params={"min_wind": 12.0},
            build=build_wind_under,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_cold_under",
            name="Cold weather - under",
            family="total",
            description="Bet the under in outdoor games with cold temperatures.",
            param_grid=[{"max_temp": t} for t in (25.0, 30.0, 32.0, 35.0, 40.0)],
            default_params={"max_temp": 32.0},
            build=build_cold_under,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="S_dome_under",
            name="Roof closed - under",
            family="total",
            description="Bet the under in roofed stadiums above a total threshold.",
            param_grid=[{"min_total": t} for t in (42.0, 44.0, 46.0, 48.0)],
            default_params={"min_total": 44.0},
            build=build_dome_under,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="P_spread_total",
            name="Parlay: model spread edge + model total edge",
            family="parlay",
            description="Two-leg parlay pairing the strongest spread and total edges of the week.",
            param_grid=[{"min_edge": e} for e in (0.5, 1.0, 1.5, 2.0)],
            default_params={"min_edge": 1.0},
            build=build_parlay_spread_total,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="P_same_game",
            name="Parlay: same-game spread + total edge",
            family="parlay",
            description="Same-game parlay combining the model spread and total edges.",
            param_grid=[{"min_edge": e} for e in (0.5, 1.0, 1.5, 2.0)],
            default_params={"min_edge": 1.0},
            build=build_parlay_same_game,
            source_keys=["nfldata_games"],
        ),
        Strategy(
            key="P_fade_under",
            name="Parlay: underdog + under mid total",
            family="parlay",
            description="Two-leg parlay combining an underdog spread leg with an under total leg.",
            param_grid=[{"min_line": m, "min_total": 44.0, "max_total": 48.0} for m in (3.5, 5.0, 6.5, 7.5)],
            default_params={"min_line": 6.5, "min_total": 44.0, "max_total": 48.0},
            build=build_parlay_fade_under,
            source_keys=["nfldata_games"],
        ),
    ]
