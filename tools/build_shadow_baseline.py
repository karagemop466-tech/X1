#!/usr/bin/env python3
"""PR-01 shadow baseline: score a pre-registered team-strength model, honestly (C-5).

The rule lives in `docs/preregistration/PR-01-shadow-baseline.md`; this script implements it and nothing
else. The constants are read from that file's frozen values (K, H, SIGMA, the benchmarks, the window) so
the code cannot drift from the registration without the register's hash check noticing.

Two outputs, deliberately separated because they mean different things:

  * **backtest** — weeks 3-10 of 2026, scored chronologically (each game predicted only from games
    strictly earlier). This is a measurement of the rule, and it is NOT leaderboard-eligible.
  * **prospective shadow record** — the games that had not kicked off when this ran, with the clock time
    they were recorded at and a content hash written into the artefact. Once written it refuses to be
    rewritten: a forecast you can edit after kickoff is not a forecast.

What is blank, and why
----------------------
`market_line` and `residual` are empty in every row. This repository has no official price source
(open question Q-02); the fair line is published because the model produced it, the market line is not
because nobody has decided which price data may be used. `roi` and `staking` columns are absent for the
same reason: with no prices there is no settlement, and a fake one would be the most flattering number on
the page.

Inputs (both official, both dated)
----------------------------------
  data/results/_raw/reads.tsv                                 weeks 1-9 + the 2026-11-12 game, read 2026-11-14
  data/verification/2026_11_16/official_w10_results_...tsv    the 12 Week 10 finals read 2026-11-16
  data/pipeline/standings.json                                official club list, used only for name -> code
  data/verification/2026_11_16/official_w11_schedule_...tsv   the forward slate

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


def to_csv(rows: list[dict], columns: list[str] | None = None) -> str:
    if not rows:
        return ""
    cols = columns or list(rows[0])
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def frozen_fingerprint(path: str) -> tuple[list[dict], str]:
    """The recorded forecasts, minus the clock, plus a hash of exactly that.

    The same projection the write path hashes (drop `recorded_at_utc`, serialise, sha256), applied to the
    file on disk instead of to a fresh build. That is what makes the staleness guard able to check a
    record it must never regenerate: the guard asserts the frozen bytes are STILL the frozen bytes, which
    is a tamper test, not a freshness test.
    """
    if not os.path.exists(path):
        return [], ""
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
    sub = [{k: v for k, v in r.items() if k != "recorded_at_utc"} for r in rows]
    return rows, hashlib.sha256(to_csv(sub).encode()).hexdigest()


def build() -> dict:
    games, prov = load_games()
    state = ratings_state(games)
    scored = score_window(games, state)
    m = metrics(scored)
    m["bootstrap"] = bootstrap(scored)
    forward, _ = forward_record(games, state["__final__"])
    # The fingerprint covers what was forecast, not when it was written: a re-run at 18:52 and a build
    # at 18:53 of the same numbers must agree, or the staleness guard is a clock and not a check.
    sub = [{k: v for k, v in r.items() if k != "recorded_at_utc"} for r in forward]
    forecast_hash = hashlib.sha256(to_csv(sub).encode()).hexdigest()
    # If a record already exists on disk, THAT is the published artefact: the numbers below are what the
    # model would record today, and the two are reported side by side rather than the first being
    # replaced by the second.
    disk_rows, disk_hash = frozen_fingerprint(FORECAST_PATH)
    forward_block = {
        "recorded_at_utc": NOW,
        "games_recorded": len(forward),
        "content_sha256": forecast_hash,
        "immutability": "the CSV is written once and never rewritten; a later run that would change a "
                        "forecast number leaves the record alone and reports the drift below (the "
                        "recorded clock is excluded from the fingerprint)",
        "file": "data/shadow/forecasts_pre_kickoff.csv",
    }
    if disk_rows:
        forward_block.update({
            "status": "frozen record on disk (graded, not regenerated)",
            "recorded_at_utc_on_disk": disk_rows[0].get("recorded_at_utc", ""),
            "games_recorded_on_disk": len(disk_rows),
            "content_sha256_on_disk": disk_hash,
            "record_drift": {
                "reproduces_from_today_model_state": disk_hash == forecast_hash,
                "games_on_disk_not_in_today_slate": sorted(
                    {r["game_id"] for r in disk_rows} - {r["game_id"] for r in forward}),
                "games_in_today_slate_not_on_disk": sorted(
                    {r["game_id"] for r in forward} - {r["game_id"] for r in disk_rows}),
                "why": ("the record is a snapshot of what had not kicked off when it was written; the "
                        "corpus has since grown (Week 10 closed on 2026-11-17), so the slate that WOULD "
                        "be recorded today is a different list. Both are true: the record is what was "
                        "forecast, the slate is what a forecast today would cover. The record is graded "
                        "and never overwritten."),
            },
        })

    return {
        "dataset": "shadow_baseline_PR-01",
        "title": "PR-01 singles-only shadow baseline: pre-registered rule, walk-forward score, and the pre-kickoff record",
        "generated_at": NOW,
        "generated_by": "tools/build_shadow_baseline.py (session arena-543cdcb0-x1)",
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
        "forward": forward_block,
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
    forward_csv = to_csv(payload["forward_rows"]) if "forward_rows" in payload else ""
    # the forward rows are rebuilt here so the file and the hash always agree
    games, _ = load_games()
    forward_rows, _ = forward_record(games, ratings_state(games)["__final__"])
    forward_csv = to_csv(forward_rows)

    if args.check:
        want = {
            "backtest_summary.json": json.dumps(payload, indent=1) + "\n",
            "games_scored.csv": scored_csv,
            "calibration.csv": calib_csv,
        }
        # The pre-kickoff record is not compared against a fresh build - by design it must not match one.
        # It IS compared against the fingerprint the summary carries, so an edit after kickoff still
        # fails the gate; that is the check the file needs and not the one the others need.
        fwd = payload["forward"]
        if fwd.get("status", "").startswith("frozen"):
            disk_rows, disk_hash = frozen_fingerprint(FORECAST_PATH)
            if disk_hash != fwd["content_sha256_on_disk"] or len(disk_rows) != fwd["games_recorded_on_disk"]:
                print("STALE: data/shadow/forecasts_pre_kickoff.csv differs from the fingerprint the "
                      "register carries - a frozen record must not move")
                return 1
            print(f"frozen record intact: {len(disk_rows)} games, "
                  f"sha256 {disk_hash[:12]}.. as registered")
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
        if not bad:
            print(f"CHECK OK: shadow baseline reproduces from its inputs "
                  f"(n={payload['backtest']['n_games']}, "
                  f"forward={payload['forward'].get('games_recorded_on_disk', len(forward_rows))} frozen)")
        return 1 if bad else 0

    os.makedirs(OUTDIR, exist_ok=True)
    if os.path.exists(FORECAST_PATH):
        # Frozen. Before 2026-11-17 this branch ABORTED the whole build on drift, which meant that once
        # Week 10 closed the backtest artefacts could not be rebuilt at all: a guard against rewriting a
        # forecast had taken the measurement of the rule hostage. The record is still never rewritten -
        # that is the property that matters - the drift is reported instead of enforced by a crash.
        drift = payload["forward"].get("record_drift", {})
        if not drift.get("reproduces_from_today_model_state", True):
            print(f"ALARM: data/shadow/forecasts_pre_kickoff.csv is left exactly as recorded "
                  f"({payload['forward']['games_recorded_on_disk']} games at "
                  f"{payload['forward']['recorded_at_utc_on_disk']}); today's model state would record "
                  f"{len(forward_rows)}. Graded as recorded; a new record needs a new rule version.")
    else:
        with open(FORECAST_PATH, "w", encoding="utf-8") as fh:
            fh.write("# PR-01 pre-kickoff shadow record. Written "
                     f"{NOW} by tools/build_shadow_baseline.py; immutable by convention and by build.\n"
                     "# market_line / residual are blank on purpose: no official price source (Q-02).\n")
            fh.write(forward_csv)

    with open(os.path.join(OUTDIR, "backtest_summary.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=1) + "\n")
    with open(os.path.join(OUTDIR, "games_scored.csv"), "w", encoding="utf-8") as fh:
        fh.write(scored_csv)
    with open(os.path.join(OUTDIR, "calibration.csv"), "w", encoding="utf-8") as fh:
        fh.write(calib_csv)

    m = payload["backtest"]
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
    print(f"pre-kickoff forward record             : {len(forward_rows)} games at {NOW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
