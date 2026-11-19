import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.designation_calibration import clock, evaluate, official, verify_manifest


SOURCE = "https://www.nfl.com/test/evidence"
KICKOFF = "2026-11-19T15:00:00Z"


def report(player="A", designation="Questionable", captured_at="2026-11-19T12:00:00Z", **extra):
    row = {
        "season": "2026",
        "game_id": "game-1",
        "team_id": "T",
        "player_id": player,
        "source": SOURCE,
        "kickoff": KICKOFF,
        "captured_at": captured_at,
        "designation": designation,
    }
    row.update(extra)
    return row


def outcome(player="A", status="played", **extra):
    row = {
        "season": "2026",
        "game_id": "game-1",
        "team_id": "T",
        "player_id": player,
        "source": SOURCE,
        "game_book_status": status,
    }
    row.update(extra)
    return row


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_for(reports_path, outcomes_path, reports, outcomes):
    return {
        "complete_official_evidence": True,
        "official_sources_reviewed": True,
        "reviewed_by": "synthetic unit-test reviewer",
        "reviewed_at": "2026-11-19T12:00:00Z",
        "seasons": ["2026"],
        "team_ids_by_season": {"2026": [f"T{i:02d}" for i in range(32)]},
        "files": {
            "reports": {"sha256": digest(reports_path), "rows": len(reports)},
            "outcomes": {"sha256": digest(outcomes_path), "rows": len(outcomes)},
        },
    }


class CalibrationTests(unittest.TestCase):
    def test_status_counts_and_missingness_are_separate(self):
        reports = [report("A"), report("B"), report("C"), report("D")]
        results = evaluate(
            reports,
            [outcome("A", "played"), outcome("B", "active_dnp"), outcome("C", "inactive")],
        )
        result, = results
        self.assertEqual(result["reported"], 4)
        self.assertEqual(result["n"], 3)
        self.assertEqual(result["unmatched"], 1)
        self.assertEqual((result["played"], result["active_dnp"], result["inactive"]), (1, 1, 1))
        self.assertAlmostEqual(result["play_rate"], 1 / 3)
        self.assertEqual(len(result["wilson95"]), 2)
        self.assertLess(result["wilson95"][0], result["wilson95"][1])

    def test_latest_strictly_pre_kickoff_designation_wins(self):
        rows = [
            report("A", "Questionable", "2026-11-19T07:00:00-05:00"),
            report("A", "Doubtful", "2026-11-19T08:00:00-05:00"),
            # At and after kickoff must not overwrite the last pregame observation.
            report("A", "Out", "2026-11-19T15:00:00Z"),
            report("A", "invalid-postgame-value", "2026-11-19T16:00:00Z"),
        ]
        result, = evaluate(rows, [outcome("A", "played")])
        self.assertEqual(result["designation"], "Doubtful")
        self.assertEqual(result["reported"], 1)
        self.assertEqual(result["n"], 1)

    def test_explicit_clearance_removes_prior_designation(self):
        rows = [
            report("A", "Questionable", "2026-11-19T12:00:00Z"),
            report("A", "Cleared", "2026-11-19T14:00:00Z"),
        ]
        self.assertEqual(evaluate(rows, [outcome("A", "played")]), [])

    def test_conflicting_kickoffs_for_one_player_game_fail_closed(self):
        rows = [
            report("A", "Questionable", "2026-11-19T12:00:00Z"),
            report("A", "Doubtful", "2026-11-19T13:00:00Z", kickoff="2026-11-19T16:00:00Z"),
        ]
        with self.assertRaisesRegex(ValueError, "conflicting kickoff"):
            evaluate(rows, [outcome()])

    def test_duplicate_capture_and_duplicate_outcome_fail_closed(self):
        r = report()
        with self.assertRaisesRegex(ValueError, "duplicate player-game capture"):
            evaluate([r, dict(r)], [outcome()])
        with self.assertRaisesRegex(ValueError, "duplicate player-game outcome"):
            evaluate([r], [outcome(), outcome()])

    def test_invalid_status_designation_and_incomplete_identity_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            evaluate([report()], [outcome(status="unknown")])
        with self.assertRaisesRegex(ValueError, "invalid designation"):
            evaluate([report(designation="Probable")], [])
        with self.assertRaisesRegex(ValueError, "not a blank"):
            evaluate([report(designation="")], [])
        with self.assertRaisesRegex(ValueError, "incomplete evidence key"):
            evaluate([dict(report(), player_id="")], [])

    def test_manifest_binds_synthetic_files_to_complete_source_review_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_path = Path(tmp) / "reports.csv"
            outcomes_path = Path(tmp) / "outcomes.csv"
            reports = [report(team_id="T00")]
            outcomes = [outcome(team_id="T00")]
            write_csv(reports_path, reports)
            write_csv(outcomes_path, outcomes)
            manifest = manifest_for(reports_path, outcomes_path, reports, outcomes)
            verify_manifest(manifest, reports_path, outcomes_path, reports, outcomes)

            incomplete = manifest_for(reports_path, outcomes_path, reports, outcomes)
            incomplete["complete_official_evidence"] = False
            with self.assertRaisesRegex(ValueError, "complete official evidence"):
                verify_manifest(incomplete, reports_path, outcomes_path, reports, outcomes)

            bad_hash = manifest_for(reports_path, outcomes_path, reports, outcomes)
            bad_hash["files"]["reports"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash does not match"):
                verify_manifest(bad_hash, reports_path, outcomes_path, reports, outcomes)

            bad_coverage = manifest_for(reports_path, outcomes_path, reports, outcomes)
            bad_coverage["team_ids_by_season"]["2026"][-1] = bad_coverage["team_ids_by_season"]["2026"][0]
            with self.assertRaisesRegex(ValueError, "32 distinct team IDs"):
                verify_manifest(bad_coverage, reports_path, outcomes_path, reports, outcomes)

    def test_manifest_rejects_rows_outside_attested_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_path = Path(tmp) / "reports.csv"
            outcomes_path = Path(tmp) / "outcomes.csv"
            reports = [report(team_id="UNLISTED")]
            outcomes = [outcome(team_id="T00")]
            write_csv(reports_path, reports)
            write_csv(outcomes_path, outcomes)
            manifest = manifest_for(reports_path, outcomes_path, reports, outcomes)
            with self.assertRaisesRegex(ValueError, "outside the manifest"):
                verify_manifest(manifest, reports_path, outcomes_path, reports, outcomes)

    def test_official_host_gate_rejects_spoofed_or_non_https_urls(self):
        for url in (
            "http://www.nfl.com/injuries/",
            "https://nfl.com.example.org/injuries/",
            "https://www.nfl.com.evil.example/injuries/",
            "https://www.nfl.com/",
            "https://user@www.nfl.com/injuries/",
            "https://www.nfl.com:444/injuries/",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                official(url)
        official("https://www.nfl.com/injuries/league/2026/reg10")
        official("https://operations.nfl.com/rules/")

    def test_timestamp_requires_a_valid_explicit_offset(self):
        for value in ("", "2026-11-19T12:00:00", "not-a-date"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                clock(value)
        self.assertEqual(clock("2026-11-19T07:00:00-05:00").isoformat(), "2026-11-19T12:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
