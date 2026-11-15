#!/usr/bin/env python3
"""Control baselines (random picks; favourites only) — session `arena-3f5badd0-x1`.

Implements EXACTLY the rules frozen in `docs/lab/control-baselines.md` (registration commit
0747005). Do not change a rule here without a new registration commit.

Run:    python3 tools/lab/build_controls.py          # writes data/lab/controls/*
        python3 tools/lab/build_controls.py --check  # recomputes and fails if the artefacts differ

Inputs : data/lab/upstream/games.csv (pinned by SHA-256 in data/lab/upstream/_pin.json)
Outputs: data/lab/controls/control_baselines.json, data/lab/controls/control_baselines.csv
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GAMES = os.path.join(ROOT, "data", "lab", "upstream", "games.csv")
PIN = os.path.join(ROOT, "data", "lab", "upstream", "_pin.json")
OUT_DIR = os.path.join(ROOT, "data", "lab", "controls")
OUT_JSON = os.path.join(OUT_DIR, "control_baselines.json")
OUT_CSV = os.path.join(OUT_DIR, "control_baselines.csv")

RULE_VERSION = "1"
SEED = 20261115          # frozen in docs/lab/control-baselines.md
REPS = 1000              # frozen
SEASONS = list(range(2019, 2026))   # frozen: complete seasons only
BREAK_EVEN = 110 / 210   # -110 arithmetic, 52.38%; not an observed price
Z95 = 1.959963984540054


def wilson(k: int, n: int) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    d = 1 + Z95 * Z95 / n
    c = (p + Z95 * Z95 / (2 * n)) / d
    h = Z95 * math.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_universe() -> list[dict]:
    games = []
    with open(GAMES, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["game_type"] != "REG":
                continue
            if r["season"] not in {str(s) for s in SEASONS}:
                continue
            if not r["spread_line"] or r["home_score"] == "" or r["away_score"] == "":
                continue
            L = float(r["spread_line"])
            m = int(r["home_score"]) - int(r["away_score"])
            d = m - L                       # home covers iff d > 0; push iff d == 0
            fav = "home" if L > 0 else "away"
            sign = 1 if fav == "home" else -1
            games.append({
                "game_id": r["game_id"], "season": int(r["season"]), "week": int(r["week"]),
                "home": r["home_team"], "away": r["away_team"], "margin_home": m, "spread_home": L,
                "favourite": fav,
                "fav_covers": (d * sign > 0) if d != 0 else None,   # None = push
                "fav_wins_su": (m * sign > 0) if m != 0 else None,  # None = tie
            })
    return games


def ats_rate(games: list[dict], picks: list[str]) -> tuple[int, int, int]:
    """picks[i] in {'home','away'}; return (wins, losses, pushes) against the spread."""
    w = l = p = 0
    for g, s in zip(games, picks):
        d = g["margin_home"] - g["spread_home"]
        if d == 0:
            p += 1
            continue
        covered = (d > 0) if s == "home" else (d < 0)
        if covered:
            w += 1
        else:
            l += 1
    return w, l, p


def row(label: str, n_games: int, w: int, l: int, p: int, extra: dict | None = None) -> dict:
    n = w + l
    rate = w / n if n else None
    lo, hi = wilson(w, n)
    out = {
        "scope": label, "games": n_games, "wins": w, "losses": l, "pushes": p,
        "win_rate": round(rate, 4) if rate is not None else None,
        "wilson95_lo": round(lo, 4) if lo is not None else None,
        "wilson95_hi": round(hi, 4) if hi is not None else None,
        "n_non_push": n,
        "beats_break_even_lower_bound": (lo > BREAK_EVEN) if lo is not None else None,
    }
    if extra:
        out.update(extra)
    return out


def build() -> dict:
    games = load_universe()
    seasons_out = []
    for s in SEASONS:
        sub = [g for g in games if g["season"] == s]
        fav_picks = [g["favourite"] for g in sub]
        fw, fl, fp = ats_rate(sub, fav_picks)
        su = [g["fav_wins_su"] for g in sub if g["fav_wins_su"] is not None]
        seasons_out.append({"season": s, "games": len(sub), "favourites": row(
            f"{s} favourites (ATS)", len(sub), fw, fl, fp,
            {"su_fav_win_rate": round(sum(su) / len(su), 4) if su else None,
             "su_n": len(su)}),
            "games_list_source": "data/lab/upstream/games.csv"})

    # Pooled universe: favourites-only
    fav_picks = [g["favourite"] for g in games]
    fw, fl, fp = ats_rate(games, fav_picks)
    su = [g["fav_wins_su"] for g in games if g["fav_wins_su"] is not None]
    fav_row = row("2019–2025 favourites (ATS)", len(games), fw, fl, fp,
                  {"su_fav_win_rate": round(sum(su) / len(su), 4),
                   "su_n": len(su),
                   "su_wilson95": [round(x, 4) for x in wilson(sum(su), len(su))]})

    # Control A: random picks, fixed seed, REPS replications
    rng = random.Random(SEED)
    rates = []
    for _ in range(REPS):
        picks = ["home" if rng.random() < 0.5 else "away" for _ in games]
        w, l, _p = ats_rate(games, picks)
        rates.append(w / (w + l))
    rates.sort()
    mean = sum(rates) / len(rates)
    p025 = rates[int(0.025 * (REPS - 1))]
    p975 = rates[int(round(0.975 * (REPS - 1)))]
    share_ge_fav = sum(1 for r in rates if r >= fav_row["win_rate"]) / REPS
    rand_row = {
        "scope": "2019–2025 random picks (ATS), 1,000 replications",
        "games": len(games), "replications": REPS, "seed": SEED,
        "mean_win_rate": round(mean, 4), "p2_5": round(p025, 4), "p97_5": round(p975, 4),
        "share_of_reps_at_or_above_favourites": round(share_ge_fav, 4),
    }

    # Break-even check for both controls
    out = {
        "session": "arena-3f5badd0-x1",
        "rule_version": RULE_VERSION,
        "registration": "0747005 (docs/lab/control-baselines.md)",
        "source": {
            "publisher": "nflverse/nfldata (community mirror, NOT an official NFL source)",
            "file": "data/lab/upstream/games.csv",
            "sha256": sha256(GAMES),
            "pinned_archive_sha256": json.load(open(PIN))["archive_sha256"],
            "url": "https://github.com/nflverse/nfldata/blob/master/data/games.csv",
        },
        "conventions": {
            "spread_line": "home-team perspective; positive = home favoured",
            "home_covers": "margin_home - spread_line > 0; push when equal",
            "break_even_at_minus_110": round(BREAK_EVEN, 4),
        },
        "favourites_pooled": fav_row,
        "random_picks": rand_row,
        "seasons": seasons_out,
        "unverified": [
            "The mirror does not state the sportsbook, the timestamp or the price of spread_line.",
            "No 2026 spread is in the registered universe; 2026 is not scored here (Q-02).",
            "Every value is from a community mirror, not from nfl.com.",
        ],
    }
    return out


def write(out: dict) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        fh.write(text)
    rows = [out["favourites_pooled"], out["random_picks"]] + [s["favourites"] for s in out["seasons"]]
    keys = ["scope", "games", "wins", "losses", "pushes", "win_rate", "wilson95_lo", "wilson95_hi",
            "n_non_push", "beats_break_even_lower_bound", "su_fav_win_rate", "su_n", "mean_win_rate",
            "p2_5", "p97_5", "share_of_reps_at_or_above_favourites", "replications", "seed"]
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    out = build()
    if "--check" in sys.argv:
        old = open(OUT_JSON, encoding="utf-8").read() if os.path.exists(OUT_JSON) else ""
        new = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
        if old != new:
            print("STALE: data/lab/controls differs from a fresh computation")
            return 1
        print("controls up to date")
        return 0
    write(out)
    f = out["favourites_pooled"]
    r = out["random_picks"]
    print(f"games (2019–2025 REG, spread present): {f['games']}")
    print(f"favourites ATS : {f['wins']}-{f['losses']}-{f['pushes']}  rate {f['win_rate']}  "
          f"Wilson95 [{f['wilson95_lo']}, {f['wilson95_hi']}]  SU {f['su_fav_win_rate']}")
    print(f"random ATS     : mean {r['mean_win_rate']}  band [{r['p2_5']}, {r['p97_5']}]  "
          f"reps >= favourites {r['share_of_reps_at_or_above_favourites']}")
    print(f"break-even     : {out['conventions']['break_even_at_minus_110']}")
    print("wrote data/lab/controls/control_baselines.{json,csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
