# Compatibility and schema evolution

This document governs how the [intake envelope](intake-envelope.md) may change.

The envelope is the one thing every adapter and every consumer depends on. That
makes it the most expensive part of the system to change badly and the cheapest
to change well — but only if the rules are written down before anyone has shipped
against it, which is now.

## What a version means

`envelope_version` carries a **major version only**: `"1"`.

There is deliberately no minor version on the wire. The reasoning is short: a
consumer must never branch on a minor version, because a change it would need to
branch on is by definition a breaking change. Publishing a minor version invites
exactly the branch it must not take, and a field a consumer checks before
reading is a field that was not optional after all.

A consumer matches on the major version exactly. An envelope declaring a major
version a consumer does not implement is `E_VERSION_UNSUPPORTED` — it is not
partially processed, and it is not guessed at.

## Non-breaking changes

These may land in a minor release without a new `envelope_version`. Existing
adapters keep emitting valid envelopes; existing consumers keep working.

- **Adding an optional member**, at the top level or inside an existing object.
- **Adding a metadata name** to the defined vocabulary. Consumers already ignore
  names they do not recognise, which is what makes this safe.
- **Adding a core `kind`.** Consumers already treat an unrecognised kind as
  unresolved rather than guessing, so a new kind reaches an older consumer as an
  unresolved item — visible and reviewable, never silently misplaced.
- **Adding a digest algorithm.**
- **Relaxing a constraint**: widening a length limit, admitting a value
  previously refused, raising a ceiling.
- **Adding a finding code** for a rule that was already stated in prose but not
  checked.
- **Reporting a violation that previously crashed the validator.** An input that
  raised was never conforming, so turning it into a finding cannot un-conform
  anything.
- **Correcting a finding's message.** Messages are for humans; codes are the
  contract.

The test of a non-breaking change is mechanical: *every envelope that was
conforming before is still conforming after.* If that does not hold, the change
is breaking, whatever it is called.

## Breaking changes

These require a new major version.

- **Adding a required member**, or making an optional member required.
- **Removing or renaming any member.**
- **Narrowing a constraint**: tightening a pattern, lowering a ceiling,
  shrinking a vocabulary.
- **Changing the meaning of an existing member** while keeping its name. This is
  the worst kind, because nothing fails — the data simply becomes wrong.
- **Changing the identity derivation.** Every previously emitted `intake_id`
  would become wrong, and deduplication across the boundary would silently stop
  working.
- **Changing canonical form** in any way that alters the bytes of an existing
  envelope. Replay comparisons against stored projections would all diverge.
- **Removing or renaming a finding code.**
- **Changing the item projection** — moving a member into or out of it. That
  redefines what counts as a replay, and consumers would disagree with their own
  history.

## Adding a member: the questions to answer first

Most pressure on this contract will arrive as "could the envelope also carry…".
Usually the answer is no, and these three questions say why:

1. **Is it source-neutral?** If it is meaningful to one capture tool and
   nonsense for the next, it belongs in that adapter's preserved payload. A
   vendor-shaped member falsifies the project's central claim, and it is very
   hard to remove once anything depends on it.
2. **Is it about the item, or about a decision?** Destinations, routing hints,
   priorities, and delivery status are decisions. They belong to whoever makes
   them. An envelope that carried them would couple every adapter to one
   consumer's policy.
3. **Is it content?** If it can grow with the size of what was captured, it is
   content. Content lives behind `payload.uri`, which is the whole point of the
   reference.

A member that survives all three is a candidate. Add it as optional, which makes
it a minor change.

## What is fixed within a major version

These cannot change under any minor release, because something outside this
repository depends on each of them being stable:

| Fixed | Why |
|---|---|
| The identity derivation | Adapters would stop agreeing on what an item is. |
| Canonical form | Stored projections would no longer compare. |
| Finding codes, and their spelling | Consumers branch on them. |
| The item projection's membership | It defines what a replay is. |
| The closedness of every object but `metadata` | An open object silently readmits vendor fields. |

## Experimental kinds

`x-<slug>` exists so that an adapter can emit something new without waiting for
the contract to catch up.

- An experimental kind is never routed structurally.
- It may become a core kind later; that is a minor change.
- It carries no compatibility promise. An adapter relying on one should expect to
  migrate.

The namespace is what makes this safe: an experimental kind can never collide
with a core kind added later, so promoting one never breaks an adapter that
guessed the same name.

## If a new major version happens

1. The new schema is published alongside the old, not in place of it —
   `schema/intake-envelope-v2.schema.json`.
2. The reference validator accepts both for at least one release, so that
   adapters and consumers can migrate independently rather than in lockstep.
3. The fixture corpus keeps its version-1 cases. They are the regression test
   for the migration.
4. This document gains a migration section naming, member by member, what moved
   and what an adapter must change.

Nothing is silently reinterpreted. An envelope means what its declared version
says it means, for as long as that version is accepted at all.

## Stability of this contract today

Version 1 is defined, executable, and covered by fixtures — but nothing has
shipped against it, and no adapter has been written to it. The first real adapter
will find something wrong with it, and it is better for that to happen now than
after a consumer depends on it.

So: **expect a breaking change before anything depends on this.** Once something
does, these rules apply as written.
