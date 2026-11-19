# PROPER-SCORE-PROTOCOL-01 — Vig-Free Decomposition & Two-Stage Skill Leaderboard Specification

**Registered:** `2026-11-19` (UTC) · **Owner:** `arena/48279a7d-x1`
**Verifier:** `python3 tools/origination_desk/build_skill_desk.py --check`

## 1. Non-negotiable evaluation invariants

1. **Zero retrospective backtests on the ranked leaderboard.** Historical and walk-forward backtests exist only to falsify weak specifications and determine the repository-wide multiplicity count $M$. Only pre-registered prospective rules whose commit hash precedes the first eligible kickoff enter Stage-1 or Stage-2 standings.
2. **Origination order is fixed:** `1. Side (point spread) → 2. Total (Estimator A & Estimator B) → 3. Moneyline`. Moneyline probabilities are not originated independently until the spread-to-win-probability calibration clears validation (`F-01` / `Q-M3`).
3. **Proper-score ranking, never raw win rate or season-long ROI.** Stage 1 ranks entries within each division (`singles`, `game_parlays`, `same_game_parlays`, `prop_combos`) by benchmark-relative **Brier Skill Score**:
   $$\mathrm{BSS}(f, b) = 1 - \frac{\overline{\mathrm{BS}}(f)}{\overline{\mathrm{BS}}(b)}, \qquad \mathrm{BS}_i = (y_i - p_i)^2$$
   where ties ($y_i = 0.5$) are retained rather than dropped, and $b$ is the division's always-on control baseline (`CTRL-COIN-50` with $p=0.50$, $\mathrm{BS}=0.25$, paired with `CTRL-HOME-55` at $p=0.55$).
4. **Game-cluster lower bound & trial multiplicity adjustment.** Confidence bounds resample whole **game/week clusters** ($B = 10{,}000$ deterministic draws, seed `20261119`) so correlated markets within a fixture or slate never inflate effective sample size. With $M$ total strategy trials registered across the repository ($M = 28$ in `data/mind_change/register.csv` plus 3 prospective registrations = $31$ total), family-wise error at $\alpha = 0.05$ uses the Šidák threshold:
   $$\alpha_{\mathrm{adj}} = 1 - (1 - \alpha)^{1/M}$$
5. **Joint-Evidence Gate (`JEG-01..03`) for multi-leg parlays, SGPs, and player prop combos.** Multiplying marginal probabilities $p_A \cdot p_B$ is forbidden whenever within-game or slate-cluster correlation $\rho \neq 0$, because:
   $$P(A \cap B) = p_A p_B + \rho \sqrt{p_A(1-p_A)\,p_B(1-p_B)} \in \bigl[\max(0, p_A+p_B-1),\; \min(p_A, p_B)\bigr]$$
   Every parlay/combo division stays locked until both a calibrated joint probability model and explicit operator push/void reduction rules are committed.
6. **Two-Stage Gate (`Stage 1 → Stage 2`) and Demotion Gate (`D-01..D-04`).**
   - **Stage 1 (Proper-Score Qualification):** Pre-kickoff commit hash + $n_{\mathrm{clusters}} \ge 100$ prospective games + multiplicity-adjusted cluster lower bound $\mathrm{BSS}_{\mathrm{LB}} > 0$ vs all control baselines.
   - **Stage 2 (Prospective CLV / ROI Escrow):** Requires an authorized timestamped opening/closing market price feed (`Q-02`), positive vig-free Closing Line Value (CLV), and zero firing demotion triggers (`D-01` signal decay, `D-02` drawdown cap, `D-03` negative 30-ticket CLV, `D-04` calibration drift). Any single `D-01..D-04` trigger immediately demotes a live entry back to paper.

## 2. Vig-Free Consensus vs. Originated Fair-Line Decomposition

Given two-way American market quotes $(A_{\mathrm{away}}, A_{\mathrm{home}})$ with raw implied probabilities $(q_{\mathrm{away}}, q_{\mathrm{home}})$ and overround $\Omega = q_{\mathrm{away}} + q_{\mathrm{home}} - 1 > 0$:

- **Multiplicative (proportional) vig-free consensus:** $p^{\mathrm{mult}}_i = \dfrac{q_i}{q_{\mathrm{away}} + q_{\mathrm{home}}}$
- **Additive (equal-tax) vig-free consensus:** $p^{\mathrm{add}}_i = q_i - \dfrac{\Omega}{2}$
- **Power (favorite-longshot) vig-free consensus:** $p^{\mathrm{pow}}_i = q_i^k$ where $k > 1$ solves $q_{\mathrm{away}}^k + q_{\mathrm{home}}^k = 1$

For originated probability $p^{\mathrm{orig}}_i$:
$$\underbrace{p^{\mathrm{orig}}_i - q_i}_{\text{Net Edge After Vig}} = \underbrace{\bigl(p^{\mathrm{orig}}_i - p^{\mathrm{mult}}_i\bigr)}_{\text{Vig-Free Origination Alpha Candidate}} - \underbrace{\bigl(q_i - p^{\mathrm{mult}}_i\bigr)}_{\text{Operator Vig Tax}}$$
Where no licensed 2026 price feed exists (`Q-02`), $q_i$, $\Omega$, $p^{\mathrm{mult}}_i$, and residual columns remain **strictly blank (`""`)** on prospective boards; third-party mirror decompositions are segregated and labelled `MIRROR_RESEARCH_ONLY`.
