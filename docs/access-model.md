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

The `[system]` table sets `qsecurity` (20, 30, 40, 50), `qpwdlvl` (0 to 3), and `mode`.

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

How Silverlake resolves what a user may do to an object, in order: `*ALLOBJ`, then the owner, then the user's own entry on the object, then on its authorization list, then the user's groups (combined), then `*PUBLIC`. A private `*EXCLUDE` beats a generous `*PUBLIC`, which is how real systems behave.

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
| `AUDITOR` `IOADMIN` `JOBMAN` `BACKUP` `SECONLY` `SVCTOOLS` `SPOOLMAN` | `*USER` | one each | Hand out exactly one thing and see what it is worth. |
| `SVCACCT` | `*USER` | `*ALLOBJ` | An over-privileged service account. |
| `LEGACY` | `*PGMR` | `*ALLOBJ` `*JOBCTL` | A programmer who kept `*ALLOBJ`. |
| `DEVADMIN` | `*PGMR` | `*SECADM` | A programmer with a security power nobody remembers granting. |
| `NOPWD` | `*USER` | none | `PASSWORD(*NONE)`: cannot sign on. |
| `OLDTEMP` | `*USER` | none | Disabled. |
| `GRPDEV` | `*USER` | none | A group profile. |

Four secured objects (`PAYROLL` on an authorization list, `CUSTOMERS`, `SRCLIB`, `SCRATCH`) give object authority something to be checked against. Real libraries and files arrive with the object model.

## Sign-on messages

| ID | When | Confirmed |
|---|---|---|
| `CPF1120` | the user does not exist | seen on a real IBM i |
| `CPF1107` | wrong password | recalled from the earlier mock, not yet confirmed |
| `CPF1118` | profile has `PASSWORD(*NONE)` | recalled, not confirmed |
| `CPF1394` | right password, profile disabled | recalled, not confirmed |

The wording is Silverlake's own. IDs we have not seen on a real system are marked as such in `system/messages.py`. Confirming them needs a real profile signing on wrong on purpose, which counts failed attempts, so it is a deliberate human decision and not something the harness does.

Passwords ignore case at `qpwdlvl` 0 and 1, and respect it at 2 and 3.

## Not modeled yet

Said plainly, so nobody assumes otherwise:

- Creating and changing profiles from inside the system (`CRTUSRPRF`, `CHGUSRPRF`, `DSPUSRPRF`). Today access is assigned in the seed file. The authority rules for them are already in `system/authority.py`.
- Limited capabilities enforcement, expired passwords and forced change, failed-attempt lockout (`MAXSIGN`), and the `QMAXSIGN` warnings.
- Adopted authority, and the exceptions to `*ALLOBJ`.
- Whether special authorities flow from a group profile. Silverlake does not pass them down.
- Per-object commands, libraries, and the object model itself.
