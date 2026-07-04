# Test Log

## 2026-07-04 - 0.1.8 TODO Sprint

| Severity | Area | Result | Notes |
| --- | --- | --- | --- |
| Info | Static compile | Pass | `python -m py_compile Companion_Web.py Memory_Manager.py`. |
| Info | Compileall | Pass | `python -m compileall Companion_Web.py Memory_Manager.py`. |
| Info | API smoke | Pass | Temporary server returned `/api/state`, exposed reading plans, posted a disposable Epistles check-in, and reported `1/4` Epistles progress without modifying live `control_data`. |
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
