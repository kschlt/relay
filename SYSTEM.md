# System boundary

> Pre-alpha. This states the intended boundary. Most of it is not implemented.

## Role

Relay is the reusable, source-independent control plane between capture adapters
and destination systems.

Its job is to coordinate placement against a closed destination registry, and to
make delivery deterministic, idempotent, and observable.

## What Relay owns

- The generic intake, routing-decision, delivery, and receipt concepts.
- Validation of a routing decision against the registered destination set.
- Deterministic delivery semantics.
- Idempotency and recovery behaviour across partial failures.
- The boundary between probabilistic classification and physical writes.
- Integration points for scheduled runs, manual runs, and downstream wake-ups.

## Inputs and outputs

**Consumes**

- Canonical intake items from adapters.
- Destination configuration, supplied by the operator's own private state store.
- Optionally, a constrained routing decision.
- Prior delivery state.

**Produces**

- A validated destination, or an explicit unresolved result with a reason.
- A committed item in an allowed target.
- A durable delivery receipt.
- Optionally, a wake-up for a downstream processor, *after* the target write
  exists.

Vendor-specific payload shapes are normalised by adapters before handoff. Relay
never sees a vendor's response shape.

## Processing boundaries

Placement has two modes, and the difference between them is how much content is
read:

1. **Structural routing** uses the item's kind and trusted metadata only. A
   meeting can be placed without reading its transcript.
2. **Semantic routing** may inspect a general capture *once*, when its meaning is
   genuinely required to choose among registered destinations.

A model may choose a destination identifier and a bounded amount of transport
metadata. It cannot construct arbitrary paths and it cannot perform writes.
Deterministic code resolves the identifier, validates it against the allowed
set, checks idempotency, performs the write, and records the result.

## State, trust, and privacy

Relay defines reusable behaviour. It does not own personal runtime state — the
inbox, the destination registry, policies, unresolved items, and receipts belong
to an operator-owned private store that is not part of this project.

The destination's own committed state is authoritative for a completed delivery.
Stable item identity and content identity are what make recovery possible when a
receipt or a notification goes missing.

Every destination is explicitly registered. Raw content is read only where a
semantic decision requires it; a payload is referenced, never carried. Secrets
stay outside version control.

## What Relay does not own

- Calling a capture vendor's API, directly or indirectly.
- Source credentials, or an operator's personal routing configuration.
- Extracting knowledge from meetings.
- Processing ideas, defects, or requests after delivery.
- Replacing a domain-specific hub or a destination's own processor.
- Being an event bus, a vector database, or a general workflow platform.
