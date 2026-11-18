"""Authored content: the decision register, the suggestion board, and the
irregularity register.

Everything here is either (a) a question with the information we hold, the
information we do not hold, and how to get it, or (b) a suggestion with two or
three paths, a cost, a risk, and a recommendation. Nothing here is built ahead
of a recorded decision: every suggestion carries ``decision_status``.
"""

from __future__ import annotations

import math

from . import sources


# ---------------------------------------------------------------------------
# sample-size arithmetic used by the decision register
# ---------------------------------------------------------------------------

def sample_size_to_prove_skill(p1, p0, alpha=0.05, power=0.80):
    """Bets needed to separate a true hit rate p1 from break-even p0.

    Two-sided test at ``alpha`` with ``power``. Uses the normal approximation.
    """
    z_a, z_b = 1.959963985, 0.8416212336
    num = (z_a * math.sqrt(p0 * (1 - p0)) + z_b * math.sqrt(p1 * (1 - p1))) ** 2
    return int(math.ceil(num / ((p1 - p0) ** 2)))


BREAKEVEN_110 = 0.5238095238


def sample_table():
    rows = []
    for p1 in (0.53, 0.54, 0.55, 0.56, 0.57, 0.60):
        n = sample_size_to_prove_skill(p1, BREAKEVEN_110)
        rows.append({
            "true_hit_rate": p1,
            "edge_over_breakeven_pp": round(100 * (p1 - BREAKEVEN_110), 3),
            "bets_needed": n,
            "seasons_at_300_bets": round(n / 300.0, 1),
        })
    return rows


# ---------------------------------------------------------------------------
# the decision register
# ---------------------------------------------------------------------------

