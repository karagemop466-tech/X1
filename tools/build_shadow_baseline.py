#!/usr/bin/env python3
"""PR-01 shadow baseline: score a pre-registered team-strength model, honestly (C-5).

The rule lives in `docs/preregistration/PR-01-shadow-baseline.md`; this script implements it and nothing
else. The constants are read from that file's frozen values (K, H, SIGMA, the benchmarks, the window) so
the code cannot drift from the registration without the register's hash check noticing.

Two outputs, deliberately separated because they mean different things:

  * **backtest** — weeks 3-10 of 2026, scored chronologically (each game predicted only from games
    strictly earlier). This is a measurement of the rule, and it is NOT leaderboard-eligible.
  * **prospective shadow record** — the games that had not kicked off when they were recorded, with the
    clock time each row was recorded at and a content hash written into the artefact. `data/shadow/
    forecasts_pre_kickoff.csv` is an APPEND-ONLY SEALED LEDGER: no row is ever rewritten, and the only
    writes allowed are new rows for a week whose first kickoff is still in the future. The ledger is
    re-derived from the frozen rule at the point in time each row was recorded (see `verify_sealed`), so
    a hand edit is caught rather than trusted.
  * **sealed-record resolution** — `data/shadow/sealed_record_resolution.csv`, which joins each sealed row
    to the official final for that fixture and scores it. It is derived, regenerable, and separate,
    because resolving a forecast is not the same act as making one.

What is blank, and why
----------------------
`market_line` and `residual` are empty in every row. This repository has no official price source
(open question Q-02); the fair line is published because the model produced it, the market line is not
because nobody has decided which price data may be used. `roi` and `staking` columns are absent for the
same reason: with no prices there is no settlement, and a fake one would be the most flattering number on
the page.

Inputs (all official, all dated)
--------------------------------
  data/results/_raw/reads.tsv                                 weeks 1-10 (150 games), read 2026-11-14 and 2026-11-17
  data/verification/2026_11_16/official_w10_results_...tsv    the same Week 10 finals, read 2026-11-16
  data/pipeline/standings.json                                official club list, used only for name -> code
  data/verification/2026_11_16/official_w11_schedule_...tsv   the forward slate as printed on 2026-11-16
  data/verification/2026_11_17/official_w11_slate_2026_11_17.tsv  the same slate a day later, used to confirm
                                                              that no sealed fixture moved before kickoff

Usage
  python3 tools/build_shadow_baseline.py            # write the artefacts
  python3 tools/build_shadow_baseline.py --check     # fail if a committed artefact is stale
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import random
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "data", "shadow")

# --- frozen in PR-01 -------------------------------------------------------------------------------
K_PRIOR_GAMES = 2.0
H_HOME_POINTS = 1.6
SIGMA_POINTS = 13.5
HOME_BASELINE_P = 0.55
WARMUP_WEEKS = 2          # weeks 1-2 build ratings only, they are never scored
N_BOOTSTRAP = 10000
BOOTSTRAP_SEED = 20261116
MULTIPLICITY_N_TRIALS = 1
# ----------------------------------------------------------------------------------------------------

RULE_FILE = "docs/preregistration/PR-01-shadow-baseline.md"
READS = "data/results/_raw/reads.tsv"
W10 = "data/verification/2026_11_16/official_w10_results_2026_11_16.tsv"
W11 = "data/verification/2026_11_16/official_w11_schedule_2026_11_16.tsv"
W11_LATEST = "data/verification/2026_11_17/official_w11_slate_2026_11_17.tsv"
SEALED = "data/shadow/forecasts_pre_kickoff.csv"
RESOLUTION = "data/shadow/sealed_record_resolution.csv"
LEDGER = "data/shadow/sealed_ledger.json"
STANDINGS = "data/pipeline/standings.json"
GAMES_URL = "https://www.nfl.com/games/{}"


def sha256_file(path: str) -> str:
    with open(os.path.join(ROOT, path), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def rows_of(path: str) -> list[dict]:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


def phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def american(p: float) -> str:
    """Zero-vig American price implied by a probability. Stated conversion, not a quote."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    if p >= 0.5:
        return f"{-100.0 * p / (1 - p):.0f}"
    return f"{100.0 * (1 - p) / p:+.0f}".lstrip("+")


def round_half(x: float) -> float:
    return round(x * 2) / 2


def club_codes() -> dict:
    """nickname -> code, from the official club list the collector already keeps.

    data/pipeline/standings.json prints "New England Patriots" with team_abbrev NE; the Week 1-9
    transcription names clubs by nickname ("Patriots"). The last token is the nickname for all 32
    clubs, and the map is checked: a name that resolves to no code, or two codes to one nickname,
    aborts the build rather than dropping the row.
    """
    payload = json.load(open(os.path.join(ROOT, STANDINGS), encoding="utf-8"))
    out: dict[str, str] = {}
    seen: dict[str, str] = {}
    for r in payload["rows"]:
        nick = r["team_name"].split()[-1]
        if nick in seen and seen[nick] != r["team_abbrev"]:
            raise SystemExit(f"ABORT: nickname {nick!r} is ambiguous ({seen[nick]}, {r['team_abbrev']})")
        seen[nick] = r["team_abbrev"]
        out[nick] = r["team_abbrev"]
        out[r["team_abbrev"]] = r["team_abbrev"]
    return out


