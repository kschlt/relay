# The canonical intake envelope, version 1

> **Status: defined and executable.** This is the first contract Relay has
> settled. Everything downstream of it — routing, delivery, receipts,
> scheduling — remains undefined, and nothing here depends on any of them.

An **intake envelope** is what a source adapter hands to Relay when it has
captured something. It is the boundary the whole project rests on: a consumer of
envelopes contains no knowledge of which capture tool produced one, and adding a
second capture tool means writing a second adapter rather than reworking
anything downstream.

The envelope describes a captured item. It never carries the item.

## The three artifacts

| Artifact | Role |
|---|---|
| This document | Normative. Every rule, including the ones a schema cannot express. |
| [`schema/intake-envelope-v1.schema.json`](../schema/intake-envelope-v1.schema.json) | The structural rules, machine-readable, for adapters in any language. |
| [`relay_intake/`](../relay_intake) | The reference validator and the contract suite. |

The schema is deliberately the weaker artifact: rules relating two members to
each other cannot be stated in JSON Schema. A document the schema accepts is
*well-shaped*, not necessarily *conforming*. The reference validator is
authoritative, and a test enforces that the schema never rejects anything the
validator accepts.

## Shape

```json
{
  "envelope_version": "1",
  "intake_id": "sha-256:1f0e…",
  "kind": "meeting",
  "occurred_at": "2026-01-05T14:00:00Z",
  "captured_at": "2026-01-05T15:02:11Z",
  "source": {
    "system": "example-capture",
    "external_id": "mtg-0001-synthetic"
  },
  "provenance": {
    "adapter": "example-adapter",
    "adapter_version": "0.3.1",
    "acquired_at": "2026-01-05T15:30:00Z",
    "emitted_at": "2026-01-05T15:30:02Z"
  },
  "content": {
    "media_type": "text/vtt; charset=utf-8",
    "byte_length": 2048,
    "digest": { "algorithm": "sha-256", "value": "…" }
  },
  "payload": {
    "uri": "example-store:meeting/mtg-0001-synthetic.vtt",
    "preserved_at": "2026-01-05T15:30:01Z"
  },
  "metadata": {
    "title": "Synthetic planning discussion",
    "duration_seconds": 2700,
    "participant_count": 4
  }
}
```

Working versions of this and of every rejection case are in
[`fixtures/`](../fixtures). All of them are synthetic.

## Members

Every object in an envelope is **closed**: a member not listed here is a
violation, not an extension. That is what makes a vendor field which leaked past
an adapter fail loudly instead of riding along and being ignored.

### Top level

