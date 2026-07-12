# Test Log

## 2026-07-12 - 0.1.17.3 Signed-Out Auth Shell Fix

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py` passed. |
| Info | Compileall | Pass | `python -m compileall -q Companion_Web.py Memory_Manager.py` passed. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully across 15 files. |
| Info | Signed-out shell marker gate | Pass | Static search confirmed Dashboard content is separated from auth controls, hidden when signed out, and protected category/admin/companion elements are hidden in logged-out state. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.17.3`, and copied no files. |
| Info | Whitespace gate | Pass | `git diff --check` reported no whitespace errors; Git only warned that edited text files will be normalized from LF to CRLF when touched. |

## 2026-07-12 - 0.1.17.2 In-App Session Feedback Fix

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py` passed. |
| Info | Compileall | Pass | `python -m compileall -q Companion_Web.py Memory_Manager.py` passed. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully across 15 files. |
| Info | Session UI marker gate | Pass | Static search confirmed the Dashboard Session panel, session summary renderer, login/register panel toggles, and category access badges are present. |
| Info | Session data smoke | Pass | Temporary isolated data verified `Array` with empty legacy access still produces full public profile access, full `/api/state` category access, and companion access for the Session panel. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.17.2`, and copied no files. |
| Info | Whitespace gate | Pass | `git diff --check` reported no whitespace errors; Git only warned that edited text files will be normalized from LF to CRLF when touched. |

## 2026-07-12 - 0.1.17.1 Regression Fix

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py` passed. |
| Info | Compileall | Pass | `python -m compileall -q Companion_Web.py Memory_Manager.py` passed. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully across 15 files. |
| Info | Auth/category smoke | Pass | Temporary isolated data verified unauthenticated session state, stale `Array` access still resolves to all categories plus companion/proof/directive access, and a non-owner profile only receives explicitly granted categories. |
| Info | Apache auth static check | Pass | `deploy_scripts/linux_setup_subdomain.sh` defaults `REQUIRE_BASIC_AUTH` to `0`, retains the explicit `REQUIRE_BASIC_AUTH=1` override guard, and keeps the optional Basic Auth block available only when requested. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.17.1`, and copied no files. |
| Info | Whitespace gate | Pass | `git diff --check` reported no whitespace errors; Git only warned that edited text files will be normalized from LF to CRLF when touched. |

