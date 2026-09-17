"""Deterministic validation of a canonical intake envelope.

Determinism here means three specific things, each of which a test enforces:

1. The same envelope always produces the same set of findings.
2. Findings are always returned in the same order, on any platform.
3. Validation reads nothing outside the envelope — no clock, no network, no
   filesystem, no locale, no environment. A validator that consulted the clock
   would reject tomorrow what it accepts today, which makes a fixture suite
   meaningless and makes a replayed envelope unverifiable.

The rules implemented here are the ones stated in ``docs/intake-envelope.md``.
Where a rule can be expressed in JSON Schema it is also expressed in
``schema/intake-envelope-v1.schema.json``; the rules that relate two fields to
each other cannot be, and live only here.
"""

import re

from relay_intake.canonical import (
    ALGORITHM_HEX_LENGTHS,
    INTAKE_ID_SEPARATOR,
    canonical_size,
    derive_intake_id,
)
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
    sort_findings,
)

#: The envelope version this implementation validates. Only the major version
#: appears on the wire; see ``docs/compatibility.md`` for why.
ENVELOPE_VERSION = "1"

#: Ceiling on the canonical form of a whole envelope. An envelope is metadata
#: and a reference; it is never content. A hard ceiling is what turns that
#: sentence from an intention into something a machine can enforce, and it is
#: what makes it safe to say an envelope may enter model context.
MAX_ENVELOPE_BYTES = 4096

#: Ceiling on the canonical form of ``metadata`` alone, so that the free-form
#: member cannot be used to carry a payload in pieces.
MAX_METADATA_BYTES = 2048

MAX_METADATA_MEMBERS = 32
MAX_METADATA_STRING = 512
MAX_METADATA_ARRAY = 32

#: Capture kinds this version defines. A consumer routes on kind, so the
#: vocabulary is closed: an unrecognised kind must not be guessed at.
CORE_KINDS = ("meeting", "note")

#: Experimental kinds. Namespaced so they can never collide with a future core
#: kind, and defined as not structurally routable.
EXPERIMENTAL_KIND_RE = re.compile(r"^x-[a-z0-9]+(?:-[a-z0-9]+)*\Z")

#: URI schemes that inline their data. Forbidden for a payload reference:
#: the whole point of the reference is that the bytes are somewhere else.
INLINE_URI_SCHEMES = ("data",)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_INTAKE_ID_RE = re.compile(r"^sha-256:[0-9a-f]{64}\Z")
_HEX_RE = re.compile(r"^[0-9a-f]+\Z")
_SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
                        r"(?:-[0-9A-Za-z.\-]+)?(?:\+[0-9A-Za-z.\-]+)?\Z")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~\-]{0,127}\Z")
_URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:[^\s]+\Z")
_MEDIA_TYPE_RE = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+\-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+\-]{0,126}"
    r"(?:[ \t]*;[ \t]*[a-z0-9!#$&^_.+\-]+=(?:\"[^\"]*\"|[^;\s]+))*\Z"
)
_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*\Z")
_METADATA_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}\Z")
_TIMESTAMP_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z\Z"
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

#: The member names each object admits. Anything else is a finding: an envelope
#: is closed so that a typo, or a vendor field that leaked past the adapter
#: boundary, fails loudly instead of being carried along and ignored.
_ENVELOPE_MEMBERS = {
    "envelope_version": True,
    "intake_id": True,
    "kind": True,
    "occurred_at": False,
    "captured_at": True,
    "source": True,
    "provenance": True,
    "content": True,
    "payload": True,
    "metadata": False,
}
_SOURCE_MEMBERS = {"system": True, "external_id": True, "external_revision": False}
_PROVENANCE_MEMBERS = {
    "adapter": True,
    "adapter_version": True,
    "acquired_at": True,
    "emitted_at": True,
    "run_id": False,
}
_CONTENT_MEMBERS = {"media_type": True, "byte_length": True, "digest": True}
_DIGEST_MEMBERS = {"algorithm": True, "value": True}
_PAYLOAD_MEMBERS = {"uri": True, "preserved_at": True}

