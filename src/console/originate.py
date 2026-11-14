"""Line origination: side first, then total, then moneyline.

Requirement C3 is an ordering rule, not a slogan, so the order is enforced in
code: ``originate()`` returns the three markets in a fixed sequence and each
row carries ``origination_step`` 1, 2 or 3. The moneyline is *derived* from the
side (step 1) using the model's own out-of-sample margin spread, so it cannot
be produced before the side exists.

Requirement C4: every originated market publishes three separate columns - the
model's fair line, the market line, and the difference.

Model
-----
Two ridge regressions, fitted only on seasons strictly earlier than the season
being predicted (walk-forward, no leakage):

  step 1  SIDE   margin_home  = s_home - s_away + c        (32 team strengths)
  step 2  TOTAL  points(t,u)  = m + a_t - b_u + h*home     (32 offence + 32 defence)
  step 3  MONEYLINE  p_home = Phi(fair_margin / sigma)     (sigma from the side
          model's own out-of-sample residuals, never from the test season)

The ridge penalty is chosen inside the training window only (last 20% of the
training games by date are held out), so no test-season information ever
reaches a hyper-parameter.
"""

from __future__ import annotations

import math

from . import sources

SQRT2 = math.sqrt(2.0)


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / SQRT2))


def _inv_phi(p):
    """Inverse standard normal CDF by bisection (accurate enough, dependency-free)."""
    lo, hi = -12.0, 12.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if _phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def american_to_prob(odds):
    """Implied probability from an American price (includes the book's margin)."""
    if odds is None:
        return None
    odds = float(odds)
    if odds == 0:
        return None
    return abs(odds) / (abs(odds) + 100.0) if odds < 0 else 100.0 / (odds + 100.0)


def prob_to_american(p):
    """Fair American price from a probability (no margin)."""
    if p is None or p <= 0.0 or p >= 1.0:
        return None
    if p >= 0.5:
        return -round(100.0 * p / (1.0 - p))
    return round(100.0 * (1.0 - p) / p)


def devig(home_ml, away_ml):
    """Strip the book's margin from a two-way moneyline."""
    ph, pa = american_to_prob(home_ml), american_to_prob(away_ml)
    if ph is None or pa is None or (ph + pa) <= 0:
        return None, None
    return ph / (ph + pa), pa / (ph + pa)


# ---------------------------------------------------------------------------
# ridge regression, standard library only
# ---------------------------------------------------------------------------

def _solve(mat, rhs):
    """Gauss-Jordan with partial pivoting. mat is n x n, rhs is n."""
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(mat)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            continue
        a[col], a[piv] = a[piv], a[col]
        pv = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= pv
        for r in range(n):
            if r == col:
                continue
            f = a[r][col]
            if f:
                for j in range(col, n + 1):
                    a[r][j] -= f * a[col][j]
    return [a[i][n] for i in range(n)]


class Ridge:
    """Ridge with sparse row accumulation. Rows are (y, [(index, value), ...]).

    ``add`` takes an optional weight so that recent seasons can be emphasised;
    the recency decay is treated as a hyper-parameter and selected inside the
    training window, never on the season being predicted.
    """

    def __init__(self, n_features, lam):
        self.n = n_features
        self.lam = lam
        self.xtx = {}
        self.xty = [0.0] * n_features

    def add(self, y, items, w=1.0):
        for i, vi in items:
            self.xty[i] += w * vi * y
            for j, vj in items:
                self.xtx[(i, j)] = self.xtx.get((i, j), 0.0) + w * vi * vj

    def fit(self):
        mat = [[0.0] * self.n for _ in range(self.n)]
        for (i, j), v in self.xtx.items():
            mat[i][j] = v
        for i in range(self.n):
            mat[i][i] += self.lam
        self.beta = _solve(mat, self.xty[:])
        return self

    def predict(self, items):
        return sum(self.beta[i] * v for i, v in items)


# ---------------------------------------------------------------------------
# fitting
# ---------------------------------------------------------------------------

