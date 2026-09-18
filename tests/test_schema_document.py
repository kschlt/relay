"""The published JSON Schema, and its relationship to the reference validator.

The schema exists so that an adapter written in any language can check an
envelope's shape with an off-the-shelf validator. It is deliberately the weaker
of the two artifacts: rules relating two members to each other cannot be
expressed in JSON Schema at all.

What must never happen is the schema being *stricter* than the reference
validator. That would mean an envelope the contract calls conforming gets
rejected by a consumer following the published schema — the contract saying two
different things to two different readers.
"""

import json
import os
import unittest

from tests.support import (
    SCHEMA_PATH,
    a_valid_envelope,
    load_fixture,
    load_manifest,
)

from relay_intake.validator import (
    ENVELOPE_VERSION,
    _CONTENT_MEMBERS,
    _DIGEST_MEMBERS,
    _ENVELOPE_MEMBERS,
    _PAYLOAD_MEMBERS,
    _PROVENANCE_MEMBERS,
    _SOURCE_MEMBERS,
    validate,
)

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised only where the lib is absent
    jsonschema = None


def _shift_year(envelope, year):
    """Move every timestamp in ``envelope`` to ``year``, keeping the order."""
    for path in (("occurred_at",), ("captured_at",),
                 ("provenance", "acquired_at"), ("payload", "preserved_at"),
                 ("provenance", "emitted_at")):
        container = envelope
        for segment in path[:-1]:
            container = container[segment]
        if path[-1] in container:
            container[path[-1]] = year + container[path[-1]][4:]


def load_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


