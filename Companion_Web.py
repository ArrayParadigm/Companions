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
PROJECT_ASSET_DIR = APP_DIR / "project_assets"
DIRECTIVES_FILE = DATA_DIR / "directives.json"
PROOF_FILE = DATA_DIR / "proof_metadata.json"
CHECKINS_FILE = DATA_DIR / "daily_checkins.json"
PROJECT_TODOS_FILE = DATA_DIR / "project_todos.json"
READING_PROGRESS_FILE = DATA_DIR / "reading_progress.json"
KJV_FILE = APP_DIR / "kjv.txt"
DAILY_SCHEDULE_PLAN = "KJV Daily Schedule"

PROJECT_CATEGORIES = {
    "home": "Home Maintenance",
    "vehicle": "Vehicle Maintenance",
    "tech": "Tech Projects",
    "chores": "Chores",
}

PROJECT_CATEGORY_DETAILS = {
    "home": {
        "context_label": "Materials / Location / Vendor Info",
        "context_empty": "No materials, location, or vendor info yet.",
        "description": "Household repairs, maintenance, improvements, and physical-property work.",
    },
    "vehicle": {
        "context_label": "Vehicle / Parts / Shop Info",
        "context_empty": "No vehicle, parts, or shop info yet.",
        "description": "Vehicle maintenance, repair notes, parts, service records, and inspection work.",
    },
    "tech": {
        "context_label": "Repo / Environment / Access Notes",
        "context_empty": "No repo, environment, dependency, or deployment notes yet.",
        "description": "Software, hardware, automation, repos, environments, tickets, and deployment work.",
    },
    "chores": {
        "context_label": "Area / Supplies / Recurrence",
        "context_empty": "No area, supplies, or recurrence info yet.",
        "description": "Recurring upkeep, cleaning, organizing, errands, and routine home tasks.",
    },
}


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

PSALM_119_SECTIONS = [
    {"id": f"psalm-119-{start}-{start + 7}", "label": f"Psalm 119:{start}-{start + 7}"}
    for start in range(1, 176, 8)
]

