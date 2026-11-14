"""Central configuration for the X1 NFL line-origination project.

Every tunable used by the pipeline lives here so that a reviewer can see the
whole configuration surface in one file.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SITE_DATA_DIR = DATA_DIR / "site"
# The research site is published under /research/ so it cannot collide with the
# integration session's docs/*.md methodology documents.
RESEARCH_DIR = REPO_ROOT / "research"

# --------------------------------------------------------------------------
# Data acquisition
# --------------------------------------------------------------------------
# The sandbox egress allow-list only permits GitHub + PyPI hosts, so bulk data
# is pulled from GitHub through the REST contents API (raw media type).
GITHUB_API = "https://api.github.com"
GITHUB_RAW_ACCEPT = "application/vnd.github.raw"

# Owner/repo of the community data mirror used for bulk tables.
MIRROR_REPO = "nflverse/nfldata"
SECONDARY_REPO = "Beexly/Sports"

# --------------------------------------------------------------------------
# Season splits (walk-forward, no leakage)
# --------------------------------------------------------------------------
FIRST_SEASON = 2006          # first season with market lines in the mirror
TRAIN_END_SEASON = 2024      # <= TRAIN_END is training, > is strictly OOS
VALID_SEASON = 2025          # validation window (used for tuning only)
TEST_SEASON = 2026          # final holdout window
CURRENT_SEASON = 2026
CURRENT_WEEK = 10            # week whose official injury report is published

# Half-life (in games) for exponential recency weighting of training rows.
RECENCY_HALF_LIFE_GAMES = 512.0

# --------------------------------------------------------------------------
# Elo model (538-style, transparent variant - documented on the site)
# --------------------------------------------------------------------------
ELO_INIT = 1500.0
ELO_HFA = 25.0               # home-field advantage expressed in Elo points
ELO_K_BASE = 20.0
ELO_SEASON_REVERSION = 0.25  # regress ratings toward the mean between seasons

# --------------------------------------------------------------------------
# Originated-line model
# --------------------------------------------------------------------------
LINE_ROUNDING = 0.5          # lines are published on half points
SPREAD_TOTAL_EPS = 1e-9

# --------------------------------------------------------------------------
# Validation gates
# --------------------------------------------------------------------------
GATE_MIN_BETS = 100          # G1 sample-size floor for a publishable strategy
GATE_MIN_ROI = 0.02          # G4 economic floor (2% ROI on unit stakes)
GATE_CI_LEVEL = 0.95         # G3 bootstrap confidence level
GATE_MAX_PVALUE = 0.05       # G3 permutation-test ceiling
GATE_PARAM_STABILITY = 0.6  # G6 min share of sensitivity variants that stay positive
GATE_MAX_CORRELATION = 0.85 # G7 max pairwise correlation with an accepted strategy

# --------------------------------------------------------------------------
# Strategy thresholds
# --------------------------------------------------------------------------
SPREAD_EDGE_THRESHOLDS = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
TOTAL_EDGE_THRESHOLDS = (0.5, 1.0, 1.5, 2.0, 2.5)
DEFAULT_SPREAD_EDGE = 1.0
DEFAULT_TOTAL_EDGE = 1.0

# Luck filters (standard "remove luck" screens)
ONE_SCORE_MAX_MARGIN = 8    # games decided by <= 8 points
BLOWOUT_MIN_MARGIN = 25     # games decided by >= 25 points

# --------------------------------------------------------------------------
# Payouts
# --------------------------------------------------------------------------
DEFAULT_ODDS = -110          # American odds assumed when a book price is absent
ODDS_MISSING = -115          # price actually assumed where the mirror has none

# --------------------------------------------------------------------------
# Player props
# --------------------------------------------------------------------------
PROP_MIN_SAMPLE = 60         # minimum player-games for a prop model
PROP_ROLLING_WINDOW = 6      # games used for a player's rolling mean
PROP_FAMILIES = ("passing_yards", "rushing_yards", "receiving_yards", "receptions")

# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------
OFFLINE = os.environ.get("X1_OFFLINE", "0") == "1"
RANDOM_SEED = 20261114
