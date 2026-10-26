# Changelog

## Unreleased

- Phase 2: fidelity oracle. A 5250 client, host stream decoder, structural diff, and a CLI (`python -m silverlake.oracle`) with an allowlist and rate limit for non-loopback hosts. First captures from PUB400 fed back three generic fixes: monocase on the sign-on user field, fields that wrap across rows, and the bottom-row message line. Snapshots are re-derived from raw records so old captures stay comparable.
- Phase 1: 5250 core. Telnet framing, TN5250E negotiation (terminal type, NEW-ENVIRON device name, binary, EOR), GDS records, declarative screens rendered to a real data stream, sign-on screen that round-trips. Checked against web3270's tn5250 client.
- Repo scaffold: README, ROADMAP, architecture and not-faked docs, lifecycle scripts, loopback guard.
