# Companions

Local browser console for opaque AI companion memory packets, directive tracking,
proof metadata, daily check-ins, KJV Bible reading, fitness planning, project
todos, chores, diet inventory, calendar planning, local password login, approved
user profiles, and Array-only admin controls.

## Start

```bat
Run Web Console.bat
```

Or:

```powershell
python Companion_Web.py --host 127.0.0.1 --port 8787
```

## Pages And Tabs

- Home: signed-out landing page with profile login and registration. If a
  session times out, the console returns here and hides protected pages.
- Dashboard: summary cards for companion packets, directives, spiritual
  progress, fitness, diet, projects, chores, calendar, integrity, work
  categories, and latest daily check-in.
- Companion: Array-only packet management. The Memory tab copies opaque packets
  and handoffs, adds memories, applies command batches, creates companions,
  shows an ID-only memory index, and searches the archive by tag/category/ID.
  Directive Ledger creates and updates companion-issued directives. Proof Vault
  stores metadata and uploaded proof files. Council Mode is the handoff hub for
  asking multiple companions the same question while keeping packets separate.
- Daily Check-ins: summary, check-in form, and journal entry/readback controls.
- Fitness: Recruit Rebuild command center with orders, editable workout groups,
  an exercise database, group exercise prescriptions, mobility/cardio/strength
  logs, progress notes, challenges, body metrics, and history.
- Spiritual: summary, daily KJV reading, extra Bible chapter reading, and prayer
  category review.
- Projects: home, vehicle, and tech project todo management with standalone
  project pages and uploaded receipts, pictures, work logs, task files, and
  expense files.
- Chores: create, complete/reopen, and delete recurring or one-off chores.
- Diet: inventory, generated shopping list, food diary, and CSV import. Shopping
  difference values show only positive need or zero.
- Calendar: scheduled items for fitness groups, projects, chores, diet,
  spiritual work, companion directives, or general reminders.
- Profile Settings: signed-in display-name and password changes.
- Admin: Array-only profile approval, activation, access toggles, password
  resets, and session timeout configuration.

## Companion Packet Functions

- Copy Packet copies the current companion's base64 memory packet only. The UI
  does not display decoded memory content.
- Copy Handoff copies the companion instructions plus the base64 packet for use
  in a companion conversation.
- Add Memory writes one active memory into the selected companion packet.
- Apply Commands accepts companion command batches such as `add`, `update`,
  `archive`, `unarchive`, `resave`, `delete`, and `directive`.
- Archive Search shows archived memory IDs, categories, tags, and archive
  metadata. Use Archive, Unarchive, or Resave to move memories without exposing
  decoded content; then copy the updated base64 packet.
- Integrity checks validate JSON control files, packet schema basics, duplicate
  memory IDs, active/archive status markers, category names, and missing proof or
  project asset files.

## Data Files

- `Companion_Web.py` runs the browser console.
- `Memory_Manager.py` owns opaque base64 companion packet encoding and command
  application.
- `companion-files.json` lists local companion packet files.
- `control_data/users.json` stores local profile records. `Array` is the owner
  profile with companion access.
- `control_data/settings.json` stores admin-controlled console settings such as
  the session timeout timer.
- `control_data/directives.json`, `proof_metadata.json`, `daily_checkins.json`,
  `project_todos.json`, `chores.json`, `diet.json`, `fitness.json`,
  `reading_progress.json`, and `calendar.json` store Array runtime data.
- `control_data/users/<profile>/` stores non-owner profile-scoped runtime data.
- `proof_vault/` stores uploaded proof files.
- `project_assets/` stores uploaded project files, receipts, and pictures.
- `tracker_data/` stores journal, task, and fitness tracker JSON used by the
  dashboard and entry forms.
- `kjv.txt` is the KJV source used by the Spiritual Daily Reading schedule.
- `legacy_daily_reading/` preserves the old standalone Java reading-schedule
  source and build artifacts.
- `deploy_scripts/` holds Linux Apache/systemd deployment helpers.
- `copyover.bat` packages the current console for the Windows-to-Linux handoff.

Generated deployment archives and older standalone tracker tools remain outside
this repo root unless they are intentionally imported.
