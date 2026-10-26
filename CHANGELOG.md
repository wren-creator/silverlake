# Changelog

## Unreleased

- Phase 3a: the access model. Five user classes with IBM's defaults by QSECURITY level, eight special authorities, grant rules, object authority with `*ALL`/`*CHANGE`/`*USE`/`*EXCLUDE`, authorization lists and groups. Profiles come from `data/profiles.toml` (19 seed accounts, one per class, one per special authority, plus the usual misconfigurations). Sign-on now checks the profile and answers with message IDs. A placeholder menu shows the effective access after sign-on. Found live: a profile with all eight authorities overflowed the screen and dropped the session; screens now wrap, and a failing session is logged without touching others.
- Sign-on screen moved to the stock layout, taken from a photo of a default display and the stock parts of the PUB400 capture: fields at col 52 on rows 5 to 9, info block at cols 47 and 69 on rows 1 to 3, copyright at col 39, no date line. The message-on-bottom-row behavior is unchanged.
- Phase 2: fidelity oracle. A 5250 client, host stream decoder, structural diff, and a CLI (`python -m silverlake.oracle`) with an allowlist and rate limit for non-loopback hosts. First captures from PUB400 fed back three generic fixes: monocase on the sign-on user field, fields that wrap across rows, and the bottom-row message line. Snapshots are re-derived from raw records so old captures stay comparable.
- Phase 1: 5250 core. Telnet framing, TN5250E negotiation (terminal type, NEW-ENVIRON device name, binary, EOR), GDS records, declarative screens rendered to a real data stream, sign-on screen that round-trips. Checked against web3270's tn5250 client.
- Repo scaffold: README, ROADMAP, architecture and not-faked docs, lifecycle scripts, loopback guard.
