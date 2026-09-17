"""The contract suite an adapter runs against its own emitted envelopes.

``validate`` answers a question about one envelope. Two of the contract's
promises are not about one envelope, though, and this module is where they are
checked:

* **Replay** — re-emitting an unchanged item must produce the same item facts.
  An adapter that derives ``intake_id`` from the source but quietly renumbers a
  title, or reorders participants, breaks deduplication downstream in a way
  that single-envelope validation cannot see.
* **Revision** — the same item at a different content digest is legal, and a
  suite that flagged it would push adapters toward inventing a fresh identity
  for every edit, which destroys the identity's usefulness.

An adapter in any language can run this: write envelopes as JSON files or as a
JSON Lines stream, then point the module at them.

    python3 -m relay_intake.conformance path/to/envelopes/
    my-adapter emit | python3 -m relay_intake.conformance -

``--json`` emits a machine-readable report; the exit status is 0 when every
envelope conforms and 1 when any does not.
"""

import argparse
import json
import os
import sys

from relay_intake.canonical import canonical_text, item_projection
from relay_intake.findings import E_REPLAY_DIVERGENT, Finding, sort_findings
from relay_intake.validator import validate


class EnvelopeResult(object):
    """The outcome for one envelope, tied to where it came from."""

    __slots__ = ("origin", "envelope", "findings")

    def __init__(self, origin, envelope, findings):
        self.origin = origin
        self.envelope = envelope
        self.findings = findings

    @property
    def conforms(self):
        return not self.findings

    def to_dict(self):
        return {
            "origin": self.origin,
            "conforms": self.conforms,
            "findings": [finding.to_dict() for finding in self.findings],
        }


class ConformanceReport(object):
    """The outcome for a whole set of envelopes."""

    def __init__(self, results, cross_findings):
        self.results = results
        self.cross_findings = cross_findings

    @property
    def conforms(self):
        return all(r.conforms for r in self.results) and not self.cross_findings

    @property
    def counts(self):
        conforming = sum(1 for r in self.results if r.conforms)
        return {
            "envelopes": len(self.results),
            "conforming": conforming,
            "rejected": len(self.results) - conforming,
            "cross_envelope_findings": len(self.cross_findings),
        }

    def to_dict(self):
        return {
            "conforms": self.conforms,
            "counts": self.counts,
            "envelopes": [r.to_dict() for r in self.results],
            "cross_envelope_findings": [f.to_dict() for f in self.cross_findings],
        }

    def render(self):
        lines = []
        for result in self.results:
            if result.conforms:
                lines.append("ok      %s" % result.origin)
                continue
            lines.append("FAIL    %s" % result.origin)
            for finding in result.findings:
                lines.append("        %s" % finding)
        for finding in self.cross_findings:
            lines.append("FAIL    <set>")
            lines.append("        %s" % finding)
        counts = self.counts
        lines.append("")
        lines.append(
            "%d envelope(s): %d conforming, %d rejected, "
            "%d cross-envelope finding(s)"
            % (
                counts["envelopes"],
                counts["conforming"],
                counts["rejected"],
                counts["cross_envelope_findings"],
            )
        )
        return "\n".join(lines)


def check_set(pairs):
    """Run the whole suite over ``(origin, envelope)`` pairs.

    Returns a :class:`ConformanceReport`. Cross-envelope checks run only over
    envelopes that individually conform, because an invalid envelope's identity
    means nothing and reporting a consequent replay divergence would just be
    noise on top of the real finding.
    """
    results = [
        EnvelopeResult(origin, envelope, validate(envelope))
        for origin, envelope in pairs
    ]
    # Group conforming envelopes by the pair that must pin the item's facts.
    seen = {}
    cross = []
    for result in results:
        if not result.conforms:
            continue
        envelope = result.envelope
        key = (envelope["intake_id"], envelope["content"]["digest"]["value"])
        projection = canonical_text(item_projection(envelope))
        if key not in seen:
            seen[key] = (result.origin, projection)
            continue
        first_origin, first_projection = seen[key]
        if first_projection != projection:
            cross.append(
                Finding(
                    E_REPLAY_DIVERGENT,
                    "",
                    "%s and %s share an intake_id and a content digest but "
                    "describe the item differently; re-emitting an unchanged "
                    "item must reproduce its facts exactly"
                    % (first_origin, result.origin),
                )
            )
    return ConformanceReport(results, sort_findings(cross))


def load_json_lines(stream, origin="<stdin>"):
    """Yield ``(origin, envelope)`` from a JSON Lines stream.

    A line that is not JSON yields the string itself, so that ``validate``
    reports it as a non-object rather than the loader crashing on it.
    """
    for number, line in enumerate(stream, start=1):
        line = line.strip()
        if not line:
            continue
        where = "%s:%d" % (origin, number)
        try:
            yield where, json.loads(line)
        except ValueError as error:
            yield where, "<unparseable JSON: %s>" % (error,)


def load_path(path):
    """Yield ``(origin, envelope)`` from a JSON file, a JSONL file, or a tree."""
    if os.path.isdir(path):
        for root, dirnames, filenames in os.walk(path):
            dirnames.sort()
            for filename in sorted(filenames):
                if filename.endswith((".json", ".jsonl")):
                    for pair in load_path(os.path.join(root, filename)):
                        yield pair
        return
    with open(path, "r", encoding="utf-8") as handle:
        if path.endswith(".jsonl"):
            for pair in load_json_lines(handle, origin=path):
                yield pair
            return
        try:
            document = json.load(handle)
        except ValueError as error:
            yield path, "<unparseable JSON: %s>" % (error,)
            return
    # A JSON file may hold one envelope or an array of them; both are common
    # ways for an adapter to dump a run, and neither is worth refusing.
    if isinstance(document, list):
        for index, envelope in enumerate(document):
            yield "%s[%d]" % (path, index), envelope
    else:
        yield path, document


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m relay_intake.conformance",
        description="Check intake envelopes against the Relay intake contract.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="JSON file, JSON Lines file, directory, or - for stdin (JSON Lines)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit a machine-readable report instead of text",
    )
    arguments = parser.parse_args(argv)

    pairs = []
    for path in arguments.paths:
        if path == "-":
            pairs.extend(load_json_lines(sys.stdin))
        else:
            pairs.extend(load_path(path))

    report = check_set(pairs)
    if arguments.as_json:
        sys.stdout.write(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
        )
    else:
        sys.stdout.write(report.render() + "\n")
    return 0 if report.conforms else 1


if __name__ == "__main__":
    sys.exit(main())
