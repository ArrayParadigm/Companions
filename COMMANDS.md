# Companion Console Commands

Command batches can be pasted into the Memory tab. One command goes on each line.

## Memory Commands

```text
add category - memory text | weight=3 | tags=tag1,tag2
update ID -> replacement memory text
edit ID -> replacement memory text
archive ID
unarchive ID
resave ID
delete ID
```

- `add` creates a new active memory in one of the known categories.
- `update` replaces an active memory and archives the previous version.
- `edit` is an alias for `update`.
- `archive` moves active memory out of the active set.
- `unarchive` restores an archived memory with the same ID.
- `resave` copies an archived or active memory back as a new active ID.
- `delete` removes an entry entirely.

## Directive Commands

```text
directive - task title | priority=3 | due=YYYY-MM-DD HH:MM | proof=true | details=task details
task - task title | issuer=Veyra | priority=5 | deadline=2026-07-05 | evidence=yes | description=what to do
```

Supported directive fields:

- `title`, `directive`, or `task`
- `details`, `detail`, or `description`
- `priority` from `1` to `5`
- `due` or `deadline`
- `proof`, `proof_required`, or `evidence`
- `issuer` or `from`

Directive status values used by the ledger are `issued`, `complete`, and `failed`.

## Daily Check-In Data

Daily check-ins are created from the Daily Check-ins tab and stored in:

```text
control_data/daily_checkins.json
```

Each check-in uses nested `body`, `mind`, `spirit`, `work`, and `relationships`
sections so the dashboard can render daily state, history, and category summaries.
The `spirit` section only records the Daily Check-ins reading-complete
confirmation. Fitness detail is entered from the Fitness tab; Daily Check-ins
only stores a fitness-complete checkbox. Detailed Bible chapter progress is
managed from the Spiritual tab and stored in:

```text
control_data/reading_progress.json
```

## Project Todo Data

Project todos are created from the Projects tab and stored in:

```text
control_data/project_todos.json
```

Project categories are Home Maintenance, Vehicle Maintenance, Tech Projects, and Chores.
Chores is selected as a category/filter, not as a top Projects tab.
Each todo opens as a separate project page with status, date added, date started,
due date, expenses, uploaded expense/task/work-log files, receipts, pictures,
tasks, work log, category-specific info, notes, and next step. Open project
pages can save edits or delete the project after confirmation.
Uploaded project assets are stored in:

```text
project_assets/
```

## Chores And Diet Data

Chores are stored in:

```text
control_data/chores.json
```

Diet inventory and food diary entries are stored in:

```text
control_data/diet.json
```

Diet inventory tracks on-hand, par, reorder threshold, container quantity, and
cost per container. The shopping list is calculated from inventory items at or
below their reorder threshold.
