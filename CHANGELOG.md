# Changelog

## 0.1.8 - 2026-07-04

### Added

- Added Bible reading plans for Daily Rhythm, Gospels, Epistles, and Minor Prophets inside Daily Check-In.
- Added reading section selection, completed-reading checkboxes, and per-plan progress tracking stored in daily check-ins.
- Added tracker subtabs for Daily Check-Ins, Journal, Tasks, and Physical inside Tracker Imports.

### Changed

- Updated the directive ledger so task details render as a readable plaintext block in each row.
- Bumped the release file to `Version-0.1.8.md`.
- Cleared completed 0.1.7 TODO sprint items from `TODO.md`.

## 0.1.7 - 2026-07-04

### Added

- Added a dashboard tab that separates memory, directive, spiritual, physical, and work summaries.
- Added nested daily check-ins stored in `control_data/daily_checkins.json`.
- Added daily check-in fields for mood, energy, sleep, food, exercise, prayer, Scripture, Bible reading, gratitude, service, work category, recurrence, money spent, work result, and next step.
- Added directive ledger status tabs for issued, completed, failed, and all directives.
- Added `COMMANDS.md` as the companion command reference.
- Added `testlog.md` for recurring sprint verification notes.

### Changed

- Moved the active console project into the `Companions` folder.
- Updated tracker import lookup to prefer `tracker_data/` inside the project while retaining legacy fallback paths.
- Updated `copyover.bat` to package from the `Companions` root and include docs, changelog, test log, and tracker data.
- Wrapped memory, directive, proof, and tracker list surfaces in scrollable containers.
- Bumped the release file to `Version-0.1.7.md`.

### Preserved

- Companion packet contents remain opaque base64 files.
- Linux sync still preserves server-owned companion packets, directive data, proof files, and daily check-ins.
