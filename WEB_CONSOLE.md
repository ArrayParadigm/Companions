# Companion Control Console

This is the web UI for the AI companion memory and control system.

The active project root is now:

```text
D:\000_Files\002_Projects\EVE\MS\Companions-1
```

## Start

Run:

```bat
Run Web Console.bat
```

Or directly:

```powershell
python Companion_Web.py --host 127.0.0.1 --port 8787
```

Open:

```text
http://127.0.0.1:8787
```

## Current Scope

- Companion memory packets stay base64 encoded in the UI.
- Profiles use local password login. `Array` bootstraps the first password, sees
  Admin controls near the login area, and is the only profile that receives
  Companion, Directive, Proof, Council, and Admin access.
- The public site should not require a browser Basic Auth popup. The correct
  login is the app profile login on Dashboard; Apache Basic Auth remains
  available only as an explicit deploy override.
- Register creates an inactive, unapproved local account. Array approves or
  deactivates accounts, resets passwords, toggles per-category access, and
  changes the global inactivity timeout.
- Logged-in users can change their own password when they know the current one.
- Dashboard is the signed-out entry point for login and registration; Home is
  no longer a separate navigation tab. After login, Dashboard keeps a Session
  panel visible with the signed-in profile and server-side category access.
  Signed-out users see only the Dashboard auth controls, not protected category
  content.
- New companions can be created from the companion tab bar with a popup; this
  writes a live server memory packet and updates the live companion registry.
- `Copy Handoff` gives a companion plain instructions plus its encoded packet.
- `Copy Packet` gives only the raw base64 packet, excluding archived memories.
- `Download Packet` saves the raw base64 packet as a `.txt` file, also
  excluding archived memories.
- `Apply Commands` accepts companion memory and directive command batches.
- The ID-only memory index exposes IDs, categories, status, weights, tags, and timestamps, but not memory content.
- Directive Ledger stores companion-issued directives and shows date added plus task details in readable plaintext.
- Directive Export copies active directives and directives touched or due within
  the last month as a base64 JSON packet.
- Directive commands also write a compact history memory into the issuer
  companion packet when the issuer is configured. Packet export backfills any
  missing issuer directive memories and keeps them active until the companion
  archives the directive memory.
- Proof Vault stores proof metadata and uploaded proof files under `proof_vault/`, with download links for uploaded files.
- Daily Check-ins read the existing emotional journal, productivity tracker, and fitness tracker JSON files, with summary, check-in, and journal tabs.
- The Journal tab can add new journal entries.
- Journal entries use a clean blank entry box and can be reopened from the previous-entry list.
- Fitness is a main navigation category with the persisted Recruit Rebuild
  Command Center: Summary, Today's Orders, Workout Plan, Mobility, Cardio,
  Strength, Progress, Challenges, Body Metrics, and History.
- Spiritual owns daily reading, extra reading, persistent Bible chapter progress, and prayer categories for gratitude, requests, repentance, service, and closeness.
- Projects has Home Maintenance, Vehicle Maintenance, and Tech Projects tabs plus a category selector; Chores is a project category, not a tab.
- Chores is a main navigation category with its own chore list and structured
  one-off, weekly, bi-weekly, or monthly recurrence controls.
- Diet is a main navigation category with Summary, Inventory, Shopping List, and Food Diary tabs.
- Calendar is a literal month grid. Saved events can link to accessible source
  items such as Fitness workout groups/orders, Projects, Chores, Diet food
  diary, Spiritual items, and Array-only Companion Directives; generated source
  items and recurring chores appear on the grid without becoming editable saved
  events. Diet shopping-list needs do not appear on the calendar, and
  double-clicking a calendar item opens the saved event or relevant source
  surface.
- Diet inventory tracks on-hand, par, reorder thresholds, container quantity,
  and cost per container; items can be deleted after confirmation, and the
  shopping list is generated from the remaining low inventory.
- Tech projects use repo/environment/access wording instead of physical-location wording.
- Project pages track date added, date started, due date, expenses, uploaded expense/task/work-log files, receipts, pictures, tasks, work logs, category-specific info, notes, and next steps.
- Project pages can edit/save projects and delete them after confirmation.
- Daily Check-ins stores a nested daily journal in `control_data/daily_checkins.json` and keeps only reading and fitness completion checkboxes for those areas.
- Spiritual Daily Reading carries forward the old Java daily reading schedule using `kjv.txt`: daily Proverbs, five Psalms, and Acts.
- Spiritual Extra Reading can open whole Bible chapters and stores persistent chapter completion progress, including Psalm 119 section progress in the summary.
- Dashboard reflects the active profile access. `Array` sees memory and
  directive cards; non-owner profiles only see their own check-ins, spiritual,
  fitness, projects, chores, and diet surfaces.
