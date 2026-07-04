# Changelog

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
