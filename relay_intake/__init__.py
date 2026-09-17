"""Relay canonical intake envelope — reference implementation.

This package is the executable half of the intake contract. The normative
documents are ``docs/intake-envelope.md`` (what an envelope is) and
``docs/compatibility.md`` (how it may change). The machine-readable structural
schema is ``schema/intake-envelope-v1.schema.json``.

Nothing here performs routing, delivery, or any network or filesystem write on
an operator's behalf. It validates envelopes and derives identity, and that is
all it is meant to do.
"""

from relay_intake.canonical import (
    ALGORITHM_HEX_LENGTHS,
    EMISSION_MEMBERS,
    canonical_bytes,
    canonical_size,
    canonical_text,
    content_identity,
    derive_intake_id,
    item_projection,
)
from relay_intake.findings import Finding
from relay_intake.validator import (
    ENVELOPE_VERSION,
    MAX_ENVELOPE_BYTES,
    MAX_METADATA_BYTES,
    is_valid,
    validate,
)

__all__ = [
    "ALGORITHM_HEX_LENGTHS",
    "EMISSION_MEMBERS",
    "ENVELOPE_VERSION",
    "Finding",
    "MAX_ENVELOPE_BYTES",
    "MAX_METADATA_BYTES",
    "canonical_bytes",
    "canonical_size",
    "canonical_text",
    "content_identity",
    "derive_intake_id",
    "is_valid",
    "item_projection",
    "validate",
]