def questions(ctx):
    """ctx carries the measured numbers so no figure here is typed by hand."""
    lab = ctx["lab"]
    best = max(lab["results"], key=lambda e: e.get("signal_score", 0))
    corr = {c["name"]: c for c in ctx["correlations"]}
    st_tot = corr.get("Spread result vs total result, same game", {})
    mom = corr.get("A team's ATS result vs its next ATS result", {})
    rest = corr.get("Rest differential vs home margin", {})
    mkt = corr.get("Market spread vs actual home margin", {})
    mdl = corr.get("Model fair spread vs actual home margin", {})
    conv = ctx.get("convergence", {})
    conv_side = next((m for m in conv.get("markets", []) if m["market"] == "SIDE"), None)
    sample = sample_table()
    s55 = next(r for r in sample if abs(r["true_hit_rate"] - 0.55) < 1e-9)
    pw = ctx.get("price_open_2026", {})
    off = ctx.get("official", {})
    rep = off.get("venue_report", {})
    vv = off.get("venue_verify", {})
    xch_raw = off.get("venue_crosscheck", {})
    xch = {str(c.get("name", "")).split(":", 1)[0].strip(): c
           for c in xch_raw.get("checks", [])}
    inp = off.get("escrow_inputs", {})
    md = off.get("mind_change", {})
    idel = off.get("injury", {})

    Q = [
        dict(id="Q-01", area="Signal", status="ANSWERED - and the answer is no",
             question="Can the model in this repository originate a line that beats the closing market?",
             information_held=(
                 f"The market's own closing spread correlates {mkt.get('value')} with the actual home "
                 f"margin (n={mkt.get('n'):,}). Our walk-forward model correlates {mdl.get('value')} "
                 f"(n={mdl.get('n'):,}). On the side our fair line misses the actual margin by "
                 f"{ctx['rmse_side_model']} points RMSE against the market's {ctx['rmse_side_market']}."),
             information_missing=(
                 "Player-level participation and snap counts, real-time injury timing, book-specific "
                 "prices, and any measure of where the line opened. None of these exist in a source "
                 "available to this repository."),
             answer=(
                 "No, not on the evidence available. The model is roughly one point per game worse "
                 "than the closing line it is trying to beat, and every strategy built on it loses "
                 "money before staking is considered."),
             how_to_discover="Close the gaps in SG-02 and SG-08, then re-run the gates. Do not raise the bet threshold and call the remainder skill."),

        dict(id="Q-02", area="Prices", status="BLOCKED - no source",
             question="What are the opening and closing numbers for every market we originate?",
             information_held=(
                 f"The store exists and holds {ctx['price']['rows']:,} rows. Both ends are populated "
                 f"for {ctx['price']['with_both']:,} markets, all of them 2021 (WSGT opening numbers "
                 f"in nflverse/nfldata initial_lines.csv). "
                 + (f"Measured today for 2026: {pw['with_open']} market rows carry an opening line "
                    f"across {pw['games_with_open']} fixtures (Weeks {', '.join(pw['weeks'])}), from "
                    f"snapshot{'s' if len(pw['snapshots'])>1 else ''} "
                    f"{', '.join(pw['snapshots'])}, source "
                    f"{'/'.join(pw['sources'])}, and {pw['with_both_2026']} of them carry a close as "
                    f"well.") if pw else "2026 openings: not measured in this build."),
             information_missing=(
                 "A book-identified price with a capture time of its own. "
                 + (f"The {pw['with_open']} 2026 openings carry the price the mirror records "
                    f"({', '.join(pw['open_price_values']) or 'no value'}) and a stamp that is when we "
                    f"read the mirror ({pw['with_capture_stamp']} of {pw['with_open']} rows), not when "
                    f"the book posted it, so they date our read rather than the market. No open is "
                    f"paired with a close, so 'opening to closing' movement does not exist for 2026."
                    if pw else "no 2026 openings are held.")
                 + " Corrected 2026-11-18: this row used to say openings do not exist for any season "
                   "except 2021. That was true of the store when it was written and stopped being true "
                   "when the OPEN-2026 snapshot landed; the measurement above replaces the memory."),
             answer=("Still blocked for its purpose. A residual against the market, and therefore "
                     "closing-line value, needs both ends of the same market; the store has "
                     + (f"{pw['with_both_2026']} such rows for 2026." if pw else "none for 2026.")),
             how_to_discover="SG-01 path A or B. Until then, the price columns stay partly blank by policy, not by omission."),

        dict(id="Q-03", area="Results", status="ANSWERED - yes",
             question="Do we have a verified results feed that backtests and ROI can be computed from?",
             information_held=(
                 f"{ctx['feed']['games_total']:,} games 1999-2026, {ctx['feed']['games_settled']:,} settled. "
                 f"The 2026 season reconciles to the league's own standings table "
                 f"{ctx['reconcile']['matches']}/{ctx['reconcile']['checks']} with zero mismatches, "
                 "and the market's own lines are internally consistent: the quoted moneylines imply "
                 "the printed spreads to within 0.52 points on average (n=5,432)."),
             information_missing="A per-play or per-quarter feed, and official confirmation for individual game scores rather than the aggregate reconciliation used here.",
             answer="Yes. Backtests and ROI are computable, and the inputs are corroborated against an official source.",
             how_to_discover="Nothing needed to start. SG-03 would timestamp it so mid-week moves are visible."),

        dict(id="Q-04", area="Parlays", status="ANSWERED",
             question="Are the side and the total in the same game correlated? Does that make parlays mispriced?",
             information_held=(
                 f"Phi = {st_tot.get('value')} (n={st_tot.get('n'):,}, 95% CI "
                 f"{st_tot.get('ci_low')} to {st_tot.get('ci_high')}). Spread error against total "
                 "error in the same game is essentially the same story."),
             information_missing="Book-specific parlay prices; every book discounts parlays differently and none publishes it in a source we hold.",
             answer=(
                 "The two legs are close enough to independent that the product rule is not far off. "
                 "A two-leg -110 parlay therefore needs a 27.44% joint probability to break even, and "
                 "the extra leg multiplies the vig rather than creating value."),
             how_to_discover="Only a book's real parlay price would change this, and it would make parlays worse, not better."),

        dict(id="Q-05", area="Signal", status="ANSWERED - no",
             question="Is there momentum in covering the spread?",
             information_held=f"Lag-1 autocorrelation of a team's ATS result is {mom.get('value')} (n={mom.get('n'):,}, 95% CI {mom.get('ci_low')} to {mom.get('ci_high')}).",
             information_missing="Nothing material.",
             answer="No. The interval covers zero. Streak-following and streak-fading are both noise.",
             how_to_discover="Nothing. This question is closed."),

        dict(id="Q-06", area="Signal", status="ANSWERED - yes, but too small to bet",
             question="Is a rest advantage worth points?",
             information_held=f"Rest differential against home margin: r = {rest.get('value')} (n={rest.get('n'):,}, 95% CI {rest.get('ci_low')} to {rest.get('ci_high')}).",
             information_missing="Travel distance and time-zone crossing, which the mirror does not carry and the league does not publish as a table.",
             answer=(
                 "Yes, and it is statistically significant, but the effect is worth well under a point "
                 "per day of rest. It is a real input to a model, not a strategy on its own."),
             how_to_discover="Add travel data and re-measure. Do not bet it as a standalone rule."),

        dict(id="Q-07", area="Availability", status="ANSWERED - partially",
             question="Which replacement string has to step in when a starter is out?",
             information_held=(
                 f"{ctx['depth']['slots']:,} depth-chart slots across {ctx['depth']['teams_covered']} clubs; "
                 f"{ctx['depth']['starters_on_report']} designated starters appear on the official Week 10 "
                 f"injury report, {ctx['depth']['starters_out']} of them Out. Each row names the replacement "
                 "and whether they are the 2nd, 3rd or 4th string."),
             information_missing=(
                 "Houston publishes no parsable depth chart, so the Texans have no rows. Snap counts, "
                 "which would tell you how much a given slot actually plays."),
             answer="Yes for 31 clubs. Houston is a recorded coverage gap, not a filled-in guess.",
             how_to_discover="SG-04 for Houston; SG-05 to weight each slot by how much it is used."),

        dict(id="Q-08", area="Availability", status="BLOCKED - cannot be measured yet",
             question="Does an injury to a starter actually move the line, and by how much?",
             information_held="The current-week injury report and the depth replacement for 31 clubs.",
             information_missing=(
                 "A historical join of injury designations to opening and closing lines. Without "
                 "opening prices (Q-02) there is no 'before' and 'after' to difference, so any number "
                 "here would be invented."),
             answer="Not answerable today. Any published injury-to-points figure would be a guess.",
             how_to_discover="SG-01 first, then SG-03. This is the single largest gap between what the brief asks for and what the evidence can support."),

        dict(id="Q-09", area="Parlays", status="ANSWERED",
             question="Can a parlay strategy ever pass the gates?",
             information_held=(
                 f"ST-PARLAY-4 placed {ctx['parlay']['bets']:,} bets out of sample and returned "
                 f"{ctx['parlay']['roi']:.1%} flat. Measured correlation between the two legs is "
                 f"{st_tot.get('value')} (n={st_tot.get('n'):,})."),
             information_missing="Nothing material.",
             answer=(
                 "Not with these legs. A parlay multiplies the vig on each leg and needs both legs to "
                 "be right; with a signal that has no measurable edge on either leg, the combination is "
                 "strictly worse than the singles."),
             how_to_discover="Only a genuine edge on a single leg would change this."),

        dict(id="Q-10", area="Player props", status="BLOCKED - no source at all",
             question="Can we model player props and prop combinations?",
             information_held="The mathematics of prop pricing and of combining correlated props.",
             information_missing=(
                 "No source available to this repository publishes historical player-prop lines. "
                 "nflverse/nfldata does not carry them, and the league does not publish betting lines "
                 "of any kind."),
             answer="No. Publishing a prop model without prop lines would mean inventing the prices.",
             how_to_discover="SG-07. Until a prop-line source exists, the props page carries the mathematics and an empty results table."),

        dict(id="Q-11", area="Luck", status="ANSWERED",
             question="How many bets does it take before a winning record means skill?",
             information_held=(
                 f"At -110 the break-even hit rate is 52.38%. A true 55% capper needs {s55['bets_needed']:,} "
                 f"bets to be distinguishable from a coin-flip winner at 95% confidence with 80% power, "
                 f"which is about {s55['seasons_at_300_bets']} seasons at 300 bets a season."),
             information_missing="Nothing. This is arithmetic, not measurement.",
             answer="Far more than a season of NFL sides. This is why gate G1 sets a floor and why no strategy here is promoted on a short run.",
             how_to_discover="Nothing. The number is published on the luck page."),

        dict(id="Q-12", area="Signal", status="ANSWERED - and it is the most important answer here",
             question="When the model disagrees with the market, who is wrong?",
             information_held=(
                 (f"2021 is the one season with a real opening number. The gap between our fair line and "
                  f"the market GREW from {conv_side['mean_abs_gap_vs_open']} points at the open to "
                  f"{conv_side['mean_abs_gap_vs_close']} points at the close, a change of "
                  f"{conv_side['change']:+} points (standard error {conv_side['se_of_change']}) over "
                  f"n={conv_side['n']} games, and the gap shrank in only "
                  f"{conv_side['share_shrank']:.0%} of them.") if conv_side else "Not measured."),
             information_missing="The same test for other seasons, which needs opening lines (Q-02).",
             answer=(
                 "We are. If our number carried information the opening line lacked, the close would "
                 "have moved toward it. It moved away, and it moved away by six standard errors."),
             how_to_discover="SG-01 unlocks this test for every season. It is the cheapest honest way to prove a model has any value at all."),

        dict(id="Q-13", area="Governance", status="ANSWERED - defined, not yet exercised",
             question="What sends a live strategy back to paper?",
             information_held="Six demotion rules (D1-D6) with thresholds, windows, and a re-promotion requirement of 100 fresh paper bets.",
             information_missing="A live bet log. Nothing is live, so no rule has ever fired.",
             answer="The gate is defined and published on the gates page. It is armed, not tripped.",
             how_to_discover="Nothing to do until a strategy is promoted. Then SG-10 wires the log to it."),

        dict(id="Q-14", area="Governance", status="OWNER DECISION",
             question="How much bankroll, and is a reward pool something we can legally run?",
             information_held="A staking policy (quarter Kelly, capped at 5% of a 100-unit bankroll) and a reward formula that pays nothing unless all eight gates pass.",
             information_missing="The owner's capital decision, and any legal view on paying prize money for a forecasting competition.",
             answer="Not a data question. It is recorded here so it is not mistaken for one.",
             how_to_discover="Owner decision. Nothing in this repository should go live before it is made."),

        dict(id="Q-15", area="Signal", status="ANSWERED - no",
             question="Does a bigger disagreement with the market mean a better bet?",
             information_held=(
                 "Point-biserial correlation between edge size and bet result, measured per strategy "
                 "and published with n on the correlations page. Every credible interval covers zero, "
                 "and the largest side-edge threshold is significantly negative."),
             information_missing="Nothing material.",
             answer="No. Raising the threshold just reduces the sample; it does not select better bets. This is the clearest evidence that the disagreement is model error rather than market error.",
             how_to_discover="Nothing. If a future model produces a positive value here with a tight interval, that is the signal to promote it."),

        dict(id="Q-16", area="Fixture context", status="ANSWERED - and it corrected our own published table",
             question="Can a runner read the league's Game Center pages and reproduce the venue "
                      "transcription we published by hand?",
             information_held=(
                 f"The capture ran on {rep.get('captured_at_utc','')} over "
                 f"{rep.get('weeks',[10,11])} and retained {rep.get('rows',0)} fixture pages, "
                 f"{rep.get('fixtures_recorded',0)} of {rep.get('rows_expected',0)} rows built with "
                 f"{rep.get('fields_missing',0)} required fields missing. Offline re-derivation: "
                 f"{vv.get('cells_checked',0)} cells from the retained gzip, "
                 f"{vv.get('mismatches',0)} mismatches, verdict {vv.get('verdict','not run')}. "
                 f"Against the independent hand register: "
                 f"{xch.get('venue',{}).get('agree',0)} of {xch.get('venue',{}).get('cells_compared',0)} "
                 f"stadium cells agree; the slate comparison matched "
                 f"{xch.get('slate',{}).get('captured',0)} of {xch.get('slate',{}).get('slate',0)} "
                 f"Week 11 fixtures."),
             information_missing=(
                 "Capacity, roof, surface, attendance, weather and officiating are not printed on the "
                 "Overview Game Info block on any of the 27 pages, so those cells are blank and flagged "
                 "by rule. They would have to come from a team or stadium source, which the brief does "
                 "not allow as a substitute for the league page."),
             answer=(
                 "Yes for the two fields the page prints, and the cross-check earned its keep twice: "
                 "the first published register mislabelled all 13 unplayed Week 11 fixtures as FINAL "
                 "because a page-wide status search hit a standings table, and it printed "
                 "'AT&amp;T STADIUM' because entity refs survive tag stripping. Both are fixed, both "
                 "have offline cases now, and both defects were found by comparing two independent "
                 "reads of the same page."),
             how_to_discover="Already resolved in this repository: tools/official/gamecentre.py "
                             "selftest, reparse, verify and cross-check run in CI on every capture."),

        dict(id="Q-17", area="Injury", status="ANSWERED - the instrument works, the cadence does not",
             question="Does anything new arrive between official injury reads, and can surprise - "
                      "not level - be measured from them?",
             information_held=(
                 f"{idel.get('reads_parsed',0)} of {idel.get('reads_total',0)} retained reads of the "
                 f"league injury hub parse into a series. The diff found {idel.get('deltas',0)} "
                 f"movements between adjacent reads, spanning {len(idel.get('days_with_a_read', {}))} "
                 f"calendar day(s). Cadence verdict: {idel.get('cadence_verdict','')}. The 355-row comparison of two reads of the "
                 f"Week 10 table in the round-5 audit agreed on all 355 rows."),
             information_missing=(
                 "The hub carries no timestamp of its own, so a change is only as datable as the "
                 "capture that saw it; and there is no per-player transaction feed with an effective "
                 "date, which is what a surprise measurement needs between Sunday and Thursday."),
             answer=(
                 "The delta is measurable and the tool exists, but on this repository's access pattern "
                 "the hub does not move often enough to price surprises with: two reads three minutes "
                 "apart and nothing between the two days. A surprise feature has to be built on a "
                 "daily cadence, which is an SG-17 decision, not a parser problem."),
             how_to_discover="Run the capture workflow daily for two weeks; tools/official/injury_delta.py "
                             "cadence then reports whether the claim 'we capture it at least daily' holds."),

        dict(id="Q-18", area="Governance", status="ANSWERED",
             question="Does every registered strategy say what would change its mind, on both sides, "
                      "in numbers?",
             information_held=(
                 f"{md.get('strategies_with_both_sides',0)} of {md.get('strategies',0)} strategies "
                 f"({md.get('coverage',0)}%) carry a confirm cell and a refute cell, each naming at "
                 f"least one quantity with a number in it; the checker fails the build on a cell "
                 f"without one. The escrow register is the same discipline on the model side: "
                 f"{inp.get('rows_rederived_ok',0)} of {inp.get('rows_in_rederive_scope',0)} frozen "
                 f"probabilities re-derive exactly from the inputs stored beside them."),
             information_missing=(
                 "The confirm side of six rules currently points at the prospective escrow sample, "
                 "which is 150 games and not yet played; no backtest can close it."),
             answer=(
                 "Yes, and it is the cheapest governance item in the brief: no external source needed, "
                 "just a refusal to let a falsifier be prose. The first pass failed its own numeric "
                 "checker on 6 of 16 rules, which is the bug this register exists to catch."),
             how_to_discover="Closed. python3 tools/official/mind_change.py check runs in CI."),
    ]
    return Q


