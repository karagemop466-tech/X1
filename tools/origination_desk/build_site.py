#!/usr/bin/env python3
"""Generate the clean, self-contained Origination & Skill Desk HTML pages (`origination-desk/*.html`).

Every data table carries `data-table` and places a verified official `https://` source link
in its `Source` cell. Blank cells in underlying CSVs are rendered explicitly as `<span class="blank">blank — unverified</span>`
rather than filled or inferred. Uses only CSS classes defined in `assets/site.css`.

Usage:
  python3 tools/origination_desk/build_site.py
  python3 tools/origination_desk/build_site.py --check
"""
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DATA_ROSTER = ROOT / "data" / "origination_desk" / "roster"
DATA_WEATHER = ROOT / "data" / "origination_desk" / "weather"
DATA_SKILL = ROOT / "data" / "origination_desk" / "skill"
OUT_DIR = ROOT / "origination-desk"

PAGES = [
    ("index.html", "Overview & Readiness"),
    ("lines-vig.html", "Lines & Vig-Free View"),
    ("leaderboard.html", "Two-Stage Skill Board"),
    ("joint-gate.html", "Joint Gate & Correlations"),
    ("roster-turnover.html", "Reserve, Trades & Inactives"),
    ("weather-venues.html", "Roof/Surface & NWS Weather"),
    ("weekly-diff.html", "Weekly What-Changed Diff"),
    ("decisions-flags.html", "Flagged for review"),
]


def _esc(val: object) -> str:
    return html.escape(str(val if val is not None else ""), quote=True)


def _cell(val: object, blank_label: str = "blank (unverified)") -> str:
    s = str(val if val is not None else "").strip()
    if not s:
        return f'<span class="blank">{_esc(blank_label)}</span>'
    return _esc(s)


def _pill(text: str, tone: str = "muted-pill") -> str:
    return f'<span class="pill {tone}">{_esc(text)}</span>'


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _layout(active_file: str, title: str, eyebrow: str, subtitle: str, body_html: str) -> str:
    nav_links = ['<a href="../index.html">Main Root</a>', '<a href="../suggestions/index.html">Decision Center</a>']
    for fname, label in PAGES:
        cls = ' class="active"' if fname == active_file else ""
        nav_links.append(f'<a href="{fname}"{cls}>{_esc(label)}</a>')
    nav_html = " · ".join(nav_links)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} | NFL Origination &amp; Skill Desk</title>
<link rel="stylesheet" href="../assets/site.css">
<style>
main {{ max-width: 1180px; margin: 0 auto; padding: 1.25rem 1rem 3rem; }}
nav[aria-label="Desk navigation"] {{ line-height: 1.8; margin-bottom: 0.75rem; font-size: 0.92rem; }}
nav[aria-label="Desk navigation"] a.active {{ font-weight: 700; text-decoration: underline; }}
.tablewrap {{ overflow-x: auto; margin: 0.85rem 0 1.6rem; }}
input[type="search"] {{ padding: 0.45rem 0.7rem; min-width: 260px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 0.92rem; margin-bottom: 0.5rem; }}
</style>
</head>
<body>
<main>
<header class="pagetitle">
<nav aria-label="Desk navigation">{nav_html}</nav>
<p class="eyebrow">{_esc(eyebrow)} · Baseline snapshot 2026-11-14 · Live official audit 2026-11-19</p>
<h1>{_esc(title)}</h1>
<p class="lede">{_esc(subtitle)}</p>
</header>
<section class="content">
{body_html}
</section>
<footer class="mainfoot">
<p class="small muted">NFL Origination &amp; Skill Desk (<code>origination-desk/</code>) · Baseline snapshot: 2026-11-14 · Re-verified from official NFL.com, Club &amp; US National Weather Service sources: 2026-11-19 · Unconfirmed cells are intentionally left blank and listed on <a href="decisions-flags.html">Flagged for review</a>.</p>
</footer>
</main>
<script>
document.querySelectorAll('input[data-filter]').forEach(function(inp) {{
  inp.addEventListener('input', function() {{
    var q = inp.value.toLowerCase().trim();
    var tbl = document.getElementById(inp.getAttribute('data-filter'));
    if (!tbl) return;
    tbl.querySelectorAll('tbody tr').forEach(function(tr) {{
      tr.style.display = (!q || tr.textContent.toLowerCase().indexOf(q) !== -1) ? '' : 'none';
    }});
  }});
}});
</script>
</body>
</html>
"""


def _render_index(roster_sum: dict, weather_sum: dict, skill_sum: dict) -> str:
    wf = skill_sum["two_stage_leaderboard"]["walkforward_2026_w1_10"]
    mult = skill_sum["two_stage_leaderboard"]["multiplicity"]
    vf = skill_sum["vig_free_decomposition"]
    rc = roster_sum["counts"]
    wc = weather_sum["counts"]
    luck_rows = _read_csv(DATA_SKILL / "luck_removal_panel.csv")

    luck_trs = []
    for r in luck_rows:
        luck_trs.append(
            f"<tr><td><code>{_esc(r['horizon_id'])}</code></td>"
            f"<td>{_esc(r['sample_description'])}</td>"
            f"<td>{_esc(r['n_games'])}</td>"
            f"<td>{_esc(r['expected_hit_se_from_luck_pct'])}%</td>"
            f"<td>{_esc(r['two_sigma_luck_band_pct'])}</td>"
            f"<td>{_cell(r['expected_brier_pure_luck'])}</td>"
            f"<td>{_cell(r['observed_brier'], 'pending finals')}</td>"
            f"<td>{_cell(r['excess_model_misfit_brier'], 'pending finals')}</td>"
            f"<td>{_esc(r['decision_implication'])}</td>"
            f'<td><a class="src-link" href="{_esc(r["source_url"])}">Official NFL</a></td></tr>'
        )

    readiness_rows = [
        ("OD-R01", "Vig-Free Consensus vs. Originated Fair-Line Decomposition", "BUILT (W11 blank-market + W10 mirror audit)",
         "Q-02 licensed 2026 opening/closing market quotes",
         "2 timestamped permitted quotes/market across >=100 prospective fixtures",
         "lines-vig.html", "https://www.nfl.com/schedules/2026/by-week/week-11"),
        ("OD-R02", "Two-Stage Skill Leaderboard (Stage 1 Proper Score -> Stage 2 CLV Escrow)", "BUILT (0 Stage-2 live; 3 in escrow)",
         f"Prospective sample n=1 settled (<100) + multiplicity M={mult['total_trials_M']} (Sidak z={mult['sidak_z_one_sided']})",
         "n >= 100 settled prospective game clusters with multiplicity-adjusted BSS_LB > 0",
         "leaderboard.html", "https://www.nfl.com/games/chargers-at-ravens-2026-reg-10"),
        ("OD-R03", "Joint-Evidence Gate for Game Parlays, SGPs & Player Prop Combos", "BUILT & ENFORCED (all 3 combo divisions locked)",
         "Unvalidated joint copula + missing operator push/void/DNP rules + Q-02/Q-04",
         "Calibrated bivariate/multivariate Brier skill > 0 on >=200 games + committed void rules",
         "joint-gate.html", "https://www.nfl.com/schedules/2026/by-week/week-10"),
        ("OD-R04", "Official-Only Correlations Published with Sample Size n", "BUILT (9 game/club pairs; n=150 and n=32)",
         "Market-price correlations remain research-only until Q-02 clears",
         "n >= 150 verified official finals (met for score/margin/total pairs)",
         "joint-gate.html", "https://www.nfl.com/standings/league/2026/REG"),
        ("OD-R05", "Reserve/IR Sweep & Roster-Turnover Versioning Against Official Transactions", f"BUILT ({rc['reserve_rows_verified']} reserve + {rc['november_trades_verified']} trades; {rc['stale_depth_and_turnover_flags']} stale flags)",
         "NFL.com monthly Reserve List truncates at 25 rows & leaves Position blank",
         "Automated 32-club roster RES scrape before every weekly origination run (0 unjoined clubs)",
         "roster-turnover.html", "https://www.nfl.com/transactions/league/reserve-list/2026/11"),
        ("OD-R06", "Announced-Starter Evidence & Official 90-Minute Inactive Lists", f"BUILT ({rc['announced_starters_verified']} starters; {rc['week10_inactive_players_verified']} W10 inactives across 14 games)",
         "Snap counts unprinted in Game Book summary text & PDF carries written-permission notice (Q-04)",
         "Written NFL permission or licensed snap-participation feed covering all 32 clubs",
         "roster-turnover.html", "https://www.nfl.com/news/nfl-week-10-inactives-players-ruled-out-sunday-2026-season"),
        ("OD-R07", "Stadium Roof/Surface & Official NWS Hourly Wind/Precipitation Overlay", f"BUILT ({wc['us_nws_covered_fixtures']}/13 US NWS grids live; 1 intl blank)",
         "Pre-kickoff Game Center omits roof/surface; roof status declared 90 min pre-kickoff",
         "Automated 90-min pre-kickoff club roof capture + non-US WMO feed for international games",
         "weather-venues.html", "https://api.weather.gov/gridpoints/LOT/76,72/forecast"),
        ("OD-R08", "Weekly 'What Changed' Diff (Rank, Shrunk Rating & Availability)", "BUILT (32/32 clubs W9 -> Post-W10 -> W11)",
         "Historical pre-2026 weekly injury archive still incomplete for multi-season diffs",
         "32/32 clubs reconciled weekly after Monday Night Football (met for W9 -> W10)",
         "weekly-diff.html", "https://www.nfl.com/standings/league/2026/REG"),
    ]
    r_trs = []
    for rid, req, st, gate, clear, href, surl in readiness_rows:
        r_trs.append(
            f'<tr><td><code>{_esc(rid)}</code></td>'
            f'<td><a href="{_esc(href)}">{_esc(req)}</a></td>'
            f'<td>{_pill(st, "ok")}</td>'
            f'<td>{_esc(gate)}</td>'
            f'<td>{_esc(clear)}</td>'
            f'<td><a class="src-link" href="{_esc(surl)}">Official source</a></td></tr>'
        )

    return f"""
