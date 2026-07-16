"""SQLite persistence and safe backup helpers for companion memory packets."""

import copy
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
APP_DATA_DIR = APP_DIR / "app_data"
DB_PATH = APP_DATA_DIR / "companion_memories.sqlite3"
SAFETY_BACKUP_DIR = APP_DIR / "bkup" / "companion_db_backups"


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS companions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    schema_name TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    companion_id INTEGER NOT NULL REFERENCES companions(id) ON DELETE CASCADE,
    memory_id TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    weight INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_companion_memory ON memories(companion_id, memory_id);
CREATE TABLE IF NOT EXISTS tags (
    memory_row_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY(memory_row_id, tag)
);
CREATE TABLE IF NOT EXISTS archive_state (
    memory_row_id INTEGER PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    archived INTEGER NOT NULL CHECK(archived IN (0, 1)),
    archived_at TEXT,
    archived_reason TEXT
);
CREATE TABLE IF NOT EXISTS packet_import_metadata (
    id INTEGER PRIMARY KEY,
    companion_id INTEGER NOT NULL REFERENCES companions(id) ON DELETE CASCADE,
    imported_at TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    active_count INTEGER NOT NULL,
    archive_count INTEGER NOT NULL,
    active_ids_json TEXT,
    archive_ids_json TEXT,
    integrity_passed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS backup_metadata (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    backup_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    reason TEXT NOT NULL
);
"""


def now_stamp():
    return datetime.now().replace(microsecond=0).isoformat()


def connect(path=DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(packet_import_metadata)")}
    for name, definition in {
        "active_ids_json": "TEXT",
        "archive_ids_json": "TEXT",
        "integrity_passed": "INTEGER NOT NULL DEFAULT 0",
    }.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE packet_import_metadata ADD COLUMN {name} {definition}")
    return connection


def _source_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"


def _envelope(payload):
    value = copy.deepcopy(payload)
    value.pop("memories", None)
    value.pop("archive", None)
    return value


def _write_payload(connection, companion, source_path, payload, import_record=False):
    stamp = now_stamp()
    envelope = _envelope(payload)
    existing = connection.execute("SELECT id, created_at FROM companions WHERE name = ?", (companion,)).fetchone()
    created_at = existing["created_at"] if existing else stamp
    connection.execute(
        """INSERT INTO companions(name, source_file, schema_name, envelope_json, created_at, updated_at)
           VALUES(?, ?, ?, ?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET source_file=excluded.source_file,
             schema_name=excluded.schema_name, envelope_json=excluded.envelope_json, updated_at=excluded.updated_at""",
        (companion, str(source_path), payload.get("schema", "ai-companion-memory/v1"),
         json.dumps(envelope, ensure_ascii=False), created_at, stamp),
    )
    companion_id = connection.execute("SELECT id FROM companions WHERE name = ?", (companion,)).fetchone()["id"]
    connection.execute("DELETE FROM memories WHERE companion_id = ?", (companion_id,))
    for archived, collection in ((0, payload.get("memories", [])), (1, payload.get("archive", []))):
        for entry in collection:
            cursor = connection.execute(
                """INSERT INTO memories(companion_id, memory_id, category, content, weight, status,
                   created_at, updated_at, raw_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (companion_id, str(entry.get("id", "")), str(entry.get("category", "observations")),
                 str(entry.get("content", "")), int(entry.get("weight", 3)),
                 str(entry.get("status", "archived" if archived else "active")),
                 entry.get("created_at"), entry.get("updated_at"), json.dumps(entry, ensure_ascii=False)),
            )
            row_id = cursor.lastrowid
            for tag in entry.get("tags", []):
                connection.execute("INSERT OR IGNORE INTO tags(memory_row_id, tag) VALUES(?, ?)", (row_id, str(tag)))
            connection.execute(
                "INSERT INTO archive_state(memory_row_id, archived, archived_at, archived_reason) VALUES(?, ?, ?, ?)",
                (row_id, archived, entry.get("archived_at"), entry.get("archived_reason")),
            )
    if import_record:
        active_ids = [str(item.get("id")) for item in payload.get("memories", [])]
        archive_ids = [str(item.get("id")) for item in payload.get("archive", [])]
        connection.execute(
            """INSERT INTO packet_import_metadata(companion_id, imported_at, source_file, source_sha256,
               active_count, archive_count, active_ids_json, archive_ids_json, integrity_passed)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (companion_id, stamp, str(source_path), _source_hash(source_path),
             len(active_ids), len(archive_ids), json.dumps(active_ids), json.dumps(archive_ids)),
        )


def ensure_imported(companion_files, file_loader):
    with connect() as connection:
        for companion, source_path in companion_files.items():
            exists = connection.execute("SELECT 1 FROM companions WHERE name = ?", (companion,)).fetchone()
            if not exists:
                _write_payload(connection, companion, source_path, file_loader(companion), import_record=True)


def load_payload(companion, companion_files, file_loader):
    ensure_imported(companion_files, file_loader)
    with connect() as connection:
        row = connection.execute("SELECT * FROM companions WHERE name = ?", (companion,)).fetchone()
        if not row:
            raise ValueError(f"Unknown companion in database: {companion}")
        payload = json.loads(row["envelope_json"])
        payload["schema"] = row["schema_name"]
        payload["memories"] = []
        payload["archive"] = []
        memories = connection.execute(
            """SELECT m.raw_json, a.archived FROM memories m
               JOIN archive_state a ON a.memory_row_id = m.id
               WHERE m.companion_id = ? ORDER BY m.id""",
            (row["id"],),
        ).fetchall()
        for memory in memories:
            entry = json.loads(memory["raw_json"])
            payload["archive" if memory["archived"] else "memories"].append(entry)
        return payload


def sqlite_backup_bytes(reason="download", backup_type="companion-db"):
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as source, tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "companion_memories.sqlite3"
        target = sqlite3.connect(temp_path)
        try:
            source.backup(target)
        finally:
            target.close()
        body = temp_path.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    with connect() as connection:
        connection.execute(
            "INSERT INTO backup_metadata(created_at, backup_type, filename, size, sha256, reason) VALUES(?, ?, ?, ?, ?, ?)",
            (now_stamp(), backup_type, "companion_memories.sqlite3", len(body), digest, reason),
        )
    return body, digest


def safety_backup(reason):
    body, digest = sqlite_backup_bytes(reason=reason, backup_type="automatic-safety")
    SAFETY_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = SAFETY_BACKUP_DIR / f"companion-memories.{stamp}.sqlite3"
    path.write_bytes(body)
    return path, digest


def save_payload(companion, source_path, payload, reason="memory-write"):
    ensure_imported({companion: source_path}, lambda _name: payload)
    backup_path, _digest = safety_backup(reason)
    with connect() as connection:
        _write_payload(connection, companion, source_path, payload)
    return backup_path


def integrity_comparison(companion_files, file_loader):
    ensure_imported(companion_files, file_loader)
    results = []
    for companion, source_path in companion_files.items():
        source = file_loader(companion)
        source_active = {str(item.get("id")) for item in source.get("memories", [])}
        source_archive = {str(item.get("id")) for item in source.get("archive", [])}
        with connect() as connection:
            metadata = connection.execute(
                """SELECT p.* FROM packet_import_metadata p JOIN companions c ON c.id=p.companion_id
                   WHERE c.name=? ORDER BY p.id DESC LIMIT 1""",
                (companion,),
            ).fetchone()
            if metadata and not metadata["active_ids_json"]:
                connection.execute(
                    """UPDATE packet_import_metadata SET active_ids_json=?, archive_ids_json=?, integrity_passed=1
                       WHERE id=?""",
                    (json.dumps(sorted(source_active)), json.dumps(sorted(source_archive)), metadata["id"]),
                )
                metadata = connection.execute("SELECT * FROM packet_import_metadata WHERE id=?", (metadata["id"],)).fetchone()
        imported_active = set(json.loads(metadata["active_ids_json"] or "[]")) if metadata else set()
        imported_archive = set(json.loads(metadata["archive_ids_json"] or "[]")) if metadata else set()
        matches = bool(metadata and metadata["integrity_passed"] and source_active == imported_active and source_archive == imported_archive)
        results.append({
            "companion": companion,
            "source_file": source_path.name,
            "source_active": len(source_active),
            "database_active": len(imported_active),
            "source_archive": len(source_archive),
            "database_archive": len(imported_archive),
            "active_ids_match": source_active == imported_active,
            "archive_ids_match": source_archive == imported_archive,
            "matches": matches,
            "comparison_scope": "one-time packet import baseline",
        })
    return results


def validate_database_bytes(body):
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "candidate.sqlite3"
        path.write_bytes(body)
        connection = sqlite3.connect(path)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            required = {"companions", "memories", "tags", "archive_state", "packet_import_metadata", "backup_metadata"}
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()
    if result != "ok":
        raise ValueError(f"SQLite integrity check failed: {result}")
    missing = sorted(required - tables)
    if missing:
        raise ValueError(f"Companion database is missing tables: {', '.join(missing)}")
    return True


def restore_database_bytes(body):
    validate_database_bytes(body)
    safety_path, _digest = safety_backup("pre-restore")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=DB_PATH.parent, delete=False, suffix=".sqlite3") as handle:
        handle.write(body)
        temp_name = handle.name
    os.replace(temp_name, DB_PATH)
    return safety_path
