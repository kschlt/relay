# Vision

## Problem

Voice and text capture are fast, and their value leaks away in the gap between
capturing something and putting it where it belongs. Closing that gap by hand is
tedious enough that it does not happen. Closing it with a direct
vendor-to-project integration binds every downstream system to one vendor and
duplicates placement logic in every one of them.

## Where this is going

Relay is one dependable entrance for captured information.

A capture made on a phone should arrive, committed, in the right registered
destination before the next working session, without anyone filing it by hand.
A meeting arriving through the same run should be handed to whatever system owns
meetings, structurally, without Relay reading the transcript.

Adding a second capture source later should mean writing a second adapter. It
should not mean touching Relay, and it should not mean touching a single
destination.

## Goals

- **Source independence.** Downstream depends on a canonical contract, never on
  a vendor's tool names or response shapes.
- **Closed destinations.** Every physical target is registered before use. Relay
  never derives a target from free text.
- **Deterministic delivery.** Model judgement selects among options; code
  performs the write.
- **Idempotence and recovery.** Repeated runs do not duplicate. Interrupted runs
  resume. A lost notification cannot erase a successful delivery.
- **Minimal reading.** Structural decisions read metadata only. Semantic
  decisions read content once, where meaning decides the outcome.
- **Visible failure.** Ambiguity, missing configuration, and validation failure
  all produce a reviewable unresolved item, never an invented destination.

## Non-goals

Not "later" — deliberately other components' jobs:

- Acquiring data from any capture vendor.
- Owning an operator's personal destination registry, credentials, or history.
- Meeting intelligence: summarisation, action extraction, Q&A over content.
- Domain-specific processing after delivery.
- Real-time delivery or a long-running service.
- Semantic search, vector storage, or a general workflow platform.
- Perfect classification. An honest unresolved item beats a confident wrong one.
- Any permanent commitment to a particular capture vendor.

## Success criteria

The target is reached when all of these hold:

1. A new adapter can be added without changing Relay or any destination.
2. A new destination can be registered without changing any adapter.
3. A meeting reaches the system that owns meetings without Relay interpreting
   the transcript.
4. A general capture is delivered only to an explicitly registered destination.
5. Repeated runs create no duplicates, and interrupted runs resume.
6. Unresolved items stay reviewable rather than disappearing.
7. Every repository in the picture can state its role and its non-goals
   unambiguously.

## Current phase

**Pre-alpha: boundary definition.** This repository documents what Relay is
responsible for and what it refuses to do.

Contracts are being defined one at a time, smallest first, starting at the edge
where adapters meet Relay. Routing, delivery, receipts, and scheduling are all
downstream of that edge and are deliberately unsettled. Committing to them now
would be guessing.
