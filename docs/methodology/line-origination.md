# Line origination — how to make our own numbers instead of copying the market

**Scope.** This document specifies *how* to originate a line. It deliberately publishes **no
prices**. A number is only published after it is produced by a registered model version on a
frozen, licensed input snapshot and passes the gates in `validation-gates.md`. Anything else is a
guess with a decimal point.

---

## 1. The three numbers you must never confuse

| Number | What it is | Where it comes from |
|---|---|---|
| **Fair line** | Our probability converted to odds with **zero** margin (`1/p`). | Our model |
| **Market line** | A bookmaker's price, which **contains** margin (vig). | A licensed, timestamped quote |
| **Executable line** | What we could actually get at a stated book, limit and time. | Same quote, plus limits and rules |

The market line is a **benchmark, not an input**. If we feed the market into the model and then
"beat" the market, we have measured nothing but our own leakage.

## 2. Required pipeline (every strategy, no exceptions)

```
freeze inputs (as-of timestamp)
   → estimate a full outcome distribution
   → convert to fair odds (zero margin)
   → compare with a market quote of the SAME market/side/rules
   → log the forecast BEFORE kickoff (including passes)
   → grade after settlement
   → score only inside the registered test window
```

Failure at any arrow means the strategy is **not scored**. An unscored strategy is not a losing
strategy; it is an *unknown* one.

### 2.1 Converting a probability to a price

For a binary event with probability *p*:

- fair decimal odds = `1 / p`
- fair American odds = `-100·p/(1-p)` when *p* > 0.5, else `+100·(1-p)/p`
- an implied probability of a quoted price is `1 / decimal_odds`, and **always includes margin**

A spread or total is *not* a single probability. It needs a distribution:
`P(home wins by ≥ k)` and `P(push)` come from a modeled margin distribution, not a point estimate.

### 2.2 Why point estimates lie

Football scoring is discrete and low-frequency relative to basketball; a "projected 24.3–21.1"
is not a margin distribution. Model the **margin** (or total) as a distribution with an explicit
variance term, then read off:
`P(cover)`, `P(push)`, and the probability needed to price any alternate line. Without a variance
term you cannot price a 3.5 when the number is 3, and that difference is exactly where thin edges live.

## 3. Signal families to evaluate (each is a hypothesis, not an edge)

| # | Signal family | Direction of hypothesis | Data it needs | Cheap first test |
|---|---|---|---|---|
| S1 | **Opponent-adjusted efficiency** | Beating good defenses predicts better than raw yards | Play-by-play, opponent strength | Rolling regression → out-of-sample log-loss vs. a neutral baseline |
| S2 | **Availability shock** | Losing a *listed starter* moves the line more than the market adjusts | Official injury report + club depth chart + snap counts | Event study: line move vs. report timing |
| S3 | **Depth fragility** | Teams whose 2nd/3rd string is already playing degrade faster when a starter falls | Season-long snap-share concentration | Interaction term: starter lost × existing snap-share deficit |
| S4 | **Rest and travel** | Short weeks and west-east travel cost points | Official schedule + venues | Fixed effects with rest buckets |
| S5 | **Officiating crew tendency** | Penalty rates persist by crew | Official game books | Persistence test (year *t* → *t*+1) |
| S6 | **Weather** | Wind suppresses totals more than rain | Venue + archived weather | Sub-sample conditional effects |
| S7 | **Market movement** | Information arrives in price | Licensed quote history | Benchmark only — never a model input |

**S2 and S3 are the ones this repo is uniquely positioned to attack**, because it already carries
the official injury report and club depth charts with per-row sources. They are also the most likely
to be *mis-modeled* by the market, which is the only reason they could be profitable.

## 4. The availability signal, defined precisely

For player *i* on team *T* at week *w*:

```
avail_i     ∈ {full, limited, dnp}          # official practice status
designation_i ∈ {-, questionable, doubtful, out}   # official game status
depth_rank_i = rank on the club's published chart  # 1 = column 1
snap_share_i = trailing 4-game offensive/defensive snap share   # licensed data needed

starter_at_risk = (depth_rank_i == 1) AND (designation_i != "-")
replacement = the player printed directly behind i on the same chart line
```

`replacement` is **printed**, not guessed. That is why the depth chart is stored verbatim: any
reviewer can see whether "next man up" is a genuine claim or an invention.

The team-level feature is a **weighted** deficit:

