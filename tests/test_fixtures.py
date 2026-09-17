"""The fixture corpus: every file declared, every declaration exact, all synthetic."""

import json
import os
import re
import unittest

from tests.support import FIXTURE_ROOT, fixture_files, load_fixture, load_manifest

from relay_intake.findings import ALL_CODES
from relay_intake.validator import ENVELOPE_VERSION, validate


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest()

    def test_manifest_targets_this_envelope_version(self):
        self.assertEqual(self.manifest["envelope_version"], ENVELOPE_VERSION)

    def test_every_valid_fixture_on_disk_is_declared(self):
        declared = {entry["file"] for entry in self.manifest["valid"]}
        self.assertEqual(declared, set(fixture_files("valid")))

    def test_every_invalid_fixture_on_disk_is_declared(self):
        declared = {entry["file"] for entry in self.manifest["invalid"]}
        self.assertEqual(declared, set(fixture_files("invalid")))

    def test_every_declared_fixture_carries_a_note(self):
        # A fixture whose reason for existing is not written down is a fixture
        # someone will delete during the next refactor.
        for entry in self.manifest["valid"] + self.manifest["invalid"]:
            self.assertTrue(entry.get("note", "").strip(), entry["file"])

    def test_declared_codes_are_codes_this_implementation_can_emit(self):
        for entry in self.manifest["invalid"]:
            for code in entry["codes"]:
                self.assertIn(code, ALL_CODES, entry["file"])


class ValidFixtureTests(unittest.TestCase):
    def test_each_valid_fixture_conforms(self):
        for entry in load_manifest()["valid"]:
            with self.subTest(fixture=entry["file"]):
                findings = validate(load_fixture(entry["file"]))
                self.assertEqual(
                    findings, [], [str(finding) for finding in findings]
                )

    def test_both_core_kinds_are_covered(self):
        kinds = {
            load_fixture(entry["file"])["kind"]
            for entry in load_manifest()["valid"]
        }
        self.assertIn("meeting", kinds, "structural routing needs a meeting")
        self.assertIn("note", kinds, "semantic routing needs a general capture")

    def test_more_than_one_adapter_is_represented(self):
        # A corpus emitted by a single imaginary adapter would not demonstrate
        # that the contract is adapter-independent.
        adapters = {
            load_fixture(entry["file"])["provenance"]["adapter"]
            for entry in load_manifest()["valid"]
        }
        self.assertGreater(len(adapters), 1)

    def test_more_than_one_storage_scheme_is_represented(self):
        schemes = {
            load_fixture(entry["file"])["payload"]["uri"].split(":", 1)[0]
            for entry in load_manifest()["valid"]
        }
        self.assertGreater(len(schemes), 1)


class InvalidFixtureTests(unittest.TestCase):
    def test_each_invalid_fixture_produces_exactly_its_declared_codes(self):
        for entry in load_manifest()["invalid"]:
            with self.subTest(fixture=entry["file"]):
                codes = sorted({f.code for f in validate(load_fixture(entry["file"]))})
                self.assertEqual(codes, sorted(entry["codes"]))

    def test_the_corpus_covers_every_single_envelope_code(self):
        # A rule with no fixture is a rule nobody will notice breaking.
        declared = set()
        for entry in load_manifest()["invalid"]:
            declared.update(entry["codes"])
        cross_envelope = {"E_REPLAY_DIVERGENT"}
        missing = set(ALL_CODES) - declared - cross_envelope
        self.assertEqual(missing, set(), "codes with no fixture: %s" % sorted(missing))


class SyntheticCorpusTests(unittest.TestCase):
    """The corpus is published. Nothing real may enter it."""

    #: Shapes that would indicate real material had leaked into a fixture.
    FORBIDDEN = (
        (re.compile(r"/(?:home|Users)/"), "an absolute path from someone's machine"),
        (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
         "an email address"),
        (re.compile(r"https?://(?!payloads\.example\b)[^\s\"]*"), "a live URL"),
        (re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password|bearer)\b"),
         "a credential-shaped word"),
    )

    def fixture_paths(self):
        for root, _dirnames, filenames in os.walk(FIXTURE_ROOT):
            for filename in sorted(filenames):
                if filename.endswith(".json"):
                    yield os.path.join(root, filename)

    def test_no_fixture_carries_anything_that_looks_real(self):
        for path in self.fixture_paths():
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
            for pattern, description in self.FORBIDDEN:
                match = pattern.search(text)
                self.assertIsNone(
                    match,
                    "%s contains %s: %r"
                    % (os.path.relpath(path, FIXTURE_ROOT), description,
                       match.group(0) if match else None),
                )

    def test_every_source_system_and_adapter_is_visibly_invented(self):
        # Checked structurally rather than against a list of real product
        # names: an allowlist of invented prefixes cannot go stale, and this
        # repository has no reason to enumerate anyone's brand.
        for entry in load_manifest()["valid"]:
            envelope = load_fixture(entry["file"])
            for label, value in (
                ("source.system", envelope["source"]["system"]),
                ("provenance.adapter", envelope["provenance"]["adapter"]),
            ):
                self.assertTrue(
                    value.startswith("example"),
                    "%s: %s is %r, which does not read as synthetic"
                    % (entry["file"], label, value),
                )

    def test_no_fixture_names_a_capture_vendor_in_a_payload_reference(self):
        # A storage URI is the most likely place for a real product or host
        # name to slip in, because it is the one member that names a system
        # outside this repository.
        for entry in load_manifest()["valid"]:
            uri = load_fixture(entry["file"])["payload"]["uri"]
            self.assertTrue(
                uri.startswith("example") or ".example/" in uri,
                "%s references %r, which is not an obviously invented "
                "location" % (entry["file"], uri),
            )

    def test_fixtures_are_formatted_for_reading(self):
        # The corpus is documentation as much as it is test input.
        for path in self.fixture_paths():
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
            self.assertTrue(text.endswith("\n"), path)
            self.assertEqual(
                json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n",
                text,
                "%s is not indented two spaces" % os.path.basename(path),
            )


if __name__ == "__main__":
    unittest.main()