| Member | Required | Type | Meaning |
|---|---|---|---|
| `envelope_version` | yes | `"1"` | Major version of this contract. |
| `intake_id` | yes | string | Identity of the captured item. Derived — see [Identity](#identity). |
| `kind` | yes | string | What was captured. Closed vocabulary — see [Kinds](#kinds). |
| `occurred_at` | no | timestamp | When the captured thing happened. Absent when the source cannot say. |
| `captured_at` | yes | timestamp | When the source system recorded the item. |
| `source` | yes | object | Where the item came from. |
| `provenance` | yes | object | How this envelope came to exist. |
| `content` | yes | object | Identity of the preserved bytes. |
| `payload` | yes | object | Where the bytes are. |
| `metadata` | no | object | Source-neutral facts about the item. |

### `source`

| Member | Required | Type | Meaning |
|---|---|---|---|
| `system` | yes | slug, ≤64 | Vendor-neutral identifier for the capture system. |
| `external_id` | yes | string, 1–512 | The item's identifier within that system. Opaque to Relay. |
| `external_revision` | no | string, ≤256 | Source-side revision marker. Advisory only. |

`system` participates in identity derivation, so it must be stable for the
lifetime of a deployment. Changing it re-identifies every item that source ever
produced.

### `provenance`

| Member | Required | Type | Meaning |
|---|---|---|---|
| `adapter` | yes | slug, ≤64 | Which adapter produced this envelope. |
| `adapter_version` | yes | semver | Which version of it. |
| `acquired_at` | yes | timestamp | When the adapter read the item from the source. |
| `emitted_at` | yes | timestamp | When the adapter produced this envelope. |
| `run_id` | no | string, ≤128 | Collection-run identifier, for operational correlation only. |

### `content`

| Member | Required | Type | Meaning |
|---|---|---|---|
| `media_type` | yes | string, ≤255 | Media type of the preserved payload. |
| `byte_length` | yes | integer ≥0 | Length of the preserved payload in bytes. |
| `digest.algorithm` | yes | `sha-256` \| `sha-512` | Digest algorithm. |
| `digest.value` | yes | lowercase hex | Digest of the exact preserved bytes. |

The digest is over the payload **as stored**, not over any normalised or
re-encoded form. It is what distinguishes one revision of an item from another,
and what lets a consumer verify that a payload it fetched is the one the
envelope described.

### `payload`

| Member | Required | Type | Meaning |
|---|---|---|---|
| `uri` | yes | absolute URI, ≤2048 | Where the preserved bytes are. |
| `preserved_at` | yes | timestamp | When the adapter durably wrote them. |

Relay defines no storage. Any absolute URI an operator's resolver understands is
acceptable — `example-store:…`, `https://…`, `s3://…`. What is *not* acceptable
is a scheme that inlines the data: `data:` URIs are rejected, because the entire
purpose of a reference is that the bytes travel separately.

### `metadata`

The one open object, and still bounded: at most 32 members, at most 2048 bytes
in canonical form, values limited to strings (≤512 characters), integers,
booleans, and arrays of strings (≤32 items). Names are lowercase `snake_case`.

These names have a defined meaning, and all are optional:

| Name | Type | Meaning |
|---|---|---|
| `title` | string | A human-readable label for the item. |
| `language` | BCP 47 tag | Primary language of the content. |
| `duration_seconds` | integer ≥0 | Duration of a timed capture. |
| `participant_count` | integer ≥0 | Number of people involved. |
| `word_count` | integer ≥0 | Approximate length of the content. |

Other names are permitted and **a consumer must ignore names it does not
recognise**. That is what makes adding one a non-breaking change.

Metadata must be source-neutral. A vendor's room identifier, internal status
code, or proprietary flag belongs in the preserved payload, where an adapter's
own downstream reader can find it. Putting it here would make the envelope
vendor-shaped, which falsifies the project's central claim.

The size limits are not tidiness. They are the mechanism that stops content
being carried in an envelope a piece at a time.

## Kinds

`kind` is what structural routing reads, so the vocabulary is closed.

| Kind | Meaning |
|---|---|
| `meeting` | A recorded conversation between people. |
| `note` | A general capture: a dictated thought, a written note. |

An adapter may also emit an **experimental kind** matching `x-<slug>` — for
example `x-voice-memo`. Experimental kinds are namespaced so they can never
collide with a core kind added later, and they must not be routed structurally.

A consumer that does not recognise a kind **must not infer behaviour from it**.
An unrecognised kind is an unresolved item, not a guess.

The two kinds are not arbitrary — they are the two placement modes:

- A **meeting** is placed by what it *is*. Kind plus trusted metadata is
  sufficient, and the transcript is never read to decide where it goes.
- A **note** may need to be placed by what it *means*. A consumer may read the
  payload once, at the point of that decision.

The envelope supports both by carrying enough metadata for the first and a
reference sufficient for the second. It does not say which mode applies, because
that is a consumer's policy and not an adapter's to declare.

## Identity

Two identities, answering two different questions.

### `intake_id` — which item is this?

```
intake_id = "sha-256:" + hex(sha256(utf8(source.system) + U+001F + utf8(source.external_id)))
```

Derived, not assigned. Three things follow, and all three are the point:

- **An adapter needs no memory.** Re-reading the same item necessarily produces
  the same identity, with nothing stored between runs to remember it by.
- **Two adapters agree.** Two independent implementations reading the same
  source produce the same identity without coordinating.
- **The source identifier does not travel.** The identity is a hash, so a
  receipt or a log that quotes an `intake_id` does not thereby quote a
  source-system identifier.

U+001F may not appear in either component. Without that rule,
`("a\x1fb", "c")` and `("a", "b\x1fc")` would share a pre-image and therefore an
identity.

The identity covers the item, deliberately **not** its revision. An edited item
is the same item.

### `content.digest` — which revision is this?

Which version of that item this envelope describes. Together the two give
consumers what they need:

| Situation | `intake_id` | `content.digest` | What it means |
|---|---|---|---|
| Re-run over the same scope | same | same | A **replay**. Already handled; do nothing. |
| The source item was edited | same | different | A **revision**. Consumer policy decides. |
| A different item | different | — | New. |

This is what makes "just run it again" a safe response to a partial run, a
network failure mid-collection, an overlapping schedule, or a manual retry after
an error — which is to say, to every realistic failure.

## Timestamps

All timestamps are RFC 3339 with a literal `Z`. An offset-bearing timestamp
denotes the same instant and *renders* differently, which would make canonical
form ambiguous, so only `Z` is admitted. Fractional seconds are permitted to
nanosecond precision. Leap seconds are not: they are not representable in the
arithmetic every consumer will actually use.

Five timestamps must be non-decreasing in this order:

```
occurred_at  ≤  captured_at  ≤  provenance.acquired_at
             ≤  payload.preserved_at  ≤  provenance.emitted_at
```

The chain is the handoff, written down: a thing happens, the source records it,
an adapter reads it, the adapter preserves the payload, and only then does the
adapter emit an envelope pointing at it. The last link is the one that carries
weight — an envelope may not claim to have been emitted before the bytes it
references existed.

Absent optional timestamps are skipped; the remaining links still apply. Equal
timestamps are fine, because a fast adapter legitimately produces them.

## The handoff

This is how an adapter gets an item to Relay.

1. **Preserve first.** The adapter writes the payload to operator-designated
   storage, verbatim, before anything describes it.
2. **Compute identity.** Digest the bytes as stored; derive `intake_id` from the
   source.
3. **Emit an envelope.** One envelope per item, referencing the payload.

Then:

- **The unit is one envelope per item.** A handoff is a set of envelopes.
- **Transport is out of scope.** A file per envelope, a JSON Lines stream, an
  HTTP request — the operator's choice. Nothing in this contract depends on it.
- **An envelope is bounded**: at most 4096 bytes in canonical form. A captured
  item can be megabytes, and an envelope that could grow with it would stop
  being cheap to log, queue, store, and compare. The ceiling turns "an envelope
  is metadata and a reference" from an intention into something a machine
  checks: there is nowhere in a closed, bounded envelope to put a transcript.
- **The payload is preserved verbatim**, and referenced rather than carried, so
  nothing re-encodes it in transit.
- **Re-emission is expected**, and must reproduce the item's facts exactly — see
  [Replay](#replay).

## Canonical form

One byte sequence per envelope value, so that "the same envelope" is something a
machine decides rather than something a human argues about:

- UTF-8, unescaped.
- Object members sorted by name. Arrays keep their order — they are data.
- No insignificant whitespace.
- No floating-point numbers **anywhere in an envelope**. Every numeric member is
  an integer.
- Every string must be encodable as UTF-8. An unpaired surrogate survives JSON
  parsing and has no UTF-8 encoding, so a string containing one has no canonical
  form and cannot be compared, hashed, or replayed.

The float rule is why canonical form works across languages. Canonical JSON
normally founders on float formatting; excluded by construction, the problem
cannot arise, and two implementations in two languages produce identical bytes.

Some values survive JSON parsing and still have no canonical form — `NaN` and
`Infinity`, which many parsers accept by default, and unpaired surrogates. Each
violates a rule above, and validation reports it as a finding. Validation never
raises: abandoning a whole conformance run over one bad envelope is the opposite
of what the run is for.

## Replay

Re-emitting an item is not merely permitted — an adapter that cannot safely
re-emit cannot safely be re-run.

The **item projection** is an envelope without `provenance` and without
`payload`. Both describe *this act of emission*: which adapter ran and when, and
where these bytes were put. Neither describes the item.

> Two conforming envelopes sharing an `intake_id` and a `content.digest` must
> have identical canonical item projections.

So a later run, a newer adapter version, or preservation to a different store
all produce a conforming replay. What does not is the same item described
differently — a title that changed on the second pass, a participant count that
drifted. That failure is invisible to single-envelope validation and corrupts
deduplication downstream, which is why the contract suite checks it across a
set.

A different digest is a **revision**, not a divergence. A suite that flagged it
would push adapters toward inventing a fresh identity for every edit, destroying
the very thing identity is for.

## Validation

Validation is deterministic in three specific senses, each enforced by a test:

1. The same envelope always produces the same findings.
2. Findings are always in the same order — sorted by JSON Pointer, then by code.
3. Validation reads nothing outside the envelope: no clock, no network, no
   filesystem, no locale, no environment.
4. Validation returns findings and never raises, whatever it is handed.

The third matters most. A validator that knew the date would reject tomorrow
what it accepts today, which would make a fixture suite meaningless and a
replayed envelope unverifiable.

Validation reports **every** violation, not the first, so that an adapter author
fixes one round instead of three.

### Finding codes

Codes are part of the contract — a consumer may branch on one.

| Code | Raised when |
|---|---|
| `E_NOT_OBJECT` | The envelope is not a JSON object. |
| `E_FIELD_MISSING` | A required member is absent. |
| `E_FIELD_UNKNOWN` | A member not defined by this version is present. |
| `E_TYPE` | A member has the wrong JSON type. |
| `E_ENUM` | A value is outside a closed vocabulary. |
| `E_FORMAT` | A string does not match its required form. |
| `E_RANGE` | A number or length is out of bounds. |
| `E_NUMBER_NOT_INTEGER` | A fractional number appears. |
| `E_VERSION_UNSUPPORTED` | `envelope_version` is not one this validator handles. |
| `E_INTAKE_ID_DERIVATION` | `intake_id` is not what the source implies. |
| `E_TIMESTAMP_ORDER` | The timestamp chain is out of order. |
| `E_DIGEST_LENGTH` | A digest's length does not match its named algorithm. |
| `E_PAYLOAD_URI_EMBEDS_CONTENT` | The payload reference inlines the payload. |
| `E_METADATA_KEY` | A metadata name is not source-neutral `snake_case`. |
| `E_METADATA_VALUE` | A metadata value is of a type metadata may not hold. |
| `E_METADATA_SIZE` | Metadata exceeds its ceiling. |
| `E_ENVELOPE_SIZE` | The envelope exceeds its ceiling. |
| `E_REPLAY_DIVERGENT` | Two envelopes for the same item and revision disagree. |

`E_REPLAY_DIVERGENT` is the only one raised across a set rather than for a
single envelope.

## Running the contract

The contract suite is pure standard library, so an adapter author in any
language can clone this repository and check their own output without adopting a
Python toolchain first:

```
python3 -m relay_intake.conformance path/to/your/envelopes/
my-adapter emit | python3 -m relay_intake.conformance -
python3 -m relay_intake.conformance --json envelopes/ > report.json
```

Accepts a JSON file (one envelope or an array), a JSON Lines file, a directory,
or `-` for a stream on stdin. Exit status is 0 when every envelope conforms and
1 when any does not. Cross-envelope replay checks run over the whole set, so
point it at a full run rather than one file at a time.

Input that cannot be decoded or parsed is reported as a rejected envelope, not
raised: one malformed line does not end the run, and the rest of the set is
still checked.

**An empty set does not conform.** A check that examined nothing cannot report
conformance, and a gate pointed at the wrong path would otherwise pass having
verified nothing at all. Where an empty run is legitimate — an incremental
collection that found nothing new — say so explicitly:

```
python3 -m relay_intake.conformance --allow-empty path/to/envelopes/
```

To run the suite over this repository's own fixtures:

```
make check
```

## What this contract deliberately does not do

None of these are "later". Each one, put here, would couple the boundary to a
consumer and destroy what it is for.

- **No destination.** An envelope never names, hints at, or ranks a target.
- **No routing policy.** It does not say which placement mode applies.
- **No delivery state.** No status, no attempt count, no receipt.
- **No content.** By construction: the envelope is closed and bounded.
- **No vendor fields.** Anything meaningful to exactly one capture tool belongs
  in that adapter's preserved payload.
- **No dependency on an operator's configuration.** An envelope is valid, or not,
  entirely on its own terms.
