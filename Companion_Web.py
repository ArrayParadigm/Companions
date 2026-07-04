import cgi
import argparse
import base64
import binascii
import copy
import json
import mimetypes
import os
import re
import shutil
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from Memory_Manager import (
    CATEGORIES,
    COMPANION_FILES,
    HANDOFF_TEMPLATE,
    add_memory,
    apply_command_line,
    create_companion,
    encode_payload,
    load_payload,
    packet_summary,
    reload_companion_files,
    save_payload,
)


APP_DIR = Path(__file__).resolve().parent
PROJECT_PARENT = APP_DIR.parent
DATA_DIR = APP_DIR / "control_data"
PROOF_DIR = APP_DIR / "proof_vault"
DIRECTIVES_FILE = DATA_DIR / "directives.json"
PROOF_FILE = DATA_DIR / "proof_metadata.json"
CHECKINS_FILE = DATA_DIR / "daily_checkins.json"


def first_existing_path(*paths):
    for path in paths:
        if path.exists():
            return path
    return paths[0]


TRACKER_FILES = {
    "journal": first_existing_path(
        APP_DIR / "tracker_data" / "journal.json",
        APP_DIR / "Emotiona Journal" / "emotional_journal.json",
        PROJECT_PARENT / "Emotiona Journal" / "emotional_journal.json",
    ),
    "tasks": first_existing_path(
        APP_DIR / "tracker_data" / "tasks.json",
        APP_DIR / "Productivity Tracker" / "task_log.json",
        PROJECT_PARENT / "Productivity Tracker" / "task_log.json",
    ),
    "physical": first_existing_path(
        APP_DIR / "tracker_data" / "physical.json",
        APP_DIR / "physical tracker" / "workout_stretch_tracker.json",
        PROJECT_PARENT / "physical tracker" / "workout_stretch_tracker.json",
    ),
}

READING_PLANS = {
    "Daily Rhythm": [
        {"id": "psalm-119-1-8", "label": "Psalm 119:1-8"},
        {"id": "psalm-119-9-16", "label": "Psalm 119:9-16"},
        {"id": "proverbs-1", "label": "Proverbs 1"},
        {"id": "john-1", "label": "John 1"},
    ],
    "Gospels": [
        {"id": "matthew-5", "label": "Matthew 5"},
        {"id": "mark-1", "label": "Mark 1"},
        {"id": "luke-15", "label": "Luke 15"},
        {"id": "john-3", "label": "John 3"},
    ],
    "Epistles": [
        {"id": "philippians-1", "label": "Philippians 1"},
        {"id": "philippians-2", "label": "Philippians 2"},
        {"id": "philippians-3", "label": "Philippians 3"},
        {"id": "philippians-4", "label": "Philippians 4"},
    ],
    "Minor Prophets": [
        {"id": "hosea-6", "label": "Hosea 6"},
        {"id": "joel-2", "label": "Joel 2"},
        {"id": "micah-6", "label": "Micah 6"},
        {"id": "malachi-3", "label": "Malachi 3"},
    ],
}


def now_stamp():
    return datetime.now().replace(microsecond=0).isoformat()


def ensure_data_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    if not DIRECTIVES_FILE.exists():
        write_json(DIRECTIVES_FILE, {"next_directive_number": 1, "directives": []})
    if not PROOF_FILE.exists():
        write_json(PROOF_FILE, {"next_proof_number": 1, "proof": []})
    if not CHECKINS_FILE.exists():
        write_json(CHECKINS_FILE, {"next_checkin_number": 1, "entries": []})


