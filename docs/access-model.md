# Access model: the levels you can assign

This is the menu of access you can hand to a user in Silverlake. It follows IBM i's own model, so what a student learns here is what they will find on a real system.

## How to assign access

Access lives in `src/silverlake/data/profiles.toml`. Edit a profile there, or copy the file, point `SILVERLAKE_PROFILES` at your copy, and run `./reset.sh`. Every profile can set:

| Field | Values | What it does |
|---|---|---|
| `user_class` | `*USER` `*SYSOPR` `*PGMR` `*SECADM` `*SECOFR` | The class. Decides default special authorities and (later) which menu options show. |
| `special_authorities` | left out = `*USRCLS`; `"*NONE"`; or a list | Overrides the class defaults. Any combination of the eight. |
| `password` | text, or `"*NONE"` | `*NONE` means the profile cannot sign on interactively. |
| `status` | `*ENABLED` `*DISABLED` | A disabled profile is refused even with the right password. |
| `group_profile`, `supplemental_groups` | profile names | Group membership, used for object authority. |
| `limited_capabilities` | `*NO` `*PARTIAL` `*YES` | Recorded now. Enforcement comes with the command line. |
| `initial_program`, `initial_menu`, `current_library`, `text` | | Recorded for the profile. |

The `[system]` table sets `qsecurity` (20, 30, 40, 50), `qpwdlvl` (0 to 3), `mode`, and `default_profile_owner` (who "created" the seeded accounts, `SECADMIN` in the seed). A profile may also set `owner`, `public_authority` (its `AUT`, default `*EXCLUDE`) and `private_authority`.

## Changing access from inside a session

Sign on as someone with `*SECADM` (`SECADMIN`, `SECONLY`, `DEVADMIN`, `QSECOFR`) and type on the command line. Keywords are written in full, positional values work in IBM's order, unquoted values are upper-cased and quoted ones keep their case. There is no F4 prompting or keyword abbreviation yet.

| Command | What it does here |
|---|---|
| `CRTUSRPRF USRPRF(BOB) PASSWORD(...) USRCLS(...) SPCAUT(...) GRPPRF(...) ...` | Creates a profile with CRTUSRPRF's defaults (`PASSWORD(*NONE)`, `USRCLS(*USER)`, `SPCAUT(*USRCLS)`, `AUT(*EXCLUDE)`). |
| `CHGUSRPRF USRPRF(BOB) STATUS(*DISABLED)` | Changes only what you name. Everything else is `*SAME`. |
| `DSPUSRPRF BOB` | Shows the profile (`TYPE(*BASIC)`, `OUTPUT(*)` only). |
| `DLTUSRPRF BOB OWNOBJOPT(*CHGOWN OTHER)` | Deletes it. `*NODLT` (default) refuses if it owns objects, `*DLT` deletes them, `*CHGOWN name` moves them. |
| `WRKUSRPRF` or `WRKUSRPRF DEV*` | A paged list of the profiles you have some authority to. Option 5 displays one. Page Up and Down scroll. |
| `SIGNOFF` | Back to the sign-on screen. |

Accepted but not modeled: `ASTLVL`. The rules come from the IBM i 7.5 command reference:

- **Create** needs `*SECADM`. You may give only special authorities you hold, and giving `*SECADM` or `*AUDIT` also takes `*ALLOBJ`. A group profile needs `*CHANGE` and `*OBJMGT` to it.
- **Change** needs `*SECADM` plus `*OBJMGT` and `*USE` to the profile. Only authorities that would be newly added are checked against what you hold.
- **Display** needs `*READ` to the profile.
- **Delete** needs `*SECADM` plus `*OBJEXIST` and `*USE` to the profile. Profiles that other profiles own pass to `QDFTOWN`. `QSYS`, `QSECOFR`, `QDFTOWN`, `QPGMR` and `QUSER` cannot be deleted, nor can a profile someone is signed on under. Group membership, private authorities, and authorization list entries naming the deleted profile are cleaned up.

