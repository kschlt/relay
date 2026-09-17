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
        # The exemption must end at the host, not at a label boundary:
        # `\b` after "example" would also exempt payloads.example.com,
        # which is a registrable domain someone can own.
        (re.compile(r"https?://(?!payloads\.example(?:[/?#]|$))[^\s\"]*"),
         "a live URL"),
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

    def all_envelopes(self):
        """Every envelope in the corpus, valid and invalid alike.

        An invalid fixture is published exactly like a valid one, so a guard
        that inspected only the valid half would leave most of the corpus
        unscanned.
        """
        manifest = load_manifest()
        for entry in manifest["valid"] + manifest["invalid"]:
            document = load_fixture(entry["file"])
            if isinstance(document, dict):
                yield entry["file"], document

    def test_every_source_system_and_adapter_is_visibly_invented(self):
        # Checked structurally rather than against a list of real product
        # names: an allowlist of invented prefixes cannot go stale, and this
        # repository has no reason to enumerate anyone's brand.
        for name, envelope in self.all_envelopes():
            for label, value in (
                ("source.system", envelope.get("source", {}).get("system")),
                ("provenance.adapter",
                 envelope.get("provenance", {}).get("adapter")),
            ):
                if not isinstance(value, str):
                    continue
                self.assertTrue(
                    value.startswith("example"),
                    "%s: %s is %r, which does not read as synthetic"
                    % (name, label, value),
                )

    def test_every_payload_reference_points_somewhere_invented(self):
        # A storage URI is the likeliest place for a real product or host name
        # to slip in: it is the one member that names a system outside this
        # repository. The data: exemption covers the fixture that exists to be
        # rejected for inlining content.
        for name, envelope in self.all_envelopes():
            uri = envelope.get("payload", {}).get("uri")
            if not isinstance(uri, str):
                continue
            self.assertTrue(
                uri.startswith("example")
                or uri.lower().startswith("data:")
                or ".example/" in uri,
                "%s references %r, which is not an obviously invented "
                "location" % (name, uri),
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
