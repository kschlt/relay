"""Rule-by-rule validation, and the three properties that make it deterministic."""

import copy
import json
import unittest

from tests.support import a_valid_envelope

from relay_intake.findings import (
    E_DIGEST_LENGTH,
    E_ENUM,
    E_ENVELOPE_SIZE,
    E_FIELD_MISSING,
    E_FIELD_UNKNOWN,
    E_FORMAT,
    E_INTAKE_ID_DERIVATION,
    E_METADATA_KEY,
    E_METADATA_SIZE,
    E_METADATA_VALUE,
    E_NOT_OBJECT,
    E_NUMBER_NOT_INTEGER,
    E_PAYLOAD_URI_EMBEDS_CONTENT,
    E_RANGE,
    E_TIMESTAMP_ORDER,
    E_TYPE,
    E_VERSION_UNSUPPORTED,
    Finding,
    pointer,
)
from relay_intake.validator import (
    MAX_ENVELOPE_BYTES,
    MAX_METADATA_BYTES,
    is_valid,
    validate,
)


class ValidatorTestCase(unittest.TestCase):
    def codes(self, envelope):
        return sorted({finding.code for finding in validate(envelope)})

    def assertCodes(self, envelope, expected):
        self.assertEqual(self.codes(envelope), sorted(expected))

    def assertFindingAt(self, envelope, code, path):
        self.assertIn(
            (code, path),
            [(f.code, f.path) for f in validate(envelope)],
            "expected %s at %s, got %s"
            % (code, path, [str(f) for f in validate(envelope)]),
        )


class BaselineTests(ValidatorTestCase):
    def test_a_conforming_envelope_produces_no_findings(self):
        self.assertEqual(validate(a_valid_envelope()), [])
        self.assertTrue(is_valid(a_valid_envelope()))

    def test_a_non_object_is_rejected_whole(self):
        for value in ([], "envelope", 7, None, True):
            self.assertCodes(value, [E_NOT_OBJECT])


class ShapeTests(ValidatorTestCase):
    def test_absent_required_member(self):
        envelope = a_valid_envelope()
        del envelope["source"]
        self.assertFindingAt(envelope, E_FIELD_MISSING, pointer("source"))

    def test_absent_nested_required_member(self):
        envelope = a_valid_envelope()
        del envelope["content"]["digest"]
        self.assertFindingAt(
            envelope, E_FIELD_MISSING, pointer("content", "digest")
        )

    def test_optional_members_may_be_absent(self):
        envelope = a_valid_envelope()
        del envelope["occurred_at"]
        del envelope["metadata"]
        self.assertEqual(validate(envelope), [])

    def test_undeclared_member_is_rejected(self):
        # The envelope is closed so that a vendor field which leaked past an
        # adapter fails loudly rather than riding along and being ignored.
        envelope = a_valid_envelope()
        envelope["vendor_room"] = "room-9"
        self.assertFindingAt(envelope, E_FIELD_UNKNOWN, pointer("vendor_room"))

    def test_destination_cannot_be_smuggled_into_an_envelope(self):
        # Intake describes an item. Where it goes is nothing an adapter decides.
        envelope = a_valid_envelope()
        envelope["destination"] = "example-destination"
        self.assertFindingAt(envelope, E_FIELD_UNKNOWN, pointer("destination"))

    def test_wrong_type(self):
        envelope = a_valid_envelope()
        envelope["content"]["byte_length"] = "2048"
        self.assertFindingAt(envelope, E_TYPE, pointer("content", "byte_length"))

    def test_a_boolean_is_not_an_integer(self):
        envelope = a_valid_envelope()
        envelope["content"]["byte_length"] = True
        self.assertFindingAt(envelope, E_TYPE, pointer("content", "byte_length"))

    def test_negative_length(self):
        envelope = a_valid_envelope()
        envelope["content"]["byte_length"] = -1
        self.assertFindingAt(envelope, E_RANGE, pointer("content", "byte_length"))

    def test_fractional_numbers_are_rejected(self):
        # Excluded so that canonical form needs no float-formatting rule and is
        # therefore reproducible in any language.
        envelope = a_valid_envelope()
        envelope["metadata"]["duration_seconds"] = 2700.5
        self.assertFindingAt(
            envelope, E_NUMBER_NOT_INTEGER, pointer("metadata", "duration_seconds")
        )