**A profile is itself a secured object.** It has an owner, a public authority (`*EXCLUDE` by default) and private entries, and it always holds `*CHANGE` and `*OBJMGT` to itself. So having `*SECADM` is not enough to touch every profile. `DEVADMIN` has `*SECADM` but owns nothing and was granted nothing, so `CHGUSRPRF STUDENT` fails with `CPF2228` while `SECADMIN`, who owns the seeded accounts, can change them. It is a real IBM i behavior and a good exercise.

Changes are saved to `state/silverlake.sqlite` and survive a restart. `./reset.sh` deletes the state directory, and the next start reads the seed again. The saved state holds profile passwords as typed. That is deliberate for a training range with weak credentials, and the reason this must never hold anything real.

## Commands are objects

Every command is a `*CMD` object in QSYS with an owner and a public authority, and running a command takes `*USE` to that object before its parameters are even looked at. That is how a real site decides who may run `CRTLIB` or `CRTUSRPRF`: it changes one object. A basic profile on PUB400 was refused `CRTLIB` this way, with the wording `Not authorized to command CRTLIB in library *LIBL.` (the message line shows no ID, so Silverlake records none).

The seed is permissive: every command is `*PUBLIC *USE`. Close one off with the commands you already have:

```
RVKOBJAUT OBJ(QSYS/CRTLIB) OBJTYPE(*CMD) USER(*PUBLIC) AUT(*USE)     # nobody ordinary can create libraries
GRTOBJAUT OBJ(QSYS/CRTLIB) OBJTYPE(*CMD) USER(DEVELOPER) AUT(*USE)  # except this one
```

The usual rules apply: `*ALLOBJ` always gets through, a private `*EXCLUDE` beats public `*USE`, groups combine, and the library holding the commands (QSYS) is itself a gate, so revoking the public's `*USE` on QSYS stops every ordinary user from running anything. `DSPOBJAUT OBJ(QSYS/CRTLIB) OBJTYPE(*CMD)` shows the setting.

That a command needs `*USE` is IBM i behavior, but I did not read it on a command page. The refusal wording was seen on a real system. New commands get their object automatically, and a state file saved before a command existed gets one on the next start. After upgrading an old checkout, run `./reset.sh` to pick up new seed objects (an existing state file keeps its old ones).

## Menus, GO and limited capabilities

After sign-on a job lands on a menu, which is a `*MENU` object whose data is a title and up to 13 numbered options, each running a command. The layout follows a real IBM i main menu captured from PUB400 (the command line is at row 19, column 6, 153 long, not monocase). The wording is ours. The seed has `QSYS/MAIN`, `APPLIB/APPMENU` and `APPLIB/RESTRICT`.

- **Options.** Typing `1` or `01` runs option 1's command. Anything that is not an option is run as a command, unless the profile is limited (below).
- **GO.** `GO MENU(lib/name) RTNPNT(*YES)` needs `*USE` to the menu and its library. The menu stack is ten deep (an eleventh pushes the oldest out). F12 is the previous menu. F3 returns to the display where `GO` was typed with `RTNPNT(*YES)`. All from IBM's `GO` page. F3 on the initial menu does nothing, which is what a real system did.
- **Sign-on fields.** Program, menu and current library can be typed on the sign-on screen. `INLPGM(*NONE)` shows the menu, `INLPGM(QCMD)` opens command entry, and any other program is refused because programs are not modeled. `INLMNU(*SIGNOFF)` signs the job straight off. A menu that cannot be found or used drops the job to command entry with the reason.
- **`CALL QCMD`** opens command entry, where every command runs whatever the limit says.
- **`CHGPRF`** changes your own initial program, initial menu or current library (needs `*USE` to what you point at).

Limited capabilities (`LMTCPB`), from IBM's text:

| | Program at sign-on or `CHGPRF` | Menu | Current library | Command line |
|---|---|---|---|---|
| `*NO` | yes | yes | yes | yes |
| `*PARTIAL` | no, CPF2294 | yes | no, CPF2297 | yes |
| `*YES` | no, CPF2294 | no, CPF2295 | no, CPF2297 | no |