DEFAULT_SIGMA = 12.0
SIGMA_GRID = (8.0, 20.0, 0.5)

SIDE_LAMBDAS = (2.0, 10.0, 50.0)
TOTAL_LAMBDAS = (2.0, 10.0, 50.0)
DECAYS = (0.7, 0.85, 1.0)
HFA = 0  # feature index reserved for the home indicator in the side model


def _team_index(teams):
    return {t: i for i, t in enumerate(sorted(teams))}


def _side_design(g, idx):
    """Row for the margin model: y = margin_home."""
    items = [(idx[g["home"]], 1.0), (idx[g["away"]], -1.0), (len(idx), 1.0)]
    return g["margin_home"], items


def _total_design(g, idx, off):
    """Two rows for the points model: home score, then away score."""
    n = len(idx)
    home_row = (float(g["home_score"]),
                [(off + idx[g["home"]], 1.0), (off + n + idx[g["away"]], -1.0),
                 (off + 2 * n + 1, 1.0), (off + 2 * n, 1.0)])
    away_row = (float(g["away_score"]),
                [(off + idx[g["away"]], 1.0), (off + n + idx[g["home"]], -1.0),
                 (off + 2 * n, 1.0)])
    return [home_row, away_row]


def _fit_side(train, teams, lam, decay=1.0, ref_season=None):
    idx = _team_index(teams)
    m = Ridge(len(teams) + 1, lam)
    ref = ref_season if ref_season is not None else max((g["season"] for g in train), default=0)
    for g in train:
        if not g["settled"]:
            continue
        y, items = _side_design(g, idx)
        m.add(y, items, decay ** (ref - g["season"]))
    return m.fit(), idx


def _fit_total(train, teams, lam, decay=1.0, ref_season=None):
    idx = _team_index(teams)
    n = len(teams)
    m = Ridge(2 * n + 2, lam)
    ref = ref_season if ref_season is not None else max((g["season"] for g in train), default=0)
    for g in train:
        if not g["settled"]:
            continue
        w = decay ** (ref - g["season"])
        for y, items in _total_design(g, idx, 0):
            m.add(y, items, w)
    return m.fit(), idx


def _rmse(model, idx, rows, kind):
    tot, n = 0.0, 0
    for g in rows:
        if not g["settled"]:
            continue
        if kind == "side":
            y, items = _side_design(g, idx)
            tot += (y - model.predict(items)) ** 2
            n += 1
        else:
            for y, items in _total_design(g, idx, 0):
                tot += (y - model.predict(items)) ** 2
                n += 1
    return math.sqrt(tot / n) if n else float("inf")


def _choose_hyper(train, teams, kind, ref_season):
    """Pick (recency decay, ridge penalty) on the last 20% of the training window.

    The hold-out is carved out of the training window only, so nothing from the
    season being predicted can reach either hyper-parameter.
    """
    ordered = sorted(train, key=lambda g: (g["gameday"], g["game_id"]))
    cut = max(1, int(len(ordered) * 0.8))
    fit_part, val_part = ordered[:cut], ordered[cut:]
    if not val_part:
        fit_part, val_part = ordered[:-1], ordered[-1:]
    best, best_pair = float("inf"), (DECAYS[0], SIDE_LAMBDAS[0])
    for decay in DECAYS:
        for lam in (SIDE_LAMBDAS if kind == "side" else TOTAL_LAMBDAS):
            if kind == "side":
                model, idx = _fit_side(fit_part, teams, lam, decay, ref_season)
            else:
                model, idx = _fit_total(fit_part, teams, lam, decay, ref_season)
            score = _rmse(model, idx, val_part, kind)
            if score < best:
                best, best_pair = score, (decay, lam)
    return best_pair


