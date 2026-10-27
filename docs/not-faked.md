# What we will not fake

IBM i has twenty-five years of surface area. Chasing all of it ends the project. This list is the guard rail. Add to it freely, remove from it only on purpose.

## Out of scope

- Hardware, SLIC, TIMI, MI instructions, single-level store
- Booting or running real IBM i media, ever
- Licensed program products beyond what a scenario needs
- Real PASE or QSH. A small themed shell exists (docs/pase.md), and it is not a real AIX runtime
- Native ILE binding, service programs, activation groups
- Clustering, HA, PowerHA, LPAR management
- Full DB2 for i SQL. We cover what scenarios and teaching need
- Real printing, tape, and optical devices

## In scope, but only as needed

- 5250 and TN5250E, enough for real clients to sign on and work (on port 5250, not the real 23; TLS on 5992, not the real 992)
- CL commands that a scenario or a lesson touches
- Authority and profile behavior that makes a finding real
- RPG IV and DDS through rpgle_library

## Rule of thumb

If no scenario and no lesson needs it, do not build it.
