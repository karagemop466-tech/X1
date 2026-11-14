# Availability & depth fragility — tracking injuries and 2nd/3rd/4th-string exposure

The requirement: track injuries, and know when defenses or offenses are running backups because
starters are out. This document defines what is **verifiable**, what is **not**, and the model that
would be built on top once the missing data exists.

---

## 1. What the official record actually gives you

Source: `https://www.nfl.com/injuries/league/2026/reg10` (official NFL injury report, retrieved 2026-11-14).

Per player it prints exactly five things: **player, position, injury, practice status, game status**.
Practice status is one of three values; game status is one of four (Out / Doubtful / Questionable / blank).

What it does **not** print:

- ❌ depth-chart rank — no "starter" or "backup" label anywhere in the report
- ❌ snap percentage or usage
- ❌ expected games missed
- ❌ any severity or impact estimate

This is the single most important finding of the whole availability exercise: **"2nd-string
replacements" cannot be read off the official injury report.** Anyone claiming otherwise is
importing a guess.

## 2. Where depth information does exist — and its exact status

| Source | Exists? | Status |
|---|---|---|
| League-wide official depth chart on nfl.com | **No** | Not published |
| Each club's own depth chart on its own site | **Yes** | Published by the club, routinely labelled *unofficial* |
| Aggregator depth charts (Lineups, ESPN, etc.) | Yes | **Not official** — out of scope for a verified row |

Two clubs state the status of their own chart in print:

- Detroit: *"2026 Unofficial Depth Chart Compiled by Lions Football Communications"*
- Green Bay: *"Unofficial, Nov. 10, 2026"*

So the verification tier for a depth row is **"club-published, self-described unofficial"**. It is
stronger than a reporter's guess and weaker than a league ruling. The site labels it exactly that way.

## 3. The join this repo performs (and its limits)

`tools/build_availability.py` joins the two sources mechanically:

```
listed_starter = 1  ⟺  the club's chart prints the player in column 1 of a position
```

Nothing else sets that flag. If a player does not appear on the club's published chart, the depth
fields stay **blank** and the row is marked `not listed on club depth chart` — it is *not* silently
treated as a backup.

Current pilot coverage: **5 of 32 clubs** (BUF, SEA, DET, GB, BAL) — chosen because they play
Week 10 games with material injury news. The remaining 27 clubs are a declared coverage gap.

## 4. The deficiency model (specified now, computable later)

### 4.1 Offense vs. defense must be scored separately

| Unit | Why different |
|---|---|
| Offense | Replacement quality is dominated by the **quarterback** and the **left side of the line**; skill-position depth is comparatively fungible |
| Defense | Replacement quality is dominated by **coverage vs. pass rush**; losing a CB1 in a man-heavy scheme is not the same as losing a run-stuffing DT |

A single "team health score" that adds these together is not a model, it is an average of unrelated
things. The site therefore reports offense and defense separately.

### 4.2 Snap-share concentration (the "already thin" detector)

The requirement mentions 2nd, 3rd and 4th string. A team already playing backups is more fragile
than a team with a healthy starter because the next injury has nowhere to fall.

```
For position group g on team T:
  HHI_g = Σ_i (snap_share_i)²          # Herfindahl concentration of snaps
  fragility_g = 1 − HHI_g
```

A unit with one player taking 95% of snaps has `HHI ≈ 0.90` and low fragility; a rotation with four
players at 25% each has `HHI = 0.25` and high fragility. The metric is neutral about *quality* —
it reports structural exposure, which is what the requirement actually asks for.

**Requires licensed snap counts.** Not available in this repo. No fragility value is published.

### 4.3 Shadow depth score

Once snap data and a historical outcome panel exist:

```
Δ expected points ≈ β_qb·1[QB1 out] + β_lt·1[LT1 out] + Σ_c β_c·Δsnap_share_c
```

`β` is estimated out-of-sample, per unit, with intervals. Two rules:

1. **No hand-set weights.** A weight of "0.75 for the QB" typed by a human is fiction.
2. **No double counting.** If QB1 is out *and* his backup is also on the report, the feature is the
   expected starter, not the sum of both absences.

## 5. Sample of what the pilot already establishes (all rows sourced)

Nine **listed starters** are ruled out or doubtful for Week 10 in the five pilot clubs, and eight are
officially **Out**:

| Team | Player | Pos | Injury | Status |
|---|---|---|---|---|
| SEA | Sam Darnold | QB | Ribs, Quadricep | Out |
| SEA | Charles Cross | T | Ankle | Out |
| SEA | Quenton Nelson | G | Knee | Out |
| SEA | Leonard Williams | DT | Stinger | Out |
| GB | Josh Jacobs | RB | Finger | Out |
| GB | Sean Rhyan | C | Ankle | Out |
| GB | Zaire Franklin | LB | Shin | Doubtful |
| DET | Cade Mays | C | Ankle | Out |
| DET | D.J. Reed | CB | Hip | Out |

Independently corroborated at the league level: NFL.com reports Drew Lock starting for Seattle in
Darnold's place (`nfl.com/news/drew-lock-no-injury-designation-seahawks-raiders`), and that Lamar
Jackson was placed on injured reserve on 2026-11-05
(`nfl.com/news/nfl-news-roundup-latest-league-updates-from-thursday-nov-5`).

**What we do not claim:** that any of these absences is worth a specific number of points. That
number needs the panel in §4.3.

## 6. Known failure modes to guard against

| Failure | Guard |
|---|---|
| Practice status ≠ game status | Track **both**; a "full practice, questionable" player is not the same as "DNP, out" |
| Report timing | Retain retrieval timestamp; the report mutates through the week |
| "Questionable" is roughly a coin flip historically | Never treat questionable as available or as out without a historical conversion rate |
| Coach-speak vs. designation | The official designation wins; press conference optimism is not a source |
| Depth chart staleness | Club charts lag trades, IR and activations; record the chart date when the club prints one |
| Position vocabulary differences | Clubs print `EDGE`, `RUSH`, `SAM`, `NB`, `DB`; do not merge them without a documented map |

## 7. Roadmap to a fully-computable model

| Step | Needs | Status |
|---|---|---|
| 1. All 32 club charts, weekly, timestamped | Club sites (33 remaining rows per week) | **Not started** — 5 clubs done |
| 2. Licensed snap counts | Data license | **Blocked** (Q-04) |
| 3. Historical outcome panel | Licensed play-by-play + closing lines | **Blocked** (Q-02) |
| 4. Fit β per unit, out-of-sample | 2 and 3 | **Blocked** |
| 5. Publish fragility + shadow scores | 4 plus Gate 3 calibration | **Blocked** |

Blocked is the honest status. Each blocked step is a decision on the Decision Register, not a
missing line of code.