def fit_window(train, teams, ref_season=None):
    """Fit both models on a training window with an inner hyper-parameter search."""
    ref = ref_season or max((g["season"] for g in train), default=0)
    decay_s, lam_side = _choose_hyper(train, teams, "side", ref)
    decay_t, lam_total = _choose_hyper(train, teams, "total", ref)
    side, idx_s = _fit_side(train, teams, lam_side, decay_s, ref)
    total, idx_t = _fit_total(train, teams, lam_total, decay_t, ref)
    return {
        "side": side, "idx_side": idx_s, "lam_side": lam_side, "decay_side": decay_s,
        "total": total, "idx_total": idx_t, "lam_total": lam_total, "decay_total": decay_t,
        "train_games": sum(1 for g in train if g["settled"]),
    }


# ---------------------------------------------------------------------------
# origination
# ---------------------------------------------------------------------------

def predict_market(fit, g):
    """Return (fair_spread_home, fair_total, fair_margin_home).

    Steps 1 and 2 are independent models; step 3 re-uses the step 1 margin.
    """
    idx_s = fit["idx_side"]
    _, items = _side_design(g, idx_s)
    fair_margin = fit["side"].predict(items)          # step 1
    idx_t = fit["idx_total"]
    n = len(idx_t)
    home_row = [(idx_t[g["home"]], 1.0), (n + idx_t[g["away"]], -1.0),
                (2 * n + 1, 1.0), (2 * n, 1.0)]
    away_row = [(idx_t[g["away"]], 1.0), (n + idx_t[g["home"]], -1.0),
                (2 * n, 1.0)]
    pred_home = fit["total"].predict(home_row)        # step 2
    pred_away = fit["total"].predict(away_row)
    # Sign convention, matched to the market column it sits beside: the model's
    # fair home spread is POSITIVE when the home team is favoured, exactly as
    # games.csv prints spread_line. The model first produces a home margin, and
    # the fair spread in this convention is that same number.
    return fair_margin, pred_home + pred_away, fair_margin


def _fit_sigma(pairs):
    """Pick the moneyline scale by minimising out-of-sample log-loss.

    ``pairs`` are (model_margin, home_won) for seasons already scored. The scale
    chosen for season S therefore comes only from seasons strictly earlier than
    S. The raw residual spread of the margin model is NOT the right scale: the
    market's own moneylines imply a scale near 12.0 (see
    ``market_sigma_check``), because the margin distribution is not normal.
    """
    if len(pairs) < 300:
        return DEFAULT_SIGMA, False
    best, best_s = float("inf"), DEFAULT_SIGMA
    i = SIGMA_GRID[0]
    while i <= SIGMA_GRID[1] + 1e-9:
        ll = 0.0
        for margin, won in pairs:
            p = _phi(margin / i)
            p = min(max(p, 1e-6), 1 - 1e-6)
            ll -= math.log(p if won else 1.0 - p)
        if ll < best:
            best, best_s = ll, i
        i += SIGMA_GRID[2]
    return round(best_s, 2), True


def market_sigma_check(games, sigma_grid=(10.0, 11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 14.0)):
    """What scale does the market's own moneyline imply against its own spread?

    For each settled game with both a spread and two moneylines, convert the
    de-vigged home win probability back to a spread and compare it with the
    printed spread. The scale that reconciles the two is published, with n.
    """
    rows = [g for g in games if g["settled"] and g["spread_line"] is not None
            and g["home_moneyline"] and g["away_moneyline"]]
    out = []
    for sg in sigma_grid:
        diffs = []
        for g in rows:
            ph, _ = devig(g["home_moneyline"], g["away_moneyline"])
            if ph is None:
                continue
            diffs.append(_inv_phi(ph) * sg - g["spread_line"])
        if diffs:
            out.append({
                "sigma": sg, "n": len(diffs),
                "mean": round(sum(diffs) / len(diffs), 3),
                "mean_abs": round(sum(abs(d) for d in diffs) / len(diffs), 3),
                "sd": round(math.sqrt(sum(d * d for d in diffs) / len(diffs)
                                      - (sum(diffs) / len(diffs)) ** 2), 3),
            })
    best = min(out, key=lambda r: r["mean_abs"]) if out else None
    return {"rows": out, "best": best, "games": len(rows)}


