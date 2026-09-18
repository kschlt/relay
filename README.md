# relay

Relay is a source-independent routing layer for captured information.

It accepts canonical intake items from capture adapters, decides which
registered destination each one belongs to, and hands it to deterministic
delivery.

> ## Status: pre-alpha — one contract defined
>
> **Defined and executable:** the canonical intake envelope — the boundary a
> source adapter hands an item across. It has a specification, a machine-readable
> schema, a reference validator, a synthetic fixture corpus, and a conformance
> suite any adapter can run against its own output.
>
> **Not defined, not implemented:** everything downstream of that boundary.
> There is no routing engine, no destination registry, no delivery mechanism,
> no receipts, and no scheduler. Nothing is packaged or released.
>
> The contract is covered by tests but nothing has shipped against it. Expect a
> breaking change before anything depends on it — see
> [docs/compatibility.md](docs/compatibility.md).

## The problem

Capture is easy and placement is hard. A thought dictated on a walk, a
transcript from this morning's call — each belongs somewhere specific, and
getting it there is a small chore that never quite happens. So captures
accumulate in whatever tool recorded them, in a pile nobody revisits.

Automating the chore usually collapses into a point-to-point integration: one
script that knows a vendor's API, the rules for where things go, and what
happens after they land, all braided together. Changing capture tools means
rewriting it, so in practice it never changes. Adding a second capture tool
means writing the whole thing again.

## The intent

Relay is the reusable middle. It is deliberately small:

- It accepts a **canonical intake item** from any adapter, in a shape that says
  nothing about which vendor produced it.
- It selects a destination **from a closed registry**, never from free text.
- It performs every write through **deterministic code**. A model may choose
  among registered destinations; it never constructs a path.
- It treats **repository state as the source of truth**, so an interrupted run
  can be resumed and a repeated run does not duplicate.
- It leaves anything it cannot place safely in a **visible unresolved state**
  rather than guessing.

The layer above Relay should not know which capture tool exists. The layer below
should not know which capture tool exists either. That is the whole point of the
boundary.

## Place in a pipeline

```
┌──────────────────┐     ┌───────────────────┐     ┌─────────────────────────┐
│  capture source  │────►│  source adapter   │────►│          Relay          │
│  (any vendor)    │     │  (vendor-specific)│     │       (this project)    │
└──────────────────┘     └─────────┬─────────┘     └────────────┬────────────┘
                                   │                            │
                         ┌─────────▼─────────┐     ┌────────────▼────────────┐
                         │  payload storage  │     │  registered destination │
                         │  (raw, verbatim)  │     │  (operator-configured)  │
                         └───────────────────┘     └─────────────────────────┘
```

An adapter owns everything vendor-specific: discovery, retrieval, pagination,
preserving raw payloads. What crosses into Relay is a small canonical item that
*references* the preserved payload rather than carrying it.

Operator-specific configuration — which destinations exist, where they live,
what each one accepts — belongs to a private state store that Relay reads. It is
not part of this repository and never will be.

## Principles

- Sources are adapters, not architectural dependencies.
- Durable state is the source of truth; receipts are operational, not
  authoritative.
- Model judgement may *select* among registered options; deterministic code
  performs every write.
- Payloads travel by reference. An envelope stays small enough to log, queue,
  and diff.
- Delivery is idempotent and recoverable — interrupted runs resume, repeated
  runs do not duplicate.
- Structural decisions do not read content. Content is read only where meaning
  is genuinely required to make a decision.
- Unknown or ambiguous destinations fail closed into an unresolved state.

## Scope

**In scope:** the canonical intake contract; validation of routing decisions
against a registered destination set; deterministic, idempotent delivery
semantics; recovery across partial failures; the boundary between probabilistic
classification and physical writes.

**Out of scope, deliberately:**

- Calling any capture vendor's API. That is an adapter's job.
- Storing credentials or an operator's personal destination configuration.
- Interpreting delivered content — summarising, extracting actions, answering
  questions about a transcript.
- Domain-specific processing after delivery. The receiving system owns that.
- Being an event bus, a vector database, or a general workflow platform.

## The intake envelope

The one boundary that is settled. An adapter preserves a payload directly, by
code, and then emits a small envelope that *references* it:

```json
{
  "envelope_version": "1",
  "intake_id": "sha-256:1f0e…",
  "kind": "meeting",
  "captured_at": "2026-01-05T15:02:11Z",
  "source":     { "system": "example-capture", "external_id": "mtg-0001-synthetic" },
  "provenance": { "adapter": "example-adapter", "adapter_version": "0.3.1",
                  "acquired_at": "2026-01-05T15:30:00Z",
                  "emitted_at":  "2026-01-05T15:30:02Z" },
  "content":    { "media_type": "text/vtt; charset=utf-8", "byte_length": 2048,
                  "digest": { "algorithm": "sha-256", "value": "…" } },
  "payload":    { "uri": "example-store:meeting/mtg-0001-synthetic.vtt",
                  "preserved_at": "2026-01-05T15:30:01Z" },
  "metadata":   { "title": "Synthetic planning discussion",
                  "duration_seconds": 2700, "participant_count": 4 }
}
```

Synthetic, and a real fixture — every example in this repository is invented.

Four properties do the work:

- **`intake_id` is derived, not assigned.** It is a hash of the source system and
  the item's identifier there, so an adapter needs no memory to re-identify an
  item, two independent adapters agree without coordinating, and the
  source-system identifier does not travel into logs and receipts.
- **Identity and revision are separate.** Same `intake_id` and same
  `content.digest` is a replay, already handled. Same identity, different digest
  is a revision. That is what makes "just run it again" safe after a partial run.
- **The envelope is closed and bounded** — at most 4096 bytes, with nowhere to
  put a transcript. A captured item can be megabytes; an envelope that could
  grow with it would stop being cheap to log, queue, and store.
- **It names no destination.** Where an item goes is not an adapter's to say.

### Checking an adapter against it

The contract suite is pure standard library, so an adapter in any language can
be checked without adopting a Python toolchain:

```
python3 -m relay_intake.conformance path/to/your/envelopes/
my-adapter emit | python3 -m relay_intake.conformance -
```

Exit status is 0 when every envelope conforms. Point it at a whole run rather
than one file at a time — replay consistency is checked across a set.

`make check` runs the suite over this repository's own fixtures.

## On privacy

This project is built to move meeting transcripts and personal notes. The design
intent — read content only where meaning decides something, keep credentials out
of the repository, write only to destinations an operator registered — and the
limits of what that can honestly promise are in
[docs/privacy-and-security.md](docs/privacy-and-security.md). Read it before
pointing anything at real data.

## Documents

| Document | What it covers |
|---|---|
| [SYSTEM.md](SYSTEM.md) | What Relay owns and refuses to own |
| [VISION.md](VISION.md) | Where this is going and how we would know it worked |
| [docs/architecture.md](docs/architecture.md) | Layers, routing modes, lifecycle, recovery |
| [docs/privacy-and-security.md](docs/privacy-and-security.md) | Data handling, threat boundary, honest limits |
| [docs/intake-envelope.md](docs/intake-envelope.md) | **The intake contract** — normative |
| [docs/compatibility.md](docs/compatibility.md) | How the contract may and may not change |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to work on this while it is pre-alpha |
| [SECURITY.md](SECURITY.md) | Reporting a vulnerability |

## License

[Apache License 2.0](LICENSE).
