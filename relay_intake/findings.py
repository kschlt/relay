"""Validation findings: stable codes and a deterministic ordering.

A finding is a machine-readable statement that one rule was violated at one
location. Codes are part of the contract: a consumer may branch on a code, so
renaming one is a breaking change (see ``docs/compatibility.md``).
"""

import re

# Structural findings — the envelope is not shaped like an envelope.
E_NOT_OBJECT = "E_NOT_OBJECT"
E_FIELD_MISSING = "E_FIELD_MISSING"
E_FIELD_UNKNOWN = "E_FIELD_UNKNOWN"
E_TYPE = "E_TYPE"
E_ENUM = "E_ENUM"
E_FORMAT = "E_FORMAT"
E_RANGE = "E_RANGE"
E_NUMBER_NOT_INTEGER = "E_NUMBER_NOT_INTEGER"

# Contract findings — the envelope is well-shaped but says something it may not.
E_VERSION_UNSUPPORTED = "E_VERSION_UNSUPPORTED"
E_INTAKE_ID_DERIVATION = "E_INTAKE_ID_DERIVATION"
E_TIMESTAMP_ORDER = "E_TIMESTAMP_ORDER"
E_DIGEST_LENGTH = "E_DIGEST_LENGTH"
E_PAYLOAD_URI_EMBEDS_CONTENT = "E_PAYLOAD_URI_EMBEDS_CONTENT"
E_METADATA_KEY = "E_METADATA_KEY"
E_METADATA_VALUE = "E_METADATA_VALUE"
E_METADATA_SIZE = "E_METADATA_SIZE"
E_ENVELOPE_SIZE = "E_ENVELOPE_SIZE"

# Cross-envelope findings — raised by the conformance suite over a set.
E_REPLAY_DIVERGENT = "E_REPLAY_DIVERGENT"

#: Every code this implementation can emit. A conformance runner may use this
#: to reject an unrecognised code rather than silently ignoring it.
ALL_CODES = (
    E_NOT_OBJECT,
    E_FIELD_MISSING,
    E_FIELD_UNKNOWN,
    E_TYPE,
    E_ENUM,
    E_FORMAT,
    E_RANGE,
    E_NUMBER_NOT_INTEGER,
    E_VERSION_UNSUPPORTED,
    E_INTAKE_ID_DERIVATION,
    E_TIMESTAMP_ORDER,
    E_DIGEST_LENGTH,
    E_PAYLOAD_URI_EMBEDS_CONTENT,
    E_METADATA_KEY,
    E_METADATA_VALUE,
    E_METADATA_SIZE,
    E_ENVELOPE_SIZE,
    E_REPLAY_DIVERGENT,
)

_POINTER_ESCAPES = ((("~"), "~0"), ("/", "~1"))


def pointer(*segments):
    """Build an RFC 6901 JSON Pointer from path segments.

    ``pointer()`` is the whole document. Integer segments index into arrays.
    """
    if not segments:
        return ""
    out = []
    for segment in segments:
        text = str(segment)
        for raw, escaped in _POINTER_ESCAPES:
            text = text.replace(raw, escaped)
        out.append(text)
    return "/" + "/".join(out)


class Finding(object):
    """One rule violation, at one JSON Pointer location.

    Findings sort by ``(path, code)`` so that the same envelope always produces
    the same report in the same order, on any platform and in any Python build.
    """

    __slots__ = ("code", "path", "message")

    def __init__(self, code, path, message):
        self.code = code
        self.path = path
        self.message = message

    @property
    def _sort_key(self):
        return (self.path, self.code, self.message)

    def __eq__(self, other):
        if not isinstance(other, Finding):
            return NotImplemented
        return self._sort_key == other._sort_key

    def __hash__(self):
        return hash(self._sort_key)

    def __lt__(self, other):
        if not isinstance(other, Finding):
            return NotImplemented
        return self._sort_key < other._sort_key

    def __repr__(self):
        return "Finding(code=%r, path=%r, message=%r)" % (
            self.code,
            self.path,
            self.message,
        )

    def __str__(self):
        return "%s at %s: %s" % (self.code, self.path or "<document>", self.message)

    def to_dict(self):
        return {"code": self.code, "path": self.path, "message": self.message}


def sort_findings(findings):
    """Return findings in the contract's deterministic order."""
    return sorted(findings)


assert all(re.match(r"^E_[A-Z0-9_]+$", code) for code in ALL_CODES)