<div class="note">
<b>Executive Summary (Honest Position as of 2026-11-19):</b>
<b>Zero strategies qualify for live Stage-2 capital deployment.</b> Across 150 verified 2026 regular-season games (Weeks 1–10), road clubs won more often than home clubs (realized home win rate <b>{wf['realized_home_win_rate']*100:.2f}%</b>), causing the naive 55% home-rate baseline (Brier <code>{wf['mean_brier_home55']:.4f}</code>) to underperform a fair 50/50 coin (<code>{wf['mean_brier_coin']:.4f}</code>). While the out-of-sample walk-forward shrinkage baseline improves mean Brier to <code>{wf['mean_brier_wf']:.4f}</code> (Brier Skill <code>{wf['bss_wf_vs_coin']:+.4f}</code>), its 95% week-cluster lower bound is <b><code>{wf['cluster_bss_lb95']:+.4f}</code></b> and its Šidák multiplicity-adjusted lower bound across <b>M = {mult['total_trials_M']}</b> repository trials is <b><code>{wf['multiplicity_adj_bss_lb']:+.4f}</code></b>. Three prospective pre-kickoff registrations (<code>PR-01</code>, <code>PR-04</code>, <code>KR-T1</code>) are locked in escrow ahead of tonight's Week 11 opener (<code>IND @ HOU</code>), all multi-leg parlay/SGP/prop divisions remain locked behind the Joint-Evidence Gate, 20 stale club depth-chart &amp; roster-turnover discrepancies are flagged from official NFL transactions, and Sunday's <code>NO @ CHI</code> fixture carries an official NWS <b>80% rain / 15 mph WSW wind</b> alert.
</div>

<div class="statrow">
  <div class="stat"><div class="big">0 / {mult['total_trials_M']}</div><div class="statnote">Strategies cleared for Stage-2 live staking (28 backtests quarantined; 3 in prospective escrow)</div></div>
  <div class="stat"><div class="big">{wf['bss_wf_vs_coin']:+.3f}</div><div class="statnote">W1–10 walk-forward Brier Skill vs coin (cluster 95% LB <code>{wf['cluster_bss_lb95']:+.3f}</code>; Sidak LB <code>{wf['multiplicity_adj_bss_lb']:+.3f}</code>)</div></div>
  <div class="stat"><div class="big">{vf['mean_w10_mirror_overround_pct']:.2f}%</div><div class="statnote">Mean 2-way moneyline overround on W10 mirror audit (<code>{vf['mean_w10_vig_tax_per_side_pct']:.2f}%</code> vig tax per side)</div></div>
  <div class="stat"><div class="big">{rc['stale_depth_and_turnover_flags']}</div><div class="statnote">Stale depth-chart &amp; roster-turnover flags caught vs official NFL IR &amp; trade logs</div></div>
</div>

<h2>Decision-Readiness Register (Origination &amp; Skill Desk Scope)</h2>
<p>One row per requirement delivered in this section, naming the exact gate that still blocks live deployment and the quantitative threshold that clears it.</p>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">ID</th><th scope="col">Requirement &amp; Subpage</th><th scope="col">Build State</th><th scope="col">Blocking Gate</th><th scope="col">Number / Condition That Clears Gate</th><th scope="col">Source</th></tr></thead>
<tbody>
{"".join(r_trs)}
</tbody>
</table>
</div>

<h2>Removal-of-Luck Panel (Outcome Variance vs. Model Calibration)</h2>
<p>Under calibrated probabilities <code>p_i</code>, irreducible Bernoulli outcome noise contributes expected Brier <code>mean(p_i * (1 - p_i))</code> and hit-rate standard error <code>sqrt(mean(p_i*(1-p_i))/n)</code>. Ranking strategies by short-window win rate or season ROI confuses coin variance with origination skill.</p>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">Horizon</th><th scope="col">Window</th><th scope="col">n</th><th scope="col">1-Sigma Luck SE</th><th scope="col">95% Pure-Luck Hit Band</th><th scope="col">Irreducible Luck Brier</th><th scope="col">Observed Brier</th><th scope="col">Excess Misfit Brier</th><th scope="col">Governance Reading</th><th scope="col">Source</th></tr></thead>
<tbody>
{"".join(luck_trs)}
</tbody>
</table>
</div>

<h2>Desk Navigation by Category</h2>
<div class="cards">
  <div class="card"><h3><a href="lines-vig.html">1. Originated Lines &amp; Vig-Free View</a></h3><p>52 prospective Week 11 escrow lines in strict <code>Side → Dual Totals (A/B) → Moneyline</code> order (market blank per Q-02) plus 14-game Week 10 multiplicative, additive &amp; power vig-free decomposition.</p></div>
  <div class="card"><h3><a href="leaderboard.html">2. Two-Stage Proper-Score Leaderboard</a></h3><p>Stage-1 Brier Skill qualification with week-cluster bootstrap &amp; M=31 Sidak multiplicity adjustment, paired controls, signal-vs-staking split, demotion gate, and two-sided mind-change rules.</p></div>
  <div class="card"><h3><a href="joint-gate.html">3. Joint Gate &amp; Official Correlations</a></h3><p>Empirical proof of why multiplying marginal probabilities fails for SGPs &amp; combos, plus 9 official-only correlations published with exact <code>n</code> (150 games; 32 clubs) and Fisher 95% CIs.</p></div>
  <div class="card"><h3><a href="roster-turnover.html">4. Reserve, Trades, Starters &amp; Inactives</a></h3><p>43 official Reserve/IR entries, all 12 Nov 2026 NFL trades, 20 stale club depth-chart flags (Hutchinson, Carlies, McCormick, Nacua, Henley), 5 announced starters, and all 172 Week 10 inactives.</p></div>
  <div class="card"><h3><a href="weather-venues.html">5. Stadium Roof/Surface &amp; NWS Overlay</a></h3><p>All 13 Week 11 Game Center venues coupled with live US National Weather Service hourly/period wind &amp; precipitation forecasts and 90-minute roof-declaration gates.</p></div>
  <div class="card"><h3><a href="weekly-diff.html">6. Weekly What-Changed Diff</a></h3><p>All 32 NFL clubs from Week 9 to Post-Week-10 and Week 11 pre-kickoff: league rank delta, shrunk margin rating delta, W10 inactive counts, and Nov 10–18 IR/trade turnover.</p></div>
