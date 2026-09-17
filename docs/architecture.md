# Architecture

> Pre-alpha. This describes an intended design. Almost none of it is
> implemented.

## Four concerns, kept apart

```
  acquisition          routing            delivery           processing
┌──────────────┐   ┌─────────────┐   ┌───────────────┐   ┌────────────────┐
│   adapter    │──►│    Relay    │──►│  deterministic│──►│  destination's │
│ (vendor-     │   │  (select a  │   │  write to a   │   │  own processor │
│  specific)   │   │  registered │   │  validated    │   │  (domain-      │
│              │   │  identifier)│   │  target)      │   │   specific)    │
└──────┬───────┘   └─────────────┘   └───────────────┘   └────────────────┘
       │
┌──────▼───────────┐
│ payload storage  │
│ (raw, verbatim)  │
└──────────────────┘
```

1. **Acquisition** gets source data and preserves it faithfully.
2. **Routing** selects a registered destination identifier — or declines.
3. **Delivery** performs a validated, idempotent write.
4. **Processing** interprets the item inside the system that owns that domain.

Each boundary exists so that a change on one side does not propagate to the
other. Collapsing any two of them is how a pipeline becomes unchangeable.

## Adapters

An adapter discovers source items, preserves their identity and raw content, and
emits a canonical intake item. The payload is written **verbatim** — straight
from the source response to storage, with nothing re-encoding it on the way.

Everything vendor-shaped stops at the adapter: tool names, response shapes,
pagination quirks, identifier formats. What crosses the boundary is canonical.

## Relay

Relay applies generic rules against a destination registry the operator owns
privately. Relay itself holds no registry and no credentials.

**Structural routing** needs the item's kind and its trusted metadata. A meeting
is placed by what it *is*, not by what it says, so the transcript is never read
to make that decision.

**Semantic routing** applies to general captures whose destination depends on
what they mean. A constrained router may read the item once and return a
registered identifier. It may not return a path, and it may not write.

Deterministic delivery then resolves the identifier to an allowed target,
validates it, checks idempotency, writes, and records the result.

## Two layers of placement

Relay performs *system* placement: this item goes to the meeting system, or to a
registered project destination, or to the unresolved inbox.

Whatever receives it performs *domain* placement. One meeting may be relevant to
zero, one, or many things downstream, and deciding that is a domain judgement
Relay is deliberately not equipped to make.

## Lifecycle and recovery

The conceptual lifecycle is **received → classified or unresolved → delivered →
notified**.

Delivery and notification are separate steps, in that order, and the ordering is
load-bearing. The target write happens first and is authoritative. A failed
wake-up is repaired by reconciliation against durable state, because a
notification is advisory and repeatable — it is never proof that a delivery
happened, and its loss can never unmake one.

Stable identity is what makes this safe. A run that stops after the target write
but before the receipt is written must not deliver twice when it resumes, and
the only thing that can prevent that is identity that survives the interruption.

## Scheduling and triggers

A scheduled or manual run may open a fresh session with the adapter, Relay, and
the operator's state available.

Triggers accelerate; reconciliation preserves correctness. Every processor must
be able to rebuild what it needs from durable state, so that a missed trigger
costs latency rather than data.

## Context and security boundary

- Discovery uses metadata and compact receipts.
- Raw payloads are persisted directly, by code.
- Structural routing does not read content at all.
- Semantic routing reads only where meaning decides the outcome.
- Physical delivery resolves a registered identifier; it never acts on free text.
- Domain-specific reading happens in the system that owns the domain.

Every target is allow-listed by identifier before use. Source credentials stay
outside version control. Ambiguity, missing configuration, and validation
failure all preserve the item in an unresolved state.

This is context *minimisation*. It is not a claim that the surrounding
infrastructure never observes a payload — see
[privacy-and-security.md](privacy-and-security.md).
