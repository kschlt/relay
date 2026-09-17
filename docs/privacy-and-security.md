# Privacy and security

> Pre-alpha. Nothing here is implemented or audited. This states the design
> intent and, just as importantly, the limits of what that intent can promise.

## What this project handles

Meeting transcripts and personal notes. In practice that means other people's
words, often recorded in settings where nobody was thinking about where the text
would end up: colleagues in a meeting, a client on a call, a half-formed thought
dictated while walking.

Treat it as sensitive by default and design accordingly.

## Design intent

### Content is not moved by a model

Payloads are preserved by the adapter, by code, and Relay carries a *reference*
to a payload rather than the payload itself.

The first reason is correctness — a model retyping a transcript can truncate or
paraphrase it and still look like it succeeded, while a direct write either
works or fails. The privacy effect is real too: content that is never placed in
a prompt is not exposed through that prompt.

### Content is read only where meaning decides something

Structural placement reads metadata and never content. Semantic placement reads
content once, to choose among registered destinations, and does not carry it
onward. Interpretation is not banned — it is **relocated** to whichever system
owns the decision that needs it.

### Destinations are closed

Relay selects among destinations an operator registered. It does not derive a
repository, a path, or any other physical target from free text — including from
a model's output. An unrecognised or ambiguous destination produces an
unresolved item.

This is a security property, not just a tidiness one. A pipeline that can be
talked into writing somewhere new is a pipeline that captured content can be
exfiltrated through.

### Credentials stay outside the repository

Source authentication, destination write access, and any other secret are the
operator's responsibility, held in the environment or in a credential store. No
credential, token, or account identifier belongs in this repository, in its
history, in its issues, or in its documentation.

## What this project does **not** claim

Stated plainly, because overstating a privacy property is worse than not
claiming it.

- **No end-to-end confidentiality.** The capture vendor, its transport, the MCP
  or API client, and the operator's storage all observe content. The design
  reduces exposure to *model context*; it cannot make the surrounding
  infrastructure blind.
- **No claim about a vendor's handling.** How a capture vendor stores, processes,
  retains, or shares data is governed by their terms, not by anything here.
- **No regulatory compliance claim.** No GDPR, HIPAA, SOC 2, or equivalent claim
  is made or implied.
- **No security review.** There is essentially no implementation to review yet.

## Operator responsibilities

These cannot be owned on an operator's behalf by any software:

- **Consent and legality of recording.** Recording and retaining conversations
  involving other people is subject to law and to reasonable expectation, both
  of which vary by jurisdiction and by relationship.
- **Destination visibility.** Confirm that every registered destination is as
  private as the content going to it. A misconfigured destination publishes
  verbatim transcripts.
- **Retention.** This project has no opinion about how long captured content
  should live. Deciding and enforcing that is the operator's job.
- **Third-party content.** Transcripts contain other people's speech. They did
  not choose this pipeline.

## Threat boundary

**In scope for this project's design:**

- Avoiding unnecessary exposure of content to model context.
- Preventing a model from choosing an unregistered write target.
- Keeping credentials out of version control.
- Failing visibly rather than delivering partially and silently.

**Out of scope — belongs to the operating environment:**

- Securing the adapter's credential store and the destination's write access.
- Access control, encryption at rest, and backups for payload storage.
- Network-level protection between components.
- Any capture vendor's own security posture.

## Reporting a problem

See [SECURITY.md](../SECURITY.md).