</div>
"""


def _render_lines_vig(skill_sum: dict) -> str:
    rows = _read_csv(DATA_SKILL / "vig_free_decomposition.csv")
    vf = skill_sum["vig_free_decomposition"]
    w11_rows = [r for r in rows if r["track"] == "PROSPECTIVE_ESCROW_PR04"]
    w10_rows = [r for r in rows if r["track"] == "MIRROR_DECOMPOSITION_AUDIT_W10"]

    w10_trs = []
    for r in w10_rows:
        w10_trs.append(
            f"<tr><td><code>{_esc(r['game_id'])}</code></td>"
            f"<td>{_esc(r['away'])} @ {_esc(r['home'])}</td>"
            f"<td>{_esc(r['orig_fair_line'])}</td>"
            f"<td><code>{_esc(r['orig_prob_home'])}</code></td>"
            f"<td><code>{_esc(r['raw_market_quote_away'])} / {_esc(r['raw_market_quote_home'])}</code></td>"
            f"<td><code>{_esc(r['raw_implied_home'])}</code></td>"
            f"<td>{_esc(r['book_overround_pct'])}%</td>"
            f"<td><code>{_esc(r['vig_free_mult_home'])}</code></td>"
            f"<td><code>{_esc(r['vig_free_add_home'])}</code></td>"
            f"<td><code>{_esc(r['vig_free_power_home'])}</code> (k={_esc(r['power_exponent_k'])})</td>"
            f"<td>{_esc(r['operator_vig_tax_home_pct'])}%</td>"
            f"<td><b>{_esc(r['vig_free_alpha_home_pct'])}%</b></td>"
            f"<td>{_esc(r['net_post_vig_edge_home_pct'])}%</td>"
            f'<td><a class="src-link" href="{_esc(r["source_url"])}">NFL Game Center</a></td></tr>'
        )

    w11_trs = []
    for r in w11_rows:
        w11_trs.append(
            f"<tr><td>{_esc(r['origination_order'])}</td>"
            f"<td><code>{_esc(r['market'])}</code></td>"
            f"<td><code>{_esc(r['game_id'])}</code></td>"
            f"<td>{_esc(r['away'])} @ {_esc(r['home'])}</td>"
            f"<td><b>{_esc(r['orig_fair_line'])}</b></td>"
            f"<td>{_cell(r['orig_prob_home'], 'gap metric / n/a')}</td>"
            f"<td>{_cell(r['raw_market_quote_home'], 'blank — Q-02')}</td>"
            f"<td>{_cell(r['vig_free_mult_home'], 'blank — Q-02')}</td>"
            f"<td>{_cell(r['vig_free_alpha_home_pct'], 'blank — Q-02')}</td>"
            f"<td>{_esc(r['price_tier_status'])}</td>"
            f'<td><a class="src-link" href="{_esc(r["source_url"])}">NFL Game Center</a></td></tr>'
        )

    return f"""
<div class="formula">
<b>Decomposition Identity:</b> <code>Net Edge (p_orig - q_raw) = Vig-Free Alpha (p_orig - p_vigfree) - Operator Vig Tax (q_raw - p_vigfree)</code> · Origination sequence enforced on every fixture: <code>1. Side → 2. Dual Totals (Estimator A &amp; Estimator B) → 3. Moneyline</code>.
</div>

<h2>Part A — Week 10 Vig-Free Market Consensus vs. Originated Fair-Line Decomposition (14 Games, Mirror Research Audit)</h2>
<p>Separates operator hold (mean overround <b>{vf['mean_w10_mirror_overround_pct']:.2f}%</b>, or <b>{vf['mean_w10_vig_tax_per_side_pct']:.2f}%</b> per side) from vig-free model disagreement across Multiplicative, Additive, and Power (<code>q_away^k + q_home^k = 1</code>) de-vigging methods. Market quotes in this audit come from the repository's labelled third-party benchmark (<code>originated_lines_2026_week10.csv</code>) and are never treated as official NFL data.</p>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">Game ID</th><th scope="col">Matchup</th><th scope="col">Originated Line</th><th scope="col">Orig p(Home)</th><th scope="col">Mirror ML (A/H)</th><th scope="col">Raw q(Home)</th><th scope="col">Overround</th><th scope="col">Vig-Free Mult</th><th scope="col">Vig-Free Add</th><th scope="col">Vig-Free Power (k)</th><th scope="col">Vig Tax</th><th scope="col">Vig-Free Diff</th><th scope="col">Net Post-Vig</th><th scope="col">Source</th></tr></thead>
<tbody>
{"".join(w10_trs)}
</tbody>
</table>
</div>

<h2>Part B — Week 11 Prospective Pre-Kickoff Origination Board (52 Rows = 13 Games × 4 Markets, Frozen PR-04 Escrow)</h2>
<p>Every model total is published twice (<code>total_A</code> league-average floor vs. <code>total_B</code> shrunk team-scoring sum) until walk-forward evaluation selects one. Market quote, vig tax, and residual columns remain intentionally blank pending an authorized 2026 price feed (<code>Q-02</code>).</p>
<input type="search" data-filter="w11-escrow-tbl" placeholder="Filter Week 11 markets (e.g. IND, CHI, total_B, side)...">
<div class="tablewrap" tabindex="0">
<table class="wide" id="w11-escrow-tbl" data-table>
<thead><tr><th scope="col">Order</th><th scope="col">Market</th><th scope="col">Game ID</th><th scope="col">Matchup</th><th scope="col">Originated Fair Line</th><th scope="col">Orig Prob / B-A Gap</th><th scope="col">Market Quote</th><th scope="col">Vig-Free Consensus</th><th scope="col">Residual / Alpha</th><th scope="col">Provenance &amp; Gate</th><th scope="col">Source</th></tr></thead>
<tbody>
{"".join(w11_trs)}
</tbody>
</table>
</div>
"""


def _render_leaderboard(skill_sum: dict) -> str:
    rows = _read_csv(DATA_SKILL / "two_stage_leaderboard.csv")
    meta = skill_sum["two_stage_leaderboard"]
    mult = meta["multiplicity"]

    trs = []
    for r in rows:
        role = r["entry_role"]
        tone = "ok" if role == "CONTROL_BASELINE" else ("warn" if "PROSPECTIVE" in role else "alert")
        trs.append(
            f"<tr><td><code>{_esc(r['entry_id'])}</code></td>"
            f"<td>{_esc(r['division'])}</td>"
            f"<td>{_pill(role, tone)}</td>"
            f"<td>{_esc(r['registration_ref'])}</td>"
            f"<td>{_esc(r['n_settled_prospective'])} settled / {_esc(r['n_pending_escrow'])} escrow (ref {_esc(r['n_walkforward_ref'])})</td>"
            f"<td>{_cell(r['mean_brier_score'], 'awaiting W11')}</td>"
            f"<td>{_cell(r['brier_skill_vs_coin'], 'awaiting W11')}</td>"
            f"<td>{_cell(r['cluster_bss_lb95'], 'n < 10 clusters')}</td>"
            f"<td>{_cell(r['multiplicity_adj_bss_lb'], 'n < 10 clusters')}</td>"
            f"<td>{_esc(r['signal_metric'])}</td>"
            f"<td>{_cell(r['staking_metric_clv_roi'], 'blank — Q-02')}</td>"
            f"<td>{_esc(r['stage1_proper_score_gate'])} → {_esc(r['stage2_escrow_clv_gate'])}</td>"
            f"<td>{_esc(r['demotion_gate_state'])}</td>"
            f"<td><b>Adopt:</b> {_esc(r['adopt_if_two_sided'])}<br><b>Abandon:</b> {_esc(r['abandon_if_two_sided'])}</td>"
            f'<td><a class="src-link" href="{_esc(r["source_url"])}">Official source</a></td></tr>'
        )

    return f"""
