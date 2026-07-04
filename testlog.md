# Test Log

## 2026-07-04 - 0.1.9 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py`. |
| Info | HTML surface | Pass | Static marker check found Daily Check-ins summary/check-in/journal tabs, Spiritual daily/extra/prayer tabs, prayer subcategory tabs, Projects category tabs, and project detail page container. |
| Info | API smoke | Pass | Temporary server returned project categories, `KJV Daily Schedule`, seven KJV readings, accepted a KJV daily check-in, created a Tech Projects todo, marked it done, and reported project/check-in state. |
| Info | JSON validation | Pass | `companion-files.json`, `control_data/*.json`, and `tracker_data/*.json` parse successfully, including `control_data/project_todos.json`. |
| Info | Copyover check | Pass | `cmd /c copyover.bat --check` detected `D:\000_Files\002_Projects\EVE\MS\Companions-1`, version `0.1.9`, required `kjv.txt`, and copied no files. |
| Info | Whitespace | Pass | `git diff --check`; only expected LF-to-CRLF warnings from Git autocrlf. |

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
