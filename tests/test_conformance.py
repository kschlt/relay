"""The suite an adapter runs against its own output: replay, revision, and the CLI."""

import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests.support import REPO_ROOT, a_valid_envelope, load_fixture

from relay_intake.conformance import (
    check_set,
    load_json_lines,
    load_path,
    main,
)
from relay_intake.findings import E_REPLAY_DIVERGENT


class SingleEnvelopeTests(unittest.TestCase):
    def test_a_conforming_set_reports_conformance(self):
        report = check_set([("a", a_valid_envelope())])
        self.assertTrue(report.conforms)
        self.assertEqual(report.counts["conforming"], 1)
        self.assertEqual(report.counts["rejected"], 0)

    def test_a_rejected_envelope_is_attributed_to_its_origin(self):
        broken = a_valid_envelope()
        broken["kind"] = "transcript"
        report = check_set([("ok.json", a_valid_envelope()), ("bad.json", broken)])
        self.assertFalse(report.conforms)
        rejected = [r for r in report.results if not r.conforms]
        self.assertEqual([r.origin for r in rejected], ["bad.json"])


class ReplayTests(unittest.TestCase):
    def test_re_emitting_an_unchanged_item_conforms(self):
        report = check_set([
            ("first", load_fixture("valid/note-minimal.json")),
            ("second", load_fixture("valid/note-minimal-replayed.json")),
        ])
        self.assertTrue(report.conforms, [str(f) for f in report.cross_findings])

    def test_the_same_item_described_differently_is_a_divergence(self):
        # The failure this check exists for: an adapter derives identity
        # correctly but does not reproduce the item's facts, so a consumer
        # deduplicating on identity silently keeps whichever arrived first.
        original = load_fixture("valid/note-minimal.json")
        divergent = copy.deepcopy(original)
        divergent["metadata"] = {"title": "Renamed on the second pass"}
        report = check_set([("first", original), ("second", divergent)])
        self.assertFalse(report.conforms)
        self.assertEqual(
            [f.code for f in report.cross_findings], [E_REPLAY_DIVERGENT]
        )

    def test_a_different_storage_location_is_not_a_divergence(self):
        # Where the bytes were put is a fact about a preservation, not about
        # the item, and the digest already proves the bytes match.
        original = load_fixture("valid/note-minimal.json")
        elsewhere = copy.deepcopy(original)
        elsewhere["payload"]["uri"] = "https://payloads.example/mirror/note-0001.txt"
        report = check_set([("first", original), ("mirror", elsewhere)])
        self.assertTrue(report.conforms, [str(f) for f in report.cross_findings])

    def test_a_revision_is_not_a_divergence(self):
        report = check_set([
            ("first", load_fixture("valid/note-minimal.json")),
            ("revised", load_fixture("valid/note-revised.json")),
        ])
        self.assertTrue(report.conforms, [str(f) for f in report.cross_findings])

    def test_divergence_is_not_reported_on_top_of_an_invalid_envelope(self):
        # An invalid envelope's identity means nothing; a consequent
        # divergence would be noise stacked on the real finding.
        original = load_fixture("valid/note-minimal.json")
        broken = copy.deepcopy(original)
        broken["kind"] = "transcript"
        broken["metadata"] = {"title": "Different"}
        report = check_set([("first", original), ("broken", broken)])
        self.assertEqual(report.cross_findings, [])
        self.assertEqual(report.counts["rejected"], 1)

    def test_the_whole_valid_corpus_is_mutually_consistent(self):
        report = check_set(list(load_path(os.path.join(REPO_ROOT, "fixtures", "valid"))))
        self.assertTrue(report.conforms, [str(f) for f in report.cross_findings])


class LoaderTests(unittest.TestCase):
    def test_json_lines_are_numbered_by_origin(self):
        stream = io.StringIO('{"a":1}\n\n{"b":2}\n')
        pairs = list(load_json_lines(stream, origin="run.jsonl"))
        self.assertEqual([origin for origin, _ in pairs],
                         ["run.jsonl:1", "run.jsonl:3"])

    def test_unparseable_input_is_reported_not_raised(self):
        # An adapter emitting malformed JSON should get a finding, not a
        # stack trace from the harness.
        pairs = list(load_json_lines(io.StringIO("{not json}\n")))
        report = check_set(pairs)
        self.assertFalse(report.conforms)

    def test_an_array_file_is_expanded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "run.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([a_valid_envelope(), a_valid_envelope()], handle)
            pairs = list(load_path(path))
        self.assertEqual([origin for origin, _ in pairs],
                         ["%s[0]" % path, "%s[1]" % path])

    def test_a_directory_is_walked_in_a_stable_order(self):
        directory = os.path.join(REPO_ROOT, "fixtures", "valid")
        first = [origin for origin, _ in load_path(directory)]
        second = [origin for origin, _ in load_path(directory)]
        self.assertEqual(first, second)
        self.assertEqual(first, sorted(first))


class CommandLineTests(unittest.TestCase):
    """An adapter in any language runs the contract through this entry point."""

    def run_cli(self, *arguments, **kwargs):
        return subprocess.run(
            [sys.executable, "-m", "relay_intake.conformance"] + list(arguments),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            **kwargs
        )

    def test_a_conforming_corpus_exits_zero(self):
        result = self.run_cli("fixtures/valid")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("8 envelope(s): 8 conforming", result.stdout)

    def test_a_rejected_corpus_exits_non_zero(self):
        result = self.run_cli("fixtures/invalid")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL", result.stdout)

    def test_stdin_accepts_a_json_lines_stream(self):
        payload = "\n".join(
            json.dumps(load_fixture("valid/%s" % name))
            for name in ("note-minimal.json", "meeting-minimal.json")
        )
        result = self.run_cli("-", input=payload + "\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_json_report_is_machine_readable(self):
        result = self.run_cli("--json", "fixtures/invalid/unknown-kind.json")
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertFalse(report["conforms"])
        self.assertEqual(report["counts"]["rejected"], 1)
        self.assertEqual(
            report["envelopes"][0]["findings"][0]["code"], "E_ENUM"
        )

    def test_the_module_entry_point_works_too(self):
        result = subprocess.run(
            [sys.executable, "-m", "relay_intake", "fixtures/valid"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_main_returns_the_exit_status_in_process(self):
        original = sys.stdout
        sys.stdout = io.StringIO()
        try:
            self.assertEqual(main(["fixtures/valid"]), 0)
            self.assertEqual(main(["fixtures/invalid"]), 1)
        finally:
            sys.stdout = original


if __name__ == "__main__":
    unittest.main()