READING_PLANS = {
    "Daily Rhythm": [
        *PSALM_119_SECTIONS,
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
    PROJECT_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    if not DIRECTIVES_FILE.exists():
        write_json(DIRECTIVES_FILE, {"next_directive_number": 1, "directives": []})
    if not PROOF_FILE.exists():
        write_json(PROOF_FILE, {"next_proof_number": 1, "proof": []})
    if not CHECKINS_FILE.exists():
        write_json(CHECKINS_FILE, {"next_checkin_number": 1, "entries": []})
    if not PROJECT_TODOS_FILE.exists():
        write_json(PROJECT_TODOS_FILE, {"next_project_todo_number": 1, "todos": []})
    if not READING_PROGRESS_FILE.exists():
        write_json(READING_PROGRESS_FILE, {"completed": {}, "updated_at": ""})


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


def project_todo_store():
    ensure_data_files()
    return read_json(PROJECT_TODOS_FILE, {"next_project_todo_number": 1, "todos": []})


def reading_progress_store():
    ensure_data_files()
    return read_json(READING_PROGRESS_FILE, {"completed": {}, "updated_at": ""})


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


def kjv_chapter_text(book, chapter):
    if not KJV_FILE.exists():
        return ""
    target_book = str(book or "").strip().lower()
    target_prefix = f"{int(chapter)}:"
    next_prefix = f"{int(chapter) + 1}:"
    found_book = False
    found_chapter = False
    lines = []
    with KJV_FILE.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line.startswith("BOOK:"):
                current_book = line.split(":", 1)[1].strip().lower()
                if found_chapter:
                    break
                found_book = current_book == target_book
                continue
            if not found_book:
                continue
            if line.startswith(target_prefix):
                found_chapter = True
            elif found_chapter and line.startswith(next_prefix):
                break
            if found_chapter and line:
                lines.append(line)
    return "\n".join(lines)


def bible_chapter_id(book, chapter):
    return f"{safe_name(str(book).lower())}-{int(chapter)}"


def bible_chapter_index():
    books = []
    if not KJV_FILE.exists():
        return books
    current_book = None
    chapters = set()
    with KJV_FILE.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line.startswith("BOOK:"):
                if current_book:
                    books.append({
                        "book": current_book,
                        "chapters": [{"id": bible_chapter_id(current_book, chapter), "chapter": chapter, "label": f"{current_book} {chapter}"} for chapter in sorted(chapters)],
                    })
                current_book = line.split(":", 1)[1].strip()
                chapters = set()
                continue
            match = re.match(r"^(\d+):", line)
            if current_book and match:
                chapters.add(int(match.group(1)))
    if current_book:
        books.append({
            "book": current_book,
            "chapters": [{"id": bible_chapter_id(current_book, chapter), "chapter": chapter, "label": f"{current_book} {chapter}"} for chapter in sorted(chapters)],
        })
    return books


def mark_reading_complete(data):
    store = reading_progress_store()
    reading_id = str(data.get("id") or "").strip()
    label = str(data.get("label") or reading_id).strip()
    source = str(data.get("source") or "spiritual").strip()
    if not reading_id:
        raise ValueError("Reading id is required.")
    completed = store.setdefault("completed", {})
    completed[reading_id] = {
        "id": reading_id,
        "label": label,
        "source": source,
        "completed_at": now_stamp(),
    }
    store["updated_at"] = now_stamp()
    write_json(READING_PROGRESS_FILE, store)
    return completed[reading_id]


def psalm_119_progress(completed):
    section_ids = {section["id"] for section in PSALM_119_SECTIONS}
    completed_ids = [reading_id for reading_id in completed if reading_id in section_ids]
    total = len(section_ids)
    return {
        "completed": len(completed_ids),
        "total": total,
        "percent": round((len(completed_ids) / total) * 100, 2) if total else 0,
        "completed_ids": sorted(completed_ids),
    }


def reading_progress_state():
    store = reading_progress_store()
    completed = store.get("completed", {})
    bible_ids = {chapter["id"] for book in bible_chapter_index() for chapter in book.get("chapters", [])}
    bible_completed = [reading_id for reading_id in completed if reading_id in bible_ids]
    total = len(bible_ids)
    percent = round((len(bible_completed) / total) * 100, 2) if total else 0
    return {
        "completed": completed,
        "bible_completed": len(bible_completed),
        "bible_total": total,
        "bible_percent": percent,
        "psalm_119": psalm_119_progress(completed),
        "updated_at": store.get("updated_at", ""),
    }


def daily_reading_schedule(for_date=None):
    target_date = for_date or datetime.now().date()
    day = target_date.day
    psalm_start = (day - 1) % 30 + 1
    chapter_specs = [("Proverbs", day)]
    chapter_specs.extend(("Psalms", psalm_start + offset * 30) for offset in range(5))
    chapter_specs.append(("Acts", ((day - 1) % 28) + 1))
    readings = []
    for book, chapter in chapter_specs:
        label = f"{book} {chapter}"
        text = kjv_chapter_text(book, chapter)
        readings.append({
            "id": bible_chapter_id(book, chapter),
            "label": label,
            "book": book,
            "chapter": chapter,
            "text": text,
            "available": bool(text),
        })
    return {
        "date": target_date.isoformat(),
        "source_file": KJV_FILE.name,
        "source_available": KJV_FILE.exists(),
        "readings": readings,
    }


def current_reading_plans(schedule=None):
    plans = copy.deepcopy(READING_PLANS)
    schedule = schedule or daily_reading_schedule()
    plans[DAILY_SCHEDULE_PLAN] = [
        {"id": item["id"], "label": item["label"]}
        for item in schedule.get("readings", [])
    ]
    return plans


def reading_plan_sections(plan_name):
    return current_reading_plans().get(str(plan_name or "").strip(), [])


def reading_section_label(plan_name, section_id):
    for section in reading_plan_sections(plan_name):
        if section["id"] == section_id:
            return section["label"]
    return str(section_id or "").strip()


def reading_progress(checkins, plans=None):
    progress = {}
    plans = plans or current_reading_plans()
    for plan_name, sections in plans.items():
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
            "fitness_completed": clean_bool(data.get("fitness_completed")),
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


def create_journal_entry(data):
    path = TRACKER_FILES["journal"]
    entries = read_json(path, [])
    entry = {
        "timestamp": now_stamp().replace("T", " "),
        "prompt": str(data.get("prompt") or "General reflection.").strip() or "General reflection.",
        "mood": clean_int(data.get("mood"), default=5, minimum=1, maximum=10),
        "entry": str(data.get("entry") or "").strip(),
    }
    if not entry["entry"]:
        raise ValueError("Journal entry text is required.")
    entries.append(entry)
    write_json(path, entries)
    return entry


def create_fitness_entry(data):
    path = TRACKER_FILES["physical"]
    entries = read_json(path, [])
    exercises = clean_string_list(data.get("exercises"))
    entry = {
        "timestamp": now_stamp().replace("T", " "),
        "session_type": str(data.get("session_type") or "Fitness").strip() or "Fitness",
        "exercises": exercises,
        "duration_minutes": clean_int(data.get("duration_minutes"), default=0, minimum=0),
        "notes": str(data.get("notes") or "").strip(),
        "progress": str(data.get("progress") or "").strip(),
    }
    if not entry["exercises"] and not entry["notes"]:
        raise ValueError("Fitness entry requires exercises or notes.")
    entries.append(entry)
    write_json(path, entries)
    return entry


def normalize_project_category(value):
    category = str(value or "").strip().lower()
    if category in PROJECT_CATEGORIES:
        return category
    for key, label in PROJECT_CATEGORIES.items():
        if category == label.lower():
            return key
    return "home"


def project_category_detail(category):
    return PROJECT_CATEGORY_DETAILS.get(normalize_project_category(category), PROJECT_CATEGORY_DETAILS["home"])


def create_project_todo(data):
    store = project_todo_store()
    todo_id = next_id(store, "next_project_todo_number", "PRJ")
    started = str(data.get("date_started", data.get("start_date", "")) or "").strip()
    todo = {
        "id": todo_id,
        "category": normalize_project_category(data.get("category")),
        "title": str(data.get("title", "") or "").strip(),
        "status": str(data.get("status", "open") or "open").strip() or "open",
        "start_date": started,
        "date_started": started,
        "due_date": str(data.get("due_date", "") or "").strip(),
        "offering_info": str(data.get("offering_info", "") or "").strip(),
        "expenses": str(data.get("expenses", "") or "").strip(),
        "tasks": str(data.get("tasks", "") or "").strip(),
        "work_log": str(data.get("work_log", "") or "").strip(),
        "notes": str(data.get("notes", "") or "").strip(),
        "next_step": str(data.get("next_step", "") or "").strip(),
        "assets": [],
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
    }
    if not todo["title"]:
        raise ValueError("Project todo title is required.")
    store["todos"].append(todo)
    write_json(PROJECT_TODOS_FILE, store)
    return todo


def update_project_todo(todo_id, data):
    store = project_todo_store()
    for todo in store.get("todos", []):
        if todo.get("id", "").lower() == todo_id.lower():
            if "date_started" in data and "start_date" not in data:
                data["start_date"] = data["date_started"]
            if "start_date" in data and "date_started" not in data:
                data["date_started"] = data["start_date"]
            for key in ("title", "status", "start_date", "date_started", "due_date", "offering_info", "expenses", "tasks", "work_log", "notes", "next_step"):
                if key in data:
                    todo[key] = str(data[key]).strip()
            if "category" in data:
                todo["category"] = normalize_project_category(data.get("category"))
            todo["updated_at"] = now_stamp()
            write_json(PROJECT_TODOS_FILE, store)
            return todo
    raise ValueError(f"Project todo not found: {todo_id}")


def delete_project_todo(todo_id):
    store = project_todo_store()
    todos = store.get("todos", [])
    for index, todo in enumerate(todos):
        if todo.get("id", "").lower() == todo_id.lower():
            removed = todos.pop(index)
            write_json(PROJECT_TODOS_FILE, store)
            shutil.rmtree(PROJECT_ASSET_DIR / safe_name(todo_id), ignore_errors=True)
            return removed
    raise ValueError(f"Project todo not found: {todo_id}")


def project_todo_by_id(todo_id):
    for todo in project_todo_store().get("todos", []):
        if todo.get("id", "").lower() == todo_id.lower():
            return todo
    raise ValueError(f"Project todo not found: {todo_id}")


def create_project_asset(form):
    store = project_todo_store()
    todo_id = field_value(form, "todo_id")
    asset_type = field_value(form, "type") or "picture"
    note = field_value(form, "note")
    item = form["file"] if "file" in form else None
    if not todo_id:
        raise ValueError("Project asset upload requires a project todo.")
    if item is None or not getattr(item, "filename", ""):
        raise ValueError("Project asset upload requires a file.")

    for todo in store.get("todos", []):
        if todo.get("id", "").lower() == todo_id.lower():
            safe_project = safe_name(todo_id)
            original_name = safe_name(Path(item.filename).name)
            target_dir = PROJECT_ASSET_DIR / safe_project
            target_dir.mkdir(parents=True, exist_ok=True)
            asset_id = f"AST-{len(todo.get('assets', [])) + 1:04d}"
            target_path = target_dir / f"{asset_id}-{original_name}"
            with target_path.open("wb") as out_file:
                shutil.copyfileobj(item.file, out_file)
            asset_path = target_path.relative_to(APP_DIR).as_posix()
            asset = {
                "id": asset_id,
                "type": asset_type,
                "note": note,
                "filename": original_name,
                "path": asset_path,
                "uploaded_at": now_stamp(),
            }
            todo.setdefault("assets", []).append(asset)
            todo["updated_at"] = now_stamp()
            write_json(PROJECT_TODOS_FILE, store)
            return asset
    raise ValueError(f"Project todo not found: {todo_id}")


def render_project_page(todo_id):
    todo = project_todo_by_id(todo_id)
    category = PROJECT_CATEGORIES.get(todo.get("category"), todo.get("category", ""))
    detail = project_category_detail(todo.get("category"))
    assets = todo.get("assets", [])
    asset_rows = render_project_asset_rows(assets)
    todo_json = json.dumps(todo)
    categories_json = json.dumps(PROJECT_CATEGORIES)
    detail_json = json.dumps(detail)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(todo.get('title', 'Project'))}</title>
  <style>
    body {{ font-family: Segoe UI, system-ui, sans-serif; margin: 18px; background: #10151a; color: #edf2f7; font-size: 14px; }}
    main {{ max-width: 980px; margin: 0 auto; }}
    section {{ border: 1px solid #303842; border-radius: 8px; padding: 12px; margin: 10px 0; background: #181d22; }}
    h1 {{ margin: 0 0 4px; font-size: 1.55rem; }}
    h2 {{ font-size: 1.02rem; margin: 0 0 8px; }}
    h3 {{ font-size: .94rem; margin: 12px 0 6px; }}
    label {{ display: block; margin: 8px 0 4px; color: #c7d0da; }}
    input, select, textarea {{ width: 100%; box-sizing: border-box; border: 1px solid #3b4652; border-radius: 6px; background: #0d1116; color: #edf2f7; padding: 8px; font: inherit; }}
    textarea {{ min-height: 78px; resize: vertical; }}
    pre {{ white-space: pre-wrap; font: inherit; color: #c7d0da; margin: 0; }}
    a {{ color: #62d6b2; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }}
    .row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}
    .pill {{ display: inline-block; border: 1px solid #3b4652; border-radius: 999px; padding: 3px 8px; margin: 2px 4px 2px 0; color: #c7d0da; }}
    .muted {{ color: #9aa7b4; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    button {{ border: 1px solid #3b4652; border-radius: 6px; background: #202832; color: #edf2f7; padding: 8px 10px; cursor: pointer; }}
    button.primary {{ background: #1e6f58; border-color: #2a8f72; }}
    button.danger {{ background: #6f2d2d; border-color: #9f4646; }}
    ul {{ margin: 0; padding-left: 18px; }}
  </style>
</head>
<body>
  <main>
    <h1 id="pageTitle">{html_escape(todo.get('title', 'Project'))}</h1>
    <p><span class="pill" id="categoryPill">{html_escape(category)}</span><span class="pill" id="statusPill">{html_escape(todo.get('status', 'open'))}</span></p>
    <p class="muted" id="categoryDescription">{html_escape(detail.get('description', ''))}</p>
    <section>
      <h2>Dates</h2>
      <p class="muted">Date added: <span id="dateAdded">{html_escape(todo.get('created_at', ''))}</span> | Date started: <span id="dateStarted">{html_escape(todo.get('date_started') or todo.get('start_date', ''))}</span> | Due: <span id="dateDue">{html_escape(todo.get('due_date', ''))}</span></p>
    </section>
    <section>
      <h2>Edit</h2>
      <div class="row">
        <div><label>Title</label><input id="editTitle"></div>
        <div><label>Category</label><select id="editCategory"></select></div>
        <div><label>Status</label><select id="editStatus"><option value="open">Open</option><option value="done">Done</option><option value="blocked">Blocked</option></select></div>
      </div>
      <div class="row">
        <div><label>Date started</label><input id="editDateStarted" type="date"></div>
        <div><label>Due date</label><input id="editDueDate" type="date"></div>
        <div><label>Next step</label><input id="editNextStep"></div>
      </div>
      <label id="contextLabel">{html_escape(detail.get('context_label', 'Project Info'))}</label>
      <textarea id="editOffering"></textarea>
      <label>Expenses</label>
      <textarea id="editExpenses"></textarea>
      <label>Tasks</label>
      <textarea id="editTasks"></textarea>
      <label>Work log</label>
      <textarea id="editWorkLog"></textarea>
      <label>Notes</label>
      <textarea id="editNotes"></textarea>
      <div class="actions">
        <button class="primary" onclick="saveProject()">Save</button>
        <button onclick="setStatusValue('done')">Mark Done</button>
        <button onclick="setStatusValue('open')">Reopen</button>
        <button class="danger" onclick="deleteProject()">Delete</button>
      </div>
    </section>
    <section>
      <h2>Uploads</h2>
      <form id="assetForm">
        <input type="hidden" name="todo_id" value="{html_escape(todo.get('id', ''))}">
        <div class="row">
          <div><label>Attach to</label><select name="type"><option value="expense">Expense file</option><option value="task">Task file</option><option value="work_log">Work log file</option><option value="receipt">Receipt</option><option value="picture">Picture</option></select></div>
          <div><label>Note</label><input name="note"></div>
          <div><label>File</label><input type="file" name="file"></div>
        </div>
        <div class="actions"><button class="primary" type="submit">Upload</button></div>
      </form>
    </section>
    <section><h2>Files</h2><ul id="assetList">{asset_rows}</ul></section>
    <section class="grid">
      <div><h2 id="contextViewLabel">{html_escape(detail.get('context_label', 'Project Info'))}</h2><pre id="contextView">{html_escape(todo.get('offering_info', detail.get('context_empty', '')))}</pre></div>
      <div><h2>Expenses</h2><pre id="expensesView">{html_escape(todo.get('expenses', ''))}</pre></div>
      <div><h2>Tasks</h2><pre id="tasksView">{html_escape(todo.get('tasks', ''))}</pre></div>
      <div><h2>Work Log</h2><pre id="workLogView">{html_escape(todo.get('work_log', ''))}</pre></div>
      <div><h2>Notes</h2><pre id="notesView">{html_escape(todo.get('notes', ''))}</pre></div>
    </section>
  </main>
  <script>
    let project = {todo_json};
    const categories = {categories_json};
    const initialCategoryDetails = {detail_json};

    function escapeHtml(value) {{
      return String(value || '').replace(/[&<>"']/g, char => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'}}[char]));
    }}

    function fillForm() {{
      document.getElementById('editTitle').value = project.title || '';
      document.getElementById('editCategory').innerHTML = Object.entries(categories).map(([key, label]) => `<option value="${{escapeHtml(key)}}">${{escapeHtml(label)}}</option>`).join('');
      document.getElementById('editCategory').value = project.category || 'home';
      document.getElementById('editStatus').value = project.status || 'open';
      document.getElementById('editDateStarted').value = project.date_started || project.start_date || '';
      document.getElementById('editDueDate').value = project.due_date || '';
      document.getElementById('editNextStep').value = project.next_step || '';
      document.getElementById('editOffering').value = project.offering_info || '';
      document.getElementById('editExpenses').value = project.expenses || '';
      document.getElementById('editTasks').value = project.tasks || '';
      document.getElementById('editWorkLog').value = project.work_log || '';
      document.getElementById('editNotes').value = project.notes || '';
    }}

    function bodyFromForm() {{
      return {{
        title: document.getElementById('editTitle').value,
        category: document.getElementById('editCategory').value,
        status: document.getElementById('editStatus').value,
        date_started: document.getElementById('editDateStarted').value,
        start_date: document.getElementById('editDateStarted').value,
        due_date: document.getElementById('editDueDate').value,
        next_step: document.getElementById('editNextStep').value,
        offering_info: document.getElementById('editOffering').value,
        expenses: document.getElementById('editExpenses').value,
        tasks: document.getElementById('editTasks').value,
        work_log: document.getElementById('editWorkLog').value,
        notes: document.getElementById('editNotes').value,
      }};
    }}

    async function saveProject() {{
      const res = await fetch(`/api/project-todos/${{encodeURIComponent(project.id)}}`, {{
        method: 'PATCH',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(bodyFromForm())
      }});
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Save failed.');
      project = data.todo;
      refreshView();
      alert(data.message || 'Saved.');
    }}

    async function setStatusValue(status) {{
      document.getElementById('editStatus').value = status;
      await saveProject();
    }}

    async function deleteProject() {{
      if (!confirm(`Delete project "${{project.title}}"? This removes the project record and uploaded files for it.`)) return;
      const res = await fetch(`/api/project-todos/${{encodeURIComponent(project.id)}}`, {{ method: 'DELETE' }});
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Delete failed.');
      document.body.innerHTML = '<main><h1>Project deleted</h1><p class="muted">This project record was removed. You can close this tab.</p></main>';
    }}

    function refreshView() {{
      const currentDetail = categoryDetailsByKey(project.category);
      document.getElementById('pageTitle').textContent = project.title || 'Project';
      document.getElementById('categoryPill').textContent = categories[project.category] || project.category || 'Project';
      document.getElementById('statusPill').textContent = project.status || 'open';
      document.getElementById('categoryDescription').textContent = currentDetail.description || initialCategoryDetails.description || '';
      document.getElementById('dateStarted').textContent = project.date_started || project.start_date || '';
      document.getElementById('dateDue').textContent = project.due_date || '';
      document.getElementById('contextLabel').textContent = currentDetail.context_label || 'Project Info';
      document.getElementById('contextViewLabel').textContent = currentDetail.context_label || 'Project Info';
      document.getElementById('contextView').textContent = project.offering_info || currentDetail.context_empty || '';
      document.getElementById('expensesView').textContent = project.expenses || '';
      document.getElementById('tasksView').textContent = project.tasks || '';
      document.getElementById('workLogView').textContent = project.work_log || '';
      document.getElementById('notesView').textContent = project.notes || '';
      fillForm();
    }}

    function categoryDetailsByKey(key) {{
      const defaults = {json.dumps(PROJECT_CATEGORY_DETAILS)};
      return defaults[key] || defaults.home;
    }}

    document.getElementById('assetForm').addEventListener('submit', async event => {{
      event.preventDefault();
      const form = new FormData(event.target);
      const res = await fetch('/api/project-assets/upload', {{ method: 'POST', body: form }});
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Upload failed.');
      location.reload();
    }});

    fillForm();
  </script>
</body>
</html>"""


def render_project_asset_rows(assets):
    return "".join(
        f"<li><a href='/{html_escape(asset.get('path', ''))}'>{html_escape(asset.get('type', 'asset'))}: {html_escape(asset.get('filename', ''))}</a> {html_escape(asset.get('note', ''))}</li>"
        for asset in assets
    ) or "<li>No files uploaded.</li>"


def html_escape(value):
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#039;")


def project_state():
    todos = project_todo_store().get("todos", [])
    summary = {
        key: {
            "label": label,
            "open": 0,
            "done": 0,
            "total": 0,
        }
        for key, label in PROJECT_CATEGORIES.items()
    }
    for todo in todos:
        category = normalize_project_category(todo.get("category"))
        bucket = summary[category]
        bucket["total"] += 1
        if str(todo.get("status", "open")).lower() in ("done", "complete", "completed"):
            bucket["done"] += 1
        else:
            bucket["open"] += 1
    return {
        "categories": PROJECT_CATEGORIES,
        "category_details": PROJECT_CATEGORY_DETAILS,
        "todos": todos,
        "summary": summary,
    }


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
            directive.setdefault("created_at", now_stamp())
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


def tracker_data(reading_plans=None):
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
        "reading_progress": reading_progress(checkins, reading_plans),
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
    daily_schedule = daily_reading_schedule()
    reading_plans = current_reading_plans(daily_schedule)
    trackers = tracker_data(reading_plans)
    return {
        "companions": companions,
        "categories": list(CATEGORIES.keys()),
        "directives": directives,
        "directive_summary": directive_summary(directives),
        "proof": proof_store().get("proof", []),
        "trackers": trackers,
        "reading_plans": reading_plans,
        "reading_progress": reading_progress_state(),
        "bible_books": bible_chapter_index(),
        "daily_reading_schedule": daily_schedule,
        "projects": project_state(),
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
    .tab-view { display: none; }
    .tab-view.active { display: block; }
    .detail-box {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #10151a;
      padding: 10px;
      min-height: 160px;
    }
    .todo-row {
      width: 100%;
      border: 1px solid var(--line);
      background: #10151a;
      color: var(--text);
      border-radius: 6px;
      padding: 8px;
      margin: 6px 0;
      text-align: left;
      cursor: pointer;
    }
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
    .schedule-reading {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      margin: 8px 0;
      background: #10151a;
    }
    .scripture-text {
      max-height: 180px;
      overflow: auto;
      white-space: pre-wrap;
      color: var(--muted);
      font-family: Georgia, serif;
      font-size: 13px;
      line-height: 1.45;
      margin-top: 8px;
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
      <button data-tab="memory">Companion</button>
      <button data-tab="directives" style="display:none;">Directive Ledger</button>
      <button data-tab="proof" style="display:none;">Proof Vault</button>
      <button data-tab="trackers">Daily Check-ins</button>
      <button data-tab="spiritual">Spiritual</button>
      <button data-tab="projects">Projects</button>
      <button data-tab="council" style="display:none;">Council Mode</button>
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
          <h2>Fitness</h2>
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
        <div class="panel full">
          <h2>Companion</h2>
          <div class="tab-row">
            <button class="active" onclick="document.querySelector('button[data-tab=memory]').click()">Memory</button>
            <button onclick="document.querySelector('button[data-tab=directives]').click()">Directives</button>
            <button onclick="document.querySelector('button[data-tab=proof]').click()">Proof</button>
            <button onclick="document.querySelector('button[data-tab=council]').click()">Council</button>
          </div>
        </div>
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
        <div class="panel full">
          <h2>Companion</h2>
          <div class="tab-row">
            <button onclick="document.querySelector('button[data-tab=memory]').click()">Memory</button>
            <button class="active" onclick="document.querySelector('button[data-tab=directives]').click()">Directives</button>
            <button onclick="document.querySelector('button[data-tab=proof]').click()">Proof</button>
            <button onclick="document.querySelector('button[data-tab=council]').click()">Council</button>
          </div>
        </div>
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
        <div class="panel full">
          <h2>Companion</h2>
          <div class="tab-row">
            <button onclick="document.querySelector('button[data-tab=memory]').click()">Memory</button>
            <button onclick="document.querySelector('button[data-tab=directives]').click()">Directives</button>
            <button class="active" onclick="document.querySelector('button[data-tab=proof]').click()">Proof</button>
            <button onclick="document.querySelector('button[data-tab=council]').click()">Council</button>
          </div>
        </div>
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
          <h2>Daily Check-ins</h2>
          <div class="tab-row" id="trackerTabs">
            <button class="active" data-tracker="summary">Summary</button>
            <button data-tracker="checkins">Check-In</button>
            <button data-tracker="journal">Journal</button>
            <button data-tracker="fitness">Fitness</button>
          </div>
          <div class="tracker-view active" data-tracker-view="summary">
            <div id="trackerSummary"></div>
            <div id="dailySummary"></div>
          </div>
          <div class="tracker-view" data-tracker-view="checkins">
            <h2>Check-In</h2>
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
                <label>Difficulty</label>
                <input id="checkinWorkDifficulty">
              </div>
              <div>
                <label>Money spent</label>
                <input id="checkinMoneySpent" type="number" min="0" step="0.01" value="0">
              </div>
            </div>
            <div class="row">
              <label><input id="checkinFood" type="checkbox" style="width:auto;"> Food on plan</label>
              <label><input id="checkinReadingCompleted" type="checkbox" style="width:auto;"> Daily reading complete</label>
              <label><input id="checkinFitnessCompleted" type="checkbox" style="width:auto;"> Fitness complete</label>
              <label><input id="checkinWorkRecurring" type="checkbox" style="width:auto;"> Recurring</label>
            </div>
            <label>Work task</label>
            <input id="checkinWorkTask">
            <label>Result</label>
            <input id="checkinWorkResult">
            <label>Next step</label>
            <input id="checkinNextStep">
            <label>Note</label>
            <textarea id="checkinNote"></textarea>
            <button class="inline primary" onclick="saveCheckin()">Save Check-In</button>
            <h2 style="margin-top:14px;">Daily Check-Ins</h2>
            <div id="checkinList"></div>
          </div>
          <div class="tracker-view" data-tracker-view="journal">
            <h2>Journal</h2>
            <label>Prompt</label>
            <input id="journalPrompt" value="General reflection.">
            <label>Mood</label>
            <input id="journalMood" type="number" min="1" max="10" value="5">
            <label>Entry</label>
            <textarea id="journalEntry"></textarea>
            <button class="inline primary" onclick="saveJournalEntry()">Save Journal Entry</button>
            <div id="journalList"></div>
          </div>
          <div class="tracker-view" data-tracker-view="fitness">
            <h2>Fitness</h2>
            <div class="field-grid">
              <div>
                <label>Session type</label>
                <input id="fitnessSessionType" value="Fitness">
              </div>
              <div>
                <label>Exercises</label>
                <input id="fitnessExercises" placeholder="Forward Fold, Walk, Strength">
              </div>
              <div>
                <label>Minutes</label>
                <input id="fitnessMinutes" type="number" min="0" value="0">
              </div>
              <div>
                <label>Progress</label>
                <input id="fitnessProgress">
              </div>
            </div>
            <label>Notes</label>
            <textarea id="fitnessNotes"></textarea>
            <button class="inline primary" onclick="saveFitnessEntry()">Save Fitness Entry</button>
            <div id="fitnessList"></div>
          </div>
        </div>
      </div>
    </section>
    <section id="spiritual">
      <div class="grid">
        <div class="panel full">
          <h2>Spiritual</h2>
          <div class="tab-row" id="spiritualTabs">
            <button class="active" data-spiritual="summary">Summary</button>
            <button data-spiritual="daily">Daily Reading</button>
            <button data-spiritual="extra">Extra Reading</button>
            <button data-spiritual="prayer">Prayer</button>
          </div>
          <div class="tab-view active" data-spiritual-view="summary">
            <div id="spiritualSummary"></div>
          </div>
          <div class="tab-view" data-spiritual-view="daily">
            <div id="dailyReadingSchedule"></div>
          </div>
          <div class="tab-view" data-spiritual-view="extra">
            <div class="row">
              <div>
                <label>Book</label>
                <select id="extraBookSelect"></select>
              </div>
              <div>
                <label>Chapter</label>
                <select id="extraChapterSelect"></select>
              </div>
            </div>
            <button class="inline primary" onclick="loadExtraReadingChapter()">Open Chapter</button>
            <button class="inline" onclick="markExtraReadingRead()">Read</button>
            <div id="extraChapterPane" class="schedule-reading"></div>
            <div id="extraReadingPlans"></div>
          </div>
          <div class="tab-view" data-spiritual-view="prayer">
            <div class="tab-row" id="prayerTabs">
              <button class="active" data-prayer="gratitude">Gratitude</button>
              <button data-prayer="requests">Requests</button>
              <button data-prayer="repentance">Repentance</button>
              <button data-prayer="service">Service</button>
              <button data-prayer="closeness">Closeness</button>
            </div>
            <div id="prayerCategoryDetail"></div>
          </div>
        </div>
      </div>
    </section>
    <section id="projects">
      <div class="grid">
        <div class="panel full">
          <h2>Projects</h2>
          <div class="tab-row" id="projectTabs">
            <button class="active" data-project="home">Home Maintenance</button>
            <button data-project="vehicle">Vehicle Maintenance</button>
            <button data-project="tech">Tech Projects</button>
          </div>
          <label>Project category</label>
          <select id="projectCategoryFilter"></select>
          <p class="muted" id="projectCategoryDescription"></p>
        </div>
        <div class="panel">
          <h2>Project Todo</h2>
          <label>Category</label>
          <select id="projectTodoCategory"></select>
          <label>Title</label>
          <input id="projectTodoTitle">
          <div class="row">
            <div>
              <label>Start date</label>
              <input id="projectTodoStartDate" type="date">
            </div>
            <div>
              <label>Due date</label>
              <input id="projectTodoDueDate" type="date">
            </div>
          </div>
          <label id="projectContextLabel">Materials / Location / Vendor Info</label>
          <textarea id="projectTodoOffering"></textarea>
          <label>Expenses</label>
          <textarea id="projectTodoExpenses"></textarea>
          <label>Tasks</label>
          <textarea id="projectTodoTasks"></textarea>
          <label>Work log</label>
          <textarea id="projectTodoWorkLog"></textarea>
          <label>Notes</label>
          <textarea id="projectTodoNotes"></textarea>
          <label>Next step</label>
          <input id="projectTodoNextStep">
          <button class="inline primary" onclick="createProjectTodo()">Add Project Todo</button>
          <button class="inline" onclick="saveProjectTodo()">Save Selected</button>
        </div>
        <div class="panel">
          <h2>Selected Project</h2>
          <div id="projectTodoDetail" class="detail-box"></div>
          <form id="projectAssetForm" style="margin-top:10px;">
            <input type="hidden" name="todo_id" id="projectAssetTodoId">
            <label>Upload type</label>
            <select name="type">
              <option value="expense">Expense file</option>
              <option value="task">Task file</option>
              <option value="work_log">Work log file</option>
              <option value="receipt">Receipt</option>
              <option value="picture">Picture</option>
            </select>
            <label>Note</label>
            <input name="note">
            <label>File</label>
            <input type="file" name="file">
            <button class="inline primary" type="submit">Upload Asset</button>
          </form>
        </div>
        <div class="panel full">
          <div id="projectTodoList"></div>
        </div>
      </div>
    </section>
    <section id="council">
      <div class="panel">
        <h2>Companion</h2>
        <div class="tab-row">
          <button onclick="document.querySelector('button[data-tab=memory]').click()">Memory</button>
          <button onclick="document.querySelector('button[data-tab=directives]').click()">Directives</button>
          <button onclick="document.querySelector('button[data-tab=proof]').click()">Proof</button>
          <button class="active" onclick="document.querySelector('button[data-tab=council]').click()">Council</button>
        </div>
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
    let selectedTrackerTab = 'summary';
    let selectedSpiritualTab = 'summary';
    let selectedPrayerCategory = 'gratitude';
    let selectedProjectCategory = 'home';
    let selectedProjectTodoId = null;

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

    document.querySelectorAll('#spiritualTabs button').forEach(button => {
      button.addEventListener('click', () => {
        selectedSpiritualTab = button.dataset.spiritual;
        renderSpiritualTabs();
      });
    });

    document.querySelectorAll('#prayerTabs button').forEach(button => {
      button.addEventListener('click', () => {
        selectedPrayerCategory = button.dataset.prayer;
        renderPrayerCategory();
      });
    });

    document.querySelectorAll('#projectTabs button').forEach(button => {
      button.addEventListener('click', () => {
        selectedProjectCategory = button.dataset.project;
        selectedProjectTodoId = null;
        renderProjects();
      });
    });

    document.getElementById('projectCategoryFilter').addEventListener('change', event => {
      selectedProjectCategory = event.target.value;
      selectedProjectTodoId = null;
      renderProjects();
    });

    document.getElementById('projectTodoCategory').addEventListener('change', event => {
      selectedProjectCategory = event.target.value;
      selectedProjectTodoId = null;
      renderProjects();
    });

    document.getElementById('companionSelect').addEventListener('change', async event => {
      selectedCompanion = event.target.value;
      await loadPacket();
      renderMemoryIndex();
    });

    document.getElementById('extraBookSelect').addEventListener('change', renderExtraChapterSelect);

    document.getElementById('checkinDate').value = new Date().toISOString().slice(0, 10);

    document.getElementById('proofForm').addEventListener('submit', async event => {
      event.preventDefault();
      const form = new FormData(event.target);
      const res = await fetch('/api/proof/upload', { method: 'POST', body: form });
      await handleResponse(res);
      event.target.reset();
      await loadState();
    });

    document.getElementById('projectAssetForm').addEventListener('submit', async event => {
      event.preventDefault();
      const todo = currentProjectTodo();
      if (!todo) {
        setStatus('Select a project todo first.');
        return;
      }
      document.getElementById('projectAssetTodoId').value = todo.id;
      const form = new FormData(event.target);
      const res = await fetch('/api/project-assets/upload', { method: 'POST', body: form });
      await handleResponse(res);
      event.target.reset();
      selectedProjectTodoId = todo.id;
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
      renderSpiritual();
      renderProjects();
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
      document.getElementById('dashPhysicalDetail').textContent = latest ? `${latest.body.fitness_completed ? 'fitness complete' : 'fitness open'}, ${latest.body.sleep_hours || 0}h sleep latest` : 'No daily check-in yet.';
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
        return `<tr><td>${escapeHtml(d.id)}</td><td>${escapeHtml(d.issuer)}</td><td>${escapeHtml(d.created_at || '')}</td><td><strong class="directive-title">${escapeHtml(d.title)}</strong><div class="directive-detail">${details}</div></td><td><span class="pill ${statusClass}">${escapeHtml(d.status)}</span></td><td>${escapeHtml(String(d.priority || ''))}</td><td>${escapeHtml(d.due_at || '')}</td><td>${escapeHtml(proof)}</td><td><button class="inline" onclick="setDirectiveStatus('${escapeJs(d.id)}','complete')">Complete</button> <button class="inline" onclick="setDirectiveStatus('${escapeJs(d.id)}','failed')">Fail</button> <button class="inline" onclick="setDirectiveStatus('${escapeJs(d.id)}','issued')">Reopen</button></td></tr>`;
      }).join('');
      const empty = '<tr><td colspan="9" class="muted">No directives in this status.</td></tr>';
      document.getElementById('directiveList').innerHTML = `<div class="scrollbox"><table><thead><tr><th>ID</th><th>Issuer</th><th>Date Added</th><th>Command</th><th>Status</th><th>Priority</th><th>Due</th><th>Proof</th><th>Actions</th></tr></thead><tbody>${rows || empty}</tbody></table></div>`;
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
      document.getElementById('trackerSummary').innerHTML = `<span class="pill">${summary.checkin_entries} check-ins</span> <span class="pill">${summary.journal_entries} journal</span> <span class="pill">${summary.task_entries} task logs</span> <span class="pill">${summary.physical_entries} fitness logs</span> ${renderTagCloud(state.trackers.work_categories, state.trackers.task_categories)}`;
      document.getElementById('dailySummary').innerHTML = renderDailySummary();
      renderTrackerTabs();
      document.getElementById('checkinList').innerHTML = renderCheckins(state.trackers.checkins);
      document.getElementById('journalList').innerHTML = renderSimpleList(state.trackers.journal, item => `${item.timestamp || ''} | mood ${item.mood || ''} | ${item.prompt || ''}`);
      document.getElementById('fitnessList').innerHTML = renderSimpleList(state.trackers.physical, item => `${item.timestamp || ''} | ${item.session_type || ''} | ${(item.exercises || []).join(', ')} | ${item.duration_minutes || 0} min | ${item.notes || ''}`);
    }

    function renderDailySummary() {
      const latest = state.trackers.latest_checkin;
      const projectSummary = Object.values(state.projects.summary || {});
      const openProjects = projectSummary.reduce((total, item) => total + (item.open || 0), 0);
      const spiritual = latest ? latest.spirit || {} : {};
      const body = latest ? latest.body || {} : {};
      const work = latest ? latest.work || {} : {};
      const readingProgress = state.reading_progress || {};
      return `<div class="grid" style="margin-top:12px;">
        <div class="panel"><h3>Latest Check-In</h3>${latest ? renderCheckinCard(latest) : '<p class="muted">No entries.</p>'}</div>
        <div class="panel"><h3>Spiritual</h3><span class="pill">${escapeHtml(readingProgress.bible_percent || 0)}% Bible read</span><span class="pill">${escapeHtml(readingProgress.bible_completed || 0)} / ${escapeHtml(readingProgress.bible_total || 0)} chapters</span><p class="muted">${escapeHtml(spiritual.reading_status || 'No reading status.')}</p></div>
        <div class="panel"><h3>Fitness</h3><p class="muted">${body.fitness_completed ? 'Fitness complete' : 'Fitness open'}, ${escapeHtml(body.sleep_hours || 0)}h sleep latest.</p></div>
        <div class="panel"><h3>Projects</h3><p class="muted">${escapeHtml(openProjects)} open project todo(s).</p><p class="muted">${escapeHtml(work.category || '')} ${escapeHtml(work.task_name || '')}</p></div>
      </div>`;
    }

    function renderTrackerTabs() {
      document.querySelectorAll('#trackerTabs button').forEach(button => {
        button.classList.toggle('active', button.dataset.tracker === selectedTrackerTab);
      });
      document.querySelectorAll('[data-tracker-view]').forEach(view => {
        view.classList.toggle('active', view.dataset.trackerView === selectedTrackerTab);
      });
    }

    function renderDailyReadingSchedule() {
      const schedule = state.daily_reading_schedule || {};
      const readings = schedule.readings || [];
      if (!schedule.source_available) {
        document.getElementById('dailyReadingSchedule').innerHTML = '<p class="muted">KJV source file is not available.</p>';
        return;
      }
      document.getElementById('dailyReadingSchedule').innerHTML = readings.map(reading => {
        const text = reading.available ? escapeHtml(reading.text || '') : 'No text found for this chapter.';
        const done = isReadingComplete(reading.id) ? '<span class="pill">read</span>' : '';
        return `<div class="schedule-reading"><div class="row"><strong>${escapeHtml(reading.label)} ${done}</strong><button class="inline" onclick="markReadingRead('${escapeJs(reading.id)}','${escapeJs(reading.label)}','daily')">Read</button></div><div class="scripture-text">${text}</div></div>`;
      }).join('');
    }

    function isReadingComplete(readingId) {
      return Boolean(((state.reading_progress || {}).completed || {})[readingId]);
    }

    async function markReadingRead(readingId, label, source) {
      const res = await fetch('/api/reading-progress', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: readingId, label, source })
      });
      await handleResponse(res);
      await loadState();
    }

    function renderSpiritual() {
      renderSpiritualTabs();
      renderSpiritualSummary();
      renderExtraBookSelect();
      renderDailyReadingSchedule();
      renderExtraReadingPlans();
      renderPrayerCategory();
    }

    function renderSpiritualTabs() {
      document.querySelectorAll('#spiritualTabs button').forEach(button => {
        button.classList.toggle('active', button.dataset.spiritual === selectedSpiritualTab);
      });
      document.querySelectorAll('[data-spiritual-view]').forEach(view => {
        view.classList.toggle('active', view.dataset.spiritualView === selectedSpiritualTab);
      });
    }

    function renderSpiritualSummary() {
      const progress = state.reading_progress || {};
      const psalm119 = progress.psalm_119 || {};
      const readings = ((state.daily_reading_schedule || {}).readings || []);
      const dailyRead = readings.filter(reading => isReadingComplete(reading.id)).length;
      document.getElementById('spiritualSummary').innerHTML = `<div class="grid">
        <div><h3>Bible Progress</h3><span class="pill">${escapeHtml(progress.bible_percent || 0)}% read</span><span class="pill">${escapeHtml(progress.bible_completed || 0)} / ${escapeHtml(progress.bible_total || 0)} chapters</span></div>
        <div><h3>Psalm 119 Sections</h3><span class="pill">${escapeHtml(psalm119.percent || 0)}% read</span><span class="pill">${escapeHtml(psalm119.completed || 0)} / ${escapeHtml(psalm119.total || 0)} sections</span></div>
        <div><h3>Daily Reading</h3><span class="pill">${escapeHtml(dailyRead)} / ${escapeHtml(readings.length)} read today</span><p class="muted">${escapeHtml((state.daily_reading_schedule || {}).date || '')}</p></div>
      </div>`;
    }

    function renderExtraBookSelect() {
      const select = document.getElementById('extraBookSelect');
      const current = select.value || 'Genesis';
      const books = state.bible_books || [];
      select.innerHTML = books.map(book => `<option value="${escapeHtml(book.book)}">${escapeHtml(book.book)}</option>`).join('');
      if (books.some(book => book.book === current)) select.value = current;
      renderExtraChapterSelect();
    }

    function renderExtraChapterSelect() {
      const bookName = document.getElementById('extraBookSelect').value;
      const chapterSelect = document.getElementById('extraChapterSelect');
      const book = (state.bible_books || []).find(item => item.book === bookName);
      const current = chapterSelect.value;
      const chapters = book ? book.chapters : [];
      chapterSelect.innerHTML = chapters.map(chapter => `<option value="${escapeHtml(chapter.chapter)}">${escapeHtml(chapter.chapter)}</option>`).join('');
      if (current && chapters.some(chapter => String(chapter.chapter) === String(current))) chapterSelect.value = current;
    }

    async function loadExtraReadingChapter() {
      const book = document.getElementById('extraBookSelect').value;
      const chapter = document.getElementById('extraChapterSelect').value;
      const res = await fetch(`/api/bible/chapter?book=${encodeURIComponent(book)}&chapter=${encodeURIComponent(chapter)}`);
      const data = await handleResponse(res, false);
      const done = isReadingComplete(data.id) ? '<span class="pill">read</span>' : '';
      document.getElementById('extraChapterPane').innerHTML = `<h3>${escapeHtml(data.label)} ${done}</h3><div class="scripture-text">${escapeHtml(data.text || 'No text found.')}</div>`;
    }

    async function markExtraReadingRead() {
      const book = document.getElementById('extraBookSelect').value;
      const chapter = document.getElementById('extraChapterSelect').value;
      const id = `${book.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')}-${chapter}`;
      await markReadingRead(id, `${book} ${chapter}`, 'extra');
      await loadExtraReadingChapter();
    }

    function renderExtraReadingPlans() {
      const blocks = Object.entries(state.reading_plans || {})
        .filter(([plan]) => plan !== 'KJV Daily Schedule')
        .map(([plan, sections]) => {
          const items = sections.map(section => `<button class="todo-row" onclick="markReadingRead('${escapeJs(section.id)}','${escapeJs(section.label)}','${escapeJs(plan)}')"><strong>${escapeHtml(section.label)} ${isReadingComplete(section.id) ? '<span class="pill">read</span>' : ''}</strong><br><span class="muted">${escapeHtml(plan)}</span></button>`).join('');
          return `<div class="panel" style="margin-bottom:10px;"><h3>${escapeHtml(plan)}</h3>${items}</div>`;
        }).join('');
      document.getElementById('extraReadingPlans').innerHTML = blocks || '<p class="muted">No extra reading plans.</p>';
    }

    function renderPrayerCategory() {
      document.querySelectorAll('#prayerTabs button').forEach(button => {
        button.classList.toggle('active', button.dataset.prayer === selectedPrayerCategory);
      });
      const details = {
        gratitude: ['Gratitude', 'Use the Check-In gratitude field for thanks, praise, and answered prayer notes.'],
        requests: ['Requests', 'Use the prayer response field for requests, burdens, and follow-up answers.'],
        repentance: ['Repentance', 'Use the repentance / forgiveness field for confession and repair notes.'],
        service: ['Service', 'Use the service field for people helped, mercy work, and practical obedience.'],
        closeness: ['Closeness', 'Use the felt close / far from God field for spiritual distance and nearness notes.'],
      };
      const [title, text] = details[selectedPrayerCategory] || details.gratitude;
      document.getElementById('prayerCategoryDetail').innerHTML = `<div class="detail-box"><h3>${escapeHtml(title)}</h3><p class="muted">${escapeHtml(text)}</p><button class="inline" onclick="selectedTrackerTab='checkins'; renderTrackerTabs(); document.querySelector('button[data-tab=trackers]').click();">Open Check-In</button></div>`;
    }

    function renderProjects() {
      const projects = state.projects || { categories: {}, todos: [], summary: {} };
      document.querySelectorAll('#projectTabs button').forEach(button => {
        button.classList.toggle('active', button.dataset.project === selectedProjectCategory);
      });
      renderProjectCategorySelects(projects.categories || {});
      document.getElementById('projectTodoCategory').value = selectedProjectCategory;
      document.getElementById('projectCategoryFilter').value = selectedProjectCategory;
      updateProjectCategoryText();
      const todos = (projects.todos || []).filter(todo => todo.category === selectedProjectCategory);
      if (!todos.some(todo => todo.id === selectedProjectTodoId)) selectedProjectTodoId = todos.length ? todos[0].id : null;
      document.getElementById('projectTodoList').innerHTML = todos.length
        ? todos.map(todo => {
            const selected = todo.id === selectedProjectTodoId ? '<span class="pill">selected</span>' : '';
            return `<div class="todo-row"><strong>${escapeHtml(todo.title)}</strong> ${selected}<br><span class="muted">${escapeHtml(todo.status || 'open')} | added ${escapeHtml(todo.created_at || '')} | started ${escapeHtml(todo.date_started || todo.start_date || '')} | next ${escapeHtml(todo.next_step || '')}</span><br><button class="inline" onclick="selectProjectTodo('${escapeJs(todo.id)}')">Select</button> <a class="inline primary" href="/projects/${encodeURIComponent(todo.id)}" target="_blank">Open page</a> <button class="inline" onclick="loadProjectTodoIntoForm('${escapeJs(todo.id)}')">Edit</button> <button class="inline" onclick="deleteProjectTodo('${escapeJs(todo.id)}')">Delete</button></div>`;
          }).join('')
        : '<p class="muted">No projects in this category.</p>';
      renderProjectTodoDetail();
    }

    function renderProjectCategorySelects(categories) {
      const options = Object.entries(categories).map(([key, label]) => `<option value="${escapeHtml(key)}">${escapeHtml(label)}</option>`).join('');
      document.getElementById('projectCategoryFilter').innerHTML = options;
      document.getElementById('projectTodoCategory').innerHTML = options;
    }

    function updateProjectCategoryText() {
      const details = (((state.projects || {}).category_details || {})[selectedProjectCategory]) || {};
      document.getElementById('projectCategoryDescription').textContent = details.description || '';
      document.getElementById('projectContextLabel').textContent = details.context_label || 'Project Info';
    }

    function selectProjectTodo(todoId) {
      selectedProjectTodoId = todoId;
      renderProjectTodoDetail();
    }

    function currentProjectTodo() {
      return ((state.projects || {}).todos || []).find(todo => todo.id === selectedProjectTodoId);
    }

    function renderProjectTodoDetail() {
      const todo = currentProjectTodo();
      if (!todo) {
        document.getElementById('projectTodoDetail').innerHTML = '<p class="muted">Select a project to open, edit, upload files, or delete it.</p>';
        return;
      }
      const category = ((state.projects || {}).categories || {})[todo.category] || todo.category;
      const assets = (todo.assets || []).map(asset => `<li><a href="/${escapeHtml(asset.path)}" target="_blank">${escapeHtml(asset.type)}: ${escapeHtml(asset.filename)}</a> <span class="muted">${escapeHtml(asset.note || '')}</span></li>`).join('') || '<li class="muted">No files uploaded.</li>';
      document.getElementById('projectAssetTodoId').value = todo.id;
      document.getElementById('projectTodoDetail').innerHTML = `<h3>${escapeHtml(todo.title)}</h3><span class="pill">${escapeHtml(category)}</span><span class="pill">${escapeHtml(todo.status || 'open')}</span><p class="muted">Added ${escapeHtml(todo.created_at || '')} | Started ${escapeHtml(todo.date_started || todo.start_date || '')}</p><a class="inline primary" href="/projects/${encodeURIComponent(todo.id)}" target="_blank">Open page</a> <button class="inline" onclick="loadProjectTodoIntoForm('${escapeJs(todo.id)}')">Edit</button> <button class="inline" onclick="setProjectTodoStatus('${escapeJs(todo.id)}','done')">Mark Done</button> <button class="inline" onclick="setProjectTodoStatus('${escapeJs(todo.id)}','open')">Reopen</button> <button class="inline" onclick="deleteProjectTodo('${escapeJs(todo.id)}')">Delete</button><h3>Files</h3><ul>${assets}</ul>`;
    }

    function projectTodoBodyFromForm() {
      return {
        category: document.getElementById('projectTodoCategory').value,
        title: document.getElementById('projectTodoTitle').value,
        date_started: document.getElementById('projectTodoStartDate').value,
        start_date: document.getElementById('projectTodoStartDate').value,
        due_date: document.getElementById('projectTodoDueDate').value,
        offering_info: document.getElementById('projectTodoOffering').value,
        expenses: document.getElementById('projectTodoExpenses').value,
        tasks: document.getElementById('projectTodoTasks').value,
        work_log: document.getElementById('projectTodoWorkLog').value,
        notes: document.getElementById('projectTodoNotes').value,
        next_step: document.getElementById('projectTodoNextStep').value,
      };
    }

    async function createProjectTodo() {
      const body = projectTodoBodyFromForm();
      const res = await fetch('/api/project-todos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await handleResponse(res);
      selectedProjectTodoId = data.todo.id;
      selectedProjectCategory = data.todo.category;
      for (const id of ['projectTodoTitle', 'projectTodoStartDate', 'projectTodoDueDate', 'projectTodoOffering', 'projectTodoExpenses', 'projectTodoTasks', 'projectTodoWorkLog', 'projectTodoNotes', 'projectTodoNextStep']) {
        document.getElementById(id).value = '';
      }
      await loadState();
    }

    function loadProjectTodoIntoForm(todoId) {
      const todo = ((state.projects || {}).todos || []).find(item => item.id === todoId);
      if (!todo) return;
      selectedProjectTodoId = todo.id;
      selectedProjectCategory = todo.category;
      document.getElementById('projectTodoCategory').value = todo.category;
      updateProjectCategoryText();
      document.getElementById('projectTodoTitle').value = todo.title || '';
      document.getElementById('projectTodoStartDate').value = todo.date_started || todo.start_date || '';
      document.getElementById('projectTodoDueDate').value = todo.due_date || '';
      document.getElementById('projectTodoOffering').value = todo.offering_info || '';
      document.getElementById('projectTodoExpenses').value = todo.expenses || '';
      document.getElementById('projectTodoTasks').value = todo.tasks || '';
      document.getElementById('projectTodoWorkLog').value = todo.work_log || '';
      document.getElementById('projectTodoNotes').value = todo.notes || '';
      document.getElementById('projectTodoNextStep').value = todo.next_step || '';
      renderProjects();
    }

    async function saveProjectTodo() {
      const todo = currentProjectTodo();
      if (!todo) {
        setStatus('Select a project first.');
        return;
      }
      const res = await fetch(`/api/project-todos/${encodeURIComponent(todo.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(projectTodoBodyFromForm())
      });
      const data = await handleResponse(res);
      selectedProjectTodoId = data.todo.id;
      selectedProjectCategory = data.todo.category;
      await loadState();
    }

    async function deleteProjectTodo(todoId) {
      const todo = ((state.projects || {}).todos || []).find(item => item.id === todoId);
      if (!todo || !confirm(`Delete project "${todo.title}"? This removes its uploaded files too.`)) return;
      const res = await fetch(`/api/project-todos/${encodeURIComponent(todoId)}`, { method: 'DELETE' });
      await handleResponse(res);
      if (selectedProjectTodoId === todoId) selectedProjectTodoId = null;
      await loadState();
    }

    async function setProjectTodoStatus(todoId, status) {
      const res = await fetch(`/api/project-todos/${encodeURIComponent(todoId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status })
      });
      await handleResponse(res);
      await loadState();
    }

    async function saveJournalEntry() {
      const body = {
        prompt: document.getElementById('journalPrompt').value,
        mood: document.getElementById('journalMood').value,
        entry: document.getElementById('journalEntry').value,
      };
      const res = await fetch('/api/journal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      document.getElementById('journalEntry').value = '';
      await loadState();
    }

    async function saveFitnessEntry() {
      const body = {
        session_type: document.getElementById('fitnessSessionType').value,
        exercises: document.getElementById('fitnessExercises').value,
        duration_minutes: document.getElementById('fitnessMinutes').value,
        progress: document.getElementById('fitnessProgress').value,
        notes: document.getElementById('fitnessNotes').value,
      };
      const res = await fetch('/api/fitness', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      for (const id of ['fitnessExercises', 'fitnessProgress', 'fitnessNotes']) {
        document.getElementById(id).value = '';
      }
      document.getElementById('fitnessMinutes').value = '0';
      await loadState();
    }

    async function saveCheckin() {
      const body = {
        date: document.getElementById('checkinDate').value,
        mood: document.getElementById('checkinMood').value,
        energy: document.getElementById('checkinEnergy').value,
        sleep_hours: document.getElementById('checkinSleep').value,
        food_on_plan: document.getElementById('checkinFood').checked,
        fitness_completed: document.getElementById('checkinFitnessCompleted').checked,
        prayer: false,
        scripture: document.getElementById('checkinReadingCompleted').checked,
        reading_plan: '',
        reading_section: '',
        reading_checklist: [],
        assigned_reading: '',
        reading_completed: document.getElementById('checkinReadingCompleted').checked,
        reading_minutes: 0,
        reading_status: document.getElementById('checkinReadingCompleted').checked ? 'daily reading complete' : '',
        favorite_verse: '',
        application: '',
        prayer_response: '',
        gratitude: '',
        repentance: '',
        service: '',
        felt_close: '',
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
      for (const id of ['checkinWorkTask', 'checkinWorkDifficulty', 'checkinWorkResult', 'checkinNextStep', 'checkinNote']) {
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
      const readingStatus = spirit.reading_completed ? 'daily reading complete' : 'daily reading open';
      const fitnessStatus = body.fitness_completed ? 'fitness complete' : 'fitness open';
      return `<strong>${escapeHtml(item.date || item.id)}</strong><br><span class="muted">mood ${escapeHtml(mind.mood || '')}, energy ${escapeHtml(body.energy || '')}, sleep ${escapeHtml(body.sleep_hours || 0)}h, ${escapeHtml(fitnessStatus)}</span><br><span class="muted">${escapeHtml(work.category || '')} ${escapeHtml(work.minutes || 0)}m | ${escapeHtml(work.task_name || '')} | next ${escapeHtml(work.next_step || '')}</span><br><span class="muted">${escapeHtml(readingStatus)}</span><br><span>${escapeHtml(mind.note || work.result || '')}</span>`;
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
            elif path == "/api/bible/chapter":
                params = parse_qs(parsed.query)
                book = params.get("book", [""])[0]
                chapter = clean_int(params.get("chapter", ["0"])[0], default=0, minimum=1)
                self.send_json({
                    "id": bible_chapter_id(book, chapter),
                    "label": f"{book} {chapter}",
                    "book": book,
                    "chapter": chapter,
                    "text": kjv_chapter_text(book, chapter),
                })
            elif path.startswith("/projects/"):
                todo_id = unquote(path.rsplit("/", 1)[1])
                self.send_html(render_project_page(todo_id))
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
            elif path.startswith("/project_assets/"):
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
            elif path == "/api/journal":
                entry = create_journal_entry(self.read_json_body())
                self.send_json({"message": "Saved journal entry.", "entry": entry})
            elif path == "/api/fitness":
                entry = create_fitness_entry(self.read_json_body())
                self.send_json({"message": "Saved fitness entry.", "entry": entry})
            elif path == "/api/project-todos":
                todo = create_project_todo(self.read_json_body())
                self.send_json({"message": f"Created {todo['id']}.", "todo": todo})
            elif path == "/api/reading-progress":
                reading = mark_reading_complete(self.read_json_body())
                self.send_json({"message": f"Marked {reading['label']} read.", "reading": reading})
            elif path == "/api/project-assets/upload":
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        "REQUEST_METHOD": "POST",
                        "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    },
                )
                asset = create_project_asset(form)
                self.send_json({"message": f"Uploaded {asset['id']}.", "asset": asset})
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
            elif path.startswith("/api/project-todos/"):
                todo_id = unquote(path.rsplit("/", 1)[1])
                todo = update_project_todo(todo_id, self.read_json_body())
                self.send_json({"message": f"Updated {todo['id']}.", "todo": todo})
            else:
                self.send_error_json(404, "Not found.")
        except Exception as exc:
            self.send_error_json(400, str(exc))

    def do_DELETE(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/project-todos/"):
                todo_id = unquote(path.rsplit("/", 1)[1])
                todo = delete_project_todo(todo_id)
                self.send_json({"message": f"Deleted {todo['id']}.", "todo": todo})
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