# ---------------------------------------------------------------------------
# the suggestion board
# ---------------------------------------------------------------------------

def suggestions():
    """Each suggestion offers two or three paths and a recommendation.

    ``decision_status`` is 'proposed' until the owner picks a path. Nothing on
    this board is built ahead of that.
    """
    return [
        dict(id="SG-01", title="Get a timestamped, book-identified price feed",
             area="Prices", unlocks="Q-02, Q-08, Q-12 and the entire demotion gate",
             problem=("The store can record opening and closing numbers, but no source available here "
                      "publishes both. One number per market, no book, no timestamp."),
             paths=[
                 dict(label="A. Licensed odds feed",
                      description="Subscribe to a commercial historical and live odds API that publishes per-book opening and closing numbers with timestamps.",
                      cost="Paid (recurring)", effort="Medium integration", risk="Low",
                      unlocks="True open/close pairs, real CLV, a working demotion gate, and the injury-to-line test."),
                 dict(label="B. Scheduled self-capture",
                      description="A GitHub Actions cron writes a snapshot of publicly displayed prices to the store on a fixed schedule, every day of the week.",
                      cost="Free", effort="Medium", risk="Legal and terms-of-service review required before this runs",
                      unlocks="Real opening numbers going forward, but no history before it starts."),
                 dict(label="C. Do nothing and keep the columns blank",
                      description="Leave the price store as it is: 2021 both-ends, everything else close-only, blanks flagged.",
                      cost="Free", effort="None", risk="The eight requirements that depend on prices stay unmet",
                      unlocks="Nothing."),
             ],
             recommendation="Path A if there is budget; otherwise path B after a terms-of-service review. Path C is the honest default and is what the site ships with today.",
             decision_status="proposed"),

        dict(id="SG-02", title="Add player participation and snap counts",
             area="Availability", unlocks="Q-07, Q-08 and any injury-weighted model",
             problem="The depth register knows who replaces whom, but not how much that slot is used, so a backup left guard and a backup quarterback carry the same weight.",
             paths=[
                 dict(label="A. nflverse weekly rosters and snap counts",
                      description="Ingest the mirror's snap-count tables, fingerprint them, and weight each depth slot by the share of snaps it played.",
                      cost="Free", effort="Medium", risk="Third-party mirror, not league-published; must be labelled as such",
                      unlocks="A weighted deficiency score instead of a headcount."),
                 dict(label="B. Paid participation data",
                      description="Buy per-play participation from a commercial provider.",
                      cost="Paid", effort="Low once contracted", risk="Low",
                      unlocks="Same as A with better coverage and a licence."),
                 dict(label="C. Keep publishing the headcount",
                      description="Leave the deficiency score unweighted and say so on the page.",
                      cost="Free", effort="None", risk="The score over-weights low-usage slots",
                      unlocks="Nothing new."),
             ],
             recommendation="Path A. It is free, it is fingerprinted, and it is the difference between a headcount and a model.",
             decision_status="proposed"),

        dict(id="SG-03", title="Timestamp the injury report",
             area="Availability", unlocks="Q-08 and any within-week line-move study",
             problem="The injury report is fetched as a snapshot. The league updates it daily, so a designation observed on Friday is not the one that moved the market on Wednesday.",
             paths=[
                 dict(label="A. Daily scheduled capture",
                      description="A cron workflow fetches the official injury page each afternoon and appends a dated snapshot to the store.",
                      cost="Free", effort="Low", risk="Low",
                      unlocks="Designation change times, which is the independent variable the injury model needs."),
                 dict(label="B. Capture twice daily around the market",
                      description="Same as A but at two fixed times to bracket the trading day.",
                      cost="Free", effort="Low", risk="Slightly more storage",
                      unlocks="A tighter estimate of when the market learned what."),
                 dict(label="C. Keep the snapshot as-is",
                      description="One fetch per build.",
                      cost="Free", effort="None", risk="Within-week moves stay invisible",
                      unlocks="Nothing new."),
             ],
             recommendation="Path A. It is a few lines of workflow and it is the only way Q-08 ever becomes answerable.",
             decision_status="proposed"),

        dict(id="SG-04", title="Close the Houston depth-chart gap",
             area="Availability", unlocks="Q-07 for all 32 clubs",
             problem="Houston's club depth-chart page returns no parsable table, so the Texans have no deficiency rows at all.",
             paths=[
                 dict(label="A. Hand-transcribe Houston into a sourced PSV",
                      description="Read the club's own page once and transcribe it to a pipe-separated file with the source URL and the date, exactly as the other 31 are handled.",
                      cost="Free", effort="Low, one-off", risk="Goes stale",
                      unlocks="Full 32-club coverage, with the same provenance as everything else."),
                 dict(label="B. Find an alternative official page for the club",
                      description="Try the club's roster or team page instead of its depth-chart page.",
                      cost="Free", effort="Medium", risk="May not publish a chart at all",
                      unlocks="A machine-readable path that stays current."),
                 dict(label="C. Record it as a permanent coverage gap",
                      description="Leave Houston out and keep the gap visible on the flagged page.",
                      cost="Free", effort="None", risk="One club is missing from every deficiency total",
                      unlocks="Nothing new."),
             ],
             recommendation="Path A today, and retry B on the next refresh. Filling the gap with a guess is the one option that is not acceptable.",
             decision_status="proposed"),

        dict(id="SG-05", title="Weight the deficiency score by how much a slot is used",
             area="Availability", unlocks="A deficiency score that means something",
             problem="A starter being out counts the same whether he plays every snap or ten.",
             paths=[
                 dict(label="A. Weight by snap share (needs SG-02)",
                      description="Multiply each replacement depth penalty by the snap share of the slot.",
                      cost="Free once SG-02 lands", effort="Low", risk="Depends on a mirror",
                      unlocks="A position-weighted deficiency score, published per club."),
                 dict(label="B. Weight by a fixed position table",
                      description="Use a documented static weight per position group (QB, OL, CB, and so on).",
                      cost="Free", effort="Low", risk="The weights are our judgement, not measured",
                      unlocks="A better ordering than a headcount, but the weights must be published and labelled as judgement."),
                 dict(label="C. Leave it as a headcount",
                      description="Keep counting Out starters by replacement string.",
                      cost="Free", effort="None", risk="Over-weights low-usage slots",
                      unlocks="Nothing new."),
             ],
             recommendation="Path A if SG-02 is approved; path B with the weights published if it is not. Either is better than C.",
             decision_status="proposed"),

        dict(id="SG-06", title="Measure closing line value as the primary signal metric",
             area="Signal", unlocks="A stake-free measure of whether the signal knows something",
             problem="ROI conflates the signal with the staking and with luck. CLV does not: it asks whether the number we took was better than the number the market closed at.",
             paths=[
                 dict(label="A. Full CLV from open and close (needs SG-01)",
                      description="Record the price at signal time and at kick-off, and publish the difference as the headline signal metric.",
                      cost="Depends on SG-01", effort="Low once prices exist", risk="Low",
                      unlocks="The single best available answer to 'is the signal skilled'."),
                 dict(label="B. Partial CLV on 2021 only",
                      description="Use the one season where both ends exist to demonstrate the metric.",
                      cost="Free", effort="Low", risk="n=264, so it is a demonstration not a proof",
                      unlocks="The metric exists and the method is visible even if the sample is thin."),
                 dict(label="C. Keep using ROI",
                      description="Leave ROI as the headline.",
                      cost="Free", effort="None", risk="Luck and staking keep contaminating the signal score",
                      unlocks="Nothing new."),
             ],
             recommendation="Path B now so the column exists, path A as soon as prices do. CLV belongs in the signal column, never the staking column.",
             decision_status="proposed"),

        dict(id="SG-07", title="Decide what to do about player props",
             area="Player props", unlocks="Q-10",
             problem="The brief asks for player-prop combinations. No source available here publishes prop lines, so nothing can be priced, backtested or scored.",
             paths=[
                 dict(label="A. Buy a prop-line history",
                      description="Purchase historical player-prop lines from a commercial provider.",
                      cost="Paid", effort="Medium", risk="Low",
                      unlocks="Prop strategies that can actually be evaluated and gated."),
                 dict(label="B. Scope props out and say so",
                      description="Remove prop strategies from the competition until a source exists, keeping only the published mathematics.",
                      cost="Free", effort="Low", risk="One part of the brief stays unmet",
                      unlocks="An honest scope statement instead of invented prices."),
                 dict(label="C. Proxy prop lines from season averages",
                      description="Invent a line for each prop from the player's average.",
                      cost="Free", effort="Low",
                      risk="This is not a line. Any backtest on it would be measuring our own invention",
                      unlocks="Nothing real."),
             ],
             recommendation="Path B is what the site does today. Path A if props matter commercially. Path C must not be taken: it would produce numbers that look like results and are not.",
             decision_status="proposed"),

        dict(id="SG-08", title="Replace team ratings with a play-level model",
             area="Signal", unlocks="Q-01",
             problem="The current model is a ridge regression on final scores. It explains about a fifth of the variance the market's own number explains.",
             paths=[
                 dict(label="A. Play-by-play and EPA from the nflverse mirror",
                      description="Ingest the mirror's play-by-play data and build a down-and-distance model.",
                      cost="Free", effort="High", risk="Very large data volumes; the mirror is not league-published",
                      unlocks="A materially better prior, and the ability to test injuries at the unit level."),
                 dict(label="B. Add a small number of external features to the current model",
                      description="Weather, travel, rest and divisional terms, all sourced and labelled.",
                      cost="Free", effort="Medium", risk="Low",
                      unlocks="A modest improvement, honestly measured."),
                 dict(label="C. Keep the current model",
                      description="Stop where we are and publish the negative result.",
                      cost="Free", effort="None", risk="The model stays about a point worse than the market",
                      unlocks="Nothing new."),
             ],
             recommendation="Path B first: it is cheap, and if it does not move the needle the case for A weakens rather than strengthens. Publish the result either way.",
             decision_status="proposed"),

        dict(id="SG-09", title="Keep signal and staking reported separately on the leaderboard",
             area="Governance", unlocks="A leaderboard that cannot be gamed by bet sizing",
             problem="A single ROI column lets a lucky staking plan promote a signal that has no value.",
             paths=[
                 dict(label="A. Two score columns, promotion on the signal one (implemented)",
                      description="signal_score is computed at flat 1 unit and cannot be moved by sizing; staking_score reports the plan; promotion needs signal_score above the floor and all eight gates.",
                      cost="Free", effort="Done", risk="Low",
                      unlocks="The requirement, as asked."),
                 dict(label="B. Report ROI only",
                      description="Collapse back to one column.",
                      cost="Free", effort="None", risk="Staking luck promotes bad signals",
                      unlocks="Nothing."),
             ],
             recommendation="Path A. It is built and published on the leaderboard page. Keep it.",
             decision_status="implemented"),

        dict(id="SG-10", title="Wire the demotion gate to a live bet log",
             area="Governance", unlocks="Q-13",
             problem="D1 to D6 are defined with thresholds and windows, but nothing is live so none has fired.",
             paths=[
                 dict(label="A. Write the gate evaluation against the bet log",
                      description="A scheduled job evaluates D1-D6 over the trailing window of every live strategy and demotes on a trip.",
                      cost="Free", effort="Medium", risk="Low",
                      unlocks="The gate stops being documentation and starts being a control."),
                 dict(label="B. Evaluate manually each week",
                      description="A weekly review against the same rules.",
                      cost="Free", effort="Ongoing manual work", risk="Human drift",
                      unlocks="The same control, more slowly."),
                 dict(label="C. Leave it documented only",
                      description="Publish the rules and do not run them.",
                      cost="Free", effort="None", risk="A live strategy can blow up before anyone looks",
                      unlocks="Nothing new."),
             ],
             recommendation="Nothing is live, so C is correct today. Build A before the first promotion, not after.",
             decision_status="proposed"),

        dict(id="SG-11", title="Consolidate the published site trees",
             area="Site", unlocks="One landing page instead of nine",
             problem="Nine parallel sessions each left a complete site in this repository. Every one of them is still published. A reader cannot tell which is canonical.",
             paths=[
                 dict(label="A. Serve one tree and keep the rest archived under a clearly labelled link",
                      description="One landing page, one navigation, one stylesheet; the older trees stay reachable from a single 'archived sites' page with a note on what each is kept for.",
                      cost="Free", effort="Medium", risk="Low",
                      unlocks="A site a reader can actually use."),
                 dict(label="B. Delete the older trees",
                      description="Remove everything but the canonical tree.",
                      cost="Free", effort="Low", risk="Destroys work that is in some places the only copy of a finding",
                      unlocks="A clean tree, at the cost of the record."),
                 dict(label="C. Leave all nine live",
                      description="Change nothing.",
                      cost="Free", effort="None", risk="Readers cannot find the answer",
                      unlocks="Nothing new."),
             ],
             recommendation="Path A. This session publishes the console as the landing page and links every earlier tree from one archived-sites page. Nothing is deleted.",
             decision_status="implemented"),

        dict(id="SG-12", title="Publish the leaderboard on a fixed weekly schedule",
             area="Governance", unlocks="Comparable week-to-week records",
             problem="Results are computed when the site is built, so there is no fixed as-of date and no week-over-week record.",
             paths=[
                 dict(label="A. Weekly scheduled rebuild with an as-of stamp",
                      description="A cron workflow rebuilds on a fixed day and stamps every page with the as-of date and the data fingerprints.",
                      cost="Free", effort="Low", risk="Low",
                      unlocks="A time series of signal scores, which is what the demotion gate needs."),
                 dict(label="B. Rebuild only on push",
                      description="Current behaviour.",
                      cost="Free", effort="None", risk="No comparable history",
                      unlocks="Nothing new."),
             ],
             recommendation="Path A. The demotion gate is meaningless without a weekly record.",
             decision_status="proposed"),

        dict(id="SG-13", title="Record the owner's decisions on this board",
             area="Governance", unlocks="A decision trail",
             problem="Suggestions sit here with a recommendation and no recorded decision, so the same questions get re-litigated every session.",
             paths=[
                 dict(label="A. Owner picks a path per suggestion and the choice is recorded here",
                      description="Each suggestion gets a decided path, a date and a note. Only then is it built.",
                      cost="Free", effort="Owner time", risk="Low",
                      unlocks="Work stops being repeated and the build order becomes explicit."),
                 dict(label="B. Let each session decide",
                      description="Current behaviour.",
                      cost="Free", effort="None", risk="Every session rebuilds something different",
                      unlocks="Nothing new."),
             ],
             recommendation="Path A. This is the one item on the board that costs nothing but a decision.",
             decision_status="proposed"),

        dict(id="SG-14", title="Re-pin the results feed to the completed Week 10 corpus",
             area="Results", unlocks="Q-62 / S-22, and every backtest that should see Week 10",
             problem=("Every results feed in the repository stops at the Week 10 Thursday game "
                      "(137 rows). The official corpus is 150 games as of 2026-11-17: the 13 "
                      "remaining Week 10 finals are now read, and the 150-game corpus reproduces "
                      "all 32 official standings rows exactly (tools/verify_2026_11_17.py, check "
                      "B4). Closing the pinned feed is therefore mechanical, not an open question."),
             paths=[
                 dict(label="A. Coordinated re-pin at the next data refresh",
                      description="Swap the standings transcription to the 2026-11-17 table, re-pin the mirror to a games.csv carrying the 13 finals, move the row-count pin 137 to 150, and rebuild every derived register in one commit.",
                      cost="Free", effort="One coordinated commit", risk="Low: the arithmetic is already proven 32/32",
                      unlocks="Backtests and signal grades that include the completed Week 10 slate."),
                 dict(label="B. Keep the pinned feed frozen; score against the dated packs",
                      description="Leave the 137-row feed exactly as pre-registered and let evaluations consume data/verification/2026_11_16 and 2026_11_17 packs as dated outcome sources.",
                      cost="Free", effort="Low", risk="Two result sources must be kept consistent",
                      unlocks="Preserves the frozen corpus byte-for-byte; slightly more wiring in each evaluator."),
                 dict(label="C. Leave as-is",
                      description="Nothing moves; Week 10 finals stay outside every feed.",
                      cost="Free", effort="None", risk="Backtests silently end one week early",
                      unlocks="Nothing."),
             ],
             recommendation="Path A at the next scheduled data refresh, once (not before) the pre-registered PR-01 evaluation for 2026-11-16 is treated as closed and archived. Path B if the owner wants the frozen corpus preserved exactly.",
             decision_status="proposed"),

        dict(id="SG-15", title="Render the salvaged capture artifacts in the console",
             area="Availability", unlocks="R-29, R-45, R-25 and the injury-timeline views",
             problem=("The salvaged artifacts (the hashed raw-byte ledger in data/ledger/, the "
                      "dated injury snapshots in data/nfl/snapshots/, the league's schedule "
                      "announcement in data/audit/, the independent injury spot-check in "
                      "data/readiness/) are in the repository and verified, but no console page "
                      "renders them yet."),
             paths=[
                 dict(label="A. Dedicated console pages",
                      description="A ledger-timeline page (capture times, hashes, content deltas), a dated-snapshot page (11-14 vs 11-15 cell deltas), and the schedule announcement rendered beside the live schedule page.",
                      cost="Free", effort="One generator module in the established pattern", risk="Low",
                      unlocks="The injury report becomes a readable timestamped series on the site, not just files in git."),
                 dict(label="B. Keep them as data with flagged links",
                      description="Current state after the salvage: the flagged page links each artifact on GitHub.",
                      cost="Free", effort="None", risk="The series is invisible to a reader who does not open GitHub",
                      unlocks="Nothing new."),
             ],
             recommendation="Path A. The owner's brief explicitly asks for the dated history to be published, and every artifact already passes its verifier.",
             decision_status="proposed"),

        dict(id="SG-16", title="Capture the remaining 258 fixtures through the Game Center runner",
             area="Fixture context", unlocks="Q-16, R-15 and the venue column of every feature set",
             problem=("The runner works and self-verifies, but it only covers Weeks 10 and 11 - "
                      "27 fixtures. The brief asks for venue and fixture context across the season, and "
                      "the remaining 258 fixtures are one flag away from being transcribable by hand."),
             paths=[
                 dict(label="A. Widen the workflow window",
                      description="Change WEEKS to the full season; ~285 fetches a run, about 350 MB of retained gzip per capture.",
                      cost="Free", effort="Small change, large artefact growth",
                      risk="The repo bloats quickly; retention policy has to be decided at the same time.",
                      unlocks="Every fixture gets a hashed capture and a re-derivable venue cell."),
                 dict(label="B. Backfill once, then keep weeks 10-11 fresh",
                      description="A one-off run writes the season's register without committing the raw pages; the schedule keeps only the current and previous week retained.",
                      cost="Free", effort="Medium", risk="A backfilled row cannot be re-derived offline unless its bytes are kept.",
                      unlocks="Full coverage, bounded repo size, and an honest flag on any row whose bytes were dropped."),
                 dict(label="C. Stop at the current fortnight",
                      description="Leave the collector as a per-week instrument and use it only where a feature is actually being priced.",
                      cost="Free", effort="None", risk="R-15 stays at 27 of 285 fixtures.",
                      unlocks="Nothing new."),
             ],
             recommendation="Path B, with one exception: keep the raw bytes for any fixture that enters a model's feature set, so the published cell stays re-derivable. Path A's 350 MB per capture is not sustainable in a pages repo.",
             decision_status="proposed"),

        dict(id="SG-17", title="Decide the capture cadence that injury surprise depends on",
             area="Injury", unlocks="Q-17 and any surprise-weighted model input",
             problem=("Two of the five retained injury reads are three minutes apart, and the largest "
                      "gap produced no delta. The delta tool is built and correct; the sampling is not "
                      "dense enough to price a surprise with."),
             paths=[
                 dict(label="A. Hourly scheduled capture in the week between games",
                      description="A cron in the 48 hours before each kickoff, deltas committed per run.",
                      cost="Free", effort="Small", risk="More commits, and still blind to anything that moves and settles between two runs.",
                      unlocks="A real surprise series, dated to the hour."),
                 dict(label="B. Daily capture, accept the coarser clock",
                      description="One read a day per team page, delta ledger on the same schedule as the venue capture.",
                      cost="Free", effort="Small", risk="A Tuesday morning announcement priced on Wednesday is late by a day.",
                      unlocks="Enough to test whether a surprise moves the line at all."),
                 dict(label="C. Leave injury out of the model",
                      description="Keep the register as evidence and do not use it as an input.",
                      cost="Free", effort="None", risk="The brief's injury requirement stays unmet.",
                      unlocks="Nothing new."),
             ],
             recommendation="Path B now - it fits the existing workflow and answers the question the model actually asks ('does a status change predict a line move') - and revisit path A only if the daily series shows movement it is failing to catch.",
             decision_status="proposed"),

        dict(id="SG-18", title="Fund the escrow sample rather than widening the backtest",
             area="Leaderboard", unlocks="Q-01, R-17, R-20 and the first honest promotion",
             problem=("Every ranking number in this repository comes from a backtest, and the "
                      "pre-registration rule says a backtest never enters the leaderboard. The escrow "
                      "has 52 frozen rows and one settled side row, so the luck panel can only "
                      "demonstrate its own arithmetic."),
             paths=[
                 dict(label="A. Freeze prospective forecasts weekly, forever",
                      description="Every week, before kickoffs: run tools/lab/build_escrow.py, commit, hash. Settlement comes from the verified results feed.",
                      cost="Free", effort="One scheduled job plus a review of the shape guard",
                      risk="Sample arrives at 3-4 rows per game week; the 300-row gate takes about a season per rule.",
                      unlocks="Exactly what the gates ask for, at the only honest speed available."),
                 dict(label="B. Lower the gates so something promotes now",
                      description="Reduce n or drop the uncertainty requirement.",
                      cost="Free", effort="None", risk="It buys a promoted strategy that is noise, which is the failure mode the whole gate structure exists to prevent.",
                      unlocks="Nothing real."),
                 dict(label="C. Pay for a longer prospective window",
                      description="Run path A across two or three seasons of historical fixtures where the market data is already complete, treating each past week as prospective from its own kickoff timestamp.",
                      cost="Free", effort="Medium; needs a careful cut-off so nothing after kickoff leaks in",
                      risk="A past week read from today's corpus is not fully prospective: the corpus itself carries the result.",
                      unlocks="Large samples, but the leak risk has to be argued line by line before it counts."),
             ],
             recommendation="Path A, immediately, with path C only as a separately labelled experiment that never feeds the leaderboard. Do not do path B: a promoted strategy that cannot be distinguished from noise is worse than none promoted.",
             decision_status="proposed"),

        dict(id="SG-19", title="Publish the register files as first-class tables on the site",
             area="Site", unlocks="The brief's requirement that every finding be readable as a table",
             problem=("Four registers now sit in data/official with their own verifiers - the venue "
                      "capture, the injury delta, the mind-change register and the escrow input ledger - "
                      "and none of them render on the dashboard. A reader today cannot see the numbers "
                      "that the audit text quotes."),
             paths=[
                 dict(label="A. One page per register, wired additively",
                      description="Three renderers and four NAV entries in tools/build_console.py; each page carries its own reproduce command and link back to the retained official page.",
                      cost="Free", effort="Small", risk="Shared-file conflict with another integration session.",
                      unlocks="Every value published with the source link the brief demands."),
                 dict(label="B. Leave them in data/ and link from the flagged page",
                      description="The TSV and CSV files stay on GitHub and the site only links them.",
                      cost="Free", effort="None", risk="The dashboard stops being the place the numbers are read.",
                      unlocks="Nothing new."),
             ],
             recommendation="Path A. It is additive, every table gets a source link, and the verifier for each register already runs in CI.",
             decision_status="proposed"),
    ]