#: Metadata names this version gives a meaning and a type. Other names are
#: permitted and must be ignored by a consumer, which is what makes adding one
#: a non-breaking change.
_METADATA_VOCABULARY = {
    "title": "string",
    "language": "language",
    "duration_seconds": "integer",
    "participant_count": "integer",
    "word_count": "integer",
}

#: The order timestamps must occur in. Each entry is (pointer-path, label).
#: The chain encodes the handoff: a thing happens, the source records it, an
#: adapter reads it, the adapter preserves the payload, and only then does the
#: adapter emit an envelope pointing at it.
_TIMESTAMP_CHAIN = (
    (("occurred_at",), "occurred_at"),
    (("captured_at",), "captured_at"),
    (("provenance", "acquired_at"), "provenance.acquired_at"),
    (("payload", "preserved_at"), "payload.preserved_at"),
    (("provenance", "emitted_at"), "provenance.emitted_at"),
)


def _is_int(value):
    # bool is a subclass of int in Python; an envelope must not conflate them.
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_timestamp(text):
    """Parse an RFC 3339 UTC timestamp into a comparable tuple, or None.

    Returns ``(days, seconds, nanoseconds)``. Only the ``Z`` offset is
    accepted: an offset-bearing timestamp compares correctly but *renders*
    differently for the same instant, which would break canonical form.
    """
    match = _TIMESTAMP_RE.match(text)
    if match is None:
        return None
    year, month, day, hour, minute, second = (int(g) for g in match.groups()[:6])
    fraction = match.group(7) or ""
    if not 1 <= month <= 12 or not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    # Leap seconds are rejected: they are not representable as an instant in
    # the arithmetic every consumer will actually use.
    if not 0 <= second <= 59:
        return None
    days_in_month = _DAYS_IN_MONTH[month - 1]
    if month == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        days_in_month = 29
    if not 1 <= day <= days_in_month:
        return None
    ordinal = year * 372 + (month - 1) * 31 + (day - 1)
    nanoseconds = int((fraction + "000000000")[:9]) if fraction else 0
    return (ordinal, hour * 3600 + minute * 60 + second, nanoseconds)


class _Report(object):
    """Collects findings during one validation pass."""

    def __init__(self):
        self.findings = []

    def add(self, code, path, message):
        self.findings.append(Finding(code, path, message))

    def __len__(self):
        return len(self.findings)


def _check_members(report, value, members, path_segments):
    """Check required/unknown members of a closed object. Returns True if usable."""
    at = pointer(*path_segments)
    if not isinstance(value, dict):
        report.add(E_TYPE, at, "expected a JSON object")
        return False
    for name, required in sorted(members.items()):
        if required and name not in value:
            report.add(
                E_FIELD_MISSING,
                pointer(*(path_segments + (name,))),
                "required member is absent",
            )
    for name in sorted(value):
        if name not in members:
            report.add(
                E_FIELD_UNKNOWN,
                pointer(*(path_segments + (name,))),
                "member is not defined by envelope version %s" % ENVELOPE_VERSION,
            )
    return True


def _check_string(report, value, path_segments, pattern=None, max_length=None,
                  description=""):
    at = pointer(*path_segments)
    if not isinstance(value, str):
        report.add(E_TYPE, at, "expected a string")
        return False
    if _CONTROL_RE.search(value):
        report.add(E_FORMAT, at, "must not contain control characters")
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        # A lone surrogate survives JSON parsing but has no UTF-8 encoding, so
        # an envelope containing one has no canonical form and cannot be
        # compared, hashed, or replayed.
        report.add(
            E_FORMAT, at,
            "must be encodable as UTF-8; an unpaired surrogate has no "
            "canonical form",
        )
        return False
    if max_length is not None and len(value) > max_length:
        report.add(E_RANGE, at, "must be at most %d characters" % max_length)
        return False
    if pattern is not None and pattern.match(value) is None:
        report.add(E_FORMAT, at, description or "does not match the required form")
        return False
    return True