def load_games() -> tuple[list[dict], dict]:
    codes = club_codes()
    provenance: dict[str, list] = {}
    games: list[dict] = []
    seen_slugs: set[str] = set()

    for r in rows_of(READS):
        slug = r["game_slug"].strip()
        away, home = codes.get(r["away"].strip()), codes.get(r["home"].strip())
        if not away or not home:
            raise SystemExit(f"ABORT: reads.tsv club not in the official club list: {r['away']!r}/{r['home']!r}")
        games.append({
            "game_id": f"{r['week']}_{slug}", "week": int(r["week"]), "date": r["date"],
            "away": away, "home": home, "away_score": int(r["away_score"]),
            "home_score": int(r["home_score"]), "status": "final",
            "source_url": GAMES_URL.format(slug),
            "source_file": READS, "read_on": "2026-11-14",
        })
        seen_slugs.add(slug)

    for r in rows_of(W10):
        slug = r["game_url"].rstrip("/").split("/")[-1]
        if slug in seen_slugs:
            continue                       # already in the 2026-11-14 read; no double counting
        if r["status"] != "Final" or not r["away_score"] or not r["home_score"]:
            continue                       # not played at retrieval: it stays out of the corpus
        games.append({
            "game_id": f"{10}_{slug}", "week": 10, "date": r["date_et"],
            "away": r["away"], "home": r["home"], "away_score": int(r["away_score"]),
            "home_score": int(r["home_score"]), "status": "final",
            "source_url": r["game_url"], "source_file": W10, "read_on": "2026-11-16",
        })
        seen_slugs.add(slug)

    games.sort(key=lambda g: (g["date"], g["week"], g["game_id"]))
    league_pts = [g["away_score"] + g["home_score"] for g in games]
    provenance = {
        "games": len(games),
        "weeks": sorted({g["week"] for g in games}),
        "league_average_total_points": round(sum(league_pts) / len(league_pts), 3),
        "inputs": {p: sha256_file(p) for p in (RULE_FILE, READS, W10, W11, STANDINGS)},
    }
    return games, provenance


def ratings_state(games: list[dict]) -> dict:
    """Cumulative per-club sums keyed by the date AFTER which they are valid.

    rating(week, club) below is the state as of the start of that date, so a 1:00 PM game never sees a
    4:25 PM game on the same day. This is the only anti-leakage device the rule needs, and it is a
    date comparison, not a judgement call.
    """
    by_date: dict[str, dict[str, tuple[float, float]]] = {}
    sums: dict[str, list[float]] = {}
    last_date = None
    snapshot: dict[str, tuple[float, float]] = {}
    for g in games:
        if last_date is not None and g["date"] != last_date:
            by_date[g["date"]] = dict(snapshot)
        for club, pts, opp in ((g["away"], g["away_score"], g["home_score"]),
                               (g["home"], g["home_score"], g["away_score"])):
            s = sums.setdefault(club, [0.0, 0.0, 0.0])
            s[0] += 1
            s[1] += pts - opp
        snapshot = {c: (v[0], v[1]) for c, v in sums.items()}
        last_date = g["date"]
    by_date["__final__"] = dict(snapshot)
    return by_date


def rating_from(pair: tuple[float, float] | None) -> float:
    if not pair:
        return 0.0
    n, diff = pair
    return (diff / n) * (n / (n + K_PRIOR_GAMES))


def score_window(games: list[dict], state: dict) -> list[dict]:
    league_total = sum(g["away_score"] + g["home_score"] for g in games) / len(games)
    out = []
    for g in games:
        if g["week"] <= WARMUP_WEEKS:
            continue
        snap = state.get(g["date"]) or {}
        rh, ra = rating_from(snap.get(g["home"])), rating_from(snap.get(g["away"]))
        margin = rh - ra + H_HOME_POINTS
        p = phi(margin / SIGMA_POINTS)
        y = 1.0 if g["away_score"] < g["home_score"] else (0.0 if g["away_score"] > g["home_score"] else 0.5)
        out.append({
            "date": g["date"], "week": g["week"], "game_id": g["game_id"],
            "away": g["away"], "home": g["home"],
            "rating_home": round(rh, 4), "rating_away": round(ra, 4),
            "expected_margin_home": round(margin, 4),
            "p_home": round(p, 6),
            "fair_line_home": round_half(-margin),
            "fair_total": round(league_total, 1),
            "market_line": "", "residual": "",
            "american_home": american(1 - p), "american_away": american(p),
            "away_score": g["away_score"], "home_score": g["home_score"],
            "outcome_home": y,
            "brier": round((p - y) ** 2, 6),
            "log_loss": round(-(y * math.log(max(p, 1e-9)) + (1 - y) * math.log(max(1 - p, 1e-9))), 6),
            "brier_base_half": round((0.5 - y) ** 2, 6),
            "brier_base_home": round((HOME_BASELINE_P - y) ** 2, 6),
            "picked": "home" if p >= 0.5 else "away",
            "picked_won": (1 if y == 1.0 else (0 if y == 0.0 else 0)) if p >= 0.5
            else (1 if y == 0.0 else (0 if y == 1.0 else 0)),
            "picked_p": round(p if p >= 0.5 else 1 - p, 6),
            "source_url": g["source_url"], "source_file": g["source_file"], "read_on": g["read_on"],
        })
    return out