<div class="note">
<b>Governance Invariants Enforced on This Board:</b>
(1) <b>Zero retrospective backtest numbers enter Stage-1 or Stage-2 rankings</b> — the {mult['quarantined_retrospective_trials_in_repo']} historical backtest entries in <code>data/mind_change/register.csv</code> are quarantined and counted strictly inside the trial multiplicity denominator <b>M = {mult['total_trials_M']}</b> (Šidák per-trial <code>alpha = {mult['sidak_alpha_per_trial']:.6f}</code>, one-sided <code>z = {mult['sidak_z_one_sided']:.3f}</code>).
(2) <b>Signal is separated from Staking</b>: Stage 1 grades probability calibration via Brier Skill Score against always-on controls; Stage 2 grades prospective vig-free CLV and staking drawdown once <code>Q-02</code> is resolved.
(3) <b>Demotion Gate (<code>D-01..D-04</code>)</b> automatically returns any live entry to paper on a single rolling-window decay, 25% drawdown breach, negative 30-ticket CLV, or calibration drift trigger.
</div>

<h2>All Four Proper-Score Divisions (Singles, Game Parlays, Same-Game Parlays, Player Prop Combos)</h2>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">Entry ID</th><th scope="col">Division</th><th scope="col">Role</th><th scope="col">Frozen Registration</th><th scope="col">Sample (Prospective / Escrow / Ref)</th><th scope="col">Mean Brier</th><th scope="col">BSS vs Coin</th><th scope="col">Cluster 95% LB</th><th scope="col">Sidak M={mult['total_trials_M']} LB</th><th scope="col">Signal Track (Stake-Free)</th><th scope="col">Staking / CLV Track</th><th scope="col">Stage-1 → Stage-2 Gate</th><th scope="col">Demotion State</th><th scope="col">Two-Sided Mind-Change Rule</th><th scope="col">Source</th></tr></thead>
<tbody>
{"".join(trs)}
</tbody>
</table>
</div>
"""


def _render_joint_gate() -> str:
    rows = _read_csv(DATA_SKILL / "official_correlations_with_n.csv")
    trs = []
    for r in rows:
        trs.append(
            f"<tr><td><code>{_esc(r['corr_id'])}</code></td>"
            f"<td><b>{_esc(r['metric_pair'])}</b></td>"
            f"<td>{_esc(r['official_corpus'])}</td>"
            f"<td><b>{_esc(r['n'])}</b></td>"
            f"<td><code>{_esc(r['pearson_r'])}</code></td>"
            f"<td><code>[{_esc(r['fisher_ci95_low'])}, {_esc(r['fisher_ci95_high'])}]</code></td>"
            f"<td><code>{_esc(r['t_stat'])}</code></td>"
            f"<td><code>{_esc(r['p_value_two_sided'])}</code></td>"
            f"<td><code>{_esc(r['sgp_joint_prob_at_50_50'])}</code></td>"
            f"<td><code>{_esc(r['frechet_bounds_at_50_50'])}</code></td>"
            f"<td>{_esc(r['parlay_gate_implication'])}</td>"
            f'<td><a class="src-link" href="{_esc(r["source_url"])}">Official NFL</a></td></tr>'
        )

    gate_rows = [
        ("JEG-01", "Division 2 — Multi-Game Parlays", "LOCKED",
         "Compound bookmaker hold escalates from 4.55% (1 leg at -110) to 20.75% (5 legs, ~4.56x single-leg hold), while slate-wide weather and model-calibration errors correlate across Sunday windows.",
         "Pre-registered slate-cluster joint calibration + explicit operator push/postponement leg-reduction rules.",
         "https://www.nfl.com/schedules/2026/by-week/week-11"),
        ("JEG-02", "Division 3 — Same-Game Parlays (SGP)", "LOCKED",
         "For two 50% legs with correlation rho = +0.30, true joint probability is 0.3250 (not 0.2500); conversely negative dependence (CORR-04 r = -0.1405 on n = 150) depresses joint hit rates below naive marginals while SGP pricing embeds extra hold.",
         "Validated bivariate (margin, total) copula on >=200 official finals + operator SGP tie/push void table.",
         "https://www.nfl.com/schedules/2026/by-week/week-10"),
        ("JEG-03", "Division 4 — Player Prop Combos", "LOCKED",
         "Player target/rush shares compete within a fixed team play budget and shift discontinuously on injuries/inactives; neither official snap-share feeds (Q-04) nor prop price snapshots (Q-02) are authorized yet.",
         "Authorized snap/route participation feed + timestamped prop quotes + book DNP/injury-reboot rules.",
         "https://www.nfl.com/injuries/league/2026/reg10"),
    ]
    g_trs = [
        f"<tr><td><code>{_esc(gid)}</code></td><td>{_esc(div)}</td><td>{_pill(st, 'alert')}</td>"
        f"<td>{_esc(why)}</td><td>{_esc(req)}</td>"
        f'<td><a class="src-link" href="{_esc(surl)}">Official NFL</a></td></tr>'
        for gid, div, st, why, req, surl in gate_rows
    ]

    return f"""
<div class="formula">
<b>Joint-Probability Law:</b> For binary legs <code>A, B</code> with marginals <code>p_A, p_B</code> and phi correlation <code>rho</code>,
<code>P(A and B) = p_A * p_B + rho * sqrt(p_A*(1-p_A)*p_B*(1-p_B))</code>, bounded by Fréchet–Hoeffding limits <code>[max(0, p_A + p_B - 1), min(p_A, p_B)]</code>. Multiplying marginal probabilities is rejected across all combo divisions.
</div>

<h2>Joint-Evidence Gate Status Across Combo Divisions</h2>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">Gate ID</th><th scope="col">Division</th><th scope="col">Gate Status</th><th scope="col">Why Marginal Multiplication Fails</th><th scope="col">Required Evidence to Unlock</th><th scope="col">Source</th></tr></thead>
<tbody>
{"".join(g_trs)}
</tbody>
</table>
</div>

