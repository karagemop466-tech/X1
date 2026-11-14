# Coordination board

Session: `arena/226be516-x1` (current Arena branch; branch name is fixed for this session)

## Tasks

| Task | Status | Owner | File scope |
|---|---|---|---|
| NFL research, requirements, decision framework, and static site | in progress | `arena/226be516-x1` | `COORDINATION.md`, `README.md`, `index.html`, `assets/`, `pages/`, `scripts/`, `.github/`, `.gitignore` |

## Log

- 2026-11-14 — Claimed the NFL research/site task. No coordination board existed. Initial repository contained only a four-byte `README.md`; no other session claims were present.
- Plan: build a source-linked GitHub Pages site that distinguishes verified official-source facts from proposals, unknowns, and unverified items. No fabricated NFL data, lines, injuries, or performance claims will be published.
- 2026-11-14 — Verified primary pages by opening them directly: NFL injury reports (`https://www.nfl.com/injuries/`), player stats (`https://www.nfl.com/stats/player-stats/`), schedules (`https://www.nfl.com/schedules/`), team directory (`https://www.nfl.com/teams/`), an NFL team roster (`https://www.nfl.com/teams/los-angeles-rams/roster`), NFL Next Gen Stats glossary (`https://nextgenstats.nfl.com/glossary`), NFL Football Operations tracking overview (`https://operations.nfl.com/game-operations-logistics/technology/performance-tracking-data-next-gen-stats`), 2026 NFL rulebook (`https://operations.nfl.com/rules-officiating/2026-nfl-rulebook`), and NFL Big Data Bowl (`https://operations.nfl.com/programs-initiatives/innovation/big-data-bowl/`). NIST correlation glossary and confidence-limits material were opened at `https://www.itl.nist.gov/div898/handbook/glossary.htm` and `https://www.itl.nist.gov/div898/handbook/eda/section3/eda352.htm` for statistical terminology/uncertainty. Limitations and unknowns are recorded on the site's Flagged for Review page.
- Verification: `python3 scripts/verify_site.py` passed (all 5 HTML pages; internal links resolve; each data-table row has an official HTTPS source link). `git diff --check` passed. No NFL results, injury values, odds, strategy estimates, or correlations were copied into the site.
- Coordination claim was committed as `82ade50` and pushed to `arena/226be516-x1`. `git pull --rebase origin arena/226be516-x1` initially failed because the branch did not yet exist on origin; after that failed pre-push sync attempt, the initial claim branch was pushed with upstream configured. Continue to use the current branch only.
