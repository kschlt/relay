"""Canonical form, derived identity, and the item projection."""

import json
import unittest

from tests.support import a_valid_envelope, load_fixture

from relay_intake.canonical import (
    EMISSION_MEMBERS,
    canonical_bytes,
    canonical_text,
    content_identity,
    derive_intake_id,
    item_projection,
    projection_digest,
)


class CanonicalFormTests(unittest.TestCase):
    def test_member_order_does_not_change_the_bytes(self):
        one = {"b": 1, "a": {"z": True, "y": [1, 2]}}
        two = {"a": {"y": [1, 2], "z": True}, "b": 1}
        self.assertEqual(canonical_bytes(one), canonical_bytes(two))

    def test_array_order_does_change_the_bytes(self):
        # Arrays are ordered data. Sorting them would silently equate two
        # different items.
        self.assertNotEqual(canonical_bytes([1, 2]), canonical_bytes([2, 1]))

    def test_no_insignificant_whitespace(self):
        self.assertEqual(canonical_text({"a": 1, "b": [1, 2]}), '{"a":1,"b":[1,2]}')

    def test_round_trips_through_json(self):
        envelope = a_valid_envelope()
        self.assertEqual(
            canonical_bytes(envelope),
            canonical_bytes(json.loads(canonical_text(envelope))),
        )

    def test_non_ascii_is_not_escaped(self):
        self.assertEqual(canonical_text({"t": "Grüße"}), '{"t":"Grüße"}')

    def test_rejects_non_finite_numbers(self):
        with self.assertRaises(ValueError):
            canonical_bytes({"x": float("nan")})

    def test_is_stable_across_repeated_calls(self):
        envelope = a_valid_envelope()
        first = canonical_bytes(envelope)
        for _ in range(16):
            self.assertEqual(canonical_bytes(envelope), first)


class DerivedIdentityTests(unittest.TestCase):
    def test_derivation_is_deterministic(self):
        self.assertEqual(
            derive_intake_id("example-capture", "item-1"),
            derive_intake_id("example-capture", "item-1"),
        )

    def test_different_systems_do_not_collide(self):
        self.assertNotEqual(
            derive_intake_id("example-capture", "item-1"),
            derive_intake_id("example-other", "item-1"),
        )

    def test_separator_cannot_be_smuggled_to_force_a_collision(self):
        # Without the guard, ("a\x1fb", "c") and ("a", "b\x1fc") would share a
        # pre-image and therefore an identity.
        with self.assertRaises(ValueError):
            derive_intake_id("a\x1fb", "c")
        with self.assertRaises(ValueError):
            derive_intake_id("a", "b\x1fc")

    def test_identity_does_not_expose_the_source_identifier(self):
        intake_id = derive_intake_id("example-capture", "confidential-item-ref")
        self.assertNotIn("confidential-item-ref", intake_id)

    def test_rejects_non_string_components(self):
        with self.assertRaises(TypeError):
            derive_intake_id("example-capture", 17)

    def test_fixtures_carry_correctly_derived_identities(self):
        envelope = a_valid_envelope()
        self.assertEqual(
            envelope["intake_id"],
            derive_intake_id(
                envelope["source"]["system"], envelope["source"]["external_id"]
            ),
        )


class ContentIdentityTests(unittest.TestCase):
    def test_reports_length_and_digest_together(self):
        identity = content_identity(b"synthetic")
        self.assertEqual(identity["byte_length"], 9)
        self.assertEqual(identity["digest"]["algorithm"], "sha-256")
        self.assertEqual(len(identity["digest"]["value"]), 64)

    def test_distinguishes_different_bytes(self):
        self.assertNotEqual(
            content_identity(b"a")["digest"]["value"],
            content_identity(b"b")["digest"]["value"],
        )

    def test_rejects_text_input(self):
        # Hashing str would make the digest depend on an implicit encoding.
        with self.assertRaises(TypeError):
            content_identity("synthetic")

    def test_rejects_an_unadmitted_algorithm(self):
        with self.assertRaises(ValueError):
            content_identity(b"synthetic", algorithm="md5")


class ItemProjectionTests(unittest.TestCase):
    def test_drops_only_the_emission_members(self):
        envelope = a_valid_envelope()
        projection = item_projection(envelope)
        for member in EMISSION_MEMBERS:
            self.assertNotIn(member, projection)
        for member in envelope:
            if member not in EMISSION_MEMBERS:
                self.assertIn(member, projection)

    def test_a_replay_has_the_same_projection(self):
        original = load_fixture("valid/note-minimal.json")
        replayed = load_fixture("valid/note-minimal-replayed.json")
        self.assertNotEqual(original["provenance"], replayed["provenance"])
        self.assertEqual(projection_digest(original), projection_digest(replayed))

    def test_a_revision_has_a_different_projection(self):
        original = load_fixture("valid/note-minimal.json")
        revised = load_fixture("valid/note-revised.json")
        self.assertEqual(original["intake_id"], revised["intake_id"])
        self.assertNotEqual(projection_digest(original), projection_digest(revised))

    def test_rejects_a_non_object(self):
        with self.assertRaises(TypeError):
            item_projection(["not", "an", "envelope"])


if __name__ == "__main__":
    unittest.main()