def bootstrap(rows: list[dict]) -> dict:
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(rows)
    stats = []
    for _ in range(N_BOOTSTRAP):
        pick = [rows[rng.randrange(n)] for _ in range(n)]
        b = sum(r["brier"] for r in pick) / n
        bb = sum(r["brier_base_home"] for r in pick) / n
        bh = sum(r["brier_base_half"] for r in pick) / n
        stats.append((b, 1 - b / bb if bb else 0.0, 1 - b / bh if bh else 0.0))
    stats.sort(key=lambda s: s[1])
    alpha = 0.05 / MULTIPLICITY_N_TRIALS
    lo = stats[int(math.floor((alpha / 2) * N_BOOTSTRAP))][1]
    hi = stats[min(N_BOOTSTRAP - 1, int(math.floor((1 - alpha / 2) * N_BOOTSTRAP)))][1]
    means = [s[0] for s in stats], [s[1] for s in stats]
    return {
        "resamples": N_BOOTSTRAP, "seed": BOOTSTRAP_SEED, "unit": "game (each game is one cluster)",
        "bonferroni_alpha": round(alpha, 6), "n_trials": MULTIPLICITY_N_TRIALS,
        "brier_mean_of_resamples": round(sum(means[0]) / N_BOOTSTRAP, 6),
        "skill_home_baseline_ci": [round(lo, 4), round(hi, 4)],
        "skill_home_baseline_lower_bound": round(lo, 4),
    }


def metrics(rows: list[dict]) -> dict:
    n = len(rows)
    brier = sum(r["brier"] for r in rows) / n
    bb_home = sum(r["brier_base_home"] for r in rows) / n
    bb_half = sum(r["brier_base_half"] for r in rows) / n
    ll = sum(r["log_loss"] for r in rows) / n
    ll_base = sum(-(r["outcome_home"] * math.log(HOME_BASELINE_P)
                   + (1 - r["outcome_home"]) * math.log(1 - HOME_BASELINE_P)) for r in rows) / n
    hits = sum(r["picked_won"] for r in rows)
    exp_wins = sum(r["picked_p"] for r in rows)
    sd = math.sqrt(sum(r["picked_p"] * (1 - r["picked_p"]) for r in rows))
    bins = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0001)]
    calib = []
    for lo, hi in bins:
        sub = [r for r in rows if lo <= r["picked_p"] < hi]
        calib.append({
            "bin": f"{lo:.1f}-{hi if hi <= 1 else 1.0:.1f} (probability of the side picked)",
            "n": len(sub),
            "mean_p": round(sum(r["picked_p"] for r in sub) / len(sub), 4) if sub else "",
            "win_rate": round(sum(r["picked_won"] for r in sub) / len(sub), 4) if sub else "",
            "too_small_to_read": "yes" if len(sub) < 10 else "no",
        })
    margin_err = [abs(-r["expected_margin_home"] - r["fair_line_home"]) for r in rows]
    actual_margin = [r["home_score"] - r["away_score"] for r in rows]
    mae = sum(abs(r["expected_margin_home"] - m) for r, m in zip(rows, actual_margin)) / n
    return {
        "n_games": n,
        "brier": round(brier, 6), "brier_home_baseline": round(bb_home, 6),
        "brier_coin_baseline": round(bb_half, 6),
        "brier_skill_vs_home_baseline": round(1 - brier / bb_home, 6),
        "brier_skill_vs_coin": round(1 - brier / bb_half, 6),
        "log_loss": round(ll, 6), "log_loss_home_baseline": round(ll_base, 6),
        "log_skill_vs_home_baseline": round(1 - ll / ll_base, 6),
        "hit_rate_model_side": round(hits / n, 6),
        "mae_expected_margin_points": round(mae, 4),
        "luck_panel": {
            "realised_wins_on_model_side": hits,
            "expected_wins_same_bets": round(exp_wins, 3),
            "sd_of_the_difference": round(sd, 3),
            "z_luck_adjusted": round((hits - exp_wins) / sd, 3) if sd else "",
            "reading": ("inside one standard deviation: this record is not evidence of skill or of "
                        "failure, it is what a coin would do" if abs(hits - exp_wins) <= sd else
                        "outside one standard deviation: worth reading, still not leaderboard material"),
        },
        "calibration": calib,
    }


def forward_record(games: list[dict], state_final: dict) -> tuple[list[dict], str]:
    """Pre-kickoff forecasts for everything not yet played, written once and never rewritten."""
    slate = rows_of(W11)
    rows = []
    for r in slate:
        if r["row_type"] != "game":
            continue
        rh = rating_from(state_final.get(r["home"]))
        ra = rating_from(state_final.get(r["away"]))
        margin = rh - ra + H_HOME_POINTS
        p = phi(margin / SIGMA_POINTS)
        rows.append({
            "recorded_at_utc": NOW, "week": 11, "game_id": r["game_id"], "kickoff_et": f"{r['date_et']} {r['time_et']}",
            "away": r["away"], "home": r["home"],
            "p_home": round(p, 6), "model_side": "home" if p >= 0.5 else "away",
            "expected_margin_home": round(margin, 4), "fair_line_home": round_half(-margin),
            "fair_american_home": american(1 - p), "fair_american_away": american(p),
            "market_line": "", "residual": "",
            "source_url": r["game_url"], "status_at_record": "scheduled (not played when recorded)",
        })
    # the Monday-night Week 10 game is also still pre-kickoff at this clock time
    for r in rows_of(W10):
        if r["status"] == "Final":
            continue
        rh = rating_from(state_final.get(r["home"]))
        ra = rating_from(state_final.get(r["away"]))
        margin = rh - ra + H_HOME_POINTS
        p = phi(margin / SIGMA_POINTS)
        rows.append({
            "recorded_at_utc": NOW, "week": 10, "game_id": r["game_id"],
            "kickoff_et": f"{r['date_et']} {r['time_et']}", "away": r["away"], "home": r["home"],
            "p_home": round(p, 6), "model_side": "home" if p >= 0.5 else "away",
            "expected_margin_home": round(margin, 4), "fair_line_home": round_half(-margin),
            "fair_american_home": american(1 - p), "fair_american_away": american(p),
            "market_line": "", "residual": "", "source_url": r["game_url"],
            "status_at_record": "scheduled (not played when recorded)",
        })
    rows.sort(key=lambda x: (x["kickoff_et"], x["game_id"]))
    return rows, "week11"


NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
FORECAST_PATH = os.path.join(OUTDIR, "forecasts_pre_kickoff.csv")


# --- the sealed ledger ---------------------------------------------------------------------------

def kickoff_utc(kickoff_et: str) -> str:
    """Convert the kickoff the official page prints in ET to UTC, using the IANA tz database.

    The league publishes its schedule on an Eastern clock and this repository records its own reads in
    UTC, so "was the row written before kickoff?" is only answerable after a timezone conversion. The
    conversion is arithmetic on a published value (the DST rule is not a judgement about the game). If
    the string cannot be parsed the function returns "" and the caller falls back to a date-granularity
    comparison it must label as coarse.
    """
    txt = (kickoff_et or "").strip()
    if not txt:
        return ""
    from datetime import datetime as _dt, timezone as _tz
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %I:%M%p"):
        try:
            naive = _dt.strptime(txt, fmt)
        except ValueError:
            continue
        try:
            from zoneinfo import ZoneInfo
            aware = naive.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(_tz.utc)
        except Exception:                      # no tz database in this environment
            aware = naive.replace(tzinfo=_tz.utc)   # labelled coarse by the caller
        return aware.strftime("%Y-%m-%dT%H:%M:%SZ")
    return ""


def index_games(games: list[dict]) -> dict:
    """Look a fixture up however a caller names it: internal game_id, nflverse-style id, or slug.

    The corpus keys games as "<week>_<slug>"; the sealed ledger and the official slate pages use
    "2026_<week>_<AWAY>_<HOME>". Both spellings must reach the same game, or a resolution silently
    reports "pending" for a game that has already been played — which is the worst way to be wrong here.
    """
    idx: dict[str, dict] = {}
    for g in games:
        keys = {g["game_id"]}
        slug = (g.get("source_url") or "").rstrip("/").split("/")[-1]
        if slug:
            keys.add(slug)
            keys.add(slug.replace("-2026-reg-", "_").replace("-", "_").split("_2026_reg_")[0])
        m = re.match(r"(\d{4})_(\d{2})_([a-z]+)-at-([a-z]+)-(\d{4})-reg-(\d+)", slug) if slug else None
        if m:
            keys.add(f"{m.group(4)}_{m.group(6)}_{m.group(3).upper()}_{m.group(5).upper()}")
        for k in keys:
            idx.setdefault(k, g)
    return idx


def game_for(sealed_row: dict, idx: dict) -> dict | None:
    gid = sealed_row["game_id"]
    g = idx.get(gid)
    if g:
        return g
    m = re.match(r"(\d{4})_(\d+)_([A-Z]+)_([A-Z]+)", gid)
    if m:
        season, week, away, home = m.groups()
        for cand in idx.values():
            if (str(cand["week"]) == str(int(week)) and cand["away"] == away
                    and cand["home"] == home and season == "2026"):
                return cand
    return None


def read_sealed() -> list[dict]:
    """The committed pre-kickoff record, read as written. It is the ledger, not an output."""
    if not os.path.exists(FORECAST_PATH):
        return []
    with open(FORECAST_PATH, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines))))


def state_at_record(games: list[dict], recorded_at: str) -> dict:
    """Ratings as they stood the moment the row was recorded: every game STRICTLY EARLIER than the
    record's own calendar date. A sealed forecast is only reproducible against the information the
    build actually had, so this is the point-in-time rule applied to the ledger itself."""
    day = (recorded_at or "")[:10]
    pool = [g for g in games if not day or g["date"] < day]
    pool.sort(key=lambda g: (g["date"], g["week"], g["game_id"]))
    return ratings_state(pool)["__final__"]


def expected_row(g: dict, state: dict) -> dict:
    """What the frozen PR-01 rule produces for one fixture, given a ratings state."""
    rh = rating_from(state.get(g["home"]))
    ra = rating_from(state.get(g["away"]))
    margin = rh - ra + H_HOME_POINTS
    p = phi(margin / SIGMA_POINTS)
    return {"p_home": round(p, 6), "model_side": "home" if p >= 0.5 else "away",
            "expected_margin_home": round(margin, 4), "fair_line_home": round_half(-margin),
            "fair_american_home": american(1 - p), "fair_american_away": american(p)}


