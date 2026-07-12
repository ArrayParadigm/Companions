# Changelog

## 0.1.17.0 - 2026-07-12

### Added

- Added Council Mode question packets that copy per-companion base64 prompts, import companion answers, and copy a consolidated answer with speaker attribution.
- Added Directive Export to copy active and recent directives as a base64 JSON packet.
- Added a New Companion dialog opened from the companion tab bar.

### Changed

- Merged Home into Dashboard so sign-in and registration use the normal console page flow.
- Changed session cookies to browser-session cookies while keeping server-side inactivity expiry.
- Removed generated Diet shopping-list items from Calendar because they do not have a scheduled shopping day.
- Calendar events now support double-click navigation to the relevant saved event or source surface.
- Bumped the release file to `Version-0.1.17.0.md`.

### Fixed

- Fixed first-login category visibility so a refresh is no longer needed after signing in.

## 0.1.17 - 2026-07-08

### Added

- Added Download Packet for saving the current encoded companion packet as a `.txt` file.

### Changed

- Copied, downloaded, and handoff companion packets now omit archived memories while preserving local archive search.
- Packet export now backfills missing issuer directive memories and keeps directive entries active until the companion archives that directive memory.
- Bumped the release file to `Version-0.1.17.md`.

## 0.1.16 - 2026-07-08

### Added

- Added a literal month-grid Calendar view with previous/next navigation and generated occurrences alongside saved events.
- Added Calendar source linking for accessible Fitness groups/orders, Projects, Chores, Diet, Spiritual items, and Array-only Companion Directives; selecting a source can auto-fill the event title.
- Added structured Chore recurrence for one-off, weekly, bi-weekly, and monthly schedules with weekday or month-day selection.

### Changed

- Calendar dashboard counts now include generated scheduled items, including recurring chores and time-based source items.
- Bumped the release file to `Version-0.1.16.md`.

## 0.1.15 - 2026-07-07

### Added

- Added security hardening for JSON request bodies, proof/project uploads, file downloads, and common response headers.
- Added companion archive search with tag cloud metadata, plus ID-only archive/unarchive/resave controls that preserve opaque packet handling.
- Added a companion packet integrity report surfaced through `/api/integrity` and the dashboard.
- Added editable Fitness exercise database records, workout groups, and per-group exercise prescriptions.
- Added a Calendar tab for scheduled fitness, projects, chores, diet, spiritual, directives, and general items.
- Added Profile Settings as a signed-in tab for display-name and password changes.

### Changed

- Moved login/register controls to the Home page and kept protected tabs hidden for unauthenticated or timed-out sessions.
- Kept Companion selection blank until explicitly chosen after login.
- Updated the dashboard with Diet, Projects, Chores, Calendar, and Integrity summaries.
- Moved the legacy Java daily-reading scheduler files into `legacy_daily_reading/`.
- Bumped the release file to `Version-0.1.15.md`.

### Fixed

- Clamped Diet shopping-list difference values to zero so overstocked items do not show negative needs.
- Mapped Fitness challenge UI status changes to `started` and `completed` so challenge history is logged.

## 0.1.14 - 2026-07-04

### Added

- Added local password authentication with PBKDF2-SHA256 hashes, HTTP-only session cookies, first-run Array password bootstrap, logout, session checks, and Array-controlled inactivity timeout.
- Added Array-only Admin controls for approving/deactivating profiles, resetting profile passwords, and toggling access to Daily Check-ins, Fitness, Spiritual, Projects, Chores, and Diet.
- Added user self-service password changes that require the current password.
- Added a persisted Fitness Recruit Rebuild Command Center seeded from `fitness_page_format.txt`, with orders, workout plan, mobility, cardio, strength, progress notes, challenges, body metrics, and history.
- Added `DELETE /api/diet/inventory/{id}` and a Diet inventory Delete control.

### Changed

- Replaced trusted profile-header access with session-backed profile access and server-side category enforcement.
- Moved Directive Ledger, Proof Vault, and Council Mode under the Companion tab workflow.
- Bumped the release file to `Version-0.1.14.md`.

## 0.1.13 - 2026-07-04

### Added

- Added local user profiles with an `Array` owner profile, profile selector, register button, and profile settings button.
- Added profile-scoped data folders for non-owner check-ins, journal, fitness, spiritual reading progress, projects, chores, and diet data under `control_data/users/`.
- Added owner-only access enforcement so only `Array` receives companion memory, directive, proof, and council state or API access.

### Changed

- Bumped the release file to `Version-0.1.13.md`.
- Updated the dashboard and navigation so non-owner profiles only see the areas they can access, without companion memory or directive cards.
- Ignored per-profile runtime folders so local user data does not become repo or transfer noise.

## 0.1.12 - 2026-07-04

### Added

- Added Fitness as a main navigation category instead of a Daily Check-ins subtab.
- Added a Chores main category with create, complete/reopen, delete, and list behavior stored in `control_data/chores.json`.
- Added a Diet main category with Summary, Inventory, Shopping List, and Food Diary tabs.
- Added diet inventory tracking with on-hand, par, reorder-at threshold, container quantity, container cost, diff, plus/minus one controls, and direct on-hand save.
- Added generated diet shopping list rows, estimated shopping cart cost, and a clean copy button.
- Added simple food diary entries and CSV import with date, food, carbs, and sugars fields.
- Added Diet summary values for last carbs, last sugars, ketosis state, ketosis start, shopping item count, and cart cost.

### Changed

- Bumped the release file to `Version-0.1.12.md`.
- Redesigned Journal so new entries use a clean blank entry box without prompt text and prior entries open into a readback panel.
- Hardened `copyover.bat` and Linux sync validation so required `kjv.txt` packaging fails loudly if the file is missing after copy/sync.
- Kept the web KJV reading schedule aligned with the old Java pattern while wrapping Acts at month end so days 29-31 still show a real chapter.
- Expanded ignore/copyover exclusions for Java build outputs so `.class` and `.jar` artifacts are not treated as transfer material.

## 0.1.11 - 2026-07-04

### Added

- Added Journal entry submission from the Journal tab.
- Added a Fitness tab with entry submission backed by the existing fitness/physical tracker data.
- Added Psalm 119 section progress to Spiritual Summary, using all 22 Psalm 119 daily sections.
- Added Date Added display to the Directive table and backfilled `created_at` when old directives are updated.

### Changed

- Bumped the release file to `Version-0.1.11.md`.
- Changed Chores from a Projects tab into a selectable project category/filter.
- Removed detailed fitness fields from Daily Check-ins; the daily form now only keeps a Fitness complete checkbox.

## 0.1.10 - 2026-07-04

### Added

- Added a Chores project category.
- Added project delete support with confirmation in the browser UI and a `DELETE /api/project-todos/{id}` route.
- Added editable standalone project pages with smaller typography, date added, date started, save controls, notes, and delete controls.
- Added project page uploads for expense files, task files, work-log files, receipts, and pictures.
- Added category-specific project wording so Tech Projects use repo, environment, access, dependency, and deployment language.

### Changed

- Bumped the release file to `Version-0.1.10.md`.
- Simplified the Projects tab so category pages show project lists instead of project summary pills.

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
