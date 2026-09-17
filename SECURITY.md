# Security policy

## Current status

This project is **pre-alpha**. There is no released software and no deployed
attack surface.

The design decisions being made now — what reaches model context, how a write
target is chosen, how credentials are kept out of the pipeline — are exactly the
decisions that produce or prevent later vulnerabilities. Reports about the
*design* and about defined contracts are in scope and welcome.

## Reporting a vulnerability

Please report privately rather than in a public issue.

Use GitHub's private vulnerability reporting for this repository:
**Security → Advisories → Report a vulnerability**. It creates a private thread
with the maintainers.

If that is unavailable to you, open a public issue saying only that you have a
security concern and asking for a private channel. Do not include details.

## What to include

- What the problem is, and why it matters.
- Which document, contract, or design decision it concerns.
- How you would exploit or trigger it, concretely.
- A suggested fix, if you have one.

**Do not include real data.** No transcripts, notes, meeting titles, account
identifiers, tokens, or other live source material — use synthetic examples.

## What to expect

This is a small personal project, not a funded program. There is no bounty and
no guaranteed response time. Reports will be read, and credible ones will be
acted on and credited unless you prefer otherwise.

## In scope

- Design or contract flaws that would let captured content reach an unintended
  destination.
- Anything that would let a model, or content under an attacker's influence,
  cause a write to an unregistered target.
- Patterns that would put credentials into version control or into model
  context.
- Overclaims in [docs/privacy-and-security.md](docs/privacy-and-security.md)
  that would mislead an operator about what is protected.

## Out of scope

- Vulnerabilities in a capture vendor's product or API — report those to the
  vendor.
- Vulnerabilities in an operator's own storage, network, or client
  configuration.
- Anything requiring software this project has not written yet.