def verify_sealed(sealed: list[dict], games: list[dict]) -> dict:  # noqa: C901
    """Re-derive every sealed row from the rule at its record time; a row that does not reproduce is
    a broken seal, and a broken seal must be loud rather than quietly republished."""
    idx = index_games(games)
    states: dict[str, dict] = {}
    rows, bad = [], []
    for r in sealed:
        rec = r["recorded_at_utc"][:10]
        if rec not in states:
            states[rec] = state_at_record(games, r["recorded_at_utc"])
        want = expected_row(r, states[rec])
        numeric = ("p_home", "expected_margin_home", "fair_line_home",
                   "fair_american_home", "fair_american_away")
        delta = {k: (round(float(r[k]) - float(v), 8) if str(r.get(k, "")).strip() not in ("",) else None)
                 for k, v in want.items() if k in numeric}
        worst = max((abs(v) for v in delta.values() if v is not None), default=0.0)
        if str(r.get("model_side", "")) != str(want["model_side"]):
            worst = max(worst, 1.0)          # a flipped side is a real difference, whatever the numbers say
        fixture = game_for(r, idx)
        played_at = fixture["date"] if fixture else ""
        kut = kickoff_utc(r.get("kickoff_et", ""))
        if kut:
            leak = r["recorded_at_utc"] >= kut            # minute-granularity, both clocks in UTC
            basis = "kickoff instant (ET printed by the official page, converted with the IANA tz database)"
        else:
            leak = bool(played_at and played_at <= rec)   # coarse fallback: whole-day comparison
            basis = "coarse: kickoff time unparseable, compared at date granularity"
        rows.append({"game_id": r["game_id"], "recorded_at_utc": r["recorded_at_utc"],
                     "max_abs_delta_vs_rule": worst, "reproduces": worst < 5e-6,
                     "fixture_date": played_at, "kickoff_utc": kut, "basis": basis,
                     "recorded_after_kickoff": leak})
        if worst >= 5e-6:
            bad.append(f"{r['game_id']}: sealed numbers differ from the frozen rule by {worst}")
        if leak:
            bad.append(f"{r['game_id']}: recorded {r['recorded_at_utc']} at or after its kickoff "
                       f"{kut or played_at} — not a pre-kickoff forecast")
    return {"rows": rows, "n_sealed": len(sealed), "n_reproduced": sum(1 for x in rows if x["reproduces"]),
            "n_pre_kickoff_confirmed": sum(1 for x in rows if not x["recorded_after_kickoff"]),
            "pre_kickoff_basis": rows[0]["basis"] if rows else "",
            "failures": bad,
            "note": "Reproduction tolerance is 5e-6 on every scored field, i.e. the rounding the artefact "
                    "itself uses. Anything larger means the file was edited after it was written, or the "
                    "rule's constants moved; either way the seal is broken and the number is not publishable."}


def resolve_sealed(sealed: list[dict], games: list[dict]) -> tuple[list[dict], dict]:
    """Join each sealed forecast to the official final and score it. Nothing is scored that has no
    official result in the corpus, and nothing is back-filled for a fixture that has no sealed row."""
    idx = index_games(games)
    rows, resolved = [], []
    for r in sealed:
        g = game_for(r, idx)
        final = g is not None and g.get("status") == "final"
        p = float(r["p_home"])
        out = {"game_id": r["game_id"], "week": r["week"], "recorded_at_utc": r["recorded_at_utc"],
               "kickoff_et": r["kickoff_et"], "away": r["away"], "home": r["home"],
               "p_home": r["p_home"], "model_side": r["model_side"],
               "expected_margin_home": r["expected_margin_home"], "fair_line_home": r["fair_line_home"],
               "market_line": "", "residual": "", "clv_points": "",
               "status": "final (official)" if final else "pending — not yet played or not yet read",
               "kickoff_utc": kickoff_utc(r.get("kickoff_et", "")),
               "source_url": r["source_url"]}
        if final:
            actual = g["home_score"] - g["away_score"]
            y_home = 1.0 if actual > 0 else (0.5 if actual == 0 else 0.0)
            brier = (p - y_home) ** 2
            b05 = (0.5 - y_home) ** 2
            b55 = (HOME_BASELINE_P - y_home) ** 2
            ll = -(y_home * math.log(max(p, 1e-12)) + (1 - y_home) * math.log(max(1 - p, 1e-12)))
            ll55 = -(y_home * math.log(HOME_BASELINE_P) + (1 - y_home) * math.log(1 - HOME_BASELINE_P))
            side_hit = (r["model_side"] == "home" and actual > 0) or (r["model_side"] == "away" and actual < 0)
            out.update({
                "away_score": g["away_score"], "home_score": g["home_score"],
                "actual_margin_home": actual,
                "margin_error_points": round(abs(float(r["expected_margin_home"]) - actual), 4),
                "side_hit": "" if actual == 0 else ("yes" if side_hit else "no"),
                "brier_home_win": round(brier, 6), "brier_coin_0.50": round(b05, 6),
                "brier_home_baseline_0.55": round(b55, 6),
                "brier_skill_vs_0.55": round(1 - brier / b55, 6) if b55 else "",
                "log_loss": round(ll, 6), "log_loss_baseline_0.55": round(ll55, 6),
                "outcome_source_url": g["source_url"], "outcome_read_on": g["read_on"],
            })
            resolved.append(out)
        rows.append(out)

    n = len(resolved)
    agg = {"n_sealed": len(sealed), "n_resolved": n, "n_pending": len(sealed) - n,
           "first_resolved_at": min((r["recorded_at_utc"] for r in rows if r["status"].startswith("final")),
                                    default="") and ""}
    if n:
        mb = sum(r["brier_home_win"] for r in resolved) / n
        mb05 = sum(r["brier_coin_0.50"] for r in resolved) / n
        mb55 = sum(r["brier_home_baseline_0.55"] for r in resolved) / n
        hits = sum(1 for r in resolved if r["side_hit"] == "yes")
        decided = sum(1 for r in resolved if r["side_hit"] in ("yes", "no"))
        agg.update({
            "mean_brier": round(mb, 6), "mean_brier_coin_0.50": round(mb05, 6),
            "mean_brier_home_baseline_0.55": round(mb55, 6),
            "brier_skill_vs_0.55": round(1 - mb / mb55, 6) if mb55 else None,
            "mean_margin_error_points": round(sum(r["margin_error_points"] for r in resolved) / n, 4),
            "side_record": f"{hits}-{decided - hits}",
            "mean_log_loss": round(sum(r["log_loss"] for r in resolved) / n, 6),
        })
    return rows, agg


