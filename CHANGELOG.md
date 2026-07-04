# Changelog

## 0.1.9 - 2026-07-04

### Added

- Renamed the tracker-facing console area to Daily Check-ins and added summary, check-in, journal, and physical tabs.
- Added a Spiritual area with Summary, Daily Reading, Extra Reading, and Prayer behavior through daily reading progress, extra Bible chapter reading, and prayer subcategories for gratitude, requests, repentance, service, and closeness.
- Added a Projects area with Home Maintenance, Vehicle Maintenance, and Tech Projects tabs.
- Added project todos with new-tab project pages for status, dates, expenses, scanned receipts, pictures, tasks, work logs, offering info, notes, and next steps.
- Added persistent reading progress stored in `control_data/reading_progress.json`, including Bible chapter completion percentage.

### Changed

- Bumped the release file to `Version-0.1.9.md`.
- Updated Linux sync validation to require `kjv.txt` with the deploy source.
- Updated docs to describe Daily Check-ins, Spiritual, Projects, and project todo runtime data.
- Moved detailed spiritual controls out of Daily Check-ins; that form now keeps only a daily-reading completion checkbox.

## 0.1.8 - 2026-07-04

### Added

- Added Bible reading plans for Daily Rhythm, Gospels, Epistles, and Minor Prophets inside Daily Check-In.
- Added reading section selection, completed-reading checkboxes, and per-plan progress tracking stored in daily check-ins.
- Added a web-native KJV daily reading schedule based on the old Java schedule: daily Proverbs, five Psalms, and Acts.
- Added tracker subtabs for Daily Check-Ins, Journal, Tasks, and Physical inside Tracker Imports.

### Changed

- Updated the directive ledger so task details render as a readable plaintext block in each row.
- Bumped the release file to `Version-0.1.8.md`.
- Cleared completed 0.1.7 TODO sprint items from `TODO.md`.

### Fixed

- Updated `copyover.bat` to use the active `D:\000_Files\002_Projects\EVE\MS\Companions-1` repo root, validate required source files, and support `--check` without writing deploy artifacts.
- Expanded `.gitignore` and the `copyover.bat` full-backup exclusions so caches, logs, local environments, proof uploads, build output, archives, and editor/OS files stay out of repo and transfer artifacts.
- Updated `copyover.bat` to require and package `kjv.txt` for the Daily Check-In reading schedule.

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