Menu options still run for a `*YES` user, and command entry still runs everything. That is the break-out the range exists for: `CLERK` (`LMTCPB(*YES)`, initial menu `APPLIB/RESTRICT`) cannot type `WRKUSRPRF`, but option 9 on that menu is `CALL QCMD`, and from command entry every command is available. Closing it is one object away: `RVKOBJAUT OBJ(QSYS/QCMD) OBJTYPE(*PGM) USER(*PUBLIC) AUT(*USE)`. The messages the table cites are documented, not seen. What a limited user sees when typing on a command line is not documented, so that text is ours. IBM's `INLMNU` text says `*YES` where its `LMTCPB` text says the menu is changeable under `*PARTIAL`; the `LMTCPB` text is followed. Not read on any page, so inferred: that running a command needs `*USE` to it, and that `*ALLOBJ` skips the library gate.

## Libraries and object authority from the command line

| Command | What it does here |
|---|---|
| `CRTLIB LIB(NAME) TEXT('...') AUT(...)` | Creates a library you own. `AUT` defaults to `*LIBCRTAUT`, which is `*CHANGE` here. `TYPE` is accepted but not stored. No authority check yet, see below. |
| `DLTLIB LIB(NAME)` | Needs `*USE` and `*OBJEXIST` on the library and `*OBJEXIST` on everything in it. What you may delete goes, and if anything is left, the library stays (`CPF2161` then `CPF2168`). Not for `QSYS`, `QGPL`, `QUSRSYS`, `QSYS2`, or a library on your list. |
| `ADDLIBLE`, `RMVLIBLE`, `DSPLIBL` | Your library list, in the order a real system showed: `QSYS`, `QSYS2`, `QUSRSYS`, `QHLPSYS` (system), your profile's current library, then `QGPL` and `QTEMP` (user). `POSITION` takes `*FIRST`, `*LAST`, or `*AFTER`/`*BEFORE`/`*REPLACE` and a library. The list belongs to the job and starts fresh at each sign-on. |
| `WRKLIB LIB(*LIBL)` | A paged list of libraries you have some authority to. Also `*ALL`, `*ALLUSR`, `*USRLIBL`, `*CURLIB`, a name, or `NAME*`. No options yet. |
| `DSPOBJAUT OBJ(LIB/NAME) OBJTYPE(*FILE)` | Shows who holds what. Someone with `*OBJMGT` (or the owner) sees everyone. Anyone else sees their own entry, or a single `*PUBLIC` row when they have none. The last part was seen on a real system. |
| `GRTOBJAUT OBJ(LIB/NAME) OBJTYPE(*LIB) USER(A B *PUBLIC) AUT(...)` | The owner, someone with `*OBJMGT`, or `*ALLOBJ`. Only the owner or `*ALLOBJ` may give `*OBJMGT`. `REPLACE(*NO)` adds to what is there, `*YES` sets it exactly, `*EXCLUDE` always replaces. `AUTL(name)` needs ownership or `*ALL`. |
| `RVKOBJAUT OBJ(LIB/NAME) OBJTYPE(*FILE) USER(A *ALL *PUBLIC) AUT(...)` | Removes only the named authorities. A user left with nothing loses the entry altogether and falls through to groups and `*PUBLIC`, which is not the same as holding `*EXCLUDE`. |

Object types so far are `*LIB`, `*FILE`, `*CMD`, `*MENU` and `*PGM`, `OBJ` takes one explicit name (no generic names or `*ALL`), `OBJ(NAME)` is found through your library list, and `REFOBJ`, `OUTPUT(*PRINT)` and `OUTFILE` are not modeled. Use `LIB/NAME`, or `OBJ(NAME) OBJTYPE(*LIB)` for a library, which always lives in QSYS.

Two things to try:

- **Open a locked library.** `STUDENT` cannot reach `SRCLIB/QRPGSRC` (`CPF2216`). Sign on as `DEVELOPER` and run `GRTOBJAUT OBJ(SRCLIB) OBJTYPE(*LIB) USER(STUDENT) AUT(*USE)`. The file was never the lock, the library was.
- **Tell what exists.** As `STUDENT`, ask `DSPOBJAUT` about a library that is not there (`CPF2209`), one that is locked (`CPF2216`), and a file that is not in an open library (`CPF2208`) against one that is but that you hold nothing on (`CPF2207`). The answers draw a map of a system you cannot see into.

