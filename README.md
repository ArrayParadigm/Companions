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

- Dashboard: profile login and registration when signed out. Protected dashboard
  category content is hidden until login. After login, the Session panel shows
  the signed-in profile and enabled category access, followed by summary cards
  for companion packets, directives, spiritual progress, fitness, diet,
  projects, chores, calendar, integrity, Garden / Realm Status, stale work,
  work categories, and latest daily check-in. If a session times out from
  inactivity, protected pages hide and the console returns to Dashboard login.
- Eve Console: Array-only aggregator for Royal Inspections, Daily Minimums,
  Royal Decrees, Tiny Tyrant Orders, Princess Campaign items, Eve memory
  candidates, Eve-related directives, recent proof/report metadata, and stale
  project/chore visibility. It does not duplicate data: Daily Check-in quick
  modes stay in Daily Check-ins and Eve-related orders stay in Directive Ledger.
- Companion: Array-only packet management. The Memory tab copies opaque packets
  and handoffs, downloads packet text files, adds memories, previews/applies
  command batch counts without showing memory text, opens the New Companion
  dialog from the companion tab bar, shows an
  ID-only memory index, and searches the archive by tag/category/ID. Copied,
  downloaded, and handoff packets omit archived memories while local archive
  search remains available. Directive Ledger creates and updates
  companion-issued directives with type/tags/timezone metadata, exports
  active/recent directives as a base64 packet, and previews/imports directive
  export packets without overwriting existing directives. Proof Vault stores
  metadata and uploaded proof files. Council Mode
  copies base64 question packets per companion, imports their answers, and
  copies a consolidated answer with attribution.
- Daily Check-ins: summary, check-in form, What Mattered Today, Array-only Royal
  Inspection, Daily Minimums, and journal entry/readback controls.
- Fitness: Recruit Rebuild command center with orders, scheduled workout
  groups, the specific PT regimen, an Exercise Library tab with search/tag
  filters/detail popup/add/edit/delete/add-to-group controls, mobility/cardio/
  strength logs, progress notes, challenges, body metrics, and history. The
  `0.1.20.0` app migration seeds `control_data/fitness.json` with the current
  Recruit Rebuild PT plan, exercises, and groups the first time Fitness data is
  loaded. Today's Orders shows only the current weekday's scheduled group and
  persists its exercise checklist for that date.
- Spiritual: summary, daily KJV reading, extra Bible chapter reading, and prayer
  category review.
- Projects: home, vehicle, and tech project todo management with status/sort
  filters, standalone project pages, and uploaded receipts, pictures, work
  logs, task files, and expense files.
- Chores: create, complete/reopen, and delete one-off, weekly, bi-weekly,
  or monthly chores with explicit weekday or month-day recurrence.
- Diet: inventory, generated shopping list, food diary, and CSV import. Shopping
  difference values show only positive need or zero.
- Calendar: a month-grid planner with saved events, generated scheduled items,
  and source links for fitness groups/orders, projects, chores, diet food diary,
  spiritual work, companion directives, or general reminders. Shopping-list
  needs do not generate calendar items. Generated labels include category,
  title, and source ID; double-click a calendar item to open its saved event or
  source surface. Upcoming calendar items can be previewed, copied, or
  downloaded as a plain-text export.
- Profile Settings: signed-in display-name and password changes.
- Admin: Array-only profile approval, activation, access toggles, password
  resets, and session timeout configuration.

## Public Site Authentication

Use the app's own profile login on the Dashboard. The Apache deployment helper
does not enable browser Basic Auth by default; if an existing live vhost still
shows a browser username/password popup, remove the Basic Auth directives from
the Companion site's `<Location />` block only, then run `apache2ctl configtest`
and reload Apache.

## Companion Packet Functions

- Copy Packet copies the current companion's base64 memory packet only. The UI
  does not display decoded memory content, and the copied packet excludes
  archived memories.
- Download Packet saves the current encoded packet as a `.txt` file with the
  same archive-free export behavior as Copy Packet.
- Download Companion Source Rollback is Array-only and saves a timestamped ZIP
  of the configured pre-SQL source files plus `companion-files.json`. It is
  rollback material and does not reflect later SQLite writes. Its
  `manifest.json` records the app version, timestamp, file sizes, and SHA256
  hashes; auth/profile data, sessions, proofs, project assets, and other control
  data are excluded.
- Download Companion DB Backup uses SQLite's online backup API and packages the
  database with a size/SHA256 manifest. Download Full Console Backup is
  explicitly private because it adds profiles/password hashes, control and
  tracker data, the companion registry/rollback packets, proof metadata/uploads,
  and project assets; sessions, caches, logs, and generated backup/transfer
  archives are excluded.
- Restore Backup first previews and validates ZIP paths, membership, hashes,
  sizes, and SQLite integrity. Restore requires typing `RESTORE` exactly and
  creates a timestamped full-console restore point before replacing data.
- Copy Handoff copies the companion instructions plus the base64 packet for use
  in a companion conversation.
- Add Memory writes one active memory into the selected companion packet.
- Apply Commands accepts companion command batches such as `add`, `update`,
  `archive`, `unarchive`, `resave`, `delete`, and `directive`. Preview Commands
  reports operation counts before apply and does not expose decoded memory text.
- Directive ledger entries are kept in the issuer companion's active memory
  until that directive memory is archived, including directives synced during
  packet export.
- Directive Export copies active and recent directives as
  `companion-directive-export/v1` base64 JSON. The import tool previews
  directive IDs/titles/statuses only, skips duplicates, merges without deleting
  existing directives, and creates a backup before writing.
- Archive Search shows archived memory IDs, categories, tags, and archive
  metadata. Use Archive, Unarchive, or Resave to move memories without exposing
  decoded content; then copy the updated base64 packet.
- Integrity checks validate JSON control files, packet schema basics, duplicate
  memory IDs, active/archive status markers, category names, and missing proof or
  project asset files. Copy Health Report exports safe diagnostics and counts
  without memory contents or secrets.

## Data Files

- `Companion_Web.py` runs the browser console.
- `Memory_Manager.py` owns opaque base64 companion packet encoding and command
  application.
- `Companion_Store.py` owns SQLite import, normalized persistence, integrity,
  safety-backup, and database-restore behavior.
- `app_data/companion_memories.sqlite3` is the companion-memory source of truth.
- `companion-files.json` and its local packet files seed the one-time SQLite
  import and remain untouched rollback/fallback material after migration.
- `control_data/users.json` stores local profile records. `Array` is the owner
  profile with companion access.
- `control_data/settings.json` stores admin-controlled console settings such as
  the inactivity timeout timer.
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