def read_json(path, fallback):
    if not path.exists():
        return copy.deepcopy(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return copy.deepcopy(fallback)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def refresh_companion_registry():
    global COMPANION_FILES
    COMPANION_FILES = reload_companion_files()
    return COMPANION_FILES


def create_companion_record(data):
    name = data.get("name", "").strip()
    filename = data.get("filename", "").strip() or None
    companion, path = create_companion(name, filename)
    refresh_companion_registry()
    return {"name": companion, "file": path.name}


def directive_store():
    ensure_data_files()
    return read_json(DIRECTIVES_FILE, {"next_directive_number": 1, "directives": []})


def proof_store():
    ensure_data_files()
    return read_json(PROOF_FILE, {"next_proof_number": 1, "proof": []})


def checkin_store():
    ensure_data_files()
    return read_json(CHECKINS_FILE, {"next_checkin_number": 1, "entries": []})


def next_id(store, counter_name, prefix):
    number = int(store.get(counter_name, 1))
    store[counter_name] = number + 1
    return f"{prefix}-{number:04d}"


def clean_int(value, default=0, minimum=None, maximum=None):
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def clean_float(value, default=0.0, minimum=None, maximum=None):
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def clean_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on", "checked")


def clean_string_list(value):
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = []
    return [str(item).strip() for item in raw_items if str(item).strip()]


def reading_plan_sections(plan_name):
    return READING_PLANS.get(str(plan_name or "").strip(), [])


def reading_section_label(plan_name, section_id):
    for section in reading_plan_sections(plan_name):
        if section["id"] == section_id:
            return section["label"]
    return str(section_id or "").strip()


def reading_progress(checkins):
    progress = {}
    for plan_name, sections in READING_PLANS.items():
        completed_ids = set()
        for item in checkins:
            spirit = item.get("spirit", {})
            if spirit.get("reading_plan") != plan_name:
                continue
            completed_ids.update(spirit.get("reading_checklist", []))
        progress[plan_name] = {
            "completed": len(completed_ids),
            "completed_ids": sorted(completed_ids),
            "total": len(sections),
            "remaining": max(0, len(sections) - len(completed_ids)),
        }
    return progress


def create_checkin(data):
    store = checkin_store()
    checkin_id = next_id(store, "next_checkin_number", "CHK")
    reading_plan = data.get("reading_plan", "").strip()
    reading_section = data.get("reading_section", "").strip()
    reading_checklist = clean_string_list(data.get("reading_checklist"))
    selected_section_label = reading_section_label(reading_plan, reading_section)
    assigned_reading = data.get("assigned_reading", "").strip()
    if not assigned_reading and selected_section_label:
        assigned_reading = selected_section_label
    entry = {
        "id": checkin_id,
        "date": data.get("date", "").strip() or datetime.now().strftime("%Y-%m-%d"),
        "created_at": now_stamp(),
        "body": {
            "energy": clean_int(data.get("energy"), default=5, minimum=1, maximum=10),
            "sleep_hours": clean_float(data.get("sleep_hours"), default=0, minimum=0, maximum=24),
            "food_on_plan": clean_bool(data.get("food_on_plan")),
            "exercise_minutes": clean_int(data.get("exercise_minutes"), default=0, minimum=0),
            "exercise_type": data.get("exercise_type", "").strip(),
            "weight": data.get("weight", "").strip(),
        },
        "mind": {
            "mood": clean_int(data.get("mood"), default=5, minimum=1, maximum=10),
            "note": data.get("note", "").strip(),
        },
        "spirit": {
            "prayer": clean_bool(data.get("prayer")),
            "scripture": clean_bool(data.get("scripture")),
            "reading_plan": reading_plan,
            "reading_section": reading_section,
            "reading_checklist": reading_checklist,
            "assigned_reading": assigned_reading,
            "reading_completed": clean_bool(data.get("reading_completed")),
            "reading_minutes": clean_int(data.get("reading_minutes"), default=0, minimum=0),
            "reading_status": data.get("reading_status", "").strip(),
            "favorite_verse": data.get("favorite_verse", "").strip(),
            "application": data.get("application", "").strip(),
            "prayer_response": data.get("prayer_response", "").strip(),
            "gratitude": data.get("gratitude", "").strip(),
            "repentance": data.get("repentance", "").strip(),
            "service": data.get("service", "").strip(),
            "felt_close": data.get("felt_close", "").strip(),
        },
        "work": {
            "category": data.get("work_category", "").strip(),
            "task_name": data.get("work_task", "").strip(),
            "minutes": clean_int(data.get("work_minutes"), default=0, minimum=0),
            "difficulty": data.get("work_difficulty", "").strip(),
            "result": data.get("work_result", "").strip(),
            "next_step": data.get("next_step", "").strip(),
            "recurring": clean_bool(data.get("work_recurring")),
            "money_spent": clean_float(data.get("money_spent"), default=0, minimum=0),
        },
        "relationships": {
            "note": data.get("relationship_note", "").strip(),
        },
    }
    store["entries"].append(entry)
    write_json(CHECKINS_FILE, store)
    return entry


def companion_name_for_issuer(issuer):
    normalized = str(issuer or "").strip().lower()
    for companion in COMPANION_FILES:
        if companion.lower() == normalized:
            return companion
    return None


def directive_memory_content(directive):
    parts = [
        f"Issued directive {directive['id']}: {directive['title']}.",
        f"Priority {directive.get('priority', '3')}.",
    ]
    if directive.get("due_at"):
        parts.append(f"Due {directive['due_at']}.")
    if directive.get("proof_required"):
        parts.append("Proof required.")
    if directive.get("details"):
        parts.append(f"Details: {directive['details']}")
    return " ".join(parts)


def remember_directive_in_payload(payload, directive):
    priority = parse_priority(str(directive.get("priority", "3")))
    return add_memory(
        payload,
        "history",
        directive_memory_content(directive),
        priority,
        ["directive-ledger", "issued-directive", directive["id"].lower()],
    )


def remember_directive_for_issuer(directive):
    companion = companion_name_for_issuer(directive.get("issuer"))
    if not companion:
        return None

    payload = load_payload(companion)
    memory_id = remember_directive_in_payload(payload, directive)
    save_payload(companion, payload)
    return memory_id


def create_directive(data, remember_issuer=True):
    store = directive_store()
    directive_id = next_id(store, "next_directive_number", "DIR")
    directive = {
        "id": directive_id,
        "issuer": data.get("issuer", "Veyra"),
        "title": data.get("title", "").strip(),
        "details": data.get("details", "").strip(),
        "status": data.get("status", "issued"),
        "priority": data.get("priority", "3"),
        "due_at": data.get("due_at", "").strip(),
        "proof_required": bool(data.get("proof_required", False)),
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
    }
    if not directive["title"]:
        raise ValueError("Directive title is required.")
    store["directives"].append(directive)
    write_json(DIRECTIVES_FILE, store)
    if remember_issuer:
        remember_directive_for_issuer(directive)
    return directive


def parse_bool_text(value):
    normalized = value.strip().lower()
    if normalized in ("1", "true", "yes", "y", "required", "needed", "on"):
        return True
    if normalized in ("0", "false", "no", "n", "not required", "none", "off"):
        return False
    return None


def parse_priority(value):
    text = value.strip().lower()
    explicit = re.search(r"\b([1-5])\b", text)
    if explicit:
        return int(explicit.group(1))

    if any(word in text for word in ("critical", "urgent", "highest", "blocker")):
        return 5
    if any(word in text for word in ("high", "important")):
        return 4
    if any(word in text for word in ("medium", "normal")):
        return 3
    if any(word in text for word in ("low", "minor", "whenever")):
        return 2
    return 3


def clean_directive_title(text):
    cleaned = re.sub(r"^\s*(directive|task|todo|action|request)\s*[:#-]\s*", "", text.strip(), flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= 90:
        return cleaned
    sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    return sentence[:90].rstrip(" ,.;:-")


def parse_directive_text(data):
    raw_text = data.get("text", "")
    text = raw_text.strip()
    if not text:
        raise ValueError("Directive text is empty.")

    parsed = {
        "issuer": data.get("issuer") or "Veyra",
        "title": "",
        "details": text,
        "priority": 3,
        "due_at": "",
        "proof_required": False,
    }

    detail_lines = []
    for line in text.splitlines():
        stripped = line.strip(" \t-•")
        if not stripped:
            continue

        key_match = re.match(r"^(issuer|from|title|directive|task|details?|description|priority|due|deadline|proof|proof_required|evidence)\s*[:=-]\s*(.+)$", stripped, flags=re.I)
        if not key_match:
            detail_lines.append(stripped)
            continue

        key = key_match.group(1).lower()
        value = key_match.group(2).strip()
        if key in ("issuer", "from"):
            parsed["issuer"] = value
        elif key in ("title", "directive", "task"):
            parsed["title"] = clean_directive_title(value)
        elif key in ("details", "detail", "description"):
            detail_lines.append(value)
        elif key == "priority":
            parsed["priority"] = parse_priority(value)
        elif key in ("due", "deadline"):
            parsed["due_at"] = value
        elif key in ("proof", "proof_required", "evidence"):
            bool_value = parse_bool_text(value)
            parsed["proof_required"] = bool_value if bool_value is not None else True

    lower_text = text.lower()
    if re.search(r"\b(proof|evidence|screenshot|receipt|verify|verification)\b", lower_text):
        parsed["proof_required"] = True
    priority_match = re.search(r"\bpriority\s*[:=-]\s*([^\n.;]+)", text, flags=re.I)
    if priority_match:
        parsed["priority"] = parse_priority(priority_match.group(1))
    due_match = re.search(r"\b(?:due|deadline)\s*[:=-]\s*([^\n]+)", text, flags=re.I)
    if due_match:
        parsed["due_at"] = due_match.group(1).strip()
    elif not parsed["due_at"]:
        by_match = re.search(r"\b(?:by|before)\s+(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?", text, flags=re.I)
        if by_match:
            parsed["due_at"] = by_match.group(1) + (f"T{by_match.group(2)}" if by_match.group(2) else "")

    if not parsed["title"]:
        candidate_lines = [line for line in detail_lines if line]
        parsed["title"] = clean_directive_title(candidate_lines[0] if candidate_lines else text)

    if detail_lines:
        parsed["details"] = "\n".join(detail_lines)

    return parsed


def update_directive(directive_id, data):
    store = directive_store()
    for directive in store.get("directives", []):
        if directive["id"].lower() == directive_id.lower():
            for key in ("status", "title", "details", "priority", "due_at", "proof_required"):
                if key in data:
                    directive[key] = data[key]
            directive["updated_at"] = now_stamp()
            write_json(DIRECTIVES_FILE, store)
            return directive
    raise ValueError(f"Directive not found: {directive_id}")


def create_text_proof(data):
    store = proof_store()
    proof_id = next_id(store, "next_proof_number", "PRF")
    directive_id = data.get("directive_id", "").strip()
    proof = {
        "id": proof_id,
        "directive_id": directive_id,
        "type": data.get("type", "note"),
        "note": data.get("note", "").strip(),
        "path": "",
        "submitted_at": now_stamp(),
        "status": "submitted",
    }
    store["proof"].append(proof)
    write_json(PROOF_FILE, store)
    return proof


def create_file_proof(form):
    store = proof_store()
    proof_id = next_id(store, "next_proof_number", "PRF")
    directive_id = field_value(form, "directive_id") or "unassigned"
    note = field_value(form, "note")
    proof_type = field_value(form, "type") or "file"
    item = form["file"] if "file" in form else None

    if item is None or not getattr(item, "filename", ""):
        raise ValueError("Proof upload requires a file.")

    safe_directive = safe_name(directive_id)
    original_name = safe_name(Path(item.filename).name)
    target_dir = PROOF_DIR / safe_directive
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{proof_id}-{original_name}"

    with target_path.open("wb") as out_file:
        shutil.copyfileobj(item.file, out_file)

    proof = {
        "id": proof_id,
        "directive_id": directive_id,
        "type": proof_type,
        "note": note,
        "path": str(target_path.relative_to(APP_DIR)),
        "submitted_at": now_stamp(),
        "status": "submitted",
    }
    store["proof"].append(proof)
    write_json(PROOF_FILE, store)
    return proof


def proof_by_id(proof_id):
    for proof in proof_store().get("proof", []):
        if proof.get("id", "").lower() == proof_id.lower():
            return proof
    raise ValueError(f"Proof not found: {proof_id}")


def field_value(form, name):
    if name not in form:
        return ""
    value = form[name]
    if isinstance(value, list):
        value = value[0]
    return value.value.strip() if hasattr(value, "value") else str(value).strip()


def safe_name(name):
    keep = []
    for char in name:
        if char.isalnum() or char in ("-", "_", "."):
            keep.append(char)
        else:
            keep.append("_")
    cleaned = "".join(keep).strip("._")
    return cleaned or "item"


def companion_index(companion):
    payload = load_payload(companion)
    entries = []
    for entry in payload.get("memories", []):
        entries.append(
            {
                "id": entry.get("id"),
                "category": entry.get("category"),
                "status": entry.get("status"),
                "weight": entry.get("weight"),
                "tags": entry.get("tags", []),
                "created_at": entry.get("created_at"),
                "updated_at": entry.get("updated_at"),
            }
        )
    for entry in payload.get("archive", []):
        entries.append(
            {
                "id": entry.get("id"),
                "category": entry.get("category"),
                "status": entry.get("status", "archived"),
                "weight": entry.get("weight"),
                "tags": entry.get("tags", []),
                "created_at": entry.get("created_at"),
                "updated_at": entry.get("updated_at"),
                "archived_at": entry.get("archived_at"),
            }
        )
    return entries


def looks_like_command_batch(command_text):
    command_prefixes = (
        "add ",
        "update ",
        "edit ",
        "archive ",
        "unarchive ",
        "resave ",
        "delete ",
        "directive ",
        "task ",
    )
    for line in command_text.splitlines():
        stripped = line.strip().lower()
        if stripped and (stripped.startswith(command_prefixes) or " - " in stripped):
            return True
    return False


def decode_command_batch_if_needed(command_text):
    cleaned = command_text.strip()
    if not cleaned or looks_like_command_batch(cleaned):
        return cleaned

    compact = "".join(cleaned.split())
    try:
        padded = compact + ("=" * (-len(compact) % 4))
        decoded = base64.b64decode(padded, validate=True).decode("utf-8").strip()
    except (binascii.Error, UnicodeDecodeError):
        return cleaned

    return decoded if looks_like_command_batch(decoded) else cleaned


def parse_command_metadata(text):
    parts = [part.strip() for part in text.split("|")]
    main = parts[0].strip()
    metadata = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        metadata[key.strip().lower()] = value.strip()
    return main, metadata


def is_directive_command(line):
    lower = line.strip().lower()
    return lower.startswith(("directive ", "directive:", "task ", "task:"))


def parse_directive_command(line, issuer):
    stripped = line.strip()
    match = re.match(r"^(directive|task)\s*(?::|-)\s*(.+)$", stripped, flags=re.I)
    if match:
        body = match.group(2).strip()
    else:
        body = re.sub(r"^(directive|task)\s+", "", stripped, flags=re.I).strip()

    main, metadata = parse_command_metadata(body)
    details = metadata.get("details") or metadata.get("detail") or metadata.get("description") or main
    proof_value = metadata.get("proof") or metadata.get("proof_required") or metadata.get("evidence") or ""
    parsed_proof = parse_bool_text(proof_value) if proof_value else None

    return {
        "issuer": metadata.get("issuer") or metadata.get("from") or issuer,
        "title": clean_directive_title(metadata.get("title") or main),
        "details": details,
        "priority": parse_priority(metadata.get("priority", "3")),
        "due_at": metadata.get("due") or metadata.get("deadline") or "",
        "proof_required": parsed_proof if parsed_proof is not None else False,
    }


def apply_commands(companion, command_text):
    payload = load_payload(companion)
    trial_payload = copy.deepcopy(payload)
    command_text = decode_command_batch_if_needed(command_text)
    lines = [line.strip() for line in command_text.splitlines() if line.strip()]
    applied = []
    directives = []
    memory_changed = False
    for line in lines:
        if is_directive_command(line):
            directive_data = parse_directive_command(line, companion)
            directive_issuer = companion_name_for_issuer(directive_data.get("issuer"))
            if directive_issuer == companion:
                directive = create_directive(directive_data, remember_issuer=False)
                remember_directive_in_payload(trial_payload, directive)
                memory_changed = True
            else:
                directive = create_directive(directive_data)
            directives.append(directive)
            applied.append(directive["id"])
            continue

        applied_id = apply_command_line(trial_payload, line)
        memory_changed = True
        if applied_id:
            applied.append(applied_id)

    backup_path = save_payload(companion, trial_payload) if memory_changed else None
    return {
        "applied": applied,
        "directives": directives,
        "backup": backup_path.name if backup_path else None,
        "summary": packet_summary(companion, trial_payload),
    }


def tracker_data():
    journal = read_json(TRACKER_FILES["journal"], [])
    tasks = read_json(TRACKER_FILES["tasks"], [])
    physical = read_json(TRACKER_FILES["physical"], [])
    checkins = checkin_store().get("entries", [])
    task_categories = {}
    for item in tasks:
        category = str(item.get("task_type") or item.get("category") or "Unsorted").strip() or "Unsorted"
        task_categories[category] = task_categories.get(category, 0) + 1
    work_categories = {}
    for item in checkins:
        category = str(item.get("work", {}).get("category") or "Unsorted").strip() or "Unsorted"
        work_categories[category] = work_categories.get(category, 0) + 1
    latest_checkin = checkins[-1] if checkins else None
    return {
        "journal": journal[-20:],
        "tasks": tasks[-20:],
        "physical": physical[-20:],
        "checkins": checkins[-20:],
        "latest_checkin": latest_checkin,
        "task_categories": task_categories,
        "work_categories": work_categories,
        "reading_progress": reading_progress(checkins),
        "summary": {
            "journal_entries": len(journal),
            "task_entries": len(tasks),
            "physical_entries": len(physical),
            "checkin_entries": len(checkins),
        },
    }


def directive_summary(directives):
    summary = {"issued": 0, "complete": 0, "failed": 0, "other": 0, "proof_required": 0}
    for directive in directives:
        status = str(directive.get("status", "issued")).lower()
        if status in summary:
            summary[status] += 1
        else:
            summary["other"] += 1
        if directive.get("proof_required"):
            summary["proof_required"] += 1
    return summary


def app_state():
    companions = []
    for companion in COMPANION_FILES:
        item = {
            "name": companion,
            "file": COMPANION_FILES[companion].name,
            "summary": "",
            "index": [],
            "error": None,
        }
        try:
            payload = load_payload(companion)
            item["summary"] = packet_summary(companion, payload)
            item["index"] = companion_index(companion)
        except Exception as exc:
            item["summary"] = f"Unable to load {COMPANION_FILES[companion].name}."
            item["error"] = str(exc)
        companions.append(item)

    directives = directive_store().get("directives", [])
    trackers = tracker_data()
    return {
        "companions": companions,
        "categories": list(CATEGORIES.keys()),
        "directives": directives,
        "directive_summary": directive_summary(directives),
        "proof": proof_store().get("proof", []),
        "trackers": trackers,
        "reading_plans": READING_PLANS,
    }


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Companion Control Console</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #101316;
      --panel: #181d22;
      --panel-2: #20262d;
      --text: #edf2f7;
      --muted: #9da8b5;
      --line: #303842;
      --accent: #62d6b2;
      --warn: #e9b949;
      --danger: #ec6b6b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Segoe UI, system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: #0d1013;
    }
    h1 { font-size: 18px; margin: 0; font-weight: 650; }
    main {
      display: grid;
      grid-template-columns: 240px minmax(0, 1fr);
      min-height: calc(100vh - 53px);
    }
    nav {
      border-right: 1px solid var(--line);
      padding: 12px;
      background: #12161a;
    }
    nav button, .action {
      width: 100%;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      padding: 9px 10px;
      border-radius: 6px;
      text-align: left;
      margin-bottom: 8px;
      cursor: pointer;
      font-size: 14px;
    }
    nav button.active, .action.primary {
      border-color: var(--accent);
      background: #16332c;
    }
    section { padding: 16px; display: none; }
    section.active { display: block; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
    .dashboard-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }
    .full { grid-column: 1 / -1; }
    .span-2 { grid-column: span 2; }
    h2 { margin: 0 0 10px; font-size: 16px; }
    h3 { margin: 0 0 8px; font-size: 14px; color: var(--muted); }
    label { display: block; color: var(--muted); font-size: 12px; margin: 8px 0 4px; }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #0f1317;
      color: var(--text);
      padding: 8px;
      font: inherit;
    }
    textarea { min-height: 110px; resize: vertical; }
    .packet { min-height: 230px; font-family: Consolas, monospace; font-size: 12px; }
    .row { display: flex; gap: 8px; align-items: center; }
    .row > * { flex: 1; }
    button.inline, a.inline {
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text);
      border-radius: 6px;
      padding: 8px 10px;
      cursor: pointer;
      width: auto;
      display: inline-block;
      text-decoration: none;
    }
    button.inline.primary, a.inline.primary { border-color: var(--accent); color: var(--accent); }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      text-align: left;
      padding: 7px 6px;
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; }
    .muted { color: var(--muted); }
    .status { color: var(--accent); font-size: 13px; }
    .pill {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 999px;
      background: var(--panel-2);
      color: var(--muted);
      font-size: 12px;
      margin: 2px 4px 2px 0;
    }
    .metric {
      font-size: 24px;
      line-height: 1.1;
      font-weight: 650;
      margin: 4px 0;
    }
    .scrollbox {
      max-height: 360px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
    }
    .scrollbox table { margin: 0; }
    .scrollbox p { padding: 10px; margin: 0; }
    .tab-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }
    .tab-row button {
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text);
      border-radius: 6px;
      padding: 7px 9px;
      cursor: pointer;
    }
    .tab-row button.active { border-color: var(--accent); color: var(--accent); }
    .tracker-view { display: none; }
    .tracker-view.active { display: block; }
    .directive-title { display: block; margin-bottom: 5px; }
    .directive-detail {
      white-space: pre-wrap;
      color: var(--text);
      background: #10151a;
      border-left: 3px solid var(--accent);
      padding: 7px 8px;
      border-radius: 4px;
      min-width: 220px;
    }
    .reading-checklist {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px 12px;
      margin: 8px 0;
    }
    .reading-checklist label {
      margin: 0;
      color: var(--text);
      background: #10151a;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 8px;
    }
    .status-complete { color: var(--accent); }
    .status-failed { color: var(--danger); }
    .status-issued { color: var(--warn); }
    .field-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; }
      nav { border-right: 0; border-bottom: 1px solid var(--line); }
      .grid, .dashboard-grid, .field-grid, .reading-checklist { grid-template-columns: 1fr; }
      .span-2 { grid-column: auto; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Companion Control Console</h1>
    <div class="status" id="status">Loading...</div>
  </header>
  <main>
    <nav>
      <button data-tab="dashboard" class="active">Dashboard</button>
      <button data-tab="memory">Companion Memory</button>
      <button data-tab="directives">Directive Ledger</button>
      <button data-tab="proof">Proof Vault</button>
      <button data-tab="trackers">Tracker Imports</button>
      <button data-tab="council">Council Mode</button>
    </nav>
    <section id="dashboard" class="active">
      <div class="dashboard-grid">
        <div class="panel">
          <h2>Memory Manager</h2>
          <div class="metric" id="dashCompanions">0</div>
          <div class="muted" id="dashMemory">No packets loaded.</div>
        </div>
        <div class="panel">
          <h2>Directives</h2>
          <div class="metric" id="dashDirectives">0</div>
          <div class="muted" id="dashDirectiveDetail"></div>
        </div>
        <div class="panel">
          <h2>Spiritual</h2>
          <div class="metric" id="dashSpirit">--</div>
          <div class="muted" id="dashSpiritDetail"></div>
        </div>
        <div class="panel">
          <h2>Physical</h2>
          <div class="metric" id="dashPhysical">0</div>
          <div class="muted" id="dashPhysicalDetail"></div>
        </div>
        <div class="panel span-2">
          <h2>Work Categories</h2>
          <div id="dashWorkCloud"></div>
        </div>
        <div class="panel span-2">
          <h2>Latest Daily Check-In</h2>
          <div id="dashLatestCheckin"></div>
        </div>
      </div>
    </section>
    <section id="memory">
      <div class="grid">
        <div class="panel">
          <h2>Packet Handoff</h2>
          <label>Companion</label>
          <select id="companionSelect"></select>
          <div class="row" style="margin-top: 10px;">
            <button class="inline primary" onclick="copyPacket()">Copy Packet</button>
            <button class="inline primary" onclick="copyHandoff()">Copy Handoff</button>
          </div>
          <label>Encoded packet</label>
          <textarea id="packetBox" class="packet" readonly></textarea>
        </div>
        <div class="panel">
          <h2>Add / Apply</h2>
          <div class="row">
            <div>
              <label>Category</label>
              <select id="categorySelect"></select>
            </div>
            <div>
              <label>Weight</label>
              <input id="memoryWeight" type="number" min="1" max="5" value="3">
            </div>
          </div>
          <label>Tags</label>
          <input id="memoryTags" placeholder="tag1,tag2">
          <label>One memory</label>
          <textarea id="memoryContent"></textarea>
          <button class="inline primary" onclick="addMemory()">Add Memory</button>
          <label>Command batch</label>
          <textarea id="commandBatch" placeholder="add projects - durable memory | weight=4 | tags=project&#10;edit NYX-0002 -> corrected memory text&#10;unarchive NYX-0007&#10;resave NYX-0008&#10;directive - Verify live console | priority=4 | due=2026-07-04 10:00 | proof=true | details=Confirm all companions load.&#10;or paste a base64-encoded command batch"></textarea>
          <button class="inline primary" onclick="applyCommands()">Apply Commands</button>
        </div>
        <div class="panel full">
          <h2>New Companion</h2>
          <div class="row">
            <div>
              <label>Name</label>
              <input id="newCompanionName">
            </div>
            <div>
              <label>Filename</label>
              <input id="newCompanionFile" placeholder="optional-name-memories.md">
            </div>
          </div>
          <button class="inline primary" onclick="createCompanion()">Create Companion</button>
        </div>
        <div class="panel full">
          <h2>ID-Only Memory Index</h2>
          <div id="memoryIndex"></div>
        </div>
      </div>
    </section>
    <section id="directives">
      <div class="grid">
        <div class="panel">
          <h2>Parse Directive</h2>
          <label>Directive text</label>
          <textarea id="directiveParseText"></textarea>
          <button class="inline primary" onclick="parseDirective()">Parse Directive</button>
        </div>
        <div class="panel">
          <h2>New Directive</h2>
          <label>Issuer</label>
          <select id="directiveIssuer"></select>
          <label>Title</label>
          <input id="directiveTitle">
          <label>Details</label>
          <textarea id="directiveDetails"></textarea>
          <div class="row">
            <div>
              <label>Priority</label>
              <input id="directivePriority" type="number" min="1" max="5" value="3">
            </div>
            <div>
              <label>Due</label>
              <input id="directiveDue" type="datetime-local">
            </div>
          </div>
          <label><input id="directiveProofRequired" type="checkbox" style="width:auto;"> Proof required</label>
          <button class="inline primary" onclick="createDirective()">Create Directive</button>
        </div>
        <div class="panel full">
          <h2>Ledger</h2>
          <div class="tab-row" id="directiveTabs">
            <button class="active" data-status="issued">Issued</button>
            <button data-status="complete">Completed</button>
            <button data-status="failed">Failed</button>
            <button data-status="all">All</button>
          </div>
          <div id="directiveList"></div>
        </div>
      </div>
    </section>
    <section id="proof">
      <div class="grid">
        <div class="panel">
          <h2>Submit Proof</h2>
          <form id="proofForm">
            <label>Directive</label>
            <select name="directive_id" id="proofDirective"></select>
            <label>Type</label>
            <input name="type" value="file">
            <label>Note</label>
            <textarea name="note"></textarea>
            <label>File</label>
            <input type="file" name="file">
            <button class="inline primary" type="submit">Upload Proof</button>
          </form>
        </div>
        <div class="panel">
          <h2>Proof Metadata</h2>
          <div id="proofList"></div>
        </div>
      </div>
    </section>
    <section id="trackers">
      <div class="grid">
        <div class="panel full">
          <h2>Imported Tracker Counts</h2>
          <div id="trackerSummary"></div>
        </div>
        <div class="panel full">
          <div class="tab-row" id="trackerTabs">
            <button class="active" data-tracker="checkins">Daily Check-Ins</button>
            <button data-tracker="journal">Journal</button>
            <button data-tracker="tasks">Tasks</button>
            <button data-tracker="physical">Physical</button>
          </div>
          <div class="tracker-view active" data-tracker-view="checkins">
            <h2>Daily Check-In</h2>
            <div class="field-grid">
              <div>
                <label>Date</label>
                <input id="checkinDate" type="date">
              </div>
              <div>
                <label>Mood</label>
                <input id="checkinMood" type="number" min="1" max="10" value="5">
              </div>
              <div>
                <label>Energy</label>
                <input id="checkinEnergy" type="number" min="1" max="10" value="5">
              </div>
              <div>
                <label>Sleep hours</label>
                <input id="checkinSleep" type="number" min="0" max="24" step="0.25">
              </div>
              <div>
                <label>Exercise minutes</label>
                <input id="checkinExerciseMinutes" type="number" min="0" value="0">
              </div>
              <div>
                <label>Exercise type</label>
                <input id="checkinExerciseType">
              </div>
              <div>
                <label>Weight</label>
                <input id="checkinWeight">
              </div>
              <div>
                <label>Work category</label>
                <select id="checkinWorkCategory">
                  <option>Companion Console</option>
                  <option>AscendedWorlds</option>
                  <option>Writing</option>
                  <option>Job</option>
                  <option>Household Chores</option>
                  <option>Maintenance</option>
                  <option>Spiritual Practice</option>
                  <option>Other</option>
                </select>
              </div>
              <div>
                <label>Work minutes</label>
                <input id="checkinWorkMinutes" type="number" min="0" value="0">
              </div>
              <div>
                <label>Reading plan</label>
                <select id="checkinReadingPlan"></select>
              </div>
              <div>
                <label>Current reading</label>
                <select id="checkinReadingSection"></select>
              </div>
              <div>
                <label>Reading status</label>
                <select id="checkinReadingStatus">
                  <option value=""></option>
                  <option>read fully</option>
                  <option>skimmed</option>
                  <option>missed</option>
                </select>
              </div>
              <div>
                <label>Reading minutes</label>
                <input id="checkinReadingMinutes" type="number" min="0" value="0">
              </div>
              <div>
                <label>Difficulty</label>
                <input id="checkinWorkDifficulty">
              </div>
              <div>
                <label>Money spent</label>
                <input id="checkinMoneySpent" type="number" min="0" step="0.01" value="0">
              </div>
            </div>
            <label>Completed readings</label>
            <div id="readingChecklist" class="reading-checklist"></div>
            <div id="readingProgress" class="muted"></div>
            <div class="row">
              <label><input id="checkinFood" type="checkbox" style="width:auto;"> Food on plan</label>
              <label><input id="checkinPrayer" type="checkbox" style="width:auto;"> Prayer</label>
              <label><input id="checkinScripture" type="checkbox" style="width:auto;"> Scripture</label>
              <label><input id="checkinReadingCompleted" type="checkbox" style="width:auto;"> Reading done</label>
              <label><input id="checkinWorkRecurring" type="checkbox" style="width:auto;"> Recurring</label>
            </div>
            <label>Assigned reading</label>
            <input id="checkinAssignedReading">
            <label>Work task</label>
            <input id="checkinWorkTask">
            <label>Result</label>
            <input id="checkinWorkResult">
            <label>Next step</label>
            <input id="checkinNextStep">
            <label>Favorite verse</label>
            <input id="checkinFavoriteVerse">
            <label>Application</label>
            <input id="checkinApplication">
            <label>Prayer response</label>
            <input id="checkinPrayerResponse">
            <label>Gratitude</label>
            <input id="checkinGratitude">
            <label>Repentance / forgiveness</label>
            <input id="checkinRepentance">
            <label>Service</label>
            <input id="checkinService">
            <label>Felt close / far from God</label>
            <input id="checkinFeltClose">
            <label>Note</label>
            <textarea id="checkinNote"></textarea>
            <button class="inline primary" onclick="saveCheckin()">Save Check-In</button>
            <h2 style="margin-top:14px;">Daily Check-Ins</h2>
            <div id="checkinList"></div>
          </div>
          <div class="tracker-view" data-tracker-view="journal">
            <h2>Journal</h2>
            <div id="journalList"></div>
          </div>
          <div class="tracker-view" data-tracker-view="tasks">
            <h2>Tasks</h2>
            <div id="taskList"></div>
          </div>
          <div class="tracker-view" data-tracker-view="physical">
            <h2>Physical</h2>
            <div id="physicalList"></div>
          </div>
        </div>
      </div>
    </section>
    <section id="council">
      <div class="panel">
        <h2>Council Mode</h2>
        <p class="muted">Use this as the collection point: copy handoffs for each companion, ask the same question, then paste each companion's command batch back into the Memory tab for that companion. This preserves separate private stances.</p>
        <div id="councilCompanions"></div>
      </div>
    </section>
  </main>
  <script>
    let state = null;
    let selectedCompanion = null;
    let selectedDirectiveStatus = 'issued';
    let selectedTrackerTab = 'checkins';

    document.querySelectorAll('nav button').forEach(button => {
      button.addEventListener('click', () => {
        document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('section').forEach(s => s.classList.remove('active'));
        button.classList.add('active');
        document.getElementById(button.dataset.tab).classList.add('active');
      });
    });

    document.querySelectorAll('#directiveTabs button').forEach(button => {
      button.addEventListener('click', () => {
        selectedDirectiveStatus = button.dataset.status;
        document.querySelectorAll('#directiveTabs button').forEach(b => b.classList.remove('active'));
        button.classList.add('active');
        renderDirectives();
      });
    });

    document.querySelectorAll('#trackerTabs button').forEach(button => {
      button.addEventListener('click', () => {
        selectedTrackerTab = button.dataset.tracker;
        renderTrackerTabs();
      });
    });

    document.getElementById('companionSelect').addEventListener('change', async event => {
      selectedCompanion = event.target.value;
      await loadPacket();
      renderMemoryIndex();
    });

    document.getElementById('checkinReadingPlan').addEventListener('change', () => {
      renderReadingSections();
      renderReadingChecklist();
    });

    document.getElementById('checkinReadingSection').addEventListener('change', event => {
      const selected = event.target.options[event.target.selectedIndex];
      if (selected && !document.getElementById('checkinAssignedReading').value.trim()) {
        document.getElementById('checkinAssignedReading').value = selected.textContent;
      }
    });

    document.getElementById('checkinDate').value = new Date().toISOString().slice(0, 10);

    document.getElementById('proofForm').addEventListener('submit', async event => {
      event.preventDefault();
      const form = new FormData(event.target);
      const res = await fetch('/api/proof/upload', { method: 'POST', body: form });
      await handleResponse(res);
      event.target.reset();
      await loadState();
    });

    async function loadState() {
      const res = await fetch('/api/state');
      state = await handleResponse(res, false);
      if (!state.companions.length) {
        setStatus('No companions configured.');
        return;
      }
      selectedCompanion = selectedCompanion || state.companions[0].name;
      renderSelectors();
      renderDashboard();
      renderDirectives();
      renderProof();
      renderTrackers();
      renderCouncil();
      await loadPacket();
      renderMemoryIndex();
      setStatus('Ready.');
    }

    function renderSelectors() {
      const companionOptions = state.companions.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)}</option>`).join('');
      for (const id of ['companionSelect', 'directiveIssuer']) {
        const select = document.getElementById(id);
        select.innerHTML = companionOptions;
        select.value = selectedCompanion;
      }
      document.getElementById('categorySelect').innerHTML = state.categories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
      document.getElementById('proofDirective').innerHTML = state.directives.map(d => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.id)} - ${escapeHtml(d.title)}</option>`).join('');
    }

    async function loadPacket() {
      const res = await fetch(`/api/companion/${encodeURIComponent(selectedCompanion)}/packet`);
      const data = await handleResponse(res, false);
      document.getElementById('packetBox').value = data.packet;
    }

    function currentCompanion() {
      return state.companions.find(c => c.name === selectedCompanion);
    }

    function renderMemoryIndex() {
      const companion = currentCompanion();
      if (!companion) {
        document.getElementById('memoryIndex').innerHTML = '<p class="muted">No companion selected.</p>';
        return;
      }
      if (companion.error) {
        document.getElementById('memoryIndex').innerHTML = `<p class="muted">${escapeHtml(companion.summary)}</p><p class="muted">${escapeHtml(companion.error)}</p>`;
        return;
      }
      const rows = companion.index.map(entry => `<tr><td>${escapeHtml(entry.id || '')}</td><td>${escapeHtml(entry.category || '')}</td><td>${escapeHtml(entry.status || '')}</td><td>${escapeHtml(String(entry.weight || ''))}</td><td>${escapeHtml((entry.tags || []).join(', '))}</td><td>${escapeHtml(entry.updated_at || entry.created_at || '')}</td></tr>`).join('');
      document.getElementById('memoryIndex').innerHTML = `<p class="muted">${escapeHtml(companion.summary)}</p><div class="scrollbox"><table><thead><tr><th>ID</th><th>Category</th><th>Status</th><th>Weight</th><th>Tags</th><th>Updated</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }

    function renderDashboard() {
      const summary = state.trackers.summary;
      const directiveSummary = state.directive_summary;
      const latest = state.trackers.latest_checkin;
      const memoryRows = state.companions.reduce((count, companion) => count + (companion.index || []).length, 0);
      document.getElementById('dashCompanions').textContent = state.companions.length;
      document.getElementById('dashMemory').textContent = `${memoryRows} indexed memory IDs`;
      document.getElementById('dashDirectives').textContent = state.directives.length;
      document.getElementById('dashDirectiveDetail').textContent = `${directiveSummary.issued} issued, ${directiveSummary.complete} complete, ${directiveSummary.failed} failed, ${directiveSummary.proof_required} proof required`;
      document.getElementById('dashPhysical').textContent = summary.physical_entries;
      document.getElementById('dashPhysicalDetail').textContent = latest ? `${latest.body.exercise_minutes || 0} exercise minutes, ${latest.body.sleep_hours || 0}h sleep latest` : 'No daily check-in yet.';
      document.getElementById('dashSpirit').textContent = latest ? (latest.spirit.scripture ? 'read' : 'open') : '--';
      document.getElementById('dashSpiritDetail').textContent = latest ? `${latest.spirit.prayer ? 'prayer' : 'no prayer logged'} / ${latest.spirit.reading_status || 'no reading status'}` : 'No spiritual check-in yet.';
      document.getElementById('dashWorkCloud').innerHTML = renderTagCloud(state.trackers.work_categories, state.trackers.task_categories);
      document.getElementById('dashLatestCheckin').innerHTML = latest ? renderCheckinCard(latest) : '<p class="muted">No entries.</p>';
    }

    async function copyPacket() {
      await navigator.clipboard.writeText(document.getElementById('packetBox').value.trim());
      setStatus(`Copied ${selectedCompanion} packet.`);
    }

    async function copyHandoff() {
      const res = await fetch(`/api/companion/${encodeURIComponent(selectedCompanion)}/handoff`);
      const data = await handleResponse(res, false);
      await navigator.clipboard.writeText(data.handoff);
      setStatus(`Copied ${selectedCompanion} handoff.`);
    }

    async function addMemory() {
      const body = {
        category: document.getElementById('categorySelect').value,
        content: document.getElementById('memoryContent').value,
        weight: document.getElementById('memoryWeight').value,
        tags: document.getElementById('memoryTags').value
      };
      const res = await fetch(`/api/companion/${encodeURIComponent(selectedCompanion)}/memory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      document.getElementById('memoryContent').value = '';
      document.getElementById('memoryTags').value = '';
      await loadState();
    }

    async function applyCommands() {
      const body = { commands: document.getElementById('commandBatch').value };
      const res = await fetch(`/api/companion/${encodeURIComponent(selectedCompanion)}/commands`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      document.getElementById('commandBatch').value = '';
      await loadState();
    }

    async function createCompanion() {
      const body = {
        name: document.getElementById('newCompanionName').value,
        filename: document.getElementById('newCompanionFile').value
      };
      const res = await fetch('/api/companions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await handleResponse(res);
      document.getElementById('newCompanionName').value = '';
      document.getElementById('newCompanionFile').value = '';
      selectedCompanion = data.companion.name;
      await loadState();
    }

    async function createDirective() {
      const body = {
        issuer: document.getElementById('directiveIssuer').value,
        title: document.getElementById('directiveTitle').value,
        details: document.getElementById('directiveDetails').value,
        priority: document.getElementById('directivePriority').value,
        due_at: document.getElementById('directiveDue').value,
        proof_required: document.getElementById('directiveProofRequired').checked
      };
      const res = await fetch('/api/directives', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      document.getElementById('directiveTitle').value = '';
      document.getElementById('directiveDetails').value = '';
      await loadState();
    }

    async function parseDirective() {
      const body = {
        text: document.getElementById('directiveParseText').value,
        issuer: document.getElementById('directiveIssuer').value || selectedCompanion
      };
      const res = await fetch('/api/directives/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await handleResponse(res);
      document.getElementById('directiveIssuer').value = data.directive.issuer;
      document.getElementById('directiveTitle').value = data.directive.title;
      document.getElementById('directiveDetails').value = data.directive.details;
      document.getElementById('directivePriority').value = data.directive.priority;
      document.getElementById('directiveDue').value = normalizeDateTimeLocal(data.directive.due_at);
      document.getElementById('directiveProofRequired').checked = Boolean(data.directive.proof_required);
    }

    async function setDirectiveStatus(id, status) {
      const res = await fetch(`/api/directives/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status })
      });
      await handleResponse(res);
      await loadState();
    }

    function renderDirectives() {
      const directives = selectedDirectiveStatus === 'all'
        ? state.directives
        : state.directives.filter(d => String(d.status || 'issued').toLowerCase() === selectedDirectiveStatus);
      const rows = directives.map(d => {
        const statusClass = `status-${escapeHtml(String(d.status || 'issued').toLowerCase())}`;
        const proof = d.proof_required ? 'required' : '';
        const details = d.details ? escapeHtml(d.details) : '<span class="muted">No details supplied.</span>';
        return `<tr><td>${escapeHtml(d.id)}</td><td>${escapeHtml(d.issuer)}</td><td><strong class="directive-title">${escapeHtml(d.title)}</strong><div class="directive-detail">${details}</div></td><td><span class="pill ${statusClass}">${escapeHtml(d.status)}</span></td><td>${escapeHtml(String(d.priority || ''))}</td><td>${escapeHtml(d.due_at || '')}</td><td>${escapeHtml(proof)}</td><td><button class="inline" onclick="setDirectiveStatus('${escapeJs(d.id)}','complete')">Complete</button> <button class="inline" onclick="setDirectiveStatus('${escapeJs(d.id)}','failed')">Fail</button> <button class="inline" onclick="setDirectiveStatus('${escapeJs(d.id)}','issued')">Reopen</button></td></tr>`;
      }).join('');
      const empty = '<tr><td colspan="8" class="muted">No directives in this status.</td></tr>';
      document.getElementById('directiveList').innerHTML = `<div class="scrollbox"><table><thead><tr><th>ID</th><th>Issuer</th><th>Command</th><th>Status</th><th>Priority</th><th>Due</th><th>Proof</th><th>Actions</th></tr></thead><tbody>${rows || empty}</tbody></table></div>`;
    }

    function renderProof() {
      const rows = state.proof.map(p => {
        const evidence = p.path || p.note || '';
        const action = p.path ? `<a class="inline" href="/api/proof/${encodeURIComponent(p.id)}/download">Download</a>` : '';
        return `<tr><td>${escapeHtml(p.id)}</td><td>${escapeHtml(p.directive_id)}</td><td>${escapeHtml(p.type)}</td><td>${escapeHtml(evidence)}</td><td>${escapeHtml(p.submitted_at)}</td><td>${action}</td></tr>`;
      }).join('');
      document.getElementById('proofList').innerHTML = `<div class="scrollbox"><table><thead><tr><th>ID</th><th>Directive</th><th>Type</th><th>Evidence</th><th>Submitted</th><th>Actions</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }

    function renderTrackers() {
      const summary = state.trackers.summary;
      document.getElementById('trackerSummary').innerHTML = `<span class="pill">${summary.checkin_entries} check-ins</span> <span class="pill">${summary.journal_entries} journal</span> <span class="pill">${summary.task_entries} task logs</span> <span class="pill">${summary.physical_entries} physical logs</span> ${renderTagCloud(state.trackers.work_categories, state.trackers.task_categories)}`;
      renderReadingPlanControls();
      renderTrackerTabs();
      document.getElementById('checkinList').innerHTML = renderCheckins(state.trackers.checkins);
      document.getElementById('journalList').innerHTML = renderSimpleList(state.trackers.journal, item => `${item.timestamp || ''} | mood ${item.mood || ''} | ${item.prompt || ''}`);
      document.getElementById('taskList').innerHTML = renderSimpleList(state.trackers.tasks, item => `${item.timestamp || ''} | ${item.task_name || ''} | ${Math.round(item.duration_minutes || 0)} min | ${item.task_type || ''}`);
      document.getElementById('physicalList').innerHTML = renderSimpleList(state.trackers.physical, item => `${item.timestamp || ''} | ${item.session_type || ''} | ${(item.exercises || []).join(', ')} | ${item.duration_minutes || 0} min`);
    }

    function renderTrackerTabs() {
      document.querySelectorAll('#trackerTabs button').forEach(button => {
        button.classList.toggle('active', button.dataset.tracker === selectedTrackerTab);
      });
      document.querySelectorAll('[data-tracker-view]').forEach(view => {
        view.classList.toggle('active', view.dataset.trackerView === selectedTrackerTab);
      });
    }

    function renderReadingPlanControls() {
      const planSelect = document.getElementById('checkinReadingPlan');
      const plans = Object.keys(state.reading_plans || {});
      const currentPlan = planSelect.value || plans[0] || '';
      planSelect.innerHTML = plans.map(plan => `<option value="${escapeHtml(plan)}">${escapeHtml(plan)}</option>`).join('');
      if (currentPlan && plans.includes(currentPlan)) {
        planSelect.value = currentPlan;
      }
      renderReadingSections();
      renderReadingChecklist();
    }

    function renderReadingSections() {
      const planName = document.getElementById('checkinReadingPlan').value;
      const sectionSelect = document.getElementById('checkinReadingSection');
      const sections = (state.reading_plans || {})[planName] || [];
      const currentSection = sectionSelect.value || (sections[0] ? sections[0].id : '');
      sectionSelect.innerHTML = sections.map(section => `<option value="${escapeHtml(section.id)}">${escapeHtml(section.label)}</option>`).join('');
      if (currentSection && sections.some(section => section.id === currentSection)) {
        sectionSelect.value = currentSection;
      }
    }

    function renderReadingChecklist() {
      const planName = document.getElementById('checkinReadingPlan').value;
      const sections = (state.reading_plans || {})[planName] || [];
      const progress = (state.trackers.reading_progress || {})[planName] || {};
      const completed = new Set(progress.completed_ids || []);
      document.getElementById('readingChecklist').innerHTML = sections.map(section => {
        const checked = completed.has(section.id) ? 'checked' : '';
        return `<label><input type="checkbox" class="reading-check" value="${escapeHtml(section.id)}" ${checked} style="width:auto;"> ${escapeHtml(section.label)}</label>`;
      }).join('');
      document.getElementById('readingProgress').textContent = sections.length ? `${progress.completed || 0}/${sections.length} completed for ${planName}` : 'No reading plan selected.';
    }

    async function saveCheckin() {
      const body = {
        date: document.getElementById('checkinDate').value,
        mood: document.getElementById('checkinMood').value,
        energy: document.getElementById('checkinEnergy').value,
        sleep_hours: document.getElementById('checkinSleep').value,
        food_on_plan: document.getElementById('checkinFood').checked,
        exercise_minutes: document.getElementById('checkinExerciseMinutes').value,
        exercise_type: document.getElementById('checkinExerciseType').value,
        weight: document.getElementById('checkinWeight').value,
        prayer: document.getElementById('checkinPrayer').checked,
        scripture: document.getElementById('checkinScripture').checked,
        reading_plan: document.getElementById('checkinReadingPlan').value,
        reading_section: document.getElementById('checkinReadingSection').value,
        reading_checklist: Array.from(document.querySelectorAll('.reading-check:checked')).map(input => input.value),
        assigned_reading: document.getElementById('checkinAssignedReading').value,
        reading_completed: document.getElementById('checkinReadingCompleted').checked,
        reading_minutes: document.getElementById('checkinReadingMinutes').value,
        reading_status: document.getElementById('checkinReadingStatus').value,
        favorite_verse: document.getElementById('checkinFavoriteVerse').value,
        application: document.getElementById('checkinApplication').value,
        prayer_response: document.getElementById('checkinPrayerResponse').value,
        gratitude: document.getElementById('checkinGratitude').value,
        repentance: document.getElementById('checkinRepentance').value,
        service: document.getElementById('checkinService').value,
        felt_close: document.getElementById('checkinFeltClose').value,
        work_category: document.getElementById('checkinWorkCategory').value,
        work_task: document.getElementById('checkinWorkTask').value,
        work_minutes: document.getElementById('checkinWorkMinutes').value,
        work_difficulty: document.getElementById('checkinWorkDifficulty').value,
        work_result: document.getElementById('checkinWorkResult').value,
        next_step: document.getElementById('checkinNextStep').value,
        work_recurring: document.getElementById('checkinWorkRecurring').checked,
        money_spent: document.getElementById('checkinMoneySpent').value,
        note: document.getElementById('checkinNote').value
      };
      const res = await fetch('/api/checkins', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      for (const id of ['checkinExerciseType', 'checkinWeight', 'checkinAssignedReading', 'checkinWorkTask', 'checkinWorkDifficulty', 'checkinWorkResult', 'checkinNextStep', 'checkinFavoriteVerse', 'checkinApplication', 'checkinPrayerResponse', 'checkinGratitude', 'checkinRepentance', 'checkinService', 'checkinFeltClose', 'checkinNote']) {
        document.getElementById(id).value = '';
      }
      await loadState();
    }

    function renderCouncil() {
      document.getElementById('councilCompanions').innerHTML = state.companions.map(c => `<div class="panel" style="margin-bottom: 10px;"><h3>${escapeHtml(c.name)}</h3><p class="muted">${escapeHtml(c.summary)}</p><button class="inline primary" onclick="selectedCompanion='${escapeJs(c.name)}'; document.getElementById('companionSelect').value=selectedCompanion; copyHandoff();">Copy ${escapeHtml(c.name)} Handoff</button></div>`).join('');
    }

    function renderSimpleList(items, formatter) {
      if (!items.length) return '<p class="muted">No entries.</p>';
      return '<div class="scrollbox"><table><tbody>' + items.map(item => `<tr><td>${escapeHtml(formatter(item))}</td></tr>`).join('') + '</tbody></table></div>';
    }

    function renderCheckins(items) {
      if (!items.length) return '<p class="muted">No entries.</p>';
      return '<div class="scrollbox"><table><tbody>' + items.slice().reverse().map(item => `<tr><td>${renderCheckinCard(item)}</td></tr>`).join('') + '</tbody></table></div>';
    }

    function renderCheckinCard(item) {
      const work = item.work || {};
      const body = item.body || {};
      const mind = item.mind || {};
      const spirit = item.spirit || {};
      const plan = spirit.reading_plan || '';
      const section = readingSectionLabel(plan, spirit.reading_section);
      const completed = readingChecklistLabels(plan, spirit.reading_checklist || []);
      const readingLine = plan
        ? `${plan} | ${section || spirit.assigned_reading || ''} | checked: ${completed || 'none'}`
        : `${spirit.assigned_reading || ''}`;
      return `<strong>${escapeHtml(item.date || item.id)}</strong><br><span class="muted">mood ${escapeHtml(mind.mood || '')}, energy ${escapeHtml(body.energy || '')}, sleep ${escapeHtml(body.sleep_hours || 0)}h, exercise ${escapeHtml(body.exercise_minutes || 0)}m</span><br><span class="muted">${escapeHtml(work.category || '')} ${escapeHtml(work.minutes || 0)}m | ${escapeHtml(work.task_name || '')} | next ${escapeHtml(work.next_step || '')}</span><br><span class="muted">prayer ${spirit.prayer ? 'yes' : 'no'} / scripture ${spirit.scripture ? 'yes' : 'no'} / reading ${spirit.reading_completed ? 'done' : 'open'} ${escapeHtml(spirit.reading_minutes || 0)}m / ${escapeHtml(spirit.reading_status || '')}</span><br><span class="muted">${escapeHtml(readingLine)}</span><br><span>${escapeHtml(mind.note || spirit.application || work.result || '')}</span>`;
    }

    function readingSectionLabel(planName, sectionId) {
      const section = ((state && state.reading_plans && state.reading_plans[planName]) || []).find(item => item.id === sectionId);
      return section ? section.label : (sectionId || '');
    }

    function readingChecklistLabels(planName, sectionIds) {
      return sectionIds.map(sectionId => readingSectionLabel(planName, sectionId)).filter(Boolean).join(', ');
    }

    function renderTagCloud(primary, secondary) {
      const merged = Object.assign({}, secondary || {});
      for (const [key, value] of Object.entries(primary || {})) {
        merged[key] = (merged[key] || 0) + value;
      }
      const entries = Object.entries(merged).sort((a, b) => b[1] - a[1]).slice(0, 12);
      if (!entries.length) return '<span class="muted">No categories.</span>';
      return entries.map(([name, count]) => `<span class="pill">${escapeHtml(name)} ${escapeHtml(count)}</span>`).join('');
    }

    async function handleResponse(res, showSaved = true) {
      const data = await res.json();
      if (!res.ok) {
        setStatus(data.error || 'Request failed.');
        throw new Error(data.error || 'Request failed.');
      }
      if (showSaved) setStatus(data.message || 'Saved.');
      return data;
    }

    function setStatus(text) { document.getElementById('status').textContent = text; }
    function normalizeDateTimeLocal(value) {
      const text = String(value || '').trim();
      if (!text) return '';
      const direct = text.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/);
      return direct ? `${direct[1]}T${direct[2]}` : '';
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
    }
    function escapeJs(value) { return String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'"); }
    loadState().catch(error => setStatus(error.message || 'Unable to load console data.'));
  </script>
</body>
</html>
"""


class CompanionWebHandler(BaseHTTPRequestHandler):
    server_version = "CompanionWeb/0.1"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                self.send_html(INDEX_HTML)
            elif path == "/api/state":
                self.send_json(app_state())
            elif path.startswith("/api/companion/"):
                self.handle_companion_get(path)
            elif path.startswith("/api/proof/") and path.endswith("/download"):
                proof_id = unquote(path.split("/")[3])
                proof = proof_by_id(proof_id)
                if not proof.get("path"):
                    self.send_error_json(404, "Proof has no downloadable file.")
                    return
                self.send_file(APP_DIR / proof["path"], as_attachment=True)
            elif path.startswith("/proof_vault/"):
                self.send_file(APP_DIR / unquote(path.lstrip("/")))
            else:
                self.send_error_json(404, "Not found.")
        except Exception as exc:
            self.send_error_json(500, str(exc))

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/directives":
                directive = create_directive(self.read_json_body())
                self.send_json({"message": f"Created {directive['id']}.", "directive": directive})
            elif path == "/api/companions":
                companion = create_companion_record(self.read_json_body())
                self.send_json({"message": f"Created companion {companion['name']}.", "companion": companion})
            elif path == "/api/directives/parse":
                directive = parse_directive_text(self.read_json_body())
                self.send_json({"message": "Parsed directive draft.", "directive": directive})
            elif path == "/api/proof":
                proof = create_text_proof(self.read_json_body())
                self.send_json({"message": f"Created {proof['id']}.", "proof": proof})
            elif path == "/api/checkins":
                checkin = create_checkin(self.read_json_body())
                self.send_json({"message": f"Saved {checkin['id']}.", "checkin": checkin})
            elif path == "/api/proof/upload":
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        "REQUEST_METHOD": "POST",
                        "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    },
                )
                proof = create_file_proof(form)
                self.send_json({"message": f"Uploaded {proof['id']}.", "proof": proof})
            elif path.startswith("/api/companion/"):
                self.handle_companion_post(path)
            else:
                self.send_error_json(404, "Not found.")
        except Exception as exc:
            self.send_error_json(400, str(exc))

    def do_PATCH(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/directives/"):
                directive_id = unquote(path.rsplit("/", 1)[1])
                directive = update_directive(directive_id, self.read_json_body())
                self.send_json({"message": f"Updated {directive['id']}.", "directive": directive})
            else:
                self.send_error_json(404, "Not found.")
        except Exception as exc:
            self.send_error_json(400, str(exc))

    def handle_companion_get(self, path):
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) < 3:
            self.send_error_json(404, "Companion endpoint missing action.")
            return
        companion = parts[2]
        action = parts[3] if len(parts) > 3 else ""
        if companion not in COMPANION_FILES:
            self.send_error_json(404, f"Unknown companion: {companion}")
            return

        payload = load_payload(companion)
        packet = encode_payload(payload).strip()
        if action == "packet":
            self.send_json({"packet": packet, "summary": packet_summary(companion, payload)})
        elif action == "handoff":
            self.send_json({"handoff": HANDOFF_TEMPLATE.format(companion=companion, packet=packet)})
        elif action == "index":
            self.send_json({"index": companion_index(companion)})
        else:
            self.send_error_json(404, "Unknown companion action.")

    def handle_companion_post(self, path):
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) < 4:
            self.send_error_json(404, "Companion endpoint missing action.")
            return
        companion = parts[2]
        action = parts[3]
        if companion not in COMPANION_FILES:
            self.send_error_json(404, f"Unknown companion: {companion}")
            return

        data = self.read_json_body()
        if action == "commands":
            result = apply_commands(companion, data.get("commands", ""))
            memory_count = len(result["applied"]) - len(result["directives"])
            directive_count = len(result["directives"])
            parts = []
            if memory_count:
                parts.append(f"{memory_count} memory command(s)")
            if directive_count:
                parts.append(f"{directive_count} directive(s)")
            message = "Applied " + " and ".join(parts) + "." if parts else "No commands applied."
            self.send_json({"message": message, **result})
        elif action == "memory":
            payload = load_payload(companion)
            tags = [tag.strip() for tag in data.get("tags", "").split(",") if tag.strip()]
            memory_id = add_memory(
                payload,
                data.get("category", "observations"),
                data.get("content", ""),
                data.get("weight", 3),
                tags,
            )
            backup_path = save_payload(companion, payload)
            self.send_json(
                {
                    "message": f"Added {memory_id}.",
                    "id": memory_id,
                    "backup": backup_path.name if backup_path else None,
                }
            )
        else:
            self.send_error_json(404, "Unknown companion action.")

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, as_attachment=False):
        resolved = path.resolve()
        if not str(resolved).lower().startswith(str(PROOF_DIR.resolve()).lower()) or not resolved.exists():
            self.send_error_json(404, "File not found.")
            return
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(resolved.name)[0] or "application/octet-stream")
        if as_attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{resolved.name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json({"error": message}, status=status)


def run(host="127.0.0.1", port=8787):
    ensure_data_files()
    server = ThreadingHTTPServer((host, port), CompanionWebHandler)
    print(f"Companion Control Console running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local Companion Control Console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    run(args.host, args.port)
