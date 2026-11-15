# Official NFL Game Book source feasibility and data-rights review

**Reviewed:** 2026-11-15 (UTC date; the page-fetch tool does not expose a trustworthy second-level retrieval timestamp).
**Scope:** one official 2026 Week 10 game-center page and the Game Book PDF linked from it. This is a source-feasibility check, not a 32-team or multi-season coverage audit.

## Decision

An NFL.com game center links to an NFL-hosted Game Book PDF. In the sampled PDF, the **Lineups**, **Substitutions**, **Did Not Play**, and **Not Active** sections are present. This is a promising official source for a book-listed lineup and game-day status evidence. It does **not** establish a player's depth rank, playing-time share, or snap count. Do not infer any of those from jersey number, roster order, the lineup list, or absence from the lineup.

The PDF also contains an explicit restriction on reuse. Until NFL terms or written permission are reviewed and recorded, the safe publication policy is **link to the official document only; do not put extracted player-level Game Book rows or the PDF itself in this public repository or GitHub Pages**. This is a conservative data-handling recommendation, not a legal determination.

## Official sources inspected

| Source | What was checked | Result and limit | Official link |
|---|---|---|---|
| NFL Game Center — New England at Detroit, 2026 REG Week 10 | The page's game information, venue labels, and the link labelled “Download Game Book (PDF)” | The Game Center links to the PDF below. Its page text labels the location `MUNICH` and the stadium `FC BAYERN MUNICH STADIUM`. Those strings are preserved as printed; they are not silently normalized. This is one fixture only. | [NFL.com Game Center](https://www.nfl.com/games/patriots-at-lions-2026-reg-10) |
| NFL Game Book PDF — same fixture | All seven parsed chunks returned by the official PDF fetch were inspected | The document is titled “National Football League Game Summary” and includes the sections listed above. The first-page venue string is `at Allianz Arena, Munich, Germany`; the game-center stadium string differs. The PDF says `Open Stadium on Natural Grass` and gives game-day weather, which is observed game-book information, not an NWS pre-kickoff forecast. | [NFL-hosted Game Book PDF](https://static.www.nfl.com/image/upload/v1794764592/gamecenter/ab582c2f-4feb-11f1-abca-2c54536568a9.pdf) |
| NFL schedule — Week 10 | Official schedule/game-center context for the sampled fixture | A schedule page is available, but this review does not claim that the one sampled Game Book represents every game, week, team, or historical season. | [NFL.com 2026 schedule](https://www.nfl.com/schedules/2026/REG/week/10) |

## Source capability and limits

| Requested evidence | What the sampled official document actually provides | Safe treatment | Source |
|---|---|---|---|
| Actual starters | A `Lineups` section divided into offense and defense, with positions and players as printed | If use is authorized, label this evidence `gamebook_listed_lineup`; do not relabel it as snap participation or a depth-chart rank. No player rows are reproduced in this memo. | [NFL Game Book PDF](https://static.www.nfl.com/image/upload/v1794764592/gamecenter/ab582c2f-4feb-11f1-abca-2c54536568a9.pdf) |
| Game-day status | Separate `Did Not Play` and `Not Active` headings are present | Preserve the source's distinct categories and original blanks. Do not merge them into one status or use absence from the injury report as evidence of availability. This one sample does not validate a league-wide parser. | [NFL Game Book PDF](https://static.www.nfl.com/image/upload/v1794764592/gamecenter/ab582c2f-4feb-11f1-abca-2c54536568a9.pdf) |
| Snap counts / playing time | No per-player snap-count field was found in the seven parsed chunks of this sampled PDF; it does contain team-level plays and individual statistical tables | Treat snap count as **not confirmed by this source sample**. Leave it blank; find and verify a separate official or authorized source before using snap share as a proxy. Do not infer snaps from box-score activity. | [NFL Game Book PDF](https://static.www.nfl.com/image/upload/v1794764592/gamecenter/ab582c2f-4feb-11f1-abca-2c54536568a9.pdf) |
| Depth order / replacement string | The sampled PDF contains lineups, not an ordinal 1st–4th string depth chart | Do not derive a backup rank from who did or did not start. Keep official club depth-chart slots, shared slots, and empty slots as separate evidence; do not use jersey number or lineup order as a rank. | [NFL Game Book PDF](https://static.www.nfl.com/image/upload/v1794764592/gamecenter/ab582c2f-4feb-11f1-abca-2c54536568a9.pdf) |
| Venue, roof/surface, weather | Game Center prints `MUNICH` and `FC BAYERN MUNICH STADIUM`; the PDF prints `Allianz Arena` and `Open Stadium on Natural Grass`, plus game-day weather | Preserve each official source's venue field separately and flag the name difference. Do not turn observed game-day weather into an NWS forecast feature or a pre-kickoff input. | [NFL.com Game Center](https://www.nfl.com/games/patriots-at-lions-2026-reg-10) · [NFL Game Book PDF](https://static.www.nfl.com/image/upload/v1794764592/gamecenter/ab582c2f-4feb-11f1-abca-2c54536568a9.pdf) |
| Permission / reuse | The PDF prints: “This summary and play-by-play is for the express purpose of assisting media in their coverage of the game; any other use of this material is prohibited without the written permission of the National Football League.” | No row-level Game Book data or PDF copy is committed or published by this session. Record written permission or reviewed terms before automating extraction or publishing derived outputs. | [NFL Game Book PDF](https://static.www.nfl.com/image/upload/v1794764592/gamecenter/ab582c2f-4feb-11f1-abca-2c54536568a9.pdf) |

## Capture integrity and outstanding gates

- The evidence above came from the official Game Center and the official PDF link it exposed, fetched on 2026-11-15. The fetch interface returned parsed text, **not the original PDF bytes**. No raw PDF was retained and no SHA-256 is available; this memo must not be treated as an immutable snapshot.
- Only one fixture was checked. Coverage across all 32 clubs, all games, past seasons, and the official inactive-list process remains unverified.
- The PDF’s reuse notice is explicit, but this review is not legal advice and does not determine whether any particular internal or derived use is permitted. A terms/permission decision remains a gate.
- The venue labels differ between two official NFL sources in this sample. Keep both source strings and flag the discrepancy; do not resolve it by assumption.
- The sample supports a future evidence design separating: report designation; gamebook-listed lineup; gamebook `Not Active` / `Did Not Play`; official depth-chart slot; and snap count (a different, as-yet-unverified source). Until source and permission gates clear, the affected player-level values stay blank and are not modeled.

## Recommended implementation path for the final integration

1. Keep the public site to links and permitted derived analysis. Do not add the sampled player rows to GitHub Pages.
2. Ask the appropriate rights owner to review the quoted Game Book notice and identify whether written authorization is required for the planned ingestion/use. Until then, no automated extraction.
3. If authorized, retain the raw PDF outside the public repository in an immutable store with fetch timestamp, source URL, content hash, parser version, and conflict flags; publish only fields covered by the authorization.
4. Use the `Lineups` and inactive evidence as named source fields, not as inferred depth rank or snap share. Require a separate source verification for snap counts and test coverage before any starter-proxy feature is built.
5. Preserve both venue labels when official sources disagree. Keep game-day observations separate from archived pregame forecasts.

**No player-level Game Book rows, derived player metrics, or PDF bytes are included in this repository change.**