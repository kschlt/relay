# Agent instructions — relay

Guidance for AI coding agents working in this repository. Humans: see
[CONTRIBUTING.md](CONTRIBUTING.md), which these rules sit on top of.

## Read this first

**This repository is public and permanent.** Anything committed here is
world-readable forever, including through history and forks. There is no private
mode and no taking it back.

**This project is pre-alpha.** Contracts are defined one at a time, smallest
first. Do not write implementation for a layer whose contract has not been
defined — routing, delivery, receipts, and scheduling are all undefined today.
Code written ahead of a contract encodes guesses about it.

## Hard rules for anything you commit here

Never commit, in files, commit messages, issues, or PR descriptions:

- Credentials, tokens, API keys, or account identifiers.
- Real source data — transcripts, note bodies, meeting titles, participant
  names, or source-system identifiers. **Use synthetic examples only.**
- Private repository names, internal hostnames, or anyone's personal
  infrastructure topology — including the names of the operator's own
  destination repositories and state stores.
- Local filesystem paths from a contributor's machine.
- Output pasted from a connected tool or connector.

If you are unsure whether something is safe to publish, leave it out and say why.

## Vendor neutrality

Relay's central claim is that a downstream consumer does not know which capture
vendor produced an item. A vendor-shaped field in a contract falsifies that
quietly, and it is very hard to remove once something depends on it.

- No contract, schema, fixture, or example may name a capture vendor or carry a
  field that only makes sense for one.
- Vendor-specific attributes belong in an adapter's preserved payload, never in
  a canonical item.
- Fixtures use invented identifiers and invented content, in obviously synthetic
  forms.

## Accuracy rules

- **Do not describe undefined behaviour as supported.** If a layer has no
  contract, no document here may imply it does.
- **Do not add installation or usage commands for software that does not exist.**
  A command in a README is a promise.
- **Do not add badges, version numbers, or release claims** for things that do
  not exist.
- Keep the pre-alpha status notices in `README.md`, `VISION.md`, `SYSTEM.md`, and
  the `docs/` files intact. Removing one is a regression.

## Scope discipline

[VISION.md](VISION.md) lists non-goals: acquisition, personal configuration,
meeting intelligence, post-delivery domain processing, real-time delivery,
general workflow platform features. Do not quietly widen scope into them. If a
change seems to require crossing that line, stop and raise it instead.

## Git workflow

The initial commit is the only commit made directly on the default branch.
Everything after it goes through a branch and a pull request — one concern per
PR, with a description of what changed and why.

Commit subjects follow [Conventional Commits](https://www.conventionalcommits.org)
(`docs:`, `chore:`, `feat:`, `fix:`, `test:`).

## Repository layout

```
README.md                        entry point and current status
SYSTEM.md                        what Relay owns and refuses to own
VISION.md                        direction, goals, non-goals, success criteria
CONTRIBUTING.md                  how to contribute at this stage
SECURITY.md                      vulnerability reporting
LICENSE                          Apache-2.0
docs/architecture.md             layers, routing modes, lifecycle, recovery
docs/privacy-and-security.md     data handling and its honest limits
```

## Workflow tooling

<!-- aos:begin id=task-workflow rev=1 managed by aos touchpoint writer - do not edit by hand -->
This project's backlog, session protocol, and workflow tooling are managed by **aos** (the meta-workflow layer mounted at `.aos/`). Machinery lives at `.aos/sys/`; the authoritative session protocol is `.aos/sys/core/CLAUDE.md`. Instance state (backlog, specs, work-log) lives in the nested state repo at `.aos/` (host-ignored, its own git history). Do not edit this managed region by hand.
<!-- aos:end id=task-workflow -->

That layer is the maintainer's local workflow tooling. It is **not a dependency
of this project**: Relay does not require it to be built, used, or contributed
to, and nothing in the public tree may be written to depend on it. Contributors
will not have it, and that is expected — ignore it if it is not present.