class VersionTests(ValidatorTestCase):
    def test_an_unknown_major_version_is_refused(self):
        envelope = a_valid_envelope()
        envelope["envelope_version"] = "2"
        self.assertFindingAt(
            envelope, E_VERSION_UNSUPPORTED, pointer("envelope_version")
        )

    def test_a_minor_version_on_the_wire_is_refused(self):
        # There is no minor on the wire; see docs/compatibility.md.
        envelope = a_valid_envelope()
        envelope["envelope_version"] = "1.1"
        self.assertFindingAt(
            envelope, E_VERSION_UNSUPPORTED, pointer("envelope_version")
        )


class KindTests(ValidatorTestCase):
    def test_core_kinds_are_accepted(self):
        for kind in ("meeting", "note"):
            envelope = a_valid_envelope()
            envelope["kind"] = kind
            self.assertEqual(validate(envelope), [])

    def test_experimental_kinds_are_accepted(self):
        envelope = a_valid_envelope()
        envelope["kind"] = "x-voice-memo"
        self.assertEqual(validate(envelope), [])

    def test_an_unnamespaced_unknown_kind_is_refused(self):
        envelope = a_valid_envelope()
        envelope["kind"] = "transcript"
        self.assertFindingAt(envelope, E_ENUM, pointer("kind"))


class IdentityTests(ValidatorTestCase):
    def test_identity_must_follow_from_the_source(self):
        envelope = a_valid_envelope()
        envelope["intake_id"] = "sha-256:" + "0" * 64
        self.assertFindingAt(
            envelope, E_INTAKE_ID_DERIVATION, pointer("intake_id")
        )

    def test_changing_the_source_changes_the_required_identity(self):
        envelope = a_valid_envelope()
        envelope["source"]["external_id"] = "mtg-9999-synthetic"
        self.assertFindingAt(
            envelope, E_INTAKE_ID_DERIVATION, pointer("intake_id")
        )

    def test_a_revision_marker_does_not_change_the_identity(self):
        # An edited item is the same item; content.digest says which revision.
        envelope = a_valid_envelope()
        envelope["source"]["external_revision"] = "7"
        self.assertEqual(validate(envelope), [])

    def test_malformed_identity(self):
        envelope = a_valid_envelope()
        envelope["intake_id"] = "SHA-256:" + "A" * 64
        self.assertFindingAt(envelope, E_FORMAT, pointer("intake_id"))

    def test_the_separator_may_not_appear_in_an_external_identifier(self):
        envelope = a_valid_envelope()
        envelope["source"]["external_id"] = "mtg\x1f0001"
        self.assertFindingAt(
            envelope, E_FORMAT, pointer("source", "external_id")
        )


class TimestampTests(ValidatorTestCase):
    def test_only_the_z_offset_is_admitted(self):
        envelope = a_valid_envelope()
        envelope["captured_at"] = "2026-01-05T16:02:11+01:00"
        self.assertFindingAt(envelope, E_FORMAT, pointer("captured_at"))

    def test_fractional_seconds_are_admitted(self):
        envelope = a_valid_envelope()
        envelope["captured_at"] = "2026-01-05T15:02:11.250Z"
        self.assertEqual(validate(envelope), [])

    def test_impossible_calendar_dates_are_refused(self):
        for stamp in ("2026-02-30T00:00:00Z", "2026-13-01T00:00:00Z",
                      "2026-01-05T24:00:00Z", "2026-01-05T23:59:60Z"):
            envelope = a_valid_envelope()
            envelope["occurred_at"] = stamp
            self.assertFindingAt(envelope, E_FORMAT, pointer("occurred_at"))

    def test_leap_day_is_admitted_in_a_leap_year(self):
        envelope = a_valid_envelope()
        envelope["occurred_at"] = "2024-02-29T00:00:00Z"
        self.assertEqual(validate(envelope), [])

    def test_leap_day_is_refused_in_a_common_year(self):
        envelope = a_valid_envelope()
        envelope["occurred_at"] = "2026-02-29T00:00:00Z"
        self.assertFindingAt(envelope, E_FORMAT, pointer("occurred_at"))

    def test_a_capture_may_not_predate_what_it_captured(self):
        envelope = a_valid_envelope()
        envelope["occurred_at"] = "2026-01-06T00:00:00Z"
        self.assertFindingAt(envelope, E_TIMESTAMP_ORDER, pointer("captured_at"))

    def test_an_envelope_may_not_predate_the_payload_it_references(self):
        # This is the handoff invariant: preserve the bytes, then announce them.
        envelope = a_valid_envelope()
        envelope["payload"]["preserved_at"] = "2026-01-05T15:30:03Z"
        self.assertFindingAt(
            envelope, E_TIMESTAMP_ORDER, pointer("provenance", "emitted_at")
        )

    def test_equal_timestamps_are_admitted(self):
        # A fast adapter may legitimately produce identical instants.
        envelope = a_valid_envelope()
        envelope["payload"]["preserved_at"] = "2026-01-05T15:30:02Z"
        self.assertEqual(validate(envelope), [])

    def test_a_missing_optional_timestamp_does_not_break_the_chain(self):
        # With occurred_at absent the chain simply starts one link later; a
        # capture that postdates the absent link is still ordered correctly.
        envelope = a_valid_envelope()
        del envelope["occurred_at"]
        envelope["captured_at"] = "2026-01-05T15:29:59Z"
        self.assertEqual(validate(envelope), [])