## 2026-07-12 - 0.1.17.0 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py` passed. |
| Info | Compileall | Pass | `python -m compileall -q Companion_Web.py Memory_Manager.py` passed. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully across 15 files. |
| Info | Functional smoke | Pass | Temporary isolated data verified session cookies no longer use a fixed `Max-Age`, server-side inactivity expiry still works, Diet shopping-list items are excluded from Calendar sources/generated events, directive calendar generation uses `due_at`, and Directive Export decodes to active plus recent directives only. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.17.0`, and copied no files. |
| Info | Static marker gate | Pass | Static search confirmed Dashboard auth panel, access-control refresh, Directive Export, Council question/import/consolidation controls, New Companion dialog, calendar double-click handlers, and session-cookie update are present; shopping-list calendar markers are absent. |
| Low | First-login category visibility | Fixed | The signed-out state hid unrestricted nav buttons; authenticated access rendering now restores unrestricted navigation before applying access gates, so first login no longer needs a refresh. |
| Info | Whitespace gate | Pass | `git diff --check` reported no whitespace errors; Git only warned that edited text files will be normalized from LF to CRLF when touched. |

## 2026-07-08 - 0.1.17 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py` passed. |
| Info | Compileall | Pass | `python -m compileall -q Companion_Web.py Memory_Manager.py` passed. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully across 15 files. |
| Info | Functional smoke | Pass | Temporary isolated data verified packet export excludes archived memories, preserves active memories, backfills one issuer directive memory, keeps the local archive intact, and does not duplicate directive memories on repeat export. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.17`, and copied no files. |
| Info | Static marker gate | Pass | Static search confirmed packet export helpers, archive export policy metadata, Download Packet control, and client-side text download creation are present. |
| Info | BUGS file | Not found | No `BUGS.md` or `BUGS` file exists in this repo during the 0.1.17 TODO sprint pass. |
| Info | Whitespace gate | Pass | `git diff --check` reported no whitespace errors; Git only warned that edited text files will be normalized from LF to CRLF when touched. |

## 2026-07-08 - 0.1.16 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py` passed. |
| Info | Compileall | Pass | `python -m compileall -q Companion_Web.py Memory_Manager.py` passed. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully. |
| Info | Functional smoke | Pass | Temporary isolated data verified Calendar source linking from a Fitness group, auto-filled calendar event titles, weekly chores, bi-weekly chores, monthly chores, generated calendar occurrences, and source lists. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.16`, and copied no files. |
| Info | Static marker gate | Pass | Static search confirmed literal calendar grid, generated events, Calendar source selector, chore recurrence controls, bi-weekly wording, grid renderer, and backend calendar source generation are present. |
| Info | BUGS file | Not found | No `BUGS.md` or `BUGS` file exists in this repo during the 0.1.16 TODO sprint pass. |
| Info | Whitespace gate | Pass | `git diff --check` reported no whitespace errors; Git only warned that edited text files will be normalized from LF to CRLF when touched. |

## 2026-07-07 - 0.1.15 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py` passed. |
| Info | Compileall | Pass | `python -m compileall -q Companion_Web.py Memory_Manager.py` passed. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully across 15 files, including `control_data/calendar.json`. |
| Info | Functional smoke | Pass | Temporary isolated data verified non-negative Diet shopping diff, Fitness exercise/group creation and group item prescriptions, challenge `active`/`complete` mapping to `started`/`completed` history, Calendar event creation, companion archive search/resave, and integrity reporting. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.15`, and copied no files. |
| Info | Static marker gate | Pass | Static search confirmed `X-Content-Type-Options`, `Path.relative_to`, calendar routes, Fitness group routes, archive search controls, and Profile Settings controls are present; `changePasswordButton` is absent. |
| Info | Folder cleanup audit | Pass | Legacy Java daily-reading files were moved under `legacy_daily_reading/`; `.gitignore` exceptions allow the moved `.class` and `.jar` artifacts to remain trackable there. |
| Info | BUGS file | Not found | No `BUGS.md` or `BUGS` file exists in this repo during the 0.1.15 TODO sprint pass. |
| Info | Whitespace gate | Pass | `git diff --check` reported no whitespace errors; Git only warned that edited text files will be normalized from LF to CRLF when touched. |

## 2026-07-04 - 0.1.14 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | API smoke | Pass | Temporary isolated server verified Array password bootstrap, cookie login, session timeout expiry after admin timeout change, self password change requiring current password, pending user registration denial, Array approval/access toggles/password reset, non-Array 403 for denied Daily Check-ins and companion APIs, diet inventory create/adjust/delete with shopping-list removal, and profile-scoped Fitness logs/orders/challenges/body metrics/history. |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py` passed. |
| Info | Compileall | Pass | `python -m compileall -q Companion_Web.py Memory_Manager.py` passed. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully across 14 files. |
| Info | Static marker gate | Pass | Static marker check found auth controls, Admin controls, timeout controls, Fitness tabs/action buttons, Diet inventory delete, and matching HTML ids for JS references; confirmed `journalPrompt`, `data-tracker="fitness"`, old `X-Profile` header injection, old `profileSelect`, and separate companion nav tabs are absent from `Companion_Web.py`. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.14`, and copied no files. |
| Info | Ignore audit | Pass | `.gitignore` already excludes pycache, backups, proof uploads, project uploads, per-profile runtime folders, and local logs including the 0.1.14 server log files. |
| Info | BUGS file | Not found | No `BUGS.md` exists in this repo during the 0.1.14 TODO sprint pass. |
| Info | Whitespace gate | Pass | `git diff --check` reported no whitespace errors; Git only warned that edited text files will be normalized from LF to CRLF when touched. |

## 2026-07-04 - 0.1.13 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Profile API/UI smoke | Pass | Temporary server rendered profile selector, register button, settings button, and companion-only markers; registered Bob; confirmed `Array` has companion access and Bob has no companions, directives, or proof state; direct Bob companion packet request returned 403; Bob check-in, journal, fitness, project, and reading progress writes landed under `control_data/users/bob/`; `Array` project state did not include Bob's project; Bob project page preserved `?profile=Bob`. |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py` passed. |
| Info | Compileall | Pass | `python -m compileall -q Companion_Web.py Memory_Manager.py` passed. |
| Info | Static marker gate | Pass | Static marker check found profile registry, profile header controls, owner-only access markers, profile-scoped data paths, fetch `X-Profile` header injection, and profile API routes; confirmed `journalPrompt` and Daily Check-ins fitness tab markers are absent. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully across 12 files. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.13`, required `kjv.txt`, and copied no files. |
| Info | BUGS file | Not found | No `BUGS.md` exists in this repo during the 0.1.13 TODO sprint pass. |
| Info | Whitespace gate | Pass | `git diff --check` reported no whitespace errors; Git only warned that edited text files will be normalized from LF to CRLF when touched. |

## 2026-07-04 - 0.1.12 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | API/UI smoke | Pass | Temporary server rendered Fitness, Chores, Diet, Diet tabs, clean Journal entry controls, Journal Open buttons, Spiritual Daily Reading, and Extra Reading; posted a prompt-free Journal entry, Fitness entry, Chore create/update/delete, Diet inventory create/adjust/update, Food Diary entry, and Food CSV import; generated a shopping list with one container and $8 cost. |
| Info | KJV schedule | Pass | Direct schedule check returned Proverbs 4, Psalms 4/34/64/94/124, and Acts 4 for 2026-07-04; end-of-month check returned Proverbs 31, Psalms 1/31/61/91/121, and wrapped Acts 3 for 2026-07-31, with all KJV text available from `kjv.txt`. |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py` passed. |
| Info | Compileall | Pass | `python -m compileall -q Companion_Web.py Memory_Manager.py` passed. |
| Info | HTML/static marker gate | Pass | Static marker check found Fitness, Chores, Diet, Diet tabs, shopping-list copy support, clean Journal readback, KJV schedule wiring, and new Chores/Diet data files; confirmed `journalPrompt` and Daily Check-ins fitness tab markers are absent. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully across 11 files. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.12`, required `kjv.txt`, and copied no files. |
| Info | BUGS file | Not found | No `BUGS.md` exists in this repo during the 0.1.12 TODO sprint pass. |
| Info | Whitespace gate | Pass | `git diff --check` reported no whitespace errors; Git only warned that edited text files will be normalized from LF to CRLF when touched. |

## 2026-07-04 - 0.1.11 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py`. |
| Info | Compileall | Pass | `python -m compileall Companion_Web.py Memory_Manager.py`. |
| Info | HTML surface | Pass | Static marker check found project category selectors, Journal and Fitness submit controls, Fitness complete checkbox, Directive Date Added column, Psalm 119 summary markers, and no Chores tab or old daily exercise field IDs. |
| Info | API smoke | Pass | Temporary server posted a Journal entry, posted a Fitness entry, saved a Daily Check-in with only `fitness_completed` for fitness, marked Psalm 119:1-8 read, reported 1/22 Psalm 119 sections, created a Chores project category item, created a directive with date added, and backfilled date added on an old directive update. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.11`, required `kjv.txt`, and copied no files. |
| Info | Whitespace | Pass | `git diff --check`; only expected LF-to-CRLF warnings from Git autocrlf. |

## 2026-07-04 - 0.1.10 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py`. |
| Info | Compileall | Pass | `python -m compileall Companion_Web.py Memory_Manager.py`. |
| Info | HTML surface | Pass | Static marker check found Chores, project delete handlers, standalone page delete/save controls, date added/date started text, expense/task/work-log upload labels, and tech repo/environment wording; no `projectSummary` UI container remains. |
| Info | API project smoke | Pass | Temporary server exposed the Chores category, returned tech-specific repo/environment wording, created a Tech project with date started, rendered the standalone edit page, patched it into Chores, uploaded a work-log file, deleted the project, and removed it from state. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.10`, required `kjv.txt`, and copied no files. |
| Info | Ignore audit | Pass | `git check-ignore -v` matched pycache, backups, proof uploads, project uploads, virtualenvs, build/dist output, logs, archives, and OS noise. |
| Info | Whitespace | Pass | `git diff --check`; only expected LF-to-CRLF warnings from Git autocrlf. |

## 2026-07-04 - 0.1.9 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py`. |
| Info | Compileall | Pass | `python -m compileall Companion_Web.py Memory_Manager.py`. |
| Info | HTML surface | Pass | Static marker check found the single Daily Check-ins reading confirmation, Spiritual summary/daily/extra/prayer tabs, Read buttons, extra book/chapter controls, Projects category tabs, project asset upload form, and project detail page container. |
| Info | API smoke | Pass | Temporary server returned `KJV Daily Schedule` with seven KJV readings, reported 1189 Bible chapters, marked a daily reading complete, returned John 3 with `3:16`, created a Tech Projects todo, rendered its new-tab project page, uploaded a receipt asset, and rendered that asset back on the project page. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully, including `control_data/project_todos.json` and `control_data/reading_progress.json`. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.9`, required `kjv.txt`, and copied no files. |
| Info | Whitespace | Pass | `git diff --check`; only expected LF-to-CRLF warnings from Git autocrlf. |
| Low | API smoke harness | Fixed | First harness run used a stale handler class name; corrected to `CompanionWebHandler` and reran successfully. |
| Low | HTML marker gate | Fixed | Static marker check caught a missing explicit Spiritual Summary tab and retired reading-checklist renderer strings; added the Summary tab and removed the stale Daily Check-ins history display. |

## 2026-07-04 - 0.1.8 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py`. |
| Info | Compileall | Pass | `python -m compileall Companion_Web.py Memory_Manager.py`. |
| Info | API smoke | Pass | Temporary server returned `/api/state`, exposed reading plans, posted a disposable Epistles check-in, and reported `1/4` Epistles progress without modifying live `control_data`. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.8`, and copied no files. |
| Info | KJV schedule | Pass | Direct schedule check for 2026-07-04 returned Proverbs 4, Psalms 4/34/64/94/124, and Acts 4 from `kjv.txt`. |
| Info | API KJV schedule | Pass | Temporary server returned `/api/state` with `KJV Daily Schedule`, seven daily readings, and KJV text available. |
| Info | Ignore audit | Pass | `git check-ignore -v` matched pycache, backups, proof uploads, logs, virtualenvs, build/dist output, archives, and OS noise. |
| Info | Backup filter | Pass | Direct PowerShell filter validation selected 34 source files and excluded `.git`, backup zips, pycache, proof uploads, build/dist output, logs, and pyc files. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully. |
| Info | Whitespace | Pass | `git diff --check`; only expected LF-to-CRLF warnings from Git autocrlf. |
| Low | API smoke harness | Fixed | First harness run called a stale helper name, `ensure_runtime_files`; corrected to `ensure_data_files` and reran successfully. |

## 2026-07-04 - 0.1.7 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py`. |
| Info | Compileall | Pass | `python -m compileall Companion_Web.py Memory_Manager.py`. |
| Info | API smoke | Pass | Temporary server returned `/api/state` with 4 companions. |
| Info | Check-in API | Pass | Posted a disposable check-in through `/api/checkins` using a temporary `control_data` directory; live data was not modified. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse with `python -m json.tool`. |
| Info | Whitespace | Pass | `git diff --check`; only LF-to-CRLF warning for `README.md`. |
| Medium | Deploy package | Not run | `copyover.bat` was statically updated but not executed because it writes to `D:\shared\MemoryManager` and the manual handoff path. |