## The five user classes

| Class | At QSECURITY 20 | At QSECURITY 30, 40, 50 |
|---|---|---|
| `*USER` | `*ALLOBJ` `*SAVSYS` | none |
| `*SYSOPR` | `*ALLOBJ` `*SAVSYS` `*JOBCTL` | `*SAVSYS` `*JOBCTL` |
| `*PGMR` | `*ALLOBJ` `*SAVSYS` `*JOBCTL` | none |
| `*SECADM` | `*ALLOBJ` `*SAVSYS` `*SECADM` `*JOBCTL` | `*SECADM` |
| `*SECOFR` | all eight | all eight |

Source: IBM i 7.5, Create User Profile, the USRCLS parameter. These apply only when a profile uses `*USRCLS`.

**Set `qsecurity = 20` and every ordinary user holds `*ALLOBJ`.** That is a real configuration found on real systems, and the fastest way to show why the level matters.

## The eight special authorities

| Authority | What it lets a user do |
|---|---|
| `*ALLOBJ` | Access any object, with or without private authorization. |
| `*SECADM` | Create, change and delete user profiles (with the right command authority). |
| `*AUDIT` | Perform auditing functions, including turning auditing on and off. |
| `*IOSYSCFG` | Change the system's I/O configuration. |
| `*JOBCTL` | Change, hold, release and cancel any job. |
| `*SAVSYS` | Save, restore and free storage for any object. |
| `*SERVICE` | Perform service functions. |
| `*SPLCTL` | Perform all spool functions. |

### Who may hand them out