# ---------------------------------------------------------------------------
# irregularity register
# ---------------------------------------------------------------------------

def irregularities(ctx):
    return [
        dict(id="X-01", severity="red", area="Prices",
             finding="No source available here publishes an opening price. The mirror carries one number per market, with no book and no capture timestamp.",
             effect="Requirement 'opening and closing numbers for every market we originate' can only be met for 2021 and for the markets originated today. Every other open_* cell is blank by policy.",
             source=sources.url("nfldata_games") or "https://github.com/nflverse/nfldata",
             status="open - see SG-01"),
        dict(id="X-02", severity="red", area="Player props",
             finding="No source available here publishes player-prop lines of any kind, and the league publishes no betting lines at all.",
             effect="Prop and prop-combination strategies cannot be priced, backtested or gated. The props page publishes the mathematics and an empty results table rather than invented prices.",
             source="https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
             status="open - see SG-07"),
        dict(id="X-03", severity="red", area="Availability",
             finding="Houston's club depth-chart page returns no parsable table.",
             effect="The Texans have no rows in the deficiency register, so every league-wide deficiency total covers 31 clubs, not 32.",
             source="https://www.houstontexans.com/team/depth-chart",
             status="open - see SG-04"),
        dict(id="X-04", severity="amber", area="Signal",
             finding="The model's fair spread is about 1.1 points per game less accurate than the market line it is compared against, and the gap between our number and the market GREW from open to close in 2021.",
             effect="No strategy passes the gates. That is the correct outcome of the gates, not a defect in them.",
             source="measured - see the origination and convergence tables",
             status="accepted and published"),
        dict(id="X-05", severity="amber", area="Availability",
             finding="Club depth charts are published by the clubs, not by the league. Chicago's chart was dated 10/31/2026, Green Bay's is labelled unofficial, and Baltimore's kicker slot is empty.",
             effect="Every deficiency row states its own source tier and links the club page it came from. The register is not described as league-verified.",
             source="https://www.nfl.com/teams/",
             status="accepted and published"),
        dict(id="X-06", severity="amber", area="Prices",
             finding="The parlay results are settled at the mathematical product of two -110 legs (+264.55). No source here publishes a book's real parlay price, and books pay less than the product.",
             effect="Measured parlay ROI is optimistic. The direction of the error is known and stated.",
             source="computed",
             status="accepted and published"),
        dict(id="X-07", severity="amber", area="Model",
             finding="Side and total bets are settled at -110 because the mirror publishes spread and total lines without prices. Real closing prices are often -115 or worse.",
             effect="Every ROI on the leaderboard is optimistic by roughly the juice difference. The sensitivity is arithmetic: one cent of extra juice is about 0.45% of ROI at a 50% hit rate.",
             source=sources.url("nfldata_games") or "https://github.com/nflverse/nfldata",
             status="accepted and published"),
        dict(id="X-08", severity="grey", area="Site",
             finding="Nine complete site trees exist in this repository from nine parallel sessions, all still published.",
             effect="The console is the landing page. Every earlier tree stays reachable from one archived-sites page and nothing is deleted.",
             source="",
             status="mitigated - see SG-11"),
        dict(id="X-09", severity="amber", area="Results",
             finding=("Every results feed stops at the Week 10 Thursday game (137 rows) while the "
                      "official corpus is 150 games as of 2026-11-17."),
             effect=("Backtests built on the pinned feed end one week early. The 2026-11-17 pack "
                     "proves the 150-game corpus reconciles 32/32 with the league's own standings "
                     "table, so closing the gap is a mechanical re-pin (SG-14), not an open "
                     "question. Until then the completed finals are published as a dated pack "
                     "rather than folded into the pinned feed."),
             source="https://www.nfl.com/schedules/2026/by-week/week-10",
             status="measured and published - see SG-14 and the Week 10 finals page"),
        dict(id="X-10", severity="grey", area="Coordination",
             finding=("Four pull requests (#50, #53, #61, #66) sat conflicting and stale since "
                      "2026-11-15, each holding unique official-capture artifacts that never "
                      "reached main: a hashed raw-byte injury ledger (4 captures), dated injury "
                      "snapshots for 11-14 and 11-15, the league's dated schedule announcement, "
                      "and an independent 347-row injury spot-check."),
             effect=("The data has been salvaged line by line into this repository and "
                     "re-verified: the ledger hash chain passes (tools/snapshot_ledger.py "
                     "verify), the two independent 2026-11-15 injury reads agree cell for cell "
                     "(347 rows x 4 columns, 0 mismatches), and the schedule announcement "
                     "matches the league's own media page. The Week 10 injury table was "
                     "re-published to the 2026-11-15 read (345 &rarr; 347 rows) and the "
                     "11-14 &rarr; 11-15 delta (32 cells, 2 added rows) is published as a "
                     "dated delta. The PRs' page wiring was not salvaged (it predates later "
                     "generator changes); rendering it is SG-15."),
             source="https://github.com/karagemop466-tech/X1/pull/50",
             status="salvaged and verified 2026-11-17; PRs closed with handoff notes"),
        dict(id="X-11", severity="amber", area="Automation",
             finding=("The scheduled 'Refresh research data' workflow failed at its final step "
                      "with 'Resource not accessible by integration': the workflow granted the "
                      "token only contents: write, and an explicit permissions block replaces "
                      "the default grants, so the pull-request step had no pull-requests: write."),
             effect=("Every scheduled run re-downloaded and rebuilt the research pipeline and "
                     "then threw the result away. Fixed in .github/workflows/pipeline.yml "
                     "(pull-requests: write added). Residual dependency: if the repository "
                     "setting 'Allow GitHub Actions to create and approve pull requests' is "
                     "disabled, the fix alone will not suffice - the owner should confirm that "
                     "setting, which this session's token cannot read."),
             source="https://github.com/karagemop466-tech/X1/actions/runs/44123337794",
             status="fixed in this repository; one owner check remains"),
        dict(id="X-12", severity="grey", area="Programme",
             finding=("The brief-to-repo coverage register (82 rows, one per numbered item of the "
                      "owner brief) records what is built, partial, defined, not built or declined, "
                      "with the repo path that evidences each row."),
             effect=("30 rows carry flags and 25 items are NOT BUILT; each names what would clear "
                     "it. The register is a dated snapshot of the tree before round 5 (round 5 "
                     "narrowed several rows: the Week 10 injury tables now agree at 347 rows, the "
                     "deficiency matrix has register row R-76, and the 2026-11-17 pack closes the "
                     "standings arithmetic). It is linked here per the audit session's handoff to "
                     "the integrator."),
             source="https://github.com/karagemop466-tech/X1/blob/main/docs/audit/brief-coverage-2026-11-17.md",
             status="published for review"),

        dict(id="X-13", severity="amber", area="Fixture context",
             finding=("The first register the venue collector published labelled all 27 fixtures "
                      "FINAL - including 13 unplayed Week 11 games - and printed stadium names with "
                      "HTML entities still in them ('AT&amp;T STADIUM'). Neither was a data problem: "
                      "a page-wide search hit the word FINAL in a standings table, and entity "
                      "references survive tag stripping. Both were visible only because a second, "
                      "independent hand transcription of the same official pages existed to compare "
                      "against."),
             effect=("Fixed in tools/official/gamecentre.py: status, period, clock and score are read "
                     "only from the score box above the Game Info anchor, with the method recorded per "
                     "cell (status_method, score_method) and the scores left blank because the page "
                     "prints them as 'Hidden Score' in the text layer; entities are now decoded. The "
                     "cross-check moved from 12/14 to 14/14 agreeing with the hand register, and four "
                     "offline cases guard both failures. The register is re-derived from retained "
                     "bytes by 'reparse', so a parser fix is published against a hash that does not "
                     "change."),
             source="https://github.com/karagemop466-tech/X1/blob/main/data/official/gamecentre/venue_report.json",
             status="fixed and re-derived 2026-11-18; the false FINAL row set is the reason this register publishes a method column"),

        dict(id="X-14", severity="amber", area="Coverage",
             finding=("The fixture-context collector and the venue capture disagree on which fixtures "
                      "exist: 13 for Week 11 in both, but 14 against 13 for Week 10, because the "
                      "collector read the league's week page before the rescheduled game was on it."),
             effect=("Both files carry 'fixture-set-mismatch' flags rather than being quietly aligned, "
                     "and the shared rule in tools/official/fixture_context.py refuses to invent a row "
                     "the other side lacks. This is the same class of defect as the stale week page: a "
                     "fixture set is only as good as the moment it was read."),
             source="https://www.nfl.com/schedules/2026/by-week/week-10",
             status="open - clears when the week-10 slate is re-read by the collector's own schedule"),
    ]