<h2>Official-Only Correlations Published with Exact Sample Size <code>n</code></h2>
<p>Every correlation below is computed strictly from verified official 2026 NFL game finals (<code>n = 150</code>, Weeks 1–10) or verified post-Week-10 official NFL league standings (<code>n = 32</code> clubs). Zero third-party market or fantasy numbers enter this table.</p>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">ID</th><th scope="col">Official Metric Pair</th><th scope="col">Official Corpus</th><th scope="col">n</th><th scope="col">Pearson r</th><th scope="col">Fisher 95% CI</th><th scope="col">t-Stat</th><th scope="col">p-Value</th><th scope="col">Implied Joint P at (0.50, 0.50)</th><th scope="col">Fréchet Bounds</th><th scope="col">Origination &amp; Parlay Implication</th><th scope="col">Source</th></tr></thead>
<tbody>
{"".join(trs)}
</tbody>
</table>
</div>
"""


def _render_roster_turnover(roster_sum: dict) -> str:
    stale = _read_csv(DATA_ROSTER / "stale_depth_and_turnover_audit.csv")
    starters = _read_csv(DATA_ROSTER / "announced_starters_evidence.csv")
    trades = _read_csv(DATA_ROSTER / "official_trades_nov_2026.csv")
    reserves = _read_csv(DATA_ROSTER / "official_reserve_list_2026_oct_nov.csv")
    clubs = _read_csv(DATA_ROSTER / "club_availability_summary_w10_w11.csv")
    inactives = _read_csv(DATA_ROSTER / "official_inactives_2026_week10.csv")
    c = roster_sum["counts"]

    stale_trs = [
        f"<tr><td><code>{_esc(r['audit_id'])}</code></td><td><b>{_esc(r['club'])}</b></td>"
        f"<td>{_esc(r['unit'])} {_esc(r['position'])} (d={_cell(r['depth_rank'], 'n/a')})</td>"
        f"<td>{_cell(r['player_printed'], 'blank — image chart')}</td>"
        f"<td>{_pill(r['issue_class'], 'warn')}</td>"
        f"<td>{_cell(r['roster_event_date'], 'club RES')} · {_esc(r['official_roster_state'])}</td>"
        f"<td>{_esc(r['finding'])}</td>"
        f'<td><a class="src-link" href="{_esc(r["official_event_source_url"])}">NFL tx/news</a> · <a class="src-link" href="{_esc(r["depth_chart_source_url"])}">Club chart</a></td></tr>'
        for r in stale
    ]

    starter_trs = [
        f"<tr><td><b>{_esc(r['club'])}</b></td><td>W{_esc(r['week'])} (<code>{_esc(r['game_id'])}</code>)</td>"
        f"<td><b>{_esc(r['announced_starter'])}</b> ({_esc(r['position'])})</td>"
        f"<td>{_esc(r['displaced_player'])} — {_esc(r['displaced_reason'])}</td>"
        f"<td>{_esc(r['announcement_date'])}</td>"
        f"<td>{_esc(r['evidence_summary'])}</td>"
        f'<td><a class="src-link" href="{_esc(r["source_url"])}">NFL.com announcement</a></td></tr>'
        for r in starters
    ]

    trade_trs = [
        f"<tr><td>{_esc(r['trade_date'])}</td><td><b>{_esc(r['from_club'])} → {_esc(r['to_club'])}</b></td>"
        f'<td><a href="{_esc(r["player_url"])}">{_esc(r["player"])}</a></td>'
        f"<td>{_cell(r['tx_printed_position'], 'blank on NFL.com')}</td>"
        f"<td>{_cell(r['verified_position'], 'unverified')}</td>"
        f"<td>{_esc(r['turnover_impact_note'])}</td>"
        f'<td><a class="src-link" href="{_esc(r["source_url"])}">NFL Trades</a></td></tr>'
        for r in trades
    ]

    res_trs = [
        f"<tr><td><b>{_esc(r['club'])}</b></td><td>{_cell(r['transaction_date'], 'prior / roster RES')}</td>"
        f'<td><a href="{_esc(r["player_url"])}">{_esc(r["player"])}</a></td>'
        f"<td>{_cell(r['tx_printed_position'], 'blank on NFL.com')}</td>"
        f"<td>{_cell(r['roster_verified_position'], 'unverified')}</td>"
        f"<td>{_esc(r['reserve_status'])}</td>"
        f"<td><code>{_esc(r['evidence_type'])}</code></td>"
        f"<td>{_esc(r['audit_note'])}</td>"
        f'<td><a class="src-link" href="{_esc(r["source_url"])}">Official NFL</a></td></tr>'
        for r in reserves
    ]

    club_trs = [
        f"<tr><td><b>{_esc(r['club'])}</b></td><td>{_esc(r['team_name'])}</td>"
        f"<td><code>{_esc(r['w10_slate_state'])}</code></td>"
        f"<td>{_cell(r['w10_injury_report_rows'], 'BYE')}</td>"
        f"<td>{_cell(r['w10_ruled_out_or_doubtful'], 'BYE')}</td>"
        f"<td>{_cell(r['w10_questionable'], 'BYE')}</td>"
        f"<td>{_cell(r['club_chart_starters_out'], 'blank — HOU image / BYE')}</td>"
        f"<td>{_cell(r['named_2nd_string_replacements'], 'none / blank')}</td>"
        f"<td>{_cell(r['w10_official_inactives_count'], 'BYE')}</td>"
        f"<td>{_esc(r['verified_oct_nov_reserve_count'])}</td>"
        f"<td>{_esc(r['depth_source_status'])}</td>"
        f'<td><a class="src-link" href="{_esc(r["team_source_url"])}">Club / NFL</a> · <a class="src-link" href="{_esc(r["injury_source_url"])}">W10 Report</a></td></tr>'
        for r in clubs
    ]

    inact_trs = [
        f"<tr><td><code>{_esc(r['game_id'])}</code></td><td><b>{_esc(r['club'])}</b></td>"
        f"<td>{_cell(r['printed_position'], 'unprinted')}</td>"
        f"<td>{_esc(r['player'])}</td>"
        f"<td>{_cell(r['designation_note'], 'standard inactive')}</td>"
        f"<td>{_cell(r['snap_count'], 'blank — Q-04')}</td>"
        f'<td><a class="src-link" href="{_esc(r["source_url"])}">NFL Inactives</a> · <a class="src-link" href="{_esc(r["game_center_url"])}">Game Center</a></td></tr>'
        for r in inactives
    ]

    return f"""
<div class="note">
<b>Why Four Official Roster Tables Must Be Joined Before Pricing Any Line:</b>
(1) <b><code>not listed != available</code></b>: Malik Willis (<code>MIA</code>), Lamar Jackson (<code>BAL</code>), Tyler Huntley (<code>BAL</code>), Puka Nacua (<code>LA</code>), and Terry McLaurin (<code>WAS</code>) are absent from weekly injury reports when on <code>Reserve/Injured</code>.
(2) <b>NFL.com's monthly Reserve List table truncates at 25 rows</b> (stopping at <code>11/10</code>) and prints an empty <code>Position</code> cell on every row, so club <code>nfl.com/teams/&lt;club&gt;/roster</code> <code>RES</code> sections must be swept alongside it.
(3) <b>Unofficial club depth charts lag official transactions</b>: our deterministic join caught <b>{c['stale_depth_and_turnover_flags']}</b> stale/turnover items on live 2026-11-19 club charts, including <code>Aidan Hutchinson</code> (DET EDGE1, IR 11/18), <code>Jaylon Carlies</code> (IND WLB1, IR 11/17 ahead of tonight's TNF game), <code>Mason McCormick</code> (PIT LG1, IR 11/18), <code>Puka Nacua</code> (LA WR1, IR 11/12), and <code>Daiyan Henley</code> (still LAC LB1 nine days after his 11/10 trade to DEN).
</div>

<h2>1. Stale Club Depth-Chart &amp; Roster-Turnover Versioning Audit ({len(stale)} Verified Findings)</h2>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">ID</th><th scope="col">Club</th><th scope="col">Slot &amp; Depth</th><th scope="col">Player Printed</th><th scope="col">Issue Class</th><th scope="col">Official Event</th><th scope="col">Verification Finding</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(stale_trs)}</tbody>
</table>
</div>

<h2>2. Announced-Starter Evidence Field ({len(starters)} Dated Official Announcements — Never Inferred)</h2>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">Club</th><th scope="col">Fixture</th><th scope="col">Announced Starter</th><th scope="col">Displaced Starter &amp; Reason</th><th scope="col">Date</th><th scope="col">Official Evidence</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(starter_trs)}</tbody>
</table>
</div>

<h2>3. Per-Club 32-Team Availability, Starters Out, Named Replacements &amp; Inactive Summary</h2>
<input type="search" data-filter="club-avail-tbl" placeholder="Filter 32 clubs (e.g. DET, IND, BAL, HOU)...">
<div class="tablewrap" tabindex="0">
<table class="wide" id="club-avail-tbl" data-table>
<thead><tr><th scope="col">Club</th><th scope="col">Team</th><th scope="col">W10 State</th><th scope="col">W10 Report Rows</th><th scope="col">Out / Doubtful</th><th scope="col">Questionable</th><th scope="col">Club-Chart Starters Out</th><th scope="col">Named 2nd-String Replacements</th><th scope="col">W10 Inactives</th><th scope="col">Verified Oct–Nov Reserve</th><th scope="col">Depth Source Status</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(club_trs)}</tbody>
</table>
</div>

<h2>4. Official November 2026 NFL Trades Log (All {len(trades)} League-Published Trades)</h2>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">Date</th><th scope="col">From → To</th><th scope="col">Player</th><th scope="col">NFL.com Tx Pos</th><th scope="col">Roster-Verified Pos</th><th scope="col">Lineup &amp; Depth Versioning Impact</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(trade_trs)}</tbody>
</table>
</div>