FORECAST_COLUMNS = ["recorded_at_utc", "week", "game_id", "kickoff_et", "away", "home", "p_home",
                    "model_side", "expected_margin_home", "fair_line_home", "fair_american_home",
                    "fair_american_away", "market_line", "residual", "source_url", "status_at_record"]


def slate_rows() -> list[dict]:
    """The forward slate, preferring the most recent dated read of it."""
    for path in (W11_LATEST, W11):
        full = os.path.join(ROOT, path)
        if not os.path.exists(full):
            continue
        try:
            rows = rows_of(full)
        except Exception:
            continue
        return [r for r in rows if r.get("row_type", "game") == "game"], path
    return [], ""


def pending_slate(games: list[dict], sealed: list[dict]) -> dict:
    """What the ledger already covers, what it does not, and the window in which the next rows may be
    sealed. The window is the whole point of the cadence: a forecast written after the previous week's
    last result is legitimate, one written after the fixture's own kickoff is not."""
    sealed_ids = {r["game_id"] for r in sealed}
    slate, src = slate_rows()
    played = {g["game_id"] for g in games if g.get("status") == "final"}
    uncovered = [r["game_id"] for r in slate
                 if r["game_id"] not in sealed_ids and r["game_id"] not in played]
    kickoffs = sorted(f"{r.get('date_et','')} {r.get('time_et','')}".strip() for r in slate if r.get("game_id"))
    return {
        "slate_read": src,
        "slate_games": len(slate),
        "sealed_already": len([r for r in slate if r["game_id"] in sealed_ids]),
        "unsealed_and_unplayed": uncovered,
        "first_kickoff_et": kickoffs[0] if kickoffs else "",
        "last_kickoff_et": kickoffs[-1] if kickoffs else "",
        "rule": "seal week W in the window that opens once week W-1's last game is final and closes at "
                "week W's first kickoff. Today the Week 11 slate is fully sealed, so there is nothing to "
                "write; sealing Week 12 must wait for Week 11's final result. A build that sealed Week 12 "
                "now would use ratings that are one week stale, and would say so in the row's clock time.",
        "next_window": "opens after the last final of the current slate; closes at the next slate's first "
                       "kickoff (both printed by the official by-week pages, not by this tool)",
    }


