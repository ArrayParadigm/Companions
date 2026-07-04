# Companions

Local companion control console for opaque AI companion memory packets,
directive tracking, proof metadata, daily check-ins, KJV Bible reading plans,
spiritual review, and project todos.

## Start

```bat
Run Web Console.bat
```

Or:

```powershell
python Companion_Web.py --host 127.0.0.1 --port 8787
```

## Project Layout

- `Companion_Web.py` runs the browser console.
- `Memory_Manager.py` owns opaque base64 companion packet encoding and command application.
- `companion-files.json` lists local companion packet files.
- `control_data/` stores directive, proof, and daily check-in JSON.
- `control_data/project_todos.json` stores home, vehicle, and tech project todos.
- `control_data/reading_progress.json` stores persistent Bible chapter completion.
- `proof_vault/` stores uploaded proof files.
- `project_assets/` stores uploaded project receipts and pictures.
- `tracker_data/` stores imported tracker JSON snapshots used by the dashboard.
- `kjv.txt` is the KJV source used by the Spiritual Daily Reading schedule.
- `deploy_scripts/` holds Linux Apache/systemd deployment helpers.
- `copyover.bat` packages the current console for the Windows-to-Linux handoff.

Generated deployment archives and older standalone tracker tools remain outside this
repo root unless they are intentionally imported.
