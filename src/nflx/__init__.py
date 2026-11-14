"""NFL research toolkit.

A dependency-free (stdlib-only) collection and analysis pipeline for official
NFL data.

Design rules enforced throughout this package:

* Only official NFL-controlled endpoints are read. Every record carries the
  exact URL it came from plus the retrieval timestamp, so any row on the site
  can be traced back to a primary source.
* Nothing is inferred. If a value cannot be read from the source it is left
  ``None`` (rendered blank on the site) and the row is flagged for review.
* Pure stdlib so it runs on a GitHub Actions runner with no install step.
"""

__version__ = "1.0.0"
