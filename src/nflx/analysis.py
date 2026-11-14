"""Derived datasets: depth analysis and correlation measurement.

This module turns the raw official records into the two analytical datasets the
site publishes:

``depth.json``
    Unavailable starters mapped to the replacement who takes the slot.
``correlation.json``
    Measured correlations between game-level measures, the relationships that
    cannot be measured without a price feed, and the joint probabilities for
    candidate two-leg combinations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .correlation import correlation_matrix, joint_probability, unmeasured_correlations
from .depth import analyse_deficiency, build_depth_charts, summarize_deficiency
from .sources import SOURCES


def _read(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _records(dataset: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not dataset:
        return []
    return list(dataset.get("records", []))


def build_depth(data_dir: Path, out_dir: Path) -> Dict[str, Any]:
    """Produce the depth-deficiency dataset."""
    injuries_dataset = _read(data_dir / "injuries.json")
    gamebooks_dataset = _read(data_dir / "gamebooks.json")

    injuries = _records(injuries_dataset)
    gamebooks = _records(gamebooks_dataset)

    if not injuries or not gamebooks:
        payload = {
            "provenance": {
                "source_key": "injuries_current",
                "source_url": SOURCES["injuries_current"].url,
                "retrieved_at": "",
                "record_count": 0,
                "notes": [
                    "Depth analysis requires both the injury report and at least "
                    "one parsed official game book. One or both were unavailable "
                    "at the time of this run, so no deficiency is asserted."
                ],
            },
            "records": [],
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "depth.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    charts = build_depth_charts(gamebooks)
    records = analyse_deficiency(
        injuries,
        charts,
        source_url=SOURCES["injuries_current"].url,
        source_label=SOURCES["injuries_current"].title,
        retrieved_at=(injuries_dataset or {}).get("provenance", {}).get("retrieved_at", ""),
    )
    summary = summarize_deficiency(records)
    provenance = {
        "source_key": "injuries_current",
        "source_url": SOURCES["injuries_current"].url,
        "retrieved_at": (injuries_dataset or {}).get("provenance", {}).get("retrieved_at", ""),
        "record_count": len(records),
        "notes": [
            f"Depth charts built from {len(gamebooks)} official game book(s).",
            f"Summary: {json.dumps(summary)}",
        ],
    }
    payload = {"provenance": provenance, "records": records, "summary": summary}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "depth.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# correlation
# ---------------------------------------------------------------------------
def _game_measures(gamebooks: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    """Extract game-level measures that can be correlated.

    Each measure is a list aligned across games. Values are taken only from
    official game-book fields; where a game lacks a field the entry is left
    empty and the correlation routine drops the pair rather than substituting.
    """
    visitor_points: List[Any] = []
    home_points: List[Any] = []
    total_points: List[Any] = []
    point_margin: List[Any] = []
    attendance: List[Any] = []
    game_length: List[Any] = []
    temperature: List[Any] = []

    for book in gamebooks:
        vp = book.get("visitor_points")
        hp = book.get("home_points")
        visitor_points.append(vp)
        home_points.append(hp)
        total_points.append((vp + hp) if (vp is not None and hp is not None) else None)
        point_margin.append((hp - vp) if (vp is not None and hp is not None) else None)
        attendance.append(book.get("attendance"))
        length = book.get("game_length")
        if length:
            try:
                parts = str(length).split(":")
                game_length.append(int(parts[0]) * 60 + int(parts[1]))
            except (ValueError, IndexError):
                game_length.append(None)
        else:
            game_length.append(None)
        temperature.append(book.get("temperature_f"))

    return {
        "visitor_points": visitor_points,
        "home_points": home_points,
        "total_points": total_points,
        "home_point_margin": point_margin,
        "attendance": attendance,
        "game_length_seconds": game_length,
        "temperature_f": temperature,
    }


UNMEASURED_SPECS = [
    {
        "id": "strategy_vs_closing_line",
        "label": "Strategy result vs closing-line value",
        "scope": "strategy",
        "metric": "clv",
        "note": (
            "Requires a licensed, timestamped opening-to-closing price history. "
            "The league publishes no such series, so no value is asserted and "
            "gate G5 cannot be evaluated."
        ),
    },
    {
        "id": "strategy_vs_market_price",
        "label": "Strategy edge vs market-implied probability",
        "scope": "strategy",
        "metric": "pearson",
        "note": (
            "Requires a timestamped market-implied probability series matched to "
            "each decision. Not available from an official source, so no "
            "correlation is claimed."
        ),
    },
    {
        "id": "player_prop_vs_team_total",
        "label": "Player prop outcome vs team total",
        "scope": "prop",
        "metric": "pearson",
        "note": (
            "The pairing is well defined, but a per-decision price is needed to "
            "turn the historical relationship into an edge. The historical "
            "relationship itself is measurable once the full game-book set is "
            "collected."
        ),
    },
    {
        "id": "practice_status_vs_game_status",
        "label": "Practice participation vs game designation",
        "scope": "availability",
        "metric": "categorical",
        "note": (
            "The official report publishes both designations but no conversion "
            "table, and the league's historical archive is not machine-readable "
            "in a citable form. No percentage conversion is asserted."
        ),
    },
]


def build_correlation(data_dir: Path, out_dir: Path) -> Dict[str, Any]:
    """Produce the correlation dataset."""
    gamebooks_dataset = _read(data_dir / "gamebooks.json")
    gamebooks = _records(gamebooks_dataset)

    measures = _game_measures(gamebooks)
    source_url = SOURCES["game_book"].url
    source_label = SOURCES["game_book"].title

    if gamebooks:
        measured = correlation_matrix(
            gamebooks, measures, source_url=source_url, source_label=source_label
        )
    else:
        measured = []

    unmeasured = unmeasured_correlations(UNMEASURED_SPECS, source_url, source_label)

    # Joint probabilities for candidate two-leg structures.
    joint_specs = [
        {
            "id": "JP-1",
            "label": "Total points vs home point margin",
            "measure_a": "total_points",
            "measure_b": "home_point_margin",
        },
        {
            "id": "JP-2",
            "label": "Visitor points vs home point margin",
            "measure_a": "visitor_points",
            "measure_b": "home_point_margin",
        },
        {
            "id": "JP-3",
            "label": "Attendance vs total points",
            "measure_a": "attendance",
            "measure_b": "total_points",
        },
    ]
    joint_rows: List[Dict[str, Any]] = []
    for spec in joint_specs:
        xs = measures.get(spec["measure_a"], [])
        ys = measures.get(spec["measure_b"], [])
        pairs = [
            (x, y)
            for x, y in zip(xs, ys)
            if isinstance(x, (int, float)) and isinstance(y, (int, float))
        ]
        n = len(pairs)
        if n < 3:
            joint_rows.append(
                {
                    "id": spec["id"],
                    "label": spec["label"],
                    "p_a": None,
                    "p_b": None,
                    "correlation": None,
                    "joint_probability": None,
                    "independent_joint_probability": None,
                    "n_observations": n,
                    "correlation_ci_low": None,
                    "correlation_ci_high": None,
                    "method": "gaussian-copula",
                    "status": "insufficient_data",
                    "note": (
                        f"Only {n} usable observation(s); the relationship cannot "
                        "be measured from the current official sample."
                    ),
                    "source_url": source_url,
                    "source_label": source_label,
                }
            )
            continue

        from .correlation import pearson

        rho = pearson([p[0] for p in pairs], [p[1] for p in pairs])
        mean_a = sum(p[0] for p in pairs) / n
        mean_b = sum(p[1] for p in pairs) / n
        p_a = _share_above(pairs, 0, mean_a)
        p_b = _share_above(pairs, 1, mean_b)
        joint = joint_probability(p_a, p_b, rho, n)
        row = joint.to_dict()
        row.update(
            {
                "id": spec["id"],
                "label": spec["label"],
                "source_url": source_url,
                "source_label": source_label,
            }
        )
        joint_rows.append(row)

    payload = {
        "provenance": {
            "source_key": "game_book",
            "source_url": source_url,
            "retrieved_at": (gamebooks_dataset or {}).get("provenance", {}).get("retrieved_at", ""),
            "record_count": len(measured),
            "notes": [
                f"Computed from {len(gamebooks)} official game book(s).",
                "Joint probabilities use a Gaussian copula; the independent "
                "product is shown alongside for comparison.",
            ],
        },
        "measured": measured,
        "unmeasured": unmeasured,
        "joint_probabilities": joint_rows,
        "evaluations": {},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "correlation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _share_above(pairs: List[Any], index: int, threshold: float) -> float:
    """Share of observations above a threshold, used as a leg probability."""
    if not pairs:
        return 0.0
    count = sum(1 for pair in pairs if pair[index] > threshold)
    return count / len(pairs)


def main(data_dir: Path, out_dir: Path) -> None:
    build_depth(data_dir, out_dir)
    build_correlation(data_dir, out_dir)


if __name__ == "__main__":
    import sys

    root = Path(sys.argv[1] if len(sys.argv) > 1 else "data/nfl")
    main(root, root)