def _check_timestamp(report, value, path_segments):
    at = pointer(*path_segments)
    if not isinstance(value, str):
        report.add(E_TYPE, at, "expected an RFC 3339 UTC timestamp string")
        return None
    parsed = _parse_timestamp(value)
    if parsed is None:
        report.add(
            E_FORMAT,
            at,
            "expected an RFC 3339 timestamp with a literal Z offset, "
            "for example 2026-01-05T15:02:11Z",
        )
        return None
    return parsed


def _check_non_negative_integer(report, value, path_segments):
    at = pointer(*path_segments)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        report.add(E_TYPE, at, "expected a number")
        return False
    if not _is_int(value):
        report.add(
            E_NUMBER_NOT_INTEGER,
            at,
            "must be an integer; the contract admits no fractional numbers",
        )
        return False
    if value < 0:
        report.add(E_RANGE, at, "must not be negative")
        return False
    return True


def _validate_source(report, source):
    if not _check_members(report, source, _SOURCE_MEMBERS, ("source",)):
        return
    if "system" in source:
        _check_string(
            report, source["system"], ("source", "system"),
            pattern=_SLUG_RE, max_length=64,
            description="must be a lowercase hyphen-separated slug",
        )
    if "external_id" in source:
        value = source["external_id"]
        # U+001F, which separates the identity derivation components, needs no
        # rule of its own here: it is a control character, and _check_string
        # rejects every one of them. The guard that remains live is the one in
        # _validate_intake_id, which keeps derive_intake_id from being called
        # with a component it refuses.
        if _check_string(report, value, ("source", "external_id"), max_length=512):
            if not value:
                report.add(
                    E_RANGE, pointer("source", "external_id"),
                    "must not be empty",
                )
    if "external_revision" in source:
        _check_string(
            report, source["external_revision"],
            ("source", "external_revision"), max_length=256,
        )


def _validate_provenance(report, provenance):
    if not _check_members(report, provenance, _PROVENANCE_MEMBERS, ("provenance",)):
        return
    if "adapter" in provenance:
        _check_string(
            report, provenance["adapter"], ("provenance", "adapter"),
            pattern=_SLUG_RE, max_length=64,
            description="must be a lowercase hyphen-separated slug",
        )
    if "adapter_version" in provenance:
        _check_string(
            report, provenance["adapter_version"],
            ("provenance", "adapter_version"), pattern=_SEMVER_RE, max_length=64,
            description="must be a semantic version, for example 1.4.2",
        )
    if "run_id" in provenance:
        _check_string(
            report, provenance["run_id"], ("provenance", "run_id"),
            pattern=_RUN_ID_RE, max_length=128,
            description="must be an opaque identifier of unreserved characters",
        )


def _validate_content(report, content):
    if not _check_members(report, content, _CONTENT_MEMBERS, ("content",)):
        return
    if "media_type" in content:
        _check_string(
            report, content["media_type"], ("content", "media_type"),
            pattern=_MEDIA_TYPE_RE, max_length=255,
            description="must be a lowercase media type, optionally with "
                        "parameters, for example text/plain; charset=utf-8",
        )
    if "byte_length" in content:
        _check_non_negative_integer(
            report, content["byte_length"], ("content", "byte_length")
        )
    if "digest" not in content:
        return
    digest = content["digest"]
    if not _check_members(report, digest, _DIGEST_MEMBERS, ("content", "digest")):
        return
    algorithm = digest.get("algorithm")
    if "algorithm" in digest:
        if not isinstance(algorithm, str):
            report.add(
                E_TYPE, pointer("content", "digest", "algorithm"),
                "expected a string",
            )
        elif algorithm not in ALGORITHM_HEX_LENGTHS:
            report.add(
                E_ENUM, pointer("content", "digest", "algorithm"),
                "must be one of: %s" % ", ".join(sorted(ALGORITHM_HEX_LENGTHS)),
            )
    if "value" not in digest:
        return
    value = digest["value"]
    if not _check_string(
        report, value, ("content", "digest", "value"),
        pattern=_HEX_RE, max_length=256,
        description="must be lowercase hexadecimal",
    ):
        return
    expected = ALGORITHM_HEX_LENGTHS.get(algorithm)
    if expected is not None and len(value) != expected:
        report.add(
            E_DIGEST_LENGTH, pointer("content", "digest", "value"),
            "%s requires %d hexadecimal characters, found %d"
            % (algorithm, expected, len(value)),
        )


