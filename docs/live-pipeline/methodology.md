# Methodology

How every number on the site is produced, and what each one does and does not mean.

## 1. Collection

The pipeline (`pipeline/`) uses only the Python standard library. It fetches a page,
parses it with `html.parser`, and reads values out of the HTML tables the page
server-renders. Nothing is scraped from a rendered browser session and nothing needs an
API key.

Each page is turned into an ordered event stream — headings, links, loose text and
tables — because some official tables carry no identifying column. The injury report, for
example, prints a club name above each table and no club column inside it, so the club has
to be recovered from the document order and then cross-checked.

## 2. Provenance

Every row written by the pipeline carries:

| Field | Meaning |
|---|---|
| `_source_url` | the official page the values were read from |
| `_source_label` | human-readable description of that page |
| `_source_org` | `NFL`, `Club — <team>`, `Derived`, or `Project brief` |
| `_retrieved_at` | UTC timestamp of the pull |
| `_verified` | true only when no field is blank and no flag is set |
| `_unverified` | the fields the source left blank, if any |
| `_flags` | integrity notes recorded while parsing |

`scripts/verify_data.py` re-checks all of this on every run and fails on a row whose
source host is not on the official allow-list.

## 3. Standings consistency check

For all 32 clubs the pipeline checks three relationships the league's own page implies:

- home record + road record = overall W-L-T;
- points for − points against = net points;
- win percentage = (W + ½T) ÷ games, within a 0.02 tolerance.

The pass/fail count is published on the standings page. This is what lets the four
unlabelled standings columns (Div %, Conf %, Non-Conf, Last 5) be used at all: their
order is validated by arithmetic even though the 2026 page prints no header row.

## 4. Depth charts

Club sites are the only official source for depth order. The league's own teams page is
the authority for which domain is a club's official site, so the pipeline reads that page
rather than trusting a fixed list.

A club prints several rows with the same position label (three WR rows, two CB rows, and
so on). Each is treated as its own **slot**, numbered in the order the club prints them,
so "2nd string" always means second within that slot.

Where a club's page cannot be fetched or parses to no rows, the club is recorded as
unreachable with its HTTP attempt log. It is never backfilled from an unofficial source.

## 5. Deficiency watch

Derived, not scraped. For each slot:

- the **starter** is column 1 of the club's own depth chart;
- the **replacement** is the next column whose player is not ruled Out on the league's
  injury report;
- `replacement_depth` is that player's string number — 2 = 2nd string, 4 = 4th string;
- `severity` is 3 for Out, 2 for Doubtful, 1 for Questionable, 0 for not listed.

Every row links to both official sources.

## 6. Correlations

Pearson product-moment correlation across the 32 clubs:

```
r = Σ(xᵢ − x̄)(yᵢ − ȳ) / √( Σ(xᵢ − x̄)² · Σ(yᵢ − ȳ)² )
```

Two-sided p-value from the t-distribution with n − 2 degrees of freedom:

```
t = r · √( df / (1 − r²) ),   df = n − 2
p = I_{df/(df+t²)}( df/2, 1/2 )
```

evaluated with the regularised incomplete beta function implemented in
`pipeline/model_correlation.py`.

Inputs are the official standings and the nine official team-stats tables, joined on club.
Pairs are published when |r| ≥ 0.40 or when either side is points for, points against, net
points, wins or win percentage. Pairs at |r| ≥ 0.99 are dropped as duplicates.

**Limits.** n = 32 team-seasons is a small sample, so these are weak estimates. They are
team-level associations: they are not game-level correlations, they are not the quantity a
same-game parlay price needs, and they say nothing about causation.

## 7. Originating lines, and why some tables are empty

Originating a line means producing a fair number from verified inputs. Scoring, net
points, home/road splits, injuries and depth are all available from official pages;
market prices and game results are not.

No official NFL or club source publishes spreads, totals, moneylines or player-prop
prices, and the league's schedule and score pages return no server-rendered table. So:

- the **market lines** table ships empty;
- the **leaderboard** result columns (graded bets, ROI, CLV, t-stat, p-value) stay blank;
- gates that depend on outcomes (sample size, closing line value, skill test, demotion)
  are defined but left **unenforced**, because an invented threshold looks like evidence
  and is not.

## 8. Removing luck

Four mechanisms, in order:

1. **Pre-registration** (G-02) — hypothesis, inputs and staking recorded before grading.
2. **Sample size before promotion** (G-03) — threshold pending Q-07.
3. **Beat the price, not just the game** (G-12) — the test is whether the hit rate beats
   the break-even rate implied by the price.
4. **Multiple-comparisons correction** (G-14) — cap the number of live strategies and
   correct significance accordingly.

Closing line value (G-11) is the preferred scoring measure because it evaluates a signal
without waiting for the result — but it needs a price feed, which no official source
provides.

## 9. Repo review

`pipeline/repo_review.py` hashes and line-counts every tracked file and applies fixed
mechanical rules (empty file, missing trailing newline, TODO/FIXME, placeholder value,
hardcoded-secret shape, bare `except:`, debug print, oversized file or line, unclosed
HTML). Findings are reproducible and are published on the Repo Review page with a link to
each file.