<h2>5. Official Reserve/IR Sweep ({len(reserves)} Verified Oct–Nov Transaction &amp; Club-Roster RES Rows)</h2>
<input type="search" data-filter="reserve-tbl" placeholder="Filter Reserve/IR players or clubs...">
<div class="tablewrap" tabindex="0">
<table class="wide" id="reserve-tbl" data-table>
<thead><tr><th scope="col">Club</th><th scope="col">Date</th><th scope="col">Player</th><th scope="col">NFL.com Tx Pos</th><th scope="col">Verified Pos</th><th scope="col">Official Status</th><th scope="col">Evidence Kind</th><th scope="col">Audit Note</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(res_trs)}</tbody>
</table>
</div>

<h2>6. Official 2026 Week 10 90-Minute Inactive Lists (All 14 Games, 28 Active Clubs, {len(inactives)} Players)</h2>
<p>Transcribed verbatim from the three official 2026 NFL.com Week 10 inactive releases (Thursday Night, Sunday 12-game slate, Monday Night). Note: the undated slug <code>nfl-week-10-inactives-players-ruled-out-for-sunday-s-12-games</code> resolves to a 2025 article and was rejected; the verified 2026 Sunday URL ends in <code>-sunday-2026-season</code>. Snap counts remain blank per Game Book reuse/coverage gates.</p>
<input type="search" data-filter="inactives-tbl" placeholder="Search 172 official Week 10 inactives by player, club, or game...">
<div class="tablewrap" tabindex="0">
<table class="wide" id="inactives-tbl" data-table>
<thead><tr><th scope="col">Game ID</th><th scope="col">Club</th><th scope="col">Pos</th><th scope="col">Player</th><th scope="col">Designation Note</th><th scope="col">Snap Count</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(inact_trs)}</tbody>
</table>
</div>
"""


def _render_weather_venues(weather_sum: dict) -> str:
    rows = _read_csv(DATA_WEATHER / "week11_stadium_nws_overlay.csv")
    wc = weather_sum["counts"]
    trs = []
    for r in rows:
        flag = r["overlay_risk_flag"]
        tone = "alert" if "HIGH_PRECIP" in flag else ("warn" if ("PRECIP" in flag or "RAIN" in flag or "OUTSIDE" in flag) else "ok")
        src_links = f'<a class="src-link" href="{_esc(r["game_center_url"])}">NFL Game Center</a>'
        if r["nws_source_url"]:
            src_links += f' · <a class="src-link" href="{_esc(r["nws_source_url"])}">NWS Grid</a>'
        trs.append(
            f"<tr><td><b>{_esc(r['away'])} @ {_esc(r['home'])}</b></td>"
            f"<td>{_esc(r['kickoff_et'])}</td>"
            f"<td>{_esc(r['game_center_stadium'])} ({_esc(r['game_center_location'])})</td>"
            f"<td>{_cell(r['official_90min_roof_status'], 'blank — pre-90m')}</td>"
            f"<td>{_cell(r['official_playing_surface'], 'blank — not on GC')}</td>"
            f"<td>{_cell(r['nws_grid_id'], 'non-US')} ({_cell(r['nws_elevation_m'], 'n/a')} m)</td>"
            f"<td>{_cell(r['nws_forecast_window'], 'outside NWS')}</td>"
            f"<td>{_cell(r['nws_temp_f'], 'blank')}°F</td>"
            f"<td>{_cell(r['nws_wind'], 'blank')}</td>"
            f"<td><b>{_cell(r['nws_precip_pct'], 'blank')}%</b></td>"
            f"<td>{_cell(r['nws_short_forecast'], 'blank')}</td>"
            f"<td>{_pill(flag.split(' (')[0], tone)}<br><span class=\"small muted\">{_esc(flag)}</span></td>"
            f"<td>{src_links}</td></tr>"
        )

    return f"""
<div class="note">
<b>Week 11 Weather &amp; Roof Coupling Summary (Fetched 2026-11-19 06:56–07:20 UTC):</b>
<b>{wc['us_nws_covered_fixtures']} of 13</b> Week 11 venues are matched to official US National Weather Service (<code>api.weather.gov</code>) forecast grids; <b>1 international fixture</b> (<code>MIN @ SF</code> at Estadio Banorte, Mexico City) lies outside US NWS jurisdiction and is kept blank rather than filled from unverified third-party weather sites. Pre-kickoff NFL Game Center pages omit roof and surface metadata (<code>0/13</code> confirmed pre-90-min); official roof open/closed designations are declared 90 minutes before kickoff and recorded post-game in official NFL Game Books (e.g., Week 10 Munich Game Book PDF confirmed <code>Open Stadium on Natural Grass</code>).
<br><b>Primary Week 11 Slate Alerts:</b> <code>NO @ CHI</code> (Soldier Field, Sun 1:00 PM ET) projects <b>80% PoP Rain Showers &amp; 15 mph WSW wind</b>; <code>JAX @ NYG</code> (MetLife, Sun 4:25 PM ET) escalates from <b>30% to 65% PoP</b> into Sunday evening; <code>PIT @ PHI</code> (Lincoln Financial Field) carries <b>45% PoP</b>; <code>LV @ DEN</code> sits at <b>1,584 m (5,197 ft)</b> NWS grid elevation.
</div>

<h2>Week 11 Official Game Center Venues + Official NWS Wind &amp; Precipitation Overlay (All 13 Fixtures)</h2>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">Matchup</th><th scope="col">Kickoff (ET)</th><th scope="col">Official Game Center Venue</th><th scope="col">90-Min Roof</th><th scope="col">Surface</th><th scope="col">NWS Grid (Elev)</th><th scope="col">NWS Window</th><th scope="col">Temp</th><th scope="col">Wind</th><th scope="col">PoP</th><th scope="col">NWS Forecast</th><th scope="col">Totals / Passing Overlay Flag</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(trs)}</tbody>
</table>
</div>
"""


def _render_weekly_diff(skill_sum: dict) -> str:
    rows = _read_csv(DATA_SKILL / "weekly_what_changed_w9_w10_w11.csv")
    meta = skill_sum["weekly_what_changed"]
    trs = []
    for r in rows:
        rc = r["rank_change"]
        tone = "ok" if rc.startswith("+") else ("alert" if rc.startswith("-") else "muted-pill")
        trs.append(
            f"<tr><td><b>{_esc(r['rank_w10'])}</b> (was {_esc(r['rank_w9'])})</td>"
            f"<td>{_pill(rc, tone)}</td>"
            f"<td><b>{_esc(r['club'])}</b> — {_esc(r['team_name'])}</td>"
            f"<td>{_esc(r['w10_game_result'])}</td>"
            f"<td><code>{_esc(r['record_w9'])} → {_esc(r['record_w10'])}</code></td>"
            f"<td><code>{_esc(r['shrunk_rating_w9'])} → {_esc(r['shrunk_rating_w10'])}</code></td>"
            f"<td><b><code>{_esc(r['rating_delta_pts'])}</code></b></td>"
            f"<td>{_cell(r['w10_inactives_count'], 'BYE')}</td>"
            f"<td>{_esc(r['w10_w11_availability_and_roster_diff'])}</td>"
            f'<td><a class="src-link" href="{_esc(r["source_url"])}">Official club</a></td></tr>'
        )

    return f"""
<div class="note">
<b>Weekly Diff Summary (Week 9 Official Snapshot 2026-11-14 → Post-Week-10 Official Standings 2026-11-18 → Week 11 Pre-Kickoff Turnover):</b>
Largest league-rank climb: <b>{meta['largest_rank_climb']['club']} (+{meta['largest_rank_climb']['spots_gained']} spots)</b> · Largest rank drop: <b>{meta['largest_rank_drop']['club']} ({meta['largest_rank_drop']['spots_lost']} spots on W10 bye tiebreakers)</b>. Shrunk margin ratings use the frozen <code>PR-01 / PR-04</code> estimator <code>net_pts / (games_played + 2.0)</code> so rating deltas reconcile directly with the Week 11 escrow lines.
</div>

