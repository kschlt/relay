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
    LoadError,
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


class EmptySetTests(unittest.TestCase):
    """A check that examined nothing cannot report conformance."""

    def test_an_empty_set_does_not_conform(self):
        # `all([])` is True, so without an explicit rule a gate pointed at the
        # wrong directory would go green having checked nothing.
        report = check_set([])
        self.assertFalse(report.conforms)
        self.assertTrue(report.is_empty)

    def test_an_empty_set_conforms_when_that_is_declared_expected(self):
        # An incremental adapter run that found nothing new is legitimate.
        report = check_set([], allow_empty=True)
        self.assertTrue(report.conforms)

    def test_the_empty_report_says_what_to_do_about_it(self):
        self.assertIn("--allow-empty", check_set([]).render())
        self.assertIn("no envelopes found", check_set([]).render())

    def test_the_json_report_marks_emptiness(self):
        self.assertTrue(check_set([]).to_dict()["empty"])
        self.assertFalse(check_set([("a", a_valid_envelope())]).to_dict()["empty"])


class UndecodableInputTests(unittest.TestCase):
    """Bad bytes are a finding, not a traceback out of the harness."""

    def write(self, directory, name, data):
        path = os.path.join(directory, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_a_non_utf8_byte_in_a_jsonl_stream_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(
                directory, "run.jsonl", b'{"a":1}\n\xff\xfe bad\n{"b":2}\n'
            )
            pairs = list(load_path(path))
        report = check_set(pairs)
        self.assertFalse(report.conforms)
        self.assertEqual(len(pairs), 3, "a bad line must not truncate the run")

    def test_a_non_utf8_json_file_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, "run.json", b'{"a":"\xff\xfe"}')
            pairs = list(load_path(path))
        self.assertEqual(len(pairs), 1)
        self.assertFalse(check_set(pairs).conforms)

    def test_a_directory_holding_a_bad_file_still_reports_the_good_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "bad.json", b'\xff\xfe')
            with open(os.path.join(directory, "good.json"), "w",
                      encoding="utf-8") as handle:
                json.dump(a_valid_envelope(), handle)
            report = check_set(list(load_path(directory)))
        self.assertEqual(report.counts["envelopes"], 2)
        self.assertEqual(report.counts["conforming"], 1)


class LoadDiagnosticTests(unittest.TestCase):
    """Why a file could not be read must survive into the report.

    All three load failures are "not a JSON object" and reporting only that is
    true and useless — for a non-UTF-8 file that *is* a JSON object it points
    at the wrong problem. An adapter author reads the message, not the code.
    """

    def report_for(self, name, data):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, name)
            with open(path, "wb") as handle:
                handle.write(data)
            return check_set(list(load_path(path)))

    def message(self, report):
        self.assertEqual(report.counts["rejected"], 1)
        findings = report.results[0].findings
        self.assertEqual(len(findings), 1)
        return findings[0].message

    def test_undecodable_input_says_so(self):
        report = self.report_for("bad.json", b'{"a":"\xff\xfe"}')
        self.assertIn("decoded as UTF-8", self.message(report))

    def test_nesting_too_deep_to_parse_says_so(self):
        deep = ("[" * 3000 + "]" * 3000).encode("ascii")
        self.assertIn("nested too deeply", self.message(self.report_for("d.json", deep)))

    def test_malformed_json_says_so(self):
        report = self.report_for("bad.json", b"{not json}")
        self.assertIn("not valid JSON", self.message(report))

    def test_the_three_diagnostics_are_distinguishable(self):
        # The defect this replaces: all three collapsed to one message.
        messages = {
            self.message(self.report_for("a.json", b'{"a":"\xff\xfe"}')),
            self.message(self.report_for("b.json", ("[" * 3000 + "]" * 3000).encode())),
            self.message(self.report_for("c.json", b"{not json}")),
        }
        self.assertEqual(len(messages), 3, messages)

    def test_a_load_failure_reaches_the_json_report(self):
        report = self.report_for("bad.json", b"{not json}")
        entry = report.to_dict()["envelopes"][0]
        self.assertIn("not valid JSON", entry["findings"][0]["message"])

    def test_a_load_failure_is_not_mistaken_for_an_envelope(self):
        # A LoadError must never reach validate(), which would report the
        # generic non-object message and lose the reason.
        self.assertIsInstance(LoadError("why"), LoadError)
        report = check_set([("x", LoadError("a specific reason"))])
        self.assertFalse(report.conforms)
        self.assertIn("a specific reason", report.results[0].findings[0].message)


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

    def test_an_empty_directory_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli(directory)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no envelopes found", result.stdout)

    def test_an_empty_directory_exits_zero_when_declared_expected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli("--allow-empty", directory)
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