class ContentAndPayloadTests(ValidatorTestCase):
    def test_digest_length_is_checked_against_its_algorithm(self):
        envelope = a_valid_envelope()
        envelope["content"]["digest"]["value"] = "ab" * 16
        self.assertFindingAt(
            envelope, E_DIGEST_LENGTH, pointer("content", "digest", "value")
        )

    def test_sha_512_is_admitted_at_its_own_length(self):
        envelope = a_valid_envelope()
        envelope["content"]["digest"] = {"algorithm": "sha-512", "value": "a" * 128}
        self.assertEqual(validate(envelope), [])

    def test_an_unadmitted_algorithm_is_refused(self):
        envelope = a_valid_envelope()
        envelope["content"]["digest"] = {"algorithm": "md5", "value": "a" * 32}
        self.assertFindingAt(
            envelope, E_ENUM, pointer("content", "digest", "algorithm")
        )

    def test_uppercase_digests_are_refused(self):
        # One rendering per digest, or the same bytes get two identities.
        envelope = a_valid_envelope()
        envelope["content"]["digest"]["value"] = (
            envelope["content"]["digest"]["value"].upper()
        )
        self.assertFindingAt(
            envelope, E_FORMAT, pointer("content", "digest", "value")
        )

    def test_a_payload_reference_must_be_absolute(self):
        envelope = a_valid_envelope()
        envelope["payload"]["uri"] = "meeting/mtg-0001-synthetic.vtt"
        self.assertFindingAt(envelope, E_FORMAT, pointer("payload", "uri"))

    def test_a_data_uri_defeats_the_reference_and_is_refused(self):
        envelope = a_valid_envelope()
        envelope["payload"]["uri"] = "data:text/vtt;base64,V0VCVlRU"
        self.assertFindingAt(
            envelope, E_PAYLOAD_URI_EMBEDS_CONTENT, pointer("payload", "uri")
        )

    def test_the_data_scheme_is_refused_whatever_its_casing(self):
        envelope = a_valid_envelope()
        envelope["payload"]["uri"] = "DaTa:text/vtt;base64,V0VCVlRU"
        self.assertFindingAt(
            envelope, E_PAYLOAD_URI_EMBEDS_CONTENT, pointer("payload", "uri")
        )

    def test_operator_defined_schemes_are_admitted(self):
        # Relay does not define storage. Any absolute URI the operator's
        # resolver understands is acceptable.
        for uri in ("example-store:note/a.txt", "https://payloads.example/a.txt",
                    "s3://example-bucket/a.txt"):
            envelope = a_valid_envelope()
            envelope["payload"]["uri"] = uri
            self.assertEqual(validate(envelope), [], uri)