<input type="search" data-filter="weekly-diff-tbl" placeholder="Filter 32 clubs by team, trade, IR player, or starter...">
<div class="tablewrap" tabindex="0">
<table class="wide" id="weekly-diff-tbl" data-table>
<thead><tr><th scope="col">W10 Rank (W9)</th><th scope="col">Rank Δ</th><th scope="col">Club</th><th scope="col">Week 10 Final</th><th scope="col">Record W9 → W10</th><th scope="col">Shrunk Rating W9 → W10</th><th scope="col">Rating Δ (Pts)</th><th scope="col">W10 Inactives</th><th scope="col">Verified W10–W11 Availability, Starter &amp; Trade Changes</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(trs)}</tbody>
</table>
</div>
"""


def _render_decisions_flags() -> str:
    suggestions = [
        ("OD-S01", "Pre-Origination 4-Table Roster Gate",
         "Path A: Join NFL.com monthly Reserve/Trades + 32 club roster RES pages + 90-min inactives before pricing (Recommended) | Path B: Rely on weekly injury report + club HTML depth charts only",
         "Proposed — awaiting owner choice (nothing auto-mutated in existing models)",
         "Eliminates silent availability errors (Willis, Jackson, Huntley) and catches the 20 stale club depth rows found on 2026-11-19.",
         "https://www.nfl.com/transactions/league/reserve-list/2026/11"),
        ("OD-S02", "90-Minute Pre-Kickoff Roof + Inactive Capture Trigger",
         "Path A: Schedule automated fetch at T-85 min per kickoff slot for official inactives + roof status (Recommended) | Path B: Daily static cron only",
         "Proposed — awaiting owner choice",
         "Resolves blank pre-kickoff roof designations (HOU, DAL, DET, LAC) simultaneously with 90-minute official 53-man inactive lists.",
         "https://www.nfl.com/schedules/2026/by-week/week-11"),
        ("OD-S03", "Vig-Free Consensus Benchmark Policy Once Q-02 Clears",
         "Path A: Power de-vigging as primary with Multiplicative sensitivity column (Recommended) | Path B: Multiplicative only | Path C: Raw vigged break-even only",
         "Proposed — awaiting owner choice & Q-02 price feed",
         "Accounts for favorite-longshot asymmetry in moneyline tails while keeping operator vig tax explicitly separated from origination alpha.",
         "https://www.nfl.com/schedules/2026/by-week/week-10"),
        ("OD-S04", "International Fixture Weather & Neutral-Site Home-Edge Rule",
         "Path A: Zero out H=1.6 home edge on neutral international venues + ingest WMO national met service (SMN Mexico / DWD Germany) | Path B: Keep H=1.6 constant until season end",
         "Proposed — awaiting owner choice for PR-05+",
         "Fixes PR-04's documented Mexico City neutral-site limitation (MIN @ SF) and fills the non-US weather coverage gap.",
         "https://www.nfl.com/games/vikings-at-49ers-2026-reg-11"),
    ]

    qia_rows = [
        ("OD-Q01 (links Q-02)", "Authorized timestamped opening & closing market prices for 2026",
         "HOLD: 52 pre-kickoff W11 fair lines in PR-04 + 14 W10 mirror quotes. MISSING: Licensed timestamped sportsbook/exchange feed.",
         "",  # Unanswered — owner decision
         "Select & license an official/authorized odds feed recording open + close timestamps per market.",
         "https://www.nfl.com/schedules/2026/by-week/week-11"),
        ("OD-Q02 (links Q-04)", "Authorized per-player offensive/defensive snap counts",
         "HOLD: 172 official W10 inactives + 31/32 club HTML depth charts + 7 Game Book PDF links. MISSING: Rights-cleared per-player snap counts.",
         "",
         "Obtain written NFL Game Book reuse permission or license an official participation table (e.g., NFL Next Gen Stats / PFR / TruMedia).",
         "https://static.www.nfl.com/image/upload/v1794764592/gamecenter/ab582c2f-4feb-11f1-abca-2c54536568a9.pdf"),
        ("OD-Q03", "Houston Texans structured depth-chart source",
         "HOLD: Official Houston Texans roster + W10 inactives + 11/17 Azeez Al-Shaair IR transaction. MISSING: Machine-parsable Texans depth table (club publishes image).",
         "",
         "Wait for snap-count participation proxy once Q-04 clears; never transcribe Texans depth-chart images by eye.",
         "https://www.houstontexans.com/team/depth-chart"),
        ("OD-Q04", "Pre-kickoff stadium roof open/closed feed",
         "HOLD: 12/13 Week 11 official NWS grids + post-game Game Book roof/surface confirmation. MISSING: Structured pre-kickoff roof-status endpoint on nfl.com.",
         "",
         "Capture club roof declarations at the 90-minute inactive window and log immutable timestamps.",
         "https://www.nfl.com/games/colts-at-texans-2026-reg-11"),
    ]

    flags = [
        ("OD-F01", "NFL.com monthly Reserve List truncates at 25 rows & omits Position",
         "https://www.nfl.com/transactions/league/reserve-list/2026/11 stops at 11/10 (25 rows) and prints a blank Position cell on every row, omitting Malik Willis (MIA QB) and earlier BAL QBs on IR.",
         "Joined club roster RES tables; left tx_printed_position blank verbatim.",
         "https://www.nfl.com/transactions/league/reserve-list/2026/11"),
        ("OD-F02", "15 stale player listings on live 2026-11-19 club depth charts",
         "Club depth charts still list Aidan Hutchinson (DET EDGE1, IR 11/18), Jaylon Carlies (IND WLB1, IR 11/17), Mason McCormick (PIT LG1, IR 11/18), Puka Nacua (LA WR1, IR 11/12), and Daiyan Henley (LAC LB1, traded to DEN 11/10).",
         "Flagged in stale_depth_and_turnover_audit.csv; never silently edited club transcriptions.",
         "https://www.detroitlions.com/team/depth-chart"),
        ("OD-F03", "Undated NFL.com Week 10 Sunday inactives slug resolves to 2025",
         "https://www.nfl.com/news/nfl-week-10-inactives-players-ruled-out-for-sunday-s-12-games contains 2025-reg-10 game links; the genuine 2026 Week 10 Sunday inactives URL ends in -sunday-2026-season.",
         "Rejected 2025 slug; verified all 12 Sunday 2026 games from -sunday-2026-season.",
         "https://www.nfl.com/news/nfl-week-10-inactives-players-ruled-out-sunday-2026-season"),
        ("OD-F04", "Lions Week 10 Out vs 53-man Sunday Inactive split (Kerby Joseph)",
         "Cade Mays and D.J. Reed were both Out on W10 report and deactivated on Sunday's Munich inactive list; Kerby Joseph (out since W6 2025, expected W11 debut vs TB) was Out on the injury report prior to 53-man activation.",
         "Documented exact roster-state split rather than assuming missing inactive row meant active play.",
         "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-tuesday-nov-17"),
        ("OD-F05", "Colts W11 depth chart went stale within 24 hours of publication",
         "Colts published Week 11 unofficial depth chart Mon 11/16 4:17 PM listing Jaylon Carlies at WLB1, then placed Carlies on IR Tue 11/17 ahead of tonight's TNF game at Houston.",
         "Logged as POST_RELEASE_IR_STALENESS proof that depth charts must be versioned against daily transactions.",
         "https://www.colts.com/news/colts-release-unofficial-depth-chart-for-week-11"),
        ("OD-F06", "Official NFL Game Center vs Schedule stadium-name drift (HOU & WAS)",
         "Week 11 Game Centers print RELIANT STADIUM (IND@HOU) and NORTHWEST STADIUM (CIN@WAS), whereas Week 11 schedule hotel links print NRG Stadium and FedEx Field.",
         "Preserved verbatim Game Center strings and flagged both naming discrepancies.",
         "https://www.nfl.com/games/colts-at-texans-2026-reg-11"),
        ("OD-F07", "Mexico City Week 11 fixture outside US NWS coverage + neutral-site H=1.6",
         "vikings-at-49ers (Estadio Banorte, Mexico City) has no US NWS gridpoint and carries PR-04's frozen +1.6 home-field constant despite neutral international venue.",
         "Left all NWS weather cells blank and flagged neutral-site prior for PR-05 review.",
         "https://www.nfl.com/games/vikings-at-49ers-2026-reg-11"),
        ("OD-F08", "Cross-file club abbreviation drift (AZ/ARI and LA/LAR)",
         "standings.tsv prints AZ & LAR, official_standings_2026_11_18.tsv prints AZ & LA, and verified_results_2026_n2.csv prints ARI & LA.",
         "Normalized deterministically in join code without altering frozen upstream files.",
         "https://www.nfl.com/standings/league/2026/REG"),
        ("OD-F09", "Week 12 NFL flex schedule changes announced Nov 17",
         "NFL.com Nov 17 roundup confirmed Browns vs. Raiders flexed to Week 12 SNF (8:20 PM ET NBC) and Jaguars vs. Titans flexed to 1:00 PM ET FOX on Nov 29.",
         "Flagged so upcoming Week 12 schedule & rest/broadcast context captures refresh kickoff slots.",
         "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-tuesday-nov-17"),
    ]

    s_trs = [
        f"<tr><td><code>{_esc(sid)}</code></td><td><b>{_esc(title)}</b></td><td>{_esc(paths)}</td>"
        f"<td>{_pill(st, 'warn')}</td><td>{_esc(imp)}</td>"
        f'<td><a class="src-link" href="{_esc(surl)}">Official source</a></td></tr>'
        for sid, title, paths, st, imp, surl in suggestions
    ]
    q_trs = [
        f"<tr><td><code>{_esc(qid)}</code></td><td><b>{_esc(topic)}</b></td><td>{_esc(hold)}</td>"
        f"<td>{_cell(ans, 'blank — awaiting owner decision')}</td><td>{_esc(disc)}</td>"
        f'<td><a class="src-link" href="{_esc(surl)}">Official source</a></td></tr>'
        for qid, topic, hold, ans, disc, surl in qia_rows
    ]
    f_trs = [
        f"<tr><td><code>{_esc(fid)}</code></td><td><b>{_esc(title)}</b></td><td>{_esc(det)}</td>"
        f"<td>{_esc(act)}</td>"
        f'<td><a class="src-link" href="{_esc(surl)}">Official source</a></td></tr>'
        for fid, title, det, act, surl in flags
    ]

    return f"""
