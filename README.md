# NFL Decision Lab

A source-first research dashboard and proposed validation framework for NFL forecasting and odds-making. The repository starts with no historical data, market odds, model code, or injury feed; therefore it publishes **no picks, original lines, performance claims, current player records, or numerical correlations**. Unknown values are deliberately left blank until they can be verified from suitable sources.

## Browse the site

- [Executive summary](index.html)
- [Requirements & decision questions](pages/requirements.html)
- [Strategy proposals & validation gates](pages/strategies.html)
- [Data source register](pages/sources.html)
- [Flagged for review](pages/review.html)

## Local preview

Open `index.html` in a browser, or run `python3 -m http.server 8000` from the repository root.

## Publishing

The site is a static GitHub Pages site. A GitHub Actions workflow under `.github/workflows/pages.yml` publishes the repository root when the workflow is enabled for Pages in repository settings.

## Verification boundary

Research was checked against the linked primary NFL / NFL Football Operations / Next Gen Stats pages and NIST reference material on 2026-11-14. NFL pages are live and may change; links are provided so each item can be reviewed at the source. The strategy designs are **proposals, not empirically validated findings**. See [Flagged for review](pages/review.html) for missing inputs and irregularities. No betting advice or guarantee is made.