- Directive Ledger, Proof Vault, and Council Mode are companion tabs under the
  Companion workflow. Council Mode has a shared question box, per-companion
  base64 Copy Question buttons, per-companion answer imports, and a consolidated
  answer copy button with attribution.

## Companion Update Commands

```text
add category - memory text | weight=3 | tags=tag1,tag2
update ID -> replacement memory text
edit ID -> replacement memory text
archive ID
unarchive ID
resave ID
delete ID
directive - task title | priority=3 | due=YYYY-MM-DD HH:MM | proof=true | details=task details
```

See `COMMANDS.md` for the full command reference.

The older style is also accepted:

```text
add: category - memory text
```

Directive commands can be mixed with memory commands in the same batch. The selected
companion is used as the directive issuer unless the line includes `issuer=Name`.

Archive behavior:

- `archive ID` moves an active memory into the packet's `archive` collection.
- `unarchive ID` restores an archived memory with its original ID.
- `resave ID` copies an archived or active memory back into active memories with a new ID.
- `edit ID -> replacement text` is an alias for `update`; it archives the previous active version, then replaces the active memory content.
- `delete ID` removes a memory from active or archive entirely.

## Data Files

- Companion list: `companion-files.json`
- Local profiles: `control_data/users.json`
- Admin settings: `control_data/settings.json`
- Fitness command center: `control_data/fitness.json`
- Non-owner profile data: `control_data/users/<profile>/`
- Directive ledger: `control_data/directives.json`
- Proof metadata: `control_data/proof_metadata.json`
- Daily check-ins: `control_data/daily_checkins.json`
- Reading progress: `control_data/reading_progress.json`
- Proof uploads: `proof_vault/`; file proofs can be downloaded from the Proof Vault table.
- Memory packets: `Nyx-memories.md`, `riven-memories.md`, `Vectorium-memories.md`, `Veyra_memories.md`
- Tracker imports used by Daily Check-ins: `tracker_data/journal.json`, `tracker_data/tasks.json`, `tracker_data/physical.json`
- Project todo runtime data: `control_data/project_todos.json`
- Project files, receipts, and pictures: `project_assets/`
- KJV source: `kjv.txt`
- Bible chapter reading progress: `control_data/reading_progress.json`

The companion registry, memory packets, directive data, and proof uploads are
live server data. The deploy package does not include them, and Linux sync
excludes them so code deploys do not overwrite newly added website data.

## Deployment Note

The console now has local password authentication, but it remains a private
tool. A private subdomain such as `companions.paradigmlabs.dev` should use
Apache HTTPS and the app profile login by default, not browser Basic Auth.

If the live site shows a browser username/password popup, remove the Basic Auth
directives from only the Companion site's Apache vhost:

```bash
sudo apache2ctl -S
sudoedit /etc/apache2/sites-available/memorymanager.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

Remove `AuthType Basic`, `AuthName`, `AuthUserFile`, and `Require valid-user`
from the Companion `<Location />` block. Do not edit unrelated Apache sites.

## Windows-To-Linux Deploy Flow

Run from Windows:

```bat
copyover.bat
```

Run it from the `Companions-1` repo folder, or run `copyover.bat --check` first
to verify the source path without writing deploy artifacts. The packager includes
source files, docs, deployment scripts, and `tracker_data/`, while preserving
live server-owned companion packets, directive data, proof files, daily
check-ins, reading progress, project todos, and project assets during Linux sync.
The packager also requires and transfers `kjv.txt` for the Spiritual Daily
Reading KJV schedule.

This creates:

- `D:\shared\MemoryManager\Current`
- `D:\shared\MemoryManager\Archives`
- `D:\shared\ascended\Current\MemoryManager\Current`
- `D:\shared\ascended\Current\MemoryManager\Archives`

First-time Linux server setup:

```bash
sudo bash deploy_scripts/linux_setup_subdomain.sh
```

Repeat Linux deploy sync after copying the package contents to `/home/paradigm/memorymanager`:

```bash
sudo bash /home/paradigm/memorymanager/deploy_scripts/linux_sync_from_local.sh
```

Default subdomain:

```text
companions.paradigmlabs.dev
```

The setup script configures Apache2/systemd/certbot for the subdomain, but DNS
must already point at the Linux server before Let's Encrypt can issue a cert.