def originate(games, test_seasons, teams, live_season=2026, live_before=None):
    """Walk-forward origination.

    ``test_seasons`` are scored out of sample. ``live_before`` (a gameday
    string) additionally builds a model on every settled game before that date
    so that this week's fixtures can be originated with all information the
    league has actually published.
    """
    rows = []
    oos_pairs = []          # (model_margin, home_won) for seasons already scored
    sigma_trace = []

    for season in test_seasons:
        train = [g for g in games if g["season"] < season and g["settled"]]
        test = [g for g in games if g["season"] == season]
        if len(train) < 400:
            continue
        fit = fit_window(train, teams, season)
        sigma, fitted = _fit_sigma(oos_pairs)
        sigma_trace.append({"season": season, "sigma": sigma, "fitted": fitted,
                            "n_calibration_games": len(oos_pairs)})
        season_pairs = []
        for g in test:
            row = _originate_one(g, fit, sigma, "oos")
            rows.append(row)
            if g["settled"]:
                season_pairs.append((row["model_margin_home"], g["margin_home"] > 0))
        oos_pairs.extend(season_pairs)

    # live model for this week's fixtures
    live_fit = None
    if live_before is not None:
        train = [g for g in games if g["settled"] and g["gameday"] < live_before]
        fit = fit_window(train, teams, live_season)
        sigma, fitted = _fit_sigma(oos_pairs)
        live_fit = (fit, sigma, len(train), fitted)
        for g in games:
            if g["season"] == live_season and not g["settled"] and g["spread_line"] is not None:
                rows.append(_originate_one(g, fit, sigma, "live"))
    return rows, live_fit, sigma_trace


def _originate_one(g, fit, sigma, mode):
    src_mkt = sources.get("nfldata_games")
    fair_spread_home, fair_total, fair_margin = predict_market(fit, g)
    row = {
        "game_id": g["game_id"],
        "season": g["season"],
        "week": g["week"] if g["week"] is not None else "",
        "gameday": g["gameday"],
        "home": g["home"],
        "away": g["away"],
        "mode": mode,
        "sigma_margin": round(sigma, 3),

        # --- step 1: the side -------------------------------------------
        "origination_step_side": 1,
        "fair_side": round(fair_spread_home, 2),
        "market_side": g["spread_line"] if g["spread_line"] is not None else "",
        "diff_side": (round(g["spread_line"] - fair_spread_home, 2)
                      if g["spread_line"] is not None else ""),

        # --- step 2: the total ------------------------------------------
        "origination_step_total": 2,
        "fair_total": round(fair_total, 2),
        "market_total": g["total_line"] if g["total_line"] is not None else "",
        "diff_total": (round(g["total_line"] - fair_total, 2)
                       if g["total_line"] is not None else ""),

        # --- step 3: the moneyline, derived from the side ----------------
        "origination_step_ml": 3,
        "model_margin_home": round(fair_margin, 3),
        "fair_prob_home": "",
        "market_prob_home": "",
        "diff_ml_pp": "",
        "fair_ml_home": "",
        "market_ml_home": g["home_moneyline"] if g["home_moneyline"] is not None else "",
        "market_ml_away": g["away_moneyline"] if g["away_moneyline"] is not None else "",
        "source": src_mkt["label"],
        "source_url": src_mkt["url"],
        "source_tier": src_mkt["tier"],
        "flag": "",
    }
    p_home = _phi(fair_margin / sigma) if sigma > 0 else None
    if p_home is not None:
        row["fair_prob_home"] = round(100 * p_home, 2)
        row["fair_ml_home"] = prob_to_american(p_home)
    mkt_h, _ = devig(g["home_moneyline"], g["away_moneyline"])
    if mkt_h is not None:
        row["market_prob_home"] = round(100 * mkt_h, 2)
        if p_home is not None:
            row["diff_ml_pp"] = round(100 * (p_home - mkt_h), 2)
    if not g["settled"]:
        row["flag"] = ("originated before kick-off; market line is the number standing at "
                       "capture, not the closing number")
    return row