class MetadataTests(ValidatorTestCase):
    def test_vocabulary_types_are_enforced(self):
        envelope = a_valid_envelope()
        envelope["metadata"]["participant_count"] = "four"
        self.assertFindingAt(
            envelope, E_TYPE, pointer("metadata", "participant_count")
        )

    def test_undeclared_names_are_admitted(self):
        # What makes adding a metadata name a non-breaking change.
        envelope = a_valid_envelope()
        envelope["metadata"]["tags"] = ["synthetic", "fixture"]
        envelope["metadata"]["is_recurring"] = True
        self.assertEqual(validate(envelope), [])

    def test_vendor_shaped_names_are_refused(self):
        envelope = a_valid_envelope()
        envelope["metadata"]["vendorRoomId"] = "room-9"
        self.assertFindingAt(
            envelope, E_METADATA_KEY, pointer("metadata", "vendorRoomId")
        )

    def test_structure_is_refused(self):
        # Nesting is how a payload gets carried in a piece at a time.
        envelope = a_valid_envelope()
        envelope["metadata"]["speakers"] = {"first": "synthetic"}
        self.assertFindingAt(
            envelope, E_METADATA_VALUE, pointer("metadata", "speakers")
        )

    def test_arrays_hold_strings_only(self):
        envelope = a_valid_envelope()
        envelope["metadata"]["tags"] = ["ok", 7]
        self.assertFindingAt(
            envelope, E_METADATA_VALUE, pointer("metadata", "tags", 1)
        )

    def test_a_long_string_is_refused(self):
        envelope = a_valid_envelope()
        envelope["metadata"]["title"] = "x" * 513
        self.assertFindingAt(envelope, E_RANGE, pointer("metadata", "title"))

    def test_the_metadata_ceiling_holds(self):
        envelope = a_valid_envelope()
        envelope["metadata"] = dict(
            ("excerpt_%02d" % i, "x" * 96) for i in range(28)
        )
        self.assertFindingAt(envelope, E_METADATA_SIZE, pointer("metadata"))

    def test_a_language_tag_is_checked(self):
        envelope = a_valid_envelope()
        envelope["metadata"]["language"] = "English"
        self.assertEqual(validate(envelope), [])
        envelope["metadata"]["language"] = "en_GB"
        self.assertFindingAt(envelope, E_FORMAT, pointer("metadata", "language"))


