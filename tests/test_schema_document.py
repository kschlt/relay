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

from tests.support import SCHEMA_PATH, load_fixture, load_manifest

from relay_intake.validator import ENVELOPE_VERSION, validate

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised only where the lib is absent
    jsonschema = None


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

    def test_the_envelope_and_every_nested_object_are_closed(self):
        # An open object would let a vendor field ride along unnoticed, which
        # is precisely the leak the boundary exists to prevent.
        self.assertFalse(self.schema["additionalProperties"])
        for name in ("source", "provenance", "content", "payload"):
            self.assertFalse(
                self.schema["properties"][name]["additionalProperties"], name
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

    def test_every_required_member_of_the_validator_is_required_here(self):
        self.assertEqual(
            sorted(self.schema["required"]),
            sorted(["envelope_version", "intake_id", "kind", "captured_at",
                    "source", "provenance", "content", "payload"]),
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

    def test_the_schema_is_never_stricter_than_the_reference_validator(self):
        # The direction that matters. If the schema rejected something the
        # contract accepts, the contract would be saying two different things.
        for entry in load_manifest()["invalid"]:
            with self.subTest(fixture=entry["file"]):
                document = load_fixture(entry["file"])
                if not self.validator.is_valid(document):
                    self.assertNotEqual(
                        validate(document), [],
                        "the schema rejects %s but the reference validator "
                        "accepts it" % entry["file"],
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