A user can only give away what they hold. Giving `*SECADM` also requires `*ALLOBJ` and `*SECADM`, and giving `*AUDIT` requires `*ALLOBJ`, `*SECADM` and `*AUDIT`. Creating or changing a profile at all requires `*SECADM`. So a `*SECADM`-only account (the seed's `SECADMIN` at level 40) can make users but cannot grant `*SECADM` onward, and a programmer who was once given `*SECADM` (`DEVADMIN`) can still create profiles. Both are good exercises.

## Object authority

| Value | Means |
|---|---|
| `*ALL` | Every detailed authority below. |
| `*CHANGE` | `*OBJOPR` `*READ` `*ADD` `*UPD` `*DLT` `*EXECUTE` |
| `*USE` | `*OBJOPR` `*READ` `*EXECUTE` |
| `*EXCLUDE` | Nothing. |

Detailed: `*OBJOPR` look at and use, `*OBJMGT` secure, move, rename, `*OBJEXIST` delete and transfer ownership, `*OBJALTER` change attributes, `*OBJREF` use as a parent in a constraint. Data: `*READ`, `*ADD`, `*UPD`, `*DLT`, `*EXECUTE`.

### Libraries and the library gate

An object is named by library, name and type, the way QSYS.LIB names it (`APPLIB/PAYROLL *FILE`). A library is itself an object of type `*LIB` that lives in QSYS. To reach an object you must first be able to locate it in its library, which takes `*EXECUTE` on the library (IBM: "Execute authority provides the authority needed to run a program or locate an object in a library"). So a wide open object in a locked library is still out of reach. The seed has exactly that mistake: `SRCLIB/QRPGSRC` is `*CHANGE` to the public, but `SRCLIB` is `*EXCLUDE` except to the developers' group, so `STUDENT` cannot touch it.

Two parts are inferred from how IBM i behaves, not read on a command page: that the gate is `*EXECUTE` on the library (IBM's pages say locating an object takes `*EXECUTE`, and `*USE` includes it), and that `*ALLOBJ` skips the gate. QSYS itself is treated as always open.

How Silverlake resolves what a user may do to an object, once past the gate, in order: `*ALLOBJ`, then the owner, then the user's own entry on the object, then on its authorization list, then the user's groups (combined), then `*PUBLIC`. A private `*EXCLUDE` beats a generous `*PUBLIC`, which is how real systems behave.

## The seed accounts

Passwords equal the profile name, on purpose.

| Profile | Class | Special authorities at QSECURITY 40 | Shows |
|---|---|---|---|
| `QSECOFR` | `*SECOFR` | all eight | The top of the tree. |
| `SECADMIN` | `*SECADM` | `*SECADM` | Can make users, cannot grant `*SECADM` onward. |
| `DEVELOPER` | `*PGMR` | none | An ordinary programmer, in group `GRPDEV`. |
| `OPERATOR` | `*SYSOPR` | `*JOBCTL` `*SAVSYS` | Operators can save and control jobs. |
| `STUDENT` | `*USER` | none | The account most attacks start from. |
| `GUEST` | `*USER` | none (`SPCAUT(*NONE)`) | Limited capabilities. |
| `CLERK` | `*USER` | none | `LMTCPB(*YES)`, initial menu `APPLIB/RESTRICT`, current library `APPLIB`. The menu has a way out. |
| `AUDITOR` `IOADMIN` `JOBMAN` `BACKUP` `SECONLY` `SVCTOOLS` `SPOOLMAN` | `*USER` | one each | Hand out exactly one thing and see what it is worth. |
| `SVCACCT` | `*USER` | `*ALLOBJ` | An over-privileged service account. |
| `LEGACY` | `*PGMR` | `*ALLOBJ` `*JOBCTL` | A programmer who kept `*ALLOBJ`. |
| `DEVADMIN` | `*PGMR` | `*SECADM` | A programmer with a security power nobody remembers granting. |
| `NOPWD` | `*USER` | none | `PASSWORD(*NONE)`: cannot sign on. |
| `OLDTEMP` | `*USER` | none | Disabled. |
| `GRPDEV` | `*USER` | none | A group profile. |
| `QSYS` `QDFTOWN` | `*SECOFR`, `*USER` | all eight, none | IBM-supplied profiles. `QSYS` owns the system libraries. Neither can sign on or be deleted. |

The seed also holds libraries (`QSYS`, `QSYS2`, `QHLPSYS`, `QGPL`, `QUSRSYS`, `QTEMP`, `APPLIB`, `SRCLIB`, `SCRATCH`) and files in them (`APPLIB/PAYROLL` on an authorization list, `APPLIB/CUSTOMERS`, and `SRCLIB/QRPGSRC`) so authority has something real to be checked against. Libraries and objects are stored in SQL tables keyed by library, name and type; the seed validates that every object's library, owner and authorization list exist.

## Sign-on messages

| ID | When | Confirmed |
|---|---|---|
| `CPF1120` | the user does not exist | seen on a real IBM i |
| `CPF1107` | wrong password | recalled from the earlier mock, not yet confirmed |
| `CPF1118` | profile has `PASSWORD(*NONE)` | recalled, not confirmed |
| `CPF1394` | right password, profile disabled | recalled, not confirmed |

The wording is Silverlake's own. IDs we have not seen on a real system are marked as such in `system/messages.py`. Confirming them needs a real profile signing on wrong on purpose, which counts failed attempts, so it is a deliberate human decision and not something the harness does.

Passwords ignore case at `qpwdlvl` 0 and 1, and respect it at 2 and 3.

## Profile administration messages

IBM's command reference lists these IDs for the profile commands but does not say exactly which condition raises each one. Silverlake's mapping is an inference, so every one is marked as such in `system/messages.py` (`DOCUMENTED`). Completion messages carry no ID because none is documented. Command line mistakes (unknown command, bad keyword) also carry no ID yet.

| ID | When |
|---|---|
| `CPF2204` | profile not found |
| `CPF2217` | not authorized to the profile (display, or group profile authority) |
| `CPF2292` | create or change without `*SECADM` |
| `CPF2214` | profile already exists |
| `CPF2228` | not authorized to change the profile |
| `CPF2229` | not authorized to delete the profile |
| `CPF2259` | group profile not found |
| `CPF2291` | giving a special authority you do not hold |
| `CPF2269` | giving `*SECADM` or `*AUDIT` without `*ALLOBJ` |
| `CPF223F` | `PWDEXP(*YES)` with `PASSWORD(*NONE)` |
| `CPF2203` | protected profile named for delete |
| `CPF2215` | delete refused (owns objects, or in use) |

## Library and object authority messages

IDs and wording come from IBM's 7.5 error lists for these commands. Which condition raises each is inferred, so each is marked `DOCUMENTED` in `system/messages.py`.

| ID | When |
|---|---|
| `CPF2110` `CPF2209` | library not found (`ADDLIBLE`, `DLTLIB`; object commands) |
| `CPF2111` | `CRTLIB` on a name that exists |
| `CPF2166` | library name not valid |
| `CPF2182` | not authorized to the library (`DLTLIB`, `ADDLIBLE`) |
| `CPF2216` | cannot use the library an object sits in |
| `CPF2129` `CPF2167` | system library, or a library on the list, cannot be deleted |
| `CPF2161` `CPF2168` | some objects could not be deleted, so the library stays |
| `CPF2103` `CPF2149` | already on the list, or not on the user portion |
| `CPF2208` `CPF2207` | object not found, or no authority to it |
| `CPF2223` `CPF2224` | not authorized to give or revoke authority |
| `CPF2290` `CPF22A0` `CPF22A4` `CPF22A5` | `*EXCLUDE` with another authority, `*AUTL` for a user, `*EXCLUDE` from `*PUBLIC`, not on that list |
| `CPF2283` | authorization list does not exist |

### Checked against a real IBM i

A test profile on PUB400 ran `DSPLIBL` and `DSPOBJAUT` (read-only, over TLS). What it showed, now in the seed:

- `QSYS` is owned by `QSYS` with `*PUBLIC` authority `*USE`. `QGPL` is owned by `QSYS` with `*PUBLIC` `*CHANGE`.
- A basic user asking `DSPOBJAUT` about `QSYS` gets one row, `*PUBLIC *USE`.
- The default library list is `QSYS`, `QSYS2`, `QUSRSYS`, `QHLPSYS`, the current library, `QGPL`, `QTEMP` (plus site libraries we do not copy).

That also undid a guess. Silverlake first assumed `CRTLIB` needs `*ADD` to QSYS, but a real `QSYS` is `*USE`, which has no `*ADD`, so that cannot be what stops ordinary users.

Then the `CRTLIB` test itself (create a throwaway library, look at it, delete it, run once with the owner's approval on a test profile) was stopped before it began. A basic profile on PUB400 gets:

> Not authorized to command CRTLIB in library *LIBL.

So the gate there is **authority to the command**, not to QSYS. A command is an object (`QSYS/CRTLIB *CMD`) with its own owner and public authority, and a site controls who may run it by changing that one object. PUB400 has evidently taken `CRTLIB` away from ordinary users. Silverlake models commands as objects now (see above). Not yet learned: whether a user who can run `CRTLIB` also needs anything on `QSYS` (the test never got that far), and what authority a new library gets by default. The ID of that message is not shown on the message line, so Silverlake has the wording and no ID.

Still inferred and unchecked: that `ADDLIBLE` needs `*USE` on the library, that `*ALLOBJ` skips the library gate, and what revoking an authorization list does to the public authority. The owners and public authorities of `QSYS2`, `QHLPSYS`, `QUSRSYS` and `QTEMP` in the seed are guesses.

## Not modeled yet

Said plainly, so nobody assumes otherwise:

- F4 prompting and keyword abbreviation on the command line, `DSPUSRPRF` types other than `*BASIC`, and `WRKUSRPRF` options other than 5.
- Authority to the job description, message queue and output queue named on a profile.
- Programs other than `QCMD`, so `INLPGM` and `CALL` cannot run anything else, and menu options that are not CL commands. Expired passwords and forced change, failed-attempt lockout (`MAXSIGN`), and the `QMAXSIGN` warnings.
- Adopted authority, and the exceptions to `*ALLOBJ`.
- Whether special authorities flow from a group profile. Silverlake does not pass them down.
- Object types beyond those five, creating objects, generic names and `*ALL` on the object commands, `*PRINT` and `*OUTFILE` output, the `CRTAUT` and `CRTOBJAUD` library settings, and primary groups on objects.