class SizeCeilingTests(ValidatorTestCase):
    def test_the_envelope_ceiling_holds(self):
        envelope = a_valid_envelope()
        envelope["payload"]["uri"] = "example-store:" + "s" * 1900
        envelope["metadata"] = dict(("note_%02d" % i, "y" * 60) for i in range(28))
        self.assertFindingAt(envelope, E_ENVELOPE_SIZE, "")

    def test_the_ceilings_leave_room_for_a_realistic_envelope(self):
        # A ceiling that rejected ordinary traffic would be a bug, not a guard.
        from relay_intake.canonical import canonical_bytes

        envelope = a_valid_envelope()
        self.assertLess(len(canonical_bytes(envelope)), MAX_ENVELOPE_BYTES // 2)
        self.assertLess(
            len(canonical_bytes(envelope["metadata"])), MAX_METADATA_BYTES // 2
        )


class UncanonicalValueTests(ValidatorTestCase):
    """Values that survive JSON parsing but have no canonical form.

    `json.loads` accepts NaN and Infinity by default, and a lone surrogate
    parses fine and then cannot be encoded as UTF-8. Both must come back as
    findings: a validator that raised would abandon a whole conformance run
    over one bad envelope, which is the opposite of what the run is for.
    """

    def test_a_non_finite_number_is_a_finding_not_an_exception(self):
        for literal in ("NaN", "Infinity", "-Infinity"):
            envelope = json.loads(
                '{"envelope_version":"1","metadata":{"x":%s}}' % literal
            )
            self.assertIn(E_NUMBER_NOT_INTEGER, self.codes(envelope), literal)

    def test_a_non_finite_number_in_a_declared_member_is_a_finding(self):
        envelope = a_valid_envelope()
        envelope["content"]["byte_length"] = float("nan")
        self.assertIn(E_NUMBER_NOT_INTEGER, self.codes(envelope))

    def test_an_unpaired_surrogate_is_a_finding_not_an_exception(self):
        envelope = a_valid_envelope()
        envelope["metadata"]["title"] = "\ud800"
        self.assertFindingAt(envelope, E_FORMAT, pointer("metadata", "title"))

    def test_an_unpaired_surrogate_anywhere_still_validates(self):
        # The size rule abstains rather than raising; the member rules report.
        envelope = a_valid_envelope()
        envelope["source"]["external_id"] = "\udfff"
        findings = validate(envelope)
        self.assertNotEqual(findings, [])

    def test_the_separator_guard_does_not_crash_identity_derivation(self):
        # derive_intake_id refuses a component containing U+001F. The validator
        # must not hand it one.
        envelope = a_valid_envelope()
        envelope["source"]["system"] = "example\x1fcapture"
        self.assertNotEqual(validate(envelope), [])


class DeterminismTests(ValidatorTestCase):
    def test_findings_are_ordered_by_path_then_code(self):
        envelope = a_valid_envelope()
        envelope["kind"] = "transcript"
        envelope["content"]["byte_length"] = -4
        del envelope["payload"]["preserved_at"]
        findings = validate(envelope)
        self.assertEqual(
            findings, sorted(findings), "findings must already be in order"
        )

    def test_the_same_envelope_always_validates_the_same_way(self):
        envelope = a_valid_envelope()
        envelope["kind"] = "transcript"
        envelope["metadata"]["vendorRoomId"] = "room-9"
        expected = [(f.code, f.path, f.message) for f in validate(envelope)]
        for _ in range(32):
            again = [(f.code, f.path, f.message) for f in validate(copy.deepcopy(envelope))]
            self.assertEqual(again, expected)

    def test_member_insertion_order_does_not_affect_the_report(self):
        envelope = a_valid_envelope()
        envelope["kind"] = "transcript"
        reversed_envelope = dict(reversed(list(envelope.items())))
        self.assertEqual(validate(envelope), validate(reversed_envelope))

    def test_every_violation_is_reported_not_just_the_first(self):
        # An adapter author should fix one round, not three.
        envelope = a_valid_envelope()
        envelope["kind"] = "transcript"
        envelope["content"]["byte_length"] = -4
        del envelope["payload"]["preserved_at"]
        self.assertCodes(envelope, [E_ENUM, E_RANGE, E_FIELD_MISSING])

    def test_validation_consults_no_clock(self):
        # A validator that knew the date would reject tomorrow what it accepts
        # today, which makes a fixture suite meaningless and a replayed
        # envelope unverifiable.
        for year in ("1904", "2999"):
            envelope = a_valid_envelope()
            for path in (("occurred_at",), ("captured_at",),
                         ("provenance", "acquired_at"),
                         ("provenance", "emitted_at"),
                         ("payload", "preserved_at")):
                container = envelope
                for segment in path[:-1]:
                    container = container[segment]
                container[path[-1]] = year + container[path[-1]][4:]
            self.assertEqual(validate(envelope), [], year)

    def test_a_value_too_deep_to_serialise_is_reported_not_raised(self):
        # Parsing and serialising both recurse, to different depths, and both
        # limits are measured against the stack already in use. So there is a
        # band that json.loads accepts and canonical form cannot represent, and
        # where the band falls depends on how deeply the caller was nested.
        # Left unguarded, the same envelope raises or returns findings
        # depending on who asked.
        #
        # The band is only a few levels wide, so sampling fixed depths misses
        # it. Find its upper edge at run time instead — the deepest nesting the
        # parser still accepts — and test downward from there.
        def parse(nesting, frames):
            def deeper(remaining):
                if remaining:
                    return deeper(remaining - 1)
                text = ('{"envelope_version":"1","metadata":{"x":%s}}'
                        % ("[" * nesting + "]" * nesting))
                try:
                    return json.loads(text)
                except RecursionError:
                    return None
            return deeper(frames)

        def validate_at(envelope, frames):
            def deeper(remaining):
                if remaining:
                    return deeper(remaining - 1)
                return validate(envelope)
            return deeper(frames)

        for frames in (0, 150, 400):
            low, high = 8, 4000
            while low < high:                       # deepest the parser accepts
                mid = (low + high + 1) // 2
                if parse(mid, frames) is None:
                    high = mid - 1
                else:
                    low = mid
            self.assertGreater(low, 8, "parser rejected everything")
            for nesting in range(max(8, low - 12), low + 1):
                envelope = parse(nesting, frames)
                if envelope is None:
                    continue
                with self.subTest(frames=frames, nesting=nesting):
                    findings = validate_at(envelope, frames)
                    self.assertNotEqual(
                        findings, [], "validated clean at depth %d" % nesting
                    )

    def test_validation_does_not_mutate_its_input(self):
        envelope = a_valid_envelope()
        envelope["kind"] = "transcript"
        before = copy.deepcopy(envelope)
        validate(envelope)
        self.assertEqual(envelope, before)

    #: Modules that would give validation a clock, a network, a filesystem, or
    #: a source of randomness. Checked by name against the parsed import
    #: statements, not by searching the text: a substring scan is evaded by any
    #: spelling it does not happen to list, and this claim is made flatly in
    #: CLAUDE.md, so it has to hold against the spellings nobody thought of.
    AMBIENT_MODULES = frozenset({
        "time", "datetime", "calendar", "random", "secrets", "uuid",
        "os", "os.path", "pathlib", "shutil", "glob", "tempfile", "io",
        "socket", "ssl", "http", "urllib", "urllib.request", "requests",
        "subprocess", "platform", "locale", "getpass", "sys",
    })

    #: Builtins that reach outside the argument, whatever is imported.
    AMBIENT_CALLS = frozenset({"open", "input", "eval", "exec", "__import__",
                               "compile", "globals", "vars"})

    #: Every module that executes during validation. The validator imports
    #: both of the others, so a clock next door is just as fatal to a replayed
    #: envelope as one here.
    VALIDATION_PATH = (
        "relay_intake.validator",
        "relay_intake.canonical",
        "relay_intake.findings",
    )

    def ambient_use(self, source):
        """Return every ambient import or call in ``source``.

        Takes source text rather than a module so that the guard itself is
        directly testable: the self-test below calls *this* function on each
        known evasion. An earlier version re-implemented the walk inline, which
        meant the self-test passed while the guard was blind — reducing this to
        `return []` left the whole suite green with a real clock imported into
        the validator.
        """
        import ast

        found = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if alias.name in self.AMBIENT_MODULES or root in self.AMBIENT_MODULES:
                        found.append("import %s" % alias.name)
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ""
                if name in self.AMBIENT_MODULES or name.split(".")[0] in self.AMBIENT_MODULES:
                    found.append("from %s import ..." % name)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in self.AMBIENT_CALLS:
                    found.append("%s(...)" % node.func.id)
        return found

    def module_source(self, dotted_name):
        import importlib

        module = importlib.import_module(dotted_name)
        with open(module.__file__, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_validation_reaches_no_ambient_state(self):
        for name in self.VALIDATION_PATH:
            with self.subTest(module=name):
                self.assertEqual(
                    self.ambient_use(self.module_source(name)), [],
                    "%s reaches outside the envelope" % name,
                )

    def test_the_ambient_guard_detects_what_it_claims_to(self):
        # Calls the guard itself, so blinding the guard fails this too. A guard
        # nobody has seen fail is a guard nobody knows works.
        cases = {
            "unlisted import spelling": "import datetime as dt\n",
            "a network module": "import socket\n",
            "a filesystem call": "def f():\n    return open('x')\n",
            "a from-import": "from time import monotonic\n",
            "a nested clock read": "def f():\n    import time\n    return time.time()\n",
        }
        for label, source in cases.items():
            with self.subTest(case=label):
                self.assertNotEqual(
                    self.ambient_use(source), [],
                    "%s slipped past the guard" % label,
                )

    def test_the_guard_does_not_fire_on_what_validation_legitimately_uses(self):
        # A guard that flagged `re` or `hashlib` would be turned off by the
        # first person it inconvenienced.
        for source in ("import re\n", "import json\n", "import hashlib\n",
                       "from relay_intake.canonical import canonical_size\n"):
            with self.subTest(source=source.strip()):
                self.assertEqual(self.ambient_use(source), [])


class FindingTests(unittest.TestCase):
    def test_pointer_escapes_reserved_characters(self):
        self.assertEqual(pointer("a/b"), "/a~1b")
        self.assertEqual(pointer("a~b"), "/a~0b")
        self.assertEqual(pointer(), "")

    def test_pointer_indexes_arrays(self):
        self.assertEqual(pointer("metadata", "tags", 1), "/metadata/tags/1")

    def test_findings_render_and_serialise(self):
        finding = Finding(E_TYPE, "/content/byte_length", "expected a number")
        self.assertEqual(
            finding.to_dict(),
            {"code": E_TYPE, "path": "/content/byte_length",
             "message": "expected a number"},
        )
        self.assertIn("E_TYPE", str(finding))


if __name__ == "__main__":
    unittest.main()