```
deficit_T = Σ_i  w_i · 1[starter_at_risk_i]        # w_i from snap_share, NOT from opinion
```

`w_i` requires licensed snap data. **Until that license exists, this feature cannot be computed**,
and publishing a version of it with hand-guessed weights would be fabrication wearing a formula.

## 5. Player prop lines

A prop is an over/under on a counting stat (yards, catches, touchdowns). Origination needs:

1. **Opportunity model** — routes run, targets, carries, red-zone snaps. Opportunity precedes production.
2. **Role model** — the probability the player is on the field for the role the line assumes.
   Depth chart and injury designation drive this; that is signal S2 again.
3. **Efficiency model** — yards per route, yards per carry, adjusted for opponent.
4. **Distribution** — count stats are over-dispersed; use a negative-binomial-style model, not a Poisson.
   Pricing an 0.5-reception line with a Poisson assumption will systematically misprice it.
5. **Push handling** — a whole-number line can push. A prop with a push has a third outcome and
   cannot be priced as a coin flip.

## 6. The three bet shapes, and why they are different problems

| Shape | Core difficulty | What kills it |
|---|---|---|
| **Single bet** | Estimating one probability accurately | Slow, tiny edge; high variance |
| **Parlay (cross-game)** | Legs are usually near-independent, so the book's margin compounds | Margin multiplication; no diversification benefit |
| **Same-game parlay / prop combo** | Legs are **dependent**; a naive product is badly wrong | Assuming independence; correlated legs are priced punitively |

The correlation work for shapes 2 and 3 lives in `correlation.md`. The short version: at −110 a
single leg carries a 4.55% hold, two legs ≈8.9%, and five legs ≈**20.75%** (about **4.6×** one leg), so parlay
strategies must clear a materially higher skill bar to be worth anything.

## 7. What we can and cannot claim today

| Claim | Status |
|---|---|
| We can identify officially-listed starters on the Week 10 injury report | **Yes** — see the Availability page; 35 rows derived from official + club sources |
| We can say how much a starter's absence is worth in points | **No** — needs licensed snap counts and historical outcomes |
| We can price a fair line | **No** — needs a licensed quote feed to compare against |
| We can rank strategies by skill | **No** — needs logged forecasts and a settled test window |
| We can state a correlation between two legs | **No** — needs joint historical results; see `correlation.md` |

Those "No" rows are the real work queue, and they are listed as open decisions in the
Decision Register rather than papered over.

## 8. Origination order and the three-column publish rule (T12/T13)

**Order (pre-registered):** the **side first, then the total, then the moneyline**
(`ORIGINATION_ORDER` in `code/build_lines.py`, asserted against the emitted column order at
write time). The order is not cosmetic: the moneyline is *derived* from the side's win
probability `p_home`, so originating it before the side would mean pricing it from something
other than our own line. The total is computed between the two because it depends on neither.

**Publish rule:** for every market we originate, three values ship as three separate columns —
never merged, never only-difference:

| Market | Fair line (model) | Market line (benchmark) | Difference |
|---|---|---|---|
| Side / spread | `x1_spread_away` | `market_spread_away` | `edge_spread_away` (pts, market − model) |
| Total | `x1_total` | `market_total` | `edge_total` (pts, model − market) |
| Moneyline | `x1_ml_away`, `x1_ml_home` | `market_ml_away`, `market_ml_home` | `edge_ml_prob_away`, `edge_ml_prob_home` (percentage points, model probability − raw market-implied probability, vig included on the market side) |

Conventions and caveats a reader must know:

- The spread columns carry the **signed game line**: positive = home favoured, negative =
  away favoured (nflverse `DATASETS.md`). This number is numerically identical to the
  away-team handicap, which is why the legacy `…_away` column names survived; the name is a
  cosmetic misnomer, recorded as a grey note for reviewers, not a data error.
- Moneyline differences are in **probability points**, because a difference between two
  American-odds numbers is not a measurable quantity. The market side of the difference is
  the *raw implied* probability, vig included — it is not a de-vigged fair price, and no page
  presents it as one.
- Market lines are a **third-party benchmark** (nflverse mirror), never official: no NFL or
  club source publishes betting prices (flag F-06, question Q-02). Blank market cells mean
  the source published no line for that game; they are never filled.
- Opening versus closing prices for these markets live in the price-snapshot store
  (`docs/methodology/price-snapshots.md`), which is a separate file with its own tier rules.