<div class="note">
<b>Non-Blocking Review &amp; Decision Discipline:</b> None of the suggestions below have been silently enacted into frozen registrations, and every unverified cell across this desk remains blank. For the repository-wide reconciled 18-question / 18-path governance board, see <a href="../suggestions/index.html">Decision Center (<code>/suggestions/</code>)</a> and <a href="../pages/flagged.html">Main Flagged Register</a>.
</div>

<h2>1. Suggestions Review Board (Choose Implementation Path Before Any Rule Change)</h2>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">ID</th><th scope="col">Topic</th><th scope="col">Candidate Paths to Review</th><th scope="col">Decision State</th><th scope="col">Expected Impact</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(s_trs)}</tbody>
</table>
</div>

<h2>2. Open Questions, Information Held vs. Missing &amp; Discovery Actions</h2>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">Question ID</th><th scope="col">Blocking Question</th><th scope="col">Information Held vs. Not Held</th><th scope="col">Owner Answer</th><th scope="col">Discovery / Clearing Action</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(q_trs)}</tbody>
</table>
</div>

<h2 id="flagged">3. Flagged for Review — Source Irregularities, Stale Upstream Data &amp; Deliberate Blanks</h2>
<div class="tablewrap" tabindex="0">
<table class="wide" data-table>
<thead><tr><th scope="col">Flag ID</th><th scope="col">Irregularity</th><th scope="col">Verified Evidence</th><th scope="col">Safe Handling Applied</th><th scope="col">Source</th></tr></thead>
<tbody>{"".join(f_trs)}</tbody>
</table>
</div>
"""


def build_all() -> dict[str, str]:
    roster_sum = json.loads((DATA_ROSTER / "roster_audit_summary.json").read_text(encoding="utf-8"))
    weather_sum = json.loads((DATA_WEATHER / "week11_stadium_nws_overlay.json").read_text(encoding="utf-8"))
    skill_sum = json.loads((DATA_SKILL / "skill_desk_summary.json").read_text(encoding="utf-8"))

    return {
        "index.html": _layout(
            "index.html",
            "Origination & Skill Desk",
            "OD-01 · Executive Overview & Decision Readiness",
            "Vig-free consensus decomposition, two-stage proper-score skill leaderboard, official reserve/trades/inactives verification, stadium NWS weather overlay, and 32-club weekly diff.",
            _render_index(roster_sum, weather_sum, skill_sum),
        ),
        "lines-vig.html": _layout(
            "lines-vig.html",
            "Originated Lines & Vig-Free Decomposition",
            "OD-02 · Side → Dual Totals → Moneyline & Vig Removal",
            "Separating bookmaker overround from vig-free origination disagreement across prospective Week 11 escrow and Week 10 mirror research.",
            _render_lines_vig(skill_sum),
        ),
        "leaderboard.html": _layout(
            "leaderboard.html",
            "Two-Stage Proper-Score Skill Leaderboard",
            "OD-03 · Stage 1 Brier Skill → Stage 2 Prospective CLV Escrow",
            "Four proper-score divisions with game-cluster bootstrap bounds, M=31 trial multiplicity adjustment, control baselines, signal-vs-staking split, and demotion gates.",
            _render_leaderboard(skill_sum),
        ),
        "joint-gate.html": _layout(
            "joint-gate.html",
            "Joint-Evidence Gate & Official Correlations",
            "OD-04 · Parlay / Combo Dependence & Official-Only r with n",
            "Why marginal probability multiplication is barred across multi-leg parlays, SGPs, and player prop combos, backed by official 2026 NFL correlations.",
            _render_joint_gate(),
        ),
        "roster-turnover.html": _layout(
            "roster-turnover.html",
            "Reserve/IR Sweep, Trades, Starters & Inactives",
            "OD-05 · Four-Table Official Availability & Turnover Audit",
            "Official NFL Reserve/IR and November trades joined against club depth charts, dated starter announcements, and all 172 Week 10 game-day inactives.",
            _render_roster_turnover(roster_sum),
        ),
        "weather-venues.html": _layout(
            "weather-venues.html",
            "Stadium Roof/Surface & Official NWS Weather Overlay",
            "OD-06 · Game Center Venues + US National Weather Service Grids",
            "Coupling verified Week 11 NFL Game Center stadium strings with live api.weather.gov wind/precipitation grids and 90-minute roof-designation gates.",
            _render_weather_venues(weather_sum),
        ),
        "weekly-diff.html": _layout(
            "weekly-diff.html",
            "Weekly What-Changed Diff (All 32 Clubs)",
            "OD-07 · Week 9 → Post-Week-10 → Week 11 Pre-Kickoff",
            "One consolidated 32-club table tracking league rank movement, shrunk margin-rating change, Week 10 inactive counts, and November roster turnover.",
            _render_weekly_diff(skill_sum),
        ),
        "decisions-flags.html": _layout(
            "decisions-flags.html",
            "Suggestions, Open Questions & Flagged for Review",
            "OD-08 · Non-Blocking Irregularities & Owner Path Choices",
            "Candidate implementation paths, missing-information discovery actions, and every official-source irregularity uncovered during the 2026-11-19 audit.",
            _render_decisions_flags(),
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    files = build_all()
    if args.check:
        diffs = []
        for name, content in sorted(files.items()):
            p = OUT_DIR / name
            if not p.exists():
                diffs.append(f"missing {p.relative_to(ROOT)}")
            elif p.read_text(encoding="utf-8") != content:
                diffs.append(f"stale {p.relative_to(ROOT)}")
        if diffs:
            print("FAIL desk site check:", "; ".join(diffs))
            return 1
        print(f"OK: {len(files)} HTML pages verified up to date in {OUT_DIR.relative_to(ROOT)}")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(files.items()):
        (OUT_DIR / name).write_text(content, encoding="utf-8")
    print(f"Wrote {len(files)} HTML pages to {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
