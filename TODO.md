### TODO Version 0.1.20.0

* Priority importance is least to greatest.
* Check the `Version-*.md` file, and follow the pattern. Update the filename based on that guidance. For the foreseeable future nothing will change with the first two segments.
* TODO formatting I use: <commands> (args)
* Completed TODO sprint items are removed from this file.
* When a TODO sprint is being done, any item not performed should be moved up a priority so it's more likely in the following sprint.
* Leave Priority headers even if empty.
* Do NOT remove items unless they're actually added/addressed
* ALL testing should have a log of issues found during testing, `testlog.md`.

  * That log should have a severity to the issue so that we can determine the usefulness in consistent testing vs periodic.
* Do not do browser based testing since it won't work correctly. Rely on user testing feedback if testings will take too much resources to be feasible.

## Priority 1

## Priority 2
- Add a first-pass <Download Companion Backup> button before the SQL migration.
    - Array-only.
    - Creates a timestamped zip of the current companion memory files and `companion-files.json`.
    - Include active and archived memories by backing up the source files, not the handoff/export packet projection.
    - Include a `manifest.json` with app version, timestamp, file list, file sizes, and SHA256 hashes.
    - Do not include users, sessions, passwords, proof uploads, project assets, or unrelated control data in this companion-only backup.

## Priority 3
- For the Fitness stuff, for the "today's orders" thing, I need a checklist I can click off for the particular group, and only see the Current day's 
- Add SQL migration groundwork for companion memories while keeping the frontend looking/feeling the same.
    - Use SQLite, not a separate database server.
    - Add a companion memory database file under app data, with tables for companions, memories, tags, archive state, packet import metadata, and backup metadata.
    - Write a one-time importer from existing `companion-files.json` + companion memory packet files into SQLite.
    - Keep existing packet files untouched as rollback/fallback during the first SQL release.
    - Add integrity checks comparing DB companion counts/IDs/archive counts against the old packet files after import.

## Priority 4
- Make SQLite the source of truth for companion memory operations.
    - Keep the Memory Manager frontend controls the same.
    - Make Add Memory, Apply Commands, archive, unarchive, resave, delete, Copy Packet, Download Packet, and Copy Handoff read/write through SQLite.
    - Generate normal companion handoff packets from SQLite while preserving the current rule that handoff/export packets omit archived memories.
    - Keep decoded companion memory content out of the casual UI; show IDs, metadata, tags, categories, status, and timestamps.
    - Add automatic companion DB safety backups before destructive or bulk operations.

## Priority 5
- Add first-class backup downloads for cloud/manual storage.
    - <Download Companion DB Backup>: Array-only download of a SQLite-safe companion memory backup plus manifest/hash file.
    - <Download Full Console Backup>: Array-only zip of companion DB, control data, tracker data, directives, calendar, fitness, projects, chores, diet, proof metadata, and selected assets.
    - Clearly label whether the full backup includes private profile/auth data; exclude sessions, caches, logs, and generated transfer archives.
    - Use SQLite-safe backup methods such as Python `sqlite3.Connection.backup()` or `VACUUM INTO`; do not casually copy a live WAL-mode DB file.
    - Add restore planning after download backups are proven: preview contents, validate hashes, require confirmation, and restore to a new timestamped backup point before replacing live data.