class SchemaDocumentTests(unittest.TestCase):
    """Checks that need no third-party validator."""

    def setUp(self):
        self.schema = load_schema()

    def test_the_schema_is_published_at_a_stable_path(self):
        self.assertTrue(os.path.exists(SCHEMA_PATH))
        self.assertTrue(SCHEMA_PATH.endswith("intake-envelope-v1.schema.json"))

    def test_it_declares_its_dialect_and_identity(self):
        self.assertEqual(
            self.schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertIn("$id", self.schema)

    def test_it_pins_the_same_envelope_version_the_validator_does(self):
        self.assertEqual(
            self.schema["properties"]["envelope_version"]["const"],
            ENVELOPE_VERSION,
        )

    def test_metadata_is_the_one_open_object_and_is_still_bounded(self):
        metadata = self.schema["properties"]["metadata"]
        self.assertIn("additionalProperties", metadata)
        self.assertNotEqual(metadata["additionalProperties"], False)
        self.assertIn("propertyNames", metadata)
        self.assertIn("maxProperties", metadata)

    def test_it_names_the_rules_it_cannot_express(self):
        # A reader who stops at the schema must be told it is not the whole
        # contract, or they will build against half of it.
        description = self.schema["description"]
        for expected in ("timestamp ordering", "identity derivation",
                         "docs/intake-envelope.md"):
            self.assertIn(expected, description)

    #: Every closed object in the contract, paired with the validator's own
    #: member table for it. Read from the validator rather than restated here:
    #: a literal copy of the required list cannot detect the two artifacts
    #: drifting apart, which is the only thing this check exists to do.
    OBJECTS = (
        ("envelope", (), _ENVELOPE_MEMBERS),
        ("source", ("source",), _SOURCE_MEMBERS),
        ("provenance", ("provenance",), _PROVENANCE_MEMBERS),
        ("content", ("content",), _CONTENT_MEMBERS),
        ("content.digest", ("content", "digest"), _DIGEST_MEMBERS),
        ("payload", ("payload",), _PAYLOAD_MEMBERS),
    )

    def schema_object(self, path):
        node = self.schema
        for segment in path:
            node = node["properties"][segment]
        return node

    def test_each_object_requires_exactly_what_the_validator_requires(self):
        # Flipping a member's requiredness in the validator must fail here.
        # While this was a hardcoded list it did not: the validator could stop
        # requiring `payload` with the whole suite still green, and then accept
        # an envelope the published schema rejects — the one invariant the
        # suite advertises, defeated from the side it was not watching.
        for label, path, members in self.OBJECTS:
            with self.subTest(object=label):
                self.assertEqual(
                    sorted(self.schema_object(path).get("required", [])),
                    sorted(name for name, required in members.items() if required),
                )

    def test_each_object_admits_exactly_the_members_the_validator_admits(self):
        # The other half of the same drift: a member added to one artifact and
        # not the other.
        for label, path, members in self.OBJECTS:
            with self.subTest(object=label):
                node = self.schema_object(path)
                self.assertEqual(node.get("additionalProperties"), False, label)
                self.assertEqual(
                    sorted(node["properties"]), sorted(members)
                )


@unittest.skipIf(jsonschema is None, "jsonschema is not installed")
class SchemaAgreementTests(unittest.TestCase):
    """Cross-checks the two artifacts where a third-party validator is available.

    These are skipped rather than required, because the contract suite must run
    on a bare Python with nothing installed.
    """

    def setUp(self):
        self.validator = jsonschema.Draft202012Validator(load_schema())

    def test_the_schema_itself_is_valid(self):
        jsonschema.Draft202012Validator.check_schema(load_schema())

    def test_the_schema_accepts_every_conforming_fixture(self):
        for entry in load_manifest()["valid"]:
            with self.subTest(fixture=entry["file"]):
                errors = sorted(
                    self.validator.iter_errors(load_fixture(entry["file"])),
                    key=lambda error: list(error.absolute_path),
                )
                self.assertEqual(
                    errors, [],
                    [(list(e.absolute_path), e.message) for e in errors],
                )

    #: Deterministic mutations of a conforming envelope, chosen to land on both
    #: sides of the two artifacts' boundary: values the schema constrains, and
    #: values only the reference validator can judge. Fixed rather than random
    #: so a failure is reproducible from the test name alone.
    MUTATIONS = (
        ("occurred_at absent", lambda e: e.pop("occurred_at", None)),
        ("metadata absent", lambda e: e.pop("metadata", None)),
        ("metadata empty", lambda e: e.update(metadata={})),
        ("undeclared metadata name", lambda e: e["metadata"].update(tags=["a"])),
        ("boolean metadata", lambda e: e["metadata"].update(is_recurring=True)),
        ("integer metadata", lambda e: e["metadata"].update(word_count=0)),
        ("zero byte_length", lambda e: e["content"].update(byte_length=0)),
        ("sha-512 digest",
         lambda e: e["content"].update(digest={"algorithm": "sha-512",
                                               "value": "a" * 128})),
        ("experimental kind", lambda e: e.update(kind="x-voice-memo")),
        ("core kind note", lambda e: e.update(kind="note")),
        ("fractional seconds",
         lambda e: e.update(captured_at="2026-01-05T15:02:11.250Z")),
        ("nanosecond precision",
         lambda e: e.update(captured_at="2026-01-05T15:02:11.123456789Z")),
        ("equal timestamps",
         lambda e: e["payload"].update(preserved_at=e["provenance"]["emitted_at"])),
        ("https payload uri",
         lambda e: e["payload"].update(uri="https://payloads.example/a.txt")),
        ("opaque scheme payload uri",
         lambda e: e["payload"].update(uri="s3://example-bucket/a.txt")),
        ("run_id present", lambda e: e["provenance"].update(run_id="run-0001")),
        ("external_revision present",
         lambda e: e["source"].update(external_revision="2")),
        ("prerelease adapter version",
         lambda e: e["provenance"].update(adapter_version="1.0.0-rc.1")),
        ("long but legal title",
         lambda e: e["metadata"].update(title="t" * 512)),
        ("far past", lambda e: _shift_year(e, "1904")),
        ("far future", lambda e: _shift_year(e, "2999")),
    )

    def test_the_schema_is_never_stricter_than_the_reference_validator(self):
        # The direction that matters: if the schema rejected something the
        # contract accepts, the contract would say two different things to two
        # readers. Driven by mutations rather than by the invalid corpus —
        # every invalid fixture is rejected by the validator by construction,
        # so asserting it there can never fail and proves nothing.
        for label, mutate in self.MUTATIONS:
            with self.subTest(mutation=label):
                envelope = a_valid_envelope()
                mutate(envelope)
                accepted_by_validator = not validate(envelope)
                schema_errors = list(self.validator.iter_errors(envelope))
                if accepted_by_validator:
                    self.assertEqual(
                        schema_errors, [],
                        "the reference validator accepts %r but the schema "
                        "rejects it: %s"
                        % (label, [e.message for e in schema_errors]),
                    )

    def test_the_mutation_sweep_actually_reaches_conforming_envelopes(self):
        # A sweep whose every mutation happened to be invalid would pass the
        # test above vacuously, which is the failure it exists to replace.
        conforming = 0
        for _label, mutate in self.MUTATIONS:
            envelope = a_valid_envelope()
            mutate(envelope)
            if not validate(envelope):
                conforming += 1
        self.assertEqual(
            conforming, len(self.MUTATIONS),
            "every mutation is meant to stay conforming; %d did not"
            % (len(self.MUTATIONS) - conforming),
        )

    def test_neither_artifact_accepts_an_invalid_fixture(self):
        for entry in load_manifest()["invalid"]:
            with self.subTest(fixture=entry["file"]):
                document = load_fixture(entry["file"])
                self.assertFalse(
                    self.validator.is_valid(document) and not validate(document),
                    "%s is accepted by both artifacts" % entry["file"],
                )


if __name__ == "__main__":
    unittest.main()