def _validate_payload(report, payload):
    if not _check_members(report, payload, _PAYLOAD_MEMBERS, ("payload",)):
        return
    if "uri" not in payload:
        return
    uri = payload["uri"]
    if not _check_string(
        report, uri, ("payload", "uri"), pattern=_URI_RE, max_length=2048,
        description="must be an absolute URI with a scheme",
    ):
        return
    scheme = uri.split(":", 1)[0].lower()
    if scheme in INLINE_URI_SCHEMES:
        report.add(
            E_PAYLOAD_URI_EMBEDS_CONTENT, pointer("payload", "uri"),
            "the %r scheme inlines content; a payload must be referenced, "
            "not embedded" % (scheme,),
        )


def _validate_metadata_value(report, key, value):
    at = pointer("metadata", key)
    declared = _METADATA_VOCABULARY.get(key)
    if declared == "integer":
        if not _check_non_negative_integer(report, value, ("metadata", key)):
            return
        return
    if declared == "language":
        _check_string(
            report, value, ("metadata", key), pattern=_LANGUAGE_RE, max_length=35,
            description="must be a BCP 47 language tag, for example en-GB",
        )
        return
    if declared == "string":
        _check_string(report, value, ("metadata", key), max_length=MAX_METADATA_STRING)
        return
    # Undeclared name: structurally constrained, but given no meaning here.
    if isinstance(value, str):
        _check_string(report, value, ("metadata", key), max_length=MAX_METADATA_STRING)
        return
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if not _is_int(value):
            report.add(
                E_NUMBER_NOT_INTEGER, at,
                "must be an integer; the contract admits no fractional numbers",
            )
        return
    if isinstance(value, list):
        if len(value) > MAX_METADATA_ARRAY:
            report.add(
                E_RANGE, at, "must hold at most %d items" % MAX_METADATA_ARRAY
            )
            return
        for index, item in enumerate(value):
            if not isinstance(item, str):
                report.add(
                    E_METADATA_VALUE, pointer("metadata", key, index),
                    "an array member must be a string",
                )
            else:
                _check_string(
                    report, item, ("metadata", key, index),
                    max_length=MAX_METADATA_STRING,
                )
        return
    report.add(
        E_METADATA_VALUE, at,
        "must be a string, an integer, a boolean, or an array of strings",
    )


def _validate_metadata(report, metadata):
    if not isinstance(metadata, dict):
        report.add(E_TYPE, pointer("metadata"), "expected a JSON object")
        return
    if len(metadata) > MAX_METADATA_MEMBERS:
        report.add(
            E_RANGE, pointer("metadata"),
            "must hold at most %d members" % MAX_METADATA_MEMBERS,
        )
    size = canonical_size(metadata)
    if size is not None and size > MAX_METADATA_BYTES:
        report.add(
            E_METADATA_SIZE, pointer("metadata"),
            "canonical form is %d bytes, exceeding the %d-byte ceiling; "
            "metadata describes an item, it does not carry it"
            % (size, MAX_METADATA_BYTES),
        )
    for key in sorted(metadata):
        if _METADATA_KEY_RE.match(key) is None:
            report.add(
                E_METADATA_KEY, pointer("metadata", key),
                "a metadata name must be lowercase snake_case and "
                "source-neutral; vendor-specific attributes belong in the "
                "preserved payload",
            )
            continue
        _validate_metadata_value(report, key, metadata[key])


