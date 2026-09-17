# Contributing

Thanks for looking. The project is at an early stage and what is useful right
now is narrower than usual, so please read this first.

## Current stage

This repository holds **design documents**, plus whatever contracts have been
defined so far. There is no routing engine, no delivery mechanism, and no
scheduler. Contracts are being defined one at a time, smallest first, starting
at the edge where adapters meet Relay.

## What helps most right now

- **Boundary critique.** If the split in [SYSTEM.md](SYSTEM.md) and
  [docs/architecture.md](docs/architecture.md) is wrong — a responsibility on
  the wrong side, a non-goal that cannot hold — argue it before it is code.
- **Contract critique.** A defined contract that would break a plausible adapter,
  or that quietly assumes one vendor's shape, is a defect worth reporting with a
  concrete example.
- **Privacy review.** If
  [docs/privacy-and-security.md](docs/privacy-and-security.md) overclaims
  anything, that is a defect too.

## What is not wanted yet

- Implementation of layers whose contract has not been defined. Code written
  ahead of the contract encodes guesses about it.
- Features listed as non-goals in [VISION.md](VISION.md). Acquisition, personal
  configuration, meeting intelligence, and post-delivery domain processing are
  deliberately other components' jobs. Proposals to move that line are welcome
  as discussion; PRs implementing the move are not.

## Working on it

- **Open an issue first** for anything beyond a typo. At this stage, agreement
  on the boundary matters more than the diff.
- **Use a branch and a pull request.** The default branch takes no direct
  pushes; every change after the initial commit lands through a PR.
- **One concern per PR**, with a description saying what changed and why.
- Commit subjects follow
  [Conventional Commits](https://www.conventionalcommits.org) — `docs:`,
  `chore:`, `feat:`, `fix:`, `test:`.

## Documentation and example standards

The documents and contracts here are the product right now, so they are held to
a few rules:

- **Do not claim behaviour that does not exist.** If a layer is undefined, the
  text says it is undefined. A described capability is a promise.
- **No installation or usage instructions for software that does not exist.**
- **Examples and fixtures are synthetic.** Never commit a real transcript, a real
  note, a real meeting title, a participant's name, an account identifier, or a
  real source-system identifier — including in issues and PR descriptions.
  Invent one instead.
- **Nothing personal or private.** No credentials, no private hostnames, no local
  filesystem paths, no private repository names, no personal infrastructure
  topology. This repository is public and permanent.
- **Nothing vendor-specific in a contract.** A field that only makes sense for
  one capture vendor falsifies the central claim of the project. It belongs in
  that adapter's payload.

## Conduct

Be straightforward and civil. Critique designs, not people. Maintainers may
remove contributions or contributors that make the project worse to work on.

## Licensing of contributions

By contributing, you agree your contributions are licensed under the
[Apache License 2.0](LICENSE), matching the project.
