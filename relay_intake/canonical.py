"""Canonical form, derived identity, and the item projection.

Three ideas live here, and all three exist to make replay checkable:

* **Canonical form** — one byte sequence per envelope value, so that "the same
  envelope" is a thing a machine can decide rather than a thing a human argues
  about.
* **Derived identity** — ``intake_id`` is a function of the source item, so an
  adapter re-reading the same item necessarily produces the same identity
  without keeping any state to remember it.
* **Item projection** — the part of an envelope that describes the captured
  item, as opposed to the part that describes this particular act of emitting
  it. Re-emission may change the latter and must not change the former.
"""

import hashlib
import json

#: Hex digest lengths for the digest algorithms the contract admits.
ALGORITHM_HEX_LENGTHS = {
    "sha-256": 64,
    "sha-512": 128,
}

#: Hash constructors, keyed by the contract's algorithm names.
_HASHERS = {
    "sha-256": hashlib.sha256,
    "sha-512": hashlib.sha512,
}

#: The algorithm used to derive ``intake_id``. Fixed for envelope version 1:
#: two adapters must agree on it without negotiating, or the identity is not
#: shared and idempotency across adapters silently stops working.
INTAKE_ID_ALGORITHM = "sha-256"

#: Separator between the two components of the derivation pre-image. U+001F
#: (UNIT SEPARATOR) is not legal in a source system identifier and is rejected
#: in an external identifier, so it cannot be smuggled in to force a collision.
INTAKE_ID_SEPARATOR = "\x1f"

#: Envelope members that describe *this act of emission* rather than the item
#: itself, and are therefore excluded from the item projection.
#:
#: ``provenance`` is obviously one: which adapter ran, when, under which run.
#: ``payload`` is the less obvious one. A payload reference says where these
#: bytes were put and when they were put there, which is a fact about a
#: preservation, not about the captured item. Two adapters that preserve the
#: same item to different stores agree on everything that matters — and the
#: content digest already guarantees the bytes are identical, so the reference
#: adds no identity the item projection needs.
EMISSION_MEMBERS = ("provenance", "payload")


def canonical_bytes(value):
    """Serialise ``value`` to the contract's canonical byte form.

    UTF-8, object members sorted by name, no insignificant whitespace, and no
    non-finite numbers. Because the contract admits no floating-point numbers,
    this form is reproducible across languages — the usual canonical-JSON
    hazard is float formatting, and it cannot arise here.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_size(value):
    """Canonical byte length of ``value``, or ``None`` if it has none.

    Some JSON values have no canonical form at all: ``json.loads`` accepts
    ``NaN`` and ``Infinity`` by default, a lone surrogate survives parsing but
    cannot be encoded as UTF-8, and a deeply nested value can parse and still
    exhaust the stack on the way back out. Each is already a violation under
    another rule, so validation reports it there — but a size check must not be
    the thing that discovers it, because raising would abandon a whole
    conformance run over one bad envelope.
    """
    try:
        return len(canonical_bytes(value))
    except (ValueError, UnicodeEncodeError):
        return None
    except RecursionError:
        # Serialising recurses, and so does parsing — but not to the same
        # depth, and neither limit is absolute: both are measured against the
        # stack already in use. So there is a narrow band of nesting that
        # json.loads accepts and this then cannot serialise, and where the band
        # falls depends on how deeply the caller was nested when it called.
        # Without this, the same envelope raises or returns findings depending
        # on who asked, which breaks the determinism the contract promises
        # before it ever reaches the never-raises guarantee.
        return None


def canonical_text(value):
    """``canonical_bytes`` decoded back to ``str``, for display and diffing."""
    return canonical_bytes(value).decode("utf-8")


def derive_intake_id(system, external_id):
    """Derive the canonical ``intake_id`` for one source item.

    The identity covers the source system and the item's identifier within it,
    and deliberately *not* any revision marker: an edited item is the same item.
    Which revision an envelope carries is answered by ``content.digest``.

    Hashing rather than concatenating is not obfuscation — it gives a
    fixed-width identifier with no parsing rules, and it keeps a source-system
    identifier out of logs and receipts that quote the intake id.
    """
    if not isinstance(system, str) or not isinstance(external_id, str):
        raise TypeError("system and external_id must both be str")
    if INTAKE_ID_SEPARATOR in system or INTAKE_ID_SEPARATOR in external_id:
        raise ValueError("U+001F is not permitted in a derivation component")
    try:
        preimage = (system + INTAKE_ID_SEPARATOR + external_id).encode("utf-8")
    except UnicodeEncodeError:
        # An unpaired surrogate has no UTF-8 encoding, so it has no pre-image
        # and therefore no identity. Re-raised as ValueError so that callers
        # have one error type to guard rather than two.
        raise ValueError(
            "derivation components must be encodable as UTF-8; an unpaired "
            "surrogate has no identity"
        )
    digest = _HASHERS[INTAKE_ID_ALGORITHM](preimage).hexdigest()
    return "%s:%s" % (INTAKE_ID_ALGORITHM, digest)


def content_identity(payload, algorithm=INTAKE_ID_ALGORITHM):
    """Build the ``content`` identity members for a preserved payload.

    Returns ``{"byte_length": ..., "digest": {...}}``. The caller supplies
    ``media_type``, which is a fact about the payload that its bytes do not
    carry.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes")
    if algorithm not in _HASHERS:
        raise ValueError("unsupported digest algorithm: %r" % (algorithm,))
    return {
        "byte_length": len(payload),
        "digest": {
            "algorithm": algorithm,
            "value": _HASHERS[algorithm](bytes(payload)).hexdigest(),
        },
    }


def item_projection(envelope):
    """Return the item-describing part of ``envelope``.

    Two envelopes for the same item, emitted by different runs or by different
    adapters, differ in how they were produced and must agree on what they
    describe. Comparing projections is how the conformance suite checks that.
    """
    if not isinstance(envelope, dict):
        raise TypeError("envelope must be a JSON object")
    return {
        key: value
        for key, value in envelope.items()
        if key not in EMISSION_MEMBERS
    }


def projection_digest(envelope):
    """A short, stable fingerprint of an envelope's item projection."""
    return _HASHERS[INTAKE_ID_ALGORITHM](
        canonical_bytes(item_projection(envelope))
    ).hexdigest()
