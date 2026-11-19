# Public/private release boundary — decision brief

**Decision: the private-data requirement is not met.** A passing Pages link check is not a privacy or source-rights check. Keep new raw captures and player-level extracts out of public Git and Pages until their source-specific use is approved. This memo does not determine whether any existing publication is legally permitted.

## Evidence checked in the release tree

| Finding | Repository evidence | Official source for review |
|---|---|---|
| The repository itself is public (`isPrivate: false`); omitting a file from Pages does not privatize Git copies. | `gh repo view --json isPrivate`; `git ls-files data/raw` returned 13 tracked paths. No claim is made here that all 13 are NFL-sourced or subject to the same terms. | [GitHub repository visibility](https://docs.github.com/en/repositories/creating-and-managing-repositories/about-repositories#about-repository-visibility) |
| The upload assembly copies named injury-report records as CSV through two wildcard rules. | `.github/workflows/pages.yml`: `data/processed/*.csv` and `data/console/*.csv`; inspected the headers and first records of `injuries_current.csv` and `injuries_week10.csv`. Both include player and report fields. | [NFL Week 10 injury report](https://www.nfl.com/injuries/league/2026/reg10) |
| Redacting downloads alone is insufficient; generated HTML and embedded JSON also need review. | Pages recursively copies multiple generated directories and `archive/`; the link crawl checks references, not payload classification. | [GitHub Pages configuration](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) |
| Official Game Book reuse is a distinct approval question, not implied by public access. | The [existing source review](official-gamebook-source-review.md) inspected one PDF and recorded its explicit written-permission notice. No new Game Book records were extracted or verified by this audit. | [NFL Game Center](https://www.nfl.com/games/patriots-at-lions-2026-reg-10) · [NFL-hosted Game Book](https://static.www.nfl.com/image/upload/v1794764592/gamecenter/ab582c2f-4feb-11f1-abca-2c54536568a9.pdf) |

## Questions to resolve before approving a change

| Question | Current answer | Next check and proposed gate | Official reference |
|---|---|---|---|
| Which source families may be fetched, retained, and republished? | No approval established by this audit. Treat capture, internal extraction, and publication as separate permissions. | Record an applicable terms version or written approval and reviewer decision for **every** source class; zero unclassified classes in a release. | [NFL terms](https://www.nfl.com/legal/terms) |
| Can exact prior evidence be replayed without exposing it? | Not established by the current public assembly. | Test private, access-controlled storage with immutable objects, fetch UTC, source URL, hash and parser version. Prove replay for every required source on two successive capture days, and test a simulated stale source and hash mismatch. | [NFL injury reports](https://www.nfl.com/injuries/) |
| How do we demonstrate the public boundary? | Current crawl: 188 HTML pages and 5,300 local links resolve; that says nothing about export eligibility. | Build from an exact, reviewed artifact allowlist; reject unknown files and inspect embedded row-level payloads, archives, and downloadable exports. Require zero disallowed payloads and zero broken links in the same staged tree. | [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) |
| Does removing the export make existing copies private? | No. It only changes future releases. | Inventory Git history, Pages artifacts, and other distribution paths; agree on remediation before claiming removal. No history rewrite proposed on this branch. | [GitHub guidance on removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) |

**Suggested order:** inventory and classify first; migrate capture and verify replay second; regenerate approved public-only outputs and run release gates third. Integration request: add a Flagged for Review entry and link this memo from the Suggestions section. Do not mark the private split delivered based on this review.