def _validate_timestamp_chain(report, envelope):
    parsed = []
    for path, label in _TIMESTAMP_CHAIN:
        container = envelope
        for segment in path[:-1]:
            if not isinstance(container, dict):
                container = None
                break
            container = container.get(segment)
        if not isinstance(container, dict) or path[-1] not in container:
            continue
        value = _check_timestamp(report, container[path[-1]], path)
        if value is not None:
            parsed.append((value, label, path))
    for index in range(1, len(parsed)):
        earlier_value, earlier_label, _ = parsed[index - 1]
        later_value, later_label, later_path = parsed[index]
        if later_value < earlier_value:
            report.add(
                E_TIMESTAMP_ORDER, pointer(*later_path),
                "%s must not precede %s" % (later_label, earlier_label),
            )


def _validate_intake_id(report, envelope):
    intake_id = envelope.get("intake_id")
    if not _check_string(
        report, intake_id, ("intake_id",), pattern=_INTAKE_ID_RE, max_length=72,
        description="must be sha-256: followed by 64 lowercase hex characters",
    ):
        return
    source = envelope.get("source")
    if not isinstance(source, dict):
        return
    system = source.get("system")
    external_id = source.get("external_id")
    if not isinstance(system, str) or not isinstance(external_id, str):
        return
    try:
        expected = derive_intake_id(system, external_id)
    except (ValueError, UnicodeEncodeError):
        # The components are not derivable — U+001F, or an unpaired surrogate
        # with no UTF-8 encoding. Both are already reported against the members
        # that carry them, and the derived identity is meaningless either way.
        return
    if intake_id != expected:
        report.add(
            E_INTAKE_ID_DERIVATION, pointer("intake_id"),
            "must be derived from source.system and source.external_id; "
            "expected %s" % expected,
        )


def validate(envelope):
    """Validate one intake envelope and return findings in canonical order.

    An empty list means the envelope satisfies every rule this version states.
    A non-empty list is the complete set of violations, not the first one: a
    caller fixing an adapter wants all of them at once.
    """
    report = _Report()

    if not isinstance(envelope, dict):
        report.add(E_NOT_OBJECT, "", "an envelope must be a JSON object")
        return sort_findings(report.findings)

    # None when the envelope holds a value with no canonical form (NaN, an
    # unpaired surrogate). Those are violations in their own right and are
    # reported by the member checks below; the size rule simply abstains rather
    # than raising and abandoning the run.
    size = canonical_size(envelope)
    if size is not None and size > MAX_ENVELOPE_BYTES:
        report.add(
            E_ENVELOPE_SIZE, "",
            "canonical form is %d bytes, exceeding the %d-byte ceiling; an "
            "envelope references a payload, it never carries one"
            % (size, MAX_ENVELOPE_BYTES),
        )

    _check_members(report, envelope, _ENVELOPE_MEMBERS, ())

    version = envelope.get("envelope_version")
    if "envelope_version" in envelope:
        if not isinstance(version, str):
            report.add(E_TYPE, pointer("envelope_version"), "expected a string")
        elif version != ENVELOPE_VERSION:
            report.add(
                E_VERSION_UNSUPPORTED, pointer("envelope_version"),
                "this implementation validates envelope version %s, found %r"
                % (ENVELOPE_VERSION, version),
            )

    if "kind" in envelope:
        kind = envelope["kind"]
        if not isinstance(kind, str):
            report.add(E_TYPE, pointer("kind"), "expected a string")
        elif kind not in CORE_KINDS and EXPERIMENTAL_KIND_RE.match(kind) is None:
            report.add(
                E_ENUM, pointer("kind"),
                "must be one of: %s; or an experimental kind matching x-*"
                % ", ".join(CORE_KINDS),
            )

    if "intake_id" in envelope:
        _validate_intake_id(report, envelope)
    if "source" in envelope:
        _validate_source(report, envelope["source"])
    if "provenance" in envelope:
        _validate_provenance(report, envelope["provenance"])
    if "content" in envelope:
        _validate_content(report, envelope["content"])
    if "payload" in envelope:
        _validate_payload(report, envelope["payload"])
    if "metadata" in envelope:
        _validate_metadata(report, envelope["metadata"])

    _validate_timestamp_chain(report, envelope)

    return sort_findings(report.findings)


def is_valid(envelope):
    """True when ``envelope`` produces no findings."""
    return not validate(envelope)