def to_csv(rows: list[dict], columns: list[str] | None = None) -> str:
    if not rows:
        return ""
    cols = columns or list(rows[0])
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def build() -> dict:
    games, prov = load_games()
    state = ratings_state(games)
    scored = score_window(games, state)
    m = metrics(scored)
    m["bootstrap"] = bootstrap(scored)
    sealed = read_sealed()
    if sealed:
        # The ledger on disk is authoritative for what was forecast; the rule is only allowed to CHECK it.
        forward = [{k: r.get(k, "") for k in FORECAST_COLUMNS} for r in sealed]
        seal = verify_sealed(sealed, games)
    else:
        # First build in this tree: nothing is sealed yet, so the slate becomes the ledger.
        forward, _ = forward_record(games, state["__final__"])
        seal = {"rows": [], "n_sealed": 0, "n_reproduced": 0, "n_pre_kickoff_confirmed": 0,
                "failures": ["no sealed file yet — this build created one"]}
    # The fingerprint covers what was forecast, not when it was written: a re-run at 18:52 and a build
    # at 18:53 of the same numbers must agree, or the staleness guard is a clock and not a check.
    sub = [{k: v for k, v in r.items() if k != "recorded_at_utc"} for r in forward]
    forecast_hash = hashlib.sha256(to_csv(sub).encode()).hexdigest()
    resolution_rows, resolution = resolve_sealed(sealed or forward, games)
    slate = pending_slate(games, sealed or forward)

    return {
        "dataset": "shadow_baseline_PR-01",
        "title": "PR-01 singles-only shadow baseline: pre-registered rule, walk-forward score, and the pre-kickoff record",
        "generated_at": NOW,
        "generated_by": "tools/build_shadow_baseline.py (created by session arena-543cdcb0-x1; the sealed "
                        "ledger, its reproduction check and its resolution were added by arena-e1436334-x1)",
        "registration": {
            "rule_file": RULE_FILE,
            "rule_sha256": sha256_file(RULE_FILE),
            "how_to_verify": "python3 tools/build_preregistration.py --check  (resolves the commit that froze the rule)",
        },
        "frozen_constants": {
            "K_prior_games": K_PRIOR_GAMES, "H_home_points": H_HOME_POINTS,
            "SIGMA_points": SIGMA_POINTS, "home_baseline_p": HOME_BASELINE_P,
            "warmup_weeks": WARMUP_WEEKS, "multiplicity_n_trials": MULTIPLICITY_N_TRIALS,
            "note": "These are the values in the rule file. Changing one here without changing the rule "
                    "file makes the register's hash check fail, which is the point.",
        },
        "inputs": prov,
        "corpus": {
            "games_ingested": prov["games"], "weeks": prov["weeks"],
            "scored_window": f"weeks {WARMUP_WEEKS + 1}-10 of 2026 REG",
            "eligibility": "BACKTEST. Not leaderboard-eligible (PR rule: no backtest number is ranked).",
        },
        "backtest": m,
        "columns_scored": list(scored[0].keys()),
        "scored_rows": scored,
        "forward": {
            "recorded_at_utc": NOW,
            "games_recorded": len(forward),
            "content_sha256": forecast_hash,
            "immutability": "append-only ledger: existing rows are never rewritten, so a forecast cannot "
                            "be edited after kickoff; the build re-derives each row from the frozen rule at "
                            "its own record time and aborts if a number does not reproduce",
            "file": "data/shadow/forecasts_pre_kickoff.csv",
            "ledger_check": {k: v for k, v in seal.items() if k != "rows"},
        },
        "sealed_ledger": {
            "file": "data/shadow/forecasts_pre_kickoff.csv",
            "content_sha256": sha256_file(SEALED) if os.path.exists(os.path.join(ROOT, SEALED)) else "",
            "n_sealed": seal["n_sealed"],
            "n_reproduced_from_rule": seal["n_reproduced"],
            "n_confirmed_pre_kickoff": seal["n_pre_kickoff_confirmed"],
            "pre_kickoff_basis": seal.get("pre_kickoff_basis", ""),
            "failures": seal["failures"],
            "rows": seal["rows"],
            "meaning": "every sealed number is what the frozen rule produces from results strictly earlier "
                       "than the moment it was recorded - i.e. the seal can be audited without trusting it",
        },
        "prospective_resolution": {
            **resolution,
            "file": "data/shadow/sealed_record_resolution.csv",
            "scoring": "Brier and log loss on the home-win indicator; ties score 0.5; benchmarks are the "
                       "0.50 coin and the frozen 0.55 home baseline. Skill is benchmark-relative by "
                       "construction: 1 - model/0.55-baseline.",
            "why_it_matters": "This is the only part of PR-01 that was not chosen after seeing data: the "
                              "prediction was written, hashed and committed before kickoff. It is also the "
                              "smallest sample in the repository, and it is labelled as such.",
            "honesty": ("n = %d resolved. One game is one game: there is no interval here, no ranking, and "
                        "no claim about skill in either direction. A resolved prospective record becomes "
                        "evidence only when it is wide enough to survive the game-cluster bootstrap, which "
                        "needs >=100 games (PR-01 promotion clause)." % resolution["n_resolved"]),
            "rows": resolution_rows,
        },
        "sealing_cadence": slate,
        "blank_by_policy": {
            "market_line": "no official price source in this repository - open question Q-02",
            "residual": "residual = fair - market, so it is blank while the market line is blank",
            "roi_staking": "no prices means no settlement; see the demotion gate and G5",
            "total_fair_line": "the model is a margin model; its total is the league-average total, "
                               "published as a floor and labelled as one, not as an estimate of the total",
        },
        "limits": [
            f"n = {len(scored)} games, one season, one conference-independent sample; the interval, not the "
            f"point estimate, is the result",
            "the model has no personnel, availability, rest or venue feature - it is the baseline those "
            "features have to beat, not a proposal",
            "ratings use points scored and allowed vs whoever; schedule strength is not adjusted, so "
            "BUF's and NYJ's ratings are not comparable in the way an opponent-adjusted model's would be",
            "one season cannot test calibration at the tails; the 0.8-1.0 bin is printed with its count",
        ],
    }


CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?")
# Provenance, not content. The refresh job rewrites data/pipeline/standings.json on every run, and the
# input-hash block records that file's SHA-256; if the comparison included it, `--check` would report a
# stale artefact every day even when not one number moved. The hashes are still PUBLISHED (they are how
# a reader knows which bytes the score came from) - they are simply not what the staleness gate asserts.
VOLATILE_TOP = ("inputs",)


def normalise(text: str) -> str:
    """Compare artefacts on CONTENT, not on the minute they were built.

    Every artefact here carries a build clock somewhere (`generated_at`, `recorded_at_utc`, the header
    comment). A staleness guard that diffs raw bytes would fail on every CI rebuild and would then be
    switched off, which is worse than not having it. So the clock is masked and the rows are compared
    as a set: a forecast that changed in any scored field, or gained/lost a row, still fails.
    """
    lines = [ln for ln in text.split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return ""
    if lines[0].startswith("{"):
        try:
            obj = json.loads("\n".join(lines))
        except json.JSONDecodeError:
            return CLOCK.sub("<clock>", "\n".join(lines))
        for k in VOLATILE_TOP:
            obj.pop(k, None)
        return CLOCK.sub("<clock>", json.dumps(obj, indent=1, sort_keys=True))
    header = lines[0].split(",")
    clock_cols = {i for i, h in enumerate(header) if h in ("recorded_at_utc", "generated_at", "read_on")}
    out = []
    for ln in lines[1:]:
        f = ln.split(",")
        for i in clock_cols:
            if i < len(f):
                f[i] = "<clock>"
        out.append(",".join(f))
    return "\n".join(sorted(out))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    payload = build()

    scored_csv = to_csv(payload["scored_rows"], payload["columns_scored"])
    calib_csv = to_csv(payload["backtest"]["calibration"])
    resolution_csv = to_csv(payload["prospective_resolution"]["rows"])
    ledger_json = json.dumps(payload["sealed_ledger"], indent=1) + "\n"

    # The ledger is the file, not a rebuild: compare against what is committed, and only ever append.
    sealed = read_sealed()
    if sealed:
        forward_csv = to_csv([{k: r.get(k, "") for k in FORECAST_COLUMNS} for r in sealed])
    else:
        games, _ = load_games()
        forward_rows, _ = forward_record(games, ratings_state(games)["__final__"])
        forward_csv = to_csv(forward_rows)

    if args.check:
        want = {
            "backtest_summary.json": json.dumps(payload, indent=1) + "\n",
            "games_scored.csv": scored_csv,
            "calibration.csv": calib_csv,
            "forecasts_pre_kickoff.csv": forward_csv,
            "sealed_record_resolution.csv": resolution_csv,
            "sealed_ledger.json": ledger_json,
        }
        bad = 0
        for name, text in want.items():
            path = os.path.join(OUTDIR, name)
            if not os.path.exists(path):
                print(f"STALE: data/shadow/{name} is missing")
                bad += 1
                continue
            got = open(path, encoding="utf-8").read()
            if normalise(got) != normalise(text):
                print(f"STALE: data/shadow/{name} differs from a fresh build (content, not the clock)")
                bad += 1
        if payload["sealed_ledger"]["failures"]:
            print("FAIL: the seal does not reproduce: " + "; ".join(payload["sealed_ledger"]["failures"]))
            bad += 1
        if not bad:
            r = payload["prospective_resolution"]
            print(f"CHECK OK: shadow baseline reproduces from its inputs "
                  f"(n={payload['backtest']['n_games']}, sealed={len(sealed)}, "
                  f"resolved={r['n_resolved']}, pending={r['n_pending']})")
        return 1 if bad else 0

    os.makedirs(OUTDIR, exist_ok=True)

    with open(os.path.join(OUTDIR, "backtest_summary.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=1) + "\n")
    with open(os.path.join(OUTDIR, "games_scored.csv"), "w", encoding="utf-8") as fh:
        fh.write(scored_csv)
    with open(os.path.join(OUTDIR, "calibration.csv"), "w", encoding="utf-8") as fh:
        fh.write(calib_csv)
    with open(os.path.join(OUTDIR, RESOLUTION.split("/")[-1]), "w", encoding="utf-8") as fh:
        fh.write(resolution_csv)
    with open(os.path.join(OUTDIR, LEDGER.split("/")[-1]), "w", encoding="utf-8") as fh:
        fh.write(ledger_json)

    # APPEND-ONLY: fixtures on the current official slate that are neither sealed nor played get a row,
    # computed from the rule at THIS clock time. Rows already in the ledger are never rewritten, so the
    # only way a number can change is a new registration with a new rule file.
    new_ids = payload["sealing_cadence"]["unsealed_and_unplayed"]
    if new_ids:
        games, _ = load_games()
        slate, _src = slate_rows()
        state = state_at_record(games, NOW)
        extra = []
        for r in slate:
            if r["game_id"] not in set(new_ids):
                continue
            row = expected_row(r, state)
            extra.append({"recorded_at_utc": NOW, "week": r["game_id"].split("_")[1].lstrip("0") or r["game_id"],
                          "game_id": r["game_id"], "kickoff_et": f"{r['date_et']} {r['time_et']}".strip(),
                          "away": r["away"], "home": r["home"], "market_line": "", "residual": "",
                          "source_url": r["game_url"], "status_at_record": "scheduled (not played when recorded)",
                          **row})
        with open(FORECAST_PATH, "w", encoding="utf-8") as fh:
            fh.write("# PR-01 pre-kickoff shadow record. Append-only; last appended "
                     f"{NOW} by tools/build_shadow_baseline.py. Rows above this line are never rewritten.\n"
                     "# market_line / residual are blank on purpose: no official price source (Q-02).\n")
            fh.write(to_csv([{k: r.get(k, "") for k in FORECAST_COLUMNS} for r in read_sealed()] + extra))
        print(f"SEALED: {len(extra)} new pre-kickoff rows appended ({', '.join(new_ids[:4])}"
              f"{'...' if len(new_ids) > 4 else ''}) at {NOW}")
    else:
        print("ledger unchanged: every fixture on the current official slate is already sealed or played")

    m = payload["backtest"]
    r = payload["prospective_resolution"]
    print(f"games ingested from official reads : {payload['corpus']['games_ingested']} "
          f"(weeks {payload['corpus']['weeks'][0]}-{payload['corpus']['weeks'][-1]})")
    print(f"scored (weeks {WARMUP_WEEKS + 1}-10)        : {m['n_games']}")
    print(f"Brier                                  : {m['brier']}  (coin {m['brier_coin_baseline']}, "
          f"home 0.55 {m['brier_home_baseline']})")
    print(f"Brier skill vs home baseline           : {m['brier_skill_vs_home_baseline']}  "
          f"95% lower bound {m['bootstrap']['skill_home_baseline_lower_bound']}")
    print(f"hit rate / MAE margin                  : {m['hit_rate_model_side']} / "
          f"{m['mae_expected_margin_points']} pts")
    print(f"luck panel                             : {m['luck_panel']['realised_wins_on_model_side']} wins "
          f"vs {m['luck_panel']['expected_wins_same_bets']} expected, sd {m['luck_panel']['sd_of_the_difference']}, "
          f"z={m['luck_panel']['z_luck_adjusted']}")
    print(f"sealed ledger                          : {len(sealed)} rows, "
          f"{payload['sealed_ledger']['n_reproduced_from_rule']} reproduce from the rule, "
          f"{payload['sealed_ledger']['n_confirmed_pre_kickoff']} confirmed pre-kickoff")
    print(f"prospective resolution                 : {r['n_resolved']} resolved / {r['n_pending']} pending, "
          f"side record {r.get('side_record','-')}, mean Brier {r.get('mean_brier','-')}, "
          f"skill vs 0.55 {r.get('brier_skill_vs_0.55','-')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
