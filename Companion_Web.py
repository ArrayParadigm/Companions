import cgi
import argparse
import calendar as calendar_lib
import base64
import binascii
import contextvars
import copy
import hashlib
import hmac
import json
import math
import mimetypes
import os
import re
import secrets
import shutil
import time
import uuid
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

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
USERS_FILE = DATA_DIR / "users.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
DIRECTIVES_FILE = DATA_DIR / "directives.json"
PROOF_FILE = DATA_DIR / "proof_metadata.json"
CHECKINS_FILE = DATA_DIR / "daily_checkins.json"
PROJECT_TODOS_FILE = DATA_DIR / "project_todos.json"
READING_PROGRESS_FILE = DATA_DIR / "reading_progress.json"
CHORES_FILE = DATA_DIR / "chores.json"
DIET_FILE = DATA_DIR / "diet.json"
FITNESS_FILE = DATA_DIR / "fitness.json"
CALENDAR_FILE = DATA_DIR / "calendar.json"
KJV_FILE = APP_DIR / "kjv.txt"
DAILY_SCHEDULE_PLAN = "KJV Daily Schedule"
ARRAY_PROFILE = "Array"
CURRENT_PROFILE = contextvars.ContextVar("current_profile", default=ARRAY_PROFILE)
SESSION_COOKIE = "companion_session"
PASSWORD_ITERATIONS = 260000
SESSIONS = {}
MAX_JSON_BYTES = 512 * 1024
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_PROOF_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".json", ".md", ".pdf", ".png", ".txt", ".webp"}
ALLOWED_PROJECT_EXTENSIONS = {
    ".csv", ".doc", ".docx", ".gif", ".jpeg", ".jpg", ".json", ".md", ".pdf", ".png",
    ".txt", ".webp", ".xls", ".xlsx",
}
ALLOWED_UPLOAD_MIME_PREFIXES = ("image/", "text/")
ALLOWED_UPLOAD_MIME_TYPES = {
    "application/json",
    "application/msword",
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
ACCESS_CATEGORIES = {
    "trackers": "Daily Check-ins",
    "fitness": "Fitness",
    "spiritual": "Spiritual",
    "projects": "Projects",
    "chores": "Chores",
    "diet": "Diet",
}

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

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CALENDAR_CATEGORY_LABELS = {
    "fitness": "Fitness",
    "projects": "Projects",
    "chores": "Chores",
    "diet": "Diet",
    "spiritual": "Spiritual",
    "directives": "Companion Directives",
    "general": "General",
}
DEFAULT_DIRECTIVE_TIMEZONE = "America/Chicago"
DIRECTIVE_TYPES = [
    "health",
    "work",
    "family",
    "fitness",
    "princess_campaign",
    "tiny_tyrant",
    "project",
    "spiritual",
    "manual",
]
DIRECTIVE_EXPORT_FIELDS = [
    "id",
    "issuer",
    "title",
    "details",
    "status",
    "priority",
    "due_at",
    "due_timezone",
    "type",
    "tags",
    "proof_required",
    "created_at",
    "updated_at",
]


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


def normalize_profile_name(name):
    cleaned = re.sub(r"\s+", " ", str(name or "").strip())
    return cleaned or ARRAY_PROFILE


def is_array_profile(name):
    return normalize_profile_name(name).lower() == ARRAY_PROFILE.lower()


def profile_slug(name):
    return safe_name(normalize_profile_name(name)).lower() or "profile"


def profile_folder(name):
    return DATA_DIR / "users" / profile_slug(name)


def default_access(name):
    allowed = True if is_array_profile(name) else False
    return {key: allowed for key in ACCESS_CATEGORIES}


def default_profile(name, display_name=None):
    clean_name = normalize_profile_name(name)
    owner = is_array_profile(clean_name)
    return {
        "name": clean_name,
        "display_name": str(display_name or clean_name).strip() or clean_name,
        "role": "owner" if owner else "user",
        "approved": owner,
        "active": owner,
        "access": default_access(clean_name),
        "password_hash": "",
        "password_salt": "",
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
    }


def normalize_profile_record(profile):
    clean_name = normalize_profile_name(profile.get("name"))
    owner = is_array_profile(clean_name)
    normalized = default_profile(clean_name, profile.get("display_name"))
    normalized.update(profile)
    normalized["name"] = clean_name
    normalized["display_name"] = str(normalized.get("display_name") or clean_name).strip() or clean_name
    normalized["role"] = "owner" if owner else normalized.get("role", "user")
    normalized["approved"] = True if owner else clean_bool(normalized.get("approved"))
    normalized["active"] = clean_bool(normalized.get("active", True))
    access = default_access(clean_name)
    access.update({key: clean_bool(value) for key, value in dict(normalized.get("access") or {}).items() if key in ACCESS_CATEGORIES})
    normalized["access"] = access
    normalized.setdefault("password_hash", "")
    normalized.setdefault("password_salt", "")
    normalized.setdefault("created_at", now_stamp())
    normalized["updated_at"] = normalized.get("updated_at") or normalized.get("created_at") or now_stamp()
    return normalized


def user_store():
    if not USERS_FILE.exists():
        write_json(USERS_FILE, {"profiles": [default_profile(ARRAY_PROFILE)]})
    store = read_json(USERS_FILE, {"profiles": []})
    profiles = [normalize_profile_record(profile) for profile in store.setdefault("profiles", [])]
    if not any(is_array_profile(profile.get("name")) for profile in profiles):
        profiles.insert(0, default_profile(ARRAY_PROFILE))
    store["profiles"] = profiles
    write_json(USERS_FILE, store)
    return store


def settings_store():
    ensure_data_files()
    store = read_json(SETTINGS_FILE, {"session_timeout_minutes": 30})
    timeout = clean_int(store.get("session_timeout_minutes"), default=30, minimum=1, maximum=1440)
    store["session_timeout_minutes"] = timeout
    if not SETTINGS_FILE.exists():
        write_json(SETTINGS_FILE, store)
    return store


def update_settings(data):
    store = settings_store()
    if "session_timeout_minutes" in data:
        store["session_timeout_minutes"] = clean_int(data.get("session_timeout_minutes"), default=30, minimum=1, maximum=1440)
    write_json(SETTINGS_FILE, store)
    return store


def ensure_user_profile(name):
    clean_name = normalize_profile_name(name)
    store = user_store()
    for profile in store.get("profiles", []):
        if normalize_profile_name(profile.get("name")).lower() == clean_name.lower():
            profile = normalize_profile_record(profile)
            return profile
    profile = default_profile(clean_name)
    store.setdefault("profiles", []).append(profile)
    write_json(USERS_FILE, store)
    ensure_profile_data_files(profile["name"])
    return profile


def create_user_profile(data):
    name = normalize_profile_name(data.get("name"))
    if is_array_profile(name):
        raise ValueError("Array already exists.")
    store = user_store()
    if any(normalize_profile_name(profile.get("name")).lower() == name.lower() for profile in store.get("profiles", [])):
        raise ValueError(f"Profile already exists: {name}")
    profile = default_profile(name, data.get("display_name"))
    set_profile_password(profile, str(data.get("password") or ""))
    profile["approved"] = False
    profile["active"] = False
    store.setdefault("profiles", []).append(profile)
    write_json(USERS_FILE, store)
    ensure_profile_data_files(profile["name"])
    return profile


def update_user_profile(name, data):
    clean_name = normalize_profile_name(name)
    store = user_store()
    for profile in store.get("profiles", []):
        if normalize_profile_name(profile.get("name")).lower() == clean_name.lower():
            if "display_name" in data:
                profile["display_name"] = str(data.get("display_name") or profile.get("name") or clean_name).strip() or clean_name
            profile["updated_at"] = now_stamp()
            write_json(USERS_FILE, store)
            return profile
    raise ValueError(f"Profile not found: {clean_name}")


def admin_update_user_profile(name, data):
    clean_name = normalize_profile_name(name)
    store = user_store()
    for profile in store.get("profiles", []):
        if normalize_profile_name(profile.get("name")).lower() == clean_name.lower():
            owner = is_array_profile(profile.get("name"))
            if "display_name" in data:
                profile["display_name"] = str(data.get("display_name") or profile.get("name") or clean_name).strip() or clean_name
            if not owner:
                if "approved" in data:
                    profile["approved"] = clean_bool(data.get("approved"))
                if "active" in data:
                    profile["active"] = clean_bool(data.get("active"))
                if "access" in data:
                    access = default_access(profile.get("name"))
                    access.update({key: clean_bool(value) for key, value in dict(data.get("access") or {}).items() if key in ACCESS_CATEGORIES})
                    profile["access"] = access
            if str(data.get("new_password") or "").strip():
                set_profile_password(profile, str(data.get("new_password") or ""))
            profile["updated_at"] = now_stamp()
            write_json(USERS_FILE, store)
            return profile
    raise ValueError(f"Profile not found: {clean_name}")


def public_profile(profile):
    normalized = normalize_profile_record(profile)
    access = default_access(normalized.get("name"))
    if not is_array_profile(normalized.get("name")):
        access.update({key: clean_bool(value) for key, value in dict(normalized.get("access") or {}).items() if key in ACCESS_CATEGORIES})
    return {
        "name": normalized.get("name", ""),
        "display_name": normalized.get("display_name") or normalized.get("name", ""),
        "role": normalized.get("role", "user"),
        "approved": clean_bool(normalized.get("approved")),
        "active": clean_bool(normalized.get("active")),
        "access": access,
        "has_password": bool(normalized.get("password_hash")),
    }


def hash_password(password, salt=None):
    password = str(password or "")
    if not password:
        raise ValueError("Password is required.")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS)
    return salt, base64.b64encode(digest).decode("ascii")


def set_profile_password(profile, password):
    salt, password_hash = hash_password(password)
    profile["password_salt"] = salt
    profile["password_hash"] = password_hash
    profile["updated_at"] = now_stamp()


def verify_profile_password(profile, password):
    if not profile.get("password_hash") or not profile.get("password_salt"):
        return False
    try:
        _, attempted = hash_password(password, profile.get("password_salt"))
    except ValueError:
        return False
    return hmac.compare_digest(attempted, profile.get("password_hash", ""))


def profile_by_name(name):
    clean_name = normalize_profile_name(name)
    for profile in user_store().get("profiles", []):
        if normalize_profile_name(profile.get("name")).lower() == clean_name.lower():
            return profile
    raise ValueError(f"Profile not found: {clean_name}")


def array_needs_bootstrap():
    profile = profile_by_name(ARRAY_PROFILE)
    return not bool(profile.get("password_hash"))


def bootstrap_array_password(data):
    if not array_needs_bootstrap():
        raise ValueError("Array password is already set.")
    password = str(data.get("password") or "")
    store = user_store()
    for profile in store.get("profiles", []):
        if is_array_profile(profile.get("name")):
            set_profile_password(profile, password)
            profile["approved"] = True
            profile["active"] = True
            profile["access"] = default_access(ARRAY_PROFILE)
            write_json(USERS_FILE, store)
            return public_profile(profile)
    raise ValueError("Array profile was not found.")


def create_session(profile_name):
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {"profile": normalize_profile_name(profile_name), "last_seen": time.time()}
    return token


def destroy_session(token):
    if token:
        SESSIONS.pop(token, None)


def session_timeout_seconds():
    return settings_store().get("session_timeout_minutes", 30) * 60


def session_profile(token, refresh=True):
    if not token or token not in SESSIONS:
        return None
    session = SESSIONS[token]
    if time.time() - float(session.get("last_seen", 0)) > session_timeout_seconds():
        destroy_session(token)
        return None
    if refresh:
        session["last_seen"] = time.time()
    try:
        profile = profile_by_name(session.get("profile"))
        if not clean_bool(profile.get("active", True)) or not clean_bool(profile.get("approved", False)):
            destroy_session(token)
            return None
        return profile
    except ValueError:
        destroy_session(token)
        return None


def login_user(data):
    profile = profile_by_name(data.get("name"))
    if not verify_profile_password(profile, data.get("password", "")):
        raise ValueError("Invalid profile or password.")
    if not clean_bool(profile.get("active", True)):
        raise ValueError("This account is inactive.")
    if not clean_bool(profile.get("approved", False)):
        raise ValueError("This account is waiting for Array approval.")
    return create_session(profile.get("name")), public_profile(profile)


def change_own_password(profile_name, data):
    store = user_store()
    clean_name = normalize_profile_name(profile_name)
    for profile in store.get("profiles", []):
        if normalize_profile_name(profile.get("name")).lower() == clean_name.lower():
            if not verify_profile_password(profile, data.get("current_password", "")):
                raise ValueError("Current password is incorrect.")
            set_profile_password(profile, str(data.get("new_password") or ""))
            write_json(USERS_FILE, store)
            return public_profile(profile)
    raise ValueError(f"Profile not found: {clean_name}")


def public_profiles():
    return [public_profile(profile) for profile in user_store().get("profiles", [])]


def session_public_state(profile=None):
    return {
        "authenticated": bool(profile),
        "profile": public_profile(profile) if profile else None,
        "profiles": public_profiles(),
        "settings": settings_store(),
        "access_categories": ACCESS_CATEGORIES,
        "bootstrap_required": array_needs_bootstrap(),
    }


def touch_session(token):
    if token and token in SESSIONS:
        SESSIONS[token]["last_seen"] = time.time()


def active_profile_name():
    return normalize_profile_name(CURRENT_PROFILE.get())


def active_profile():
    return ensure_user_profile(active_profile_name())


def active_has_companion_access():
    return is_array_profile(active_profile_name())


def active_access_map():
    profile = active_profile()
    if is_array_profile(profile.get("name")):
        return default_access(profile.get("name"))
    access = default_access(profile.get("name"))
    access.update({key: clean_bool(value) for key, value in dict(profile.get("access") or {}).items() if key in ACCESS_CATEGORIES})
    return access


def active_can_access(category):
    if is_array_profile(active_profile_name()):
        return True
    return clean_bool(active_access_map().get(category))


def profile_data_file(filename, profile_name=None):
    name = normalize_profile_name(profile_name or active_profile_name())
    if is_array_profile(name):
        return DATA_DIR / filename
    return profile_folder(name) / filename


def profile_tracker_files(profile_name=None):
    name = normalize_profile_name(profile_name or active_profile_name())
    if is_array_profile(name):
        return TRACKER_FILES
    tracker_dir = profile_folder(name) / "tracker_data"
    return {
        "journal": tracker_dir / "journal.json",
        "tasks": tracker_dir / "tasks.json",
        "physical": tracker_dir / "physical.json",
    }


def active_project_asset_dir():
    if active_has_companion_access():
        return PROJECT_ASSET_DIR
    return PROJECT_ASSET_DIR / profile_slug(active_profile_name())


def ensure_profile_data_files(profile_name=None):
    name = normalize_profile_name(profile_name or active_profile_name())
    if is_array_profile(name):
        return
    folder = profile_folder(name)
    folder.mkdir(parents=True, exist_ok=True)
    files = {
        "daily_checkins.json": {"next_checkin_number": 1, "entries": []},
        "project_todos.json": {"next_project_todo_number": 1, "todos": []},
        "reading_progress.json": {"completed": {}, "updated_at": ""},
        "chores.json": {"next_chore_number": 1, "chores": []},
        "diet.json": {"next_inventory_number": 1, "next_food_number": 1, "inventory": [], "food_diary": []},
        "fitness.json": default_fitness_store(),
        "calendar.json": default_calendar_store(),
    }
    for filename, fallback in files.items():
        path = folder / filename
        if not path.exists():
            write_json(path, fallback)
    tracker_dir = folder / "tracker_data"
    tracker_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("journal.json", "tasks.json", "physical.json"):
        path = tracker_dir / filename
        if not path.exists():
            write_json(path, [])

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
    if not USERS_FILE.exists():
        write_json(USERS_FILE, {"profiles": [default_profile(ARRAY_PROFILE)]})
    if not SETTINGS_FILE.exists():
        write_json(SETTINGS_FILE, {"session_timeout_minutes": 30})
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
    if not CHORES_FILE.exists():
        write_json(CHORES_FILE, {"next_chore_number": 1, "chores": []})
    if not DIET_FILE.exists():
        write_json(DIET_FILE, {"next_inventory_number": 1, "next_food_number": 1, "inventory": [], "food_diary": []})
    if not FITNESS_FILE.exists():
        write_json(FITNESS_FILE, default_fitness_store())
    if not CALENDAR_FILE.exists():
        write_json(CALENDAR_FILE, default_calendar_store())


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
    store = read_json(DIRECTIVES_FILE, {"next_directive_number": 1, "directives": []})
    normalized = [normalize_directive_record(directive) for directive in store.get("directives", [])]
    old_next = store.get("next_directive_number")
    refresh_directive_counter(store)
    if normalized != store.get("directives", []) or old_next != store.get("next_directive_number"):
        store["directives"] = normalized
        write_json(DIRECTIVES_FILE, store)
    return store


def proof_store():
    ensure_data_files()
    return read_json(PROOF_FILE, {"next_proof_number": 1, "proof": []})


def checkin_store():
    ensure_data_files()
    ensure_profile_data_files()
    return read_json(profile_data_file("daily_checkins.json"), {"next_checkin_number": 1, "entries": []})


def project_todo_store():
    ensure_data_files()
    ensure_profile_data_files()
    return read_json(profile_data_file("project_todos.json"), {"next_project_todo_number": 1, "todos": []})


def reading_progress_store():
    ensure_data_files()
    ensure_profile_data_files()
    return read_json(profile_data_file("reading_progress.json"), {"completed": {}, "updated_at": ""})


def chore_store():
    ensure_data_files()
    ensure_profile_data_files()
    store = read_json(profile_data_file("chores.json"), {"next_chore_number": 1, "chores": []})
    if normalize_chore_store(store):
        write_json(profile_data_file("chores.json"), store)
    return store


def clean_date(value):
    text = str(value or "").strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def split_tags(value):
    if isinstance(value, list):
        raw_tags = value
    else:
        raw_tags = re.split(r"[,;]", str(value or ""))
    tags = []
    seen = set()
    for tag in raw_tags:
        cleaned = re.sub(r"\s+", "_", str(tag or "").strip().lower())
        cleaned = re.sub(r"[^a-z0-9_-]+", "", cleaned)
        if cleaned and cleaned not in seen:
            tags.append(cleaned)
            seen.add(cleaned)
    return tags


def clean_directive_type(value):
    text = re.sub(r"\s+", "_", str(value or "").strip().lower())
    return text if text in DIRECTIVE_TYPES else "manual"


def clean_directive_due(value):
    return str(value or "").strip()


def clean_directive_timezone(value):
    text = str(value or "").strip()
    if not text:
        return DEFAULT_DIRECTIVE_TIMEZONE
    return text[:64]


def directive_due_display(value):
    text = clean_directive_due(value)
    if not text:
        return "No due date"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{1,2}:\d{2}(\s?[AP]M)?", text, flags=re.I):
        return f"Time only: {text}"
    normalized = text.replace("T", " ")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(:\d{2})?", normalized):
        return normalized[:16]
    return text


def normalize_duplicate_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def directive_duplicate_signature(directive):
    return (
        normalize_duplicate_text(directive.get("issuer")),
        normalize_duplicate_text(directive.get("title")),
        normalize_duplicate_text(directive.get("details")),
        normalize_duplicate_text(directive.get("due_at")),
        normalize_duplicate_text(directive.get("status", "issued")),
    )


def find_duplicate_directive(store, candidate, ignore_id=""):
    candidate_signature = directive_duplicate_signature(candidate)
    for directive in store.get("directives", []):
        if ignore_id and str(directive.get("id", "")).lower() == str(ignore_id).lower():
            continue
        if directive_duplicate_signature(directive) == candidate_signature:
            return directive
    return None


def directive_number(value):
    match = re.search(r"(\d+)$", str(value or ""))
    return int(match.group(1)) if match else 0


def refresh_directive_counter(store):
    highest = max([directive_number(directive.get("id")) for directive in store.get("directives", [])] or [0])
    store["next_directive_number"] = max(clean_int(store.get("next_directive_number"), default=1, minimum=1), highest + 1)
    return store["next_directive_number"]


def normalize_directive_record(directive):
    normalized = copy.deepcopy(directive)
    normalized["issuer"] = str(normalized.get("issuer") or "Veyra").strip() or "Veyra"
    normalized["title"] = str(normalized.get("title") or "").strip()
    normalized["details"] = str(normalized.get("details") or "").strip()
    normalized["status"] = str(normalized.get("status") or "issued").strip().lower() or "issued"
    normalized["priority"] = str(normalized.get("priority") or "3").strip() or "3"
    normalized["due_at"] = clean_directive_due(normalized.get("due_at"))
    normalized["due_timezone"] = clean_directive_timezone(normalized.get("due_timezone") or normalized.get("timezone"))
    normalized["type"] = clean_directive_type(normalized.get("type"))
    normalized["tags"] = split_tags(normalized.get("tags"))
    normalized["proof_required"] = clean_bool(normalized.get("proof_required", False))
    normalized.setdefault("created_at", now_stamp())
    normalized["updated_at"] = normalized.get("updated_at") or normalized.get("created_at") or now_stamp()
    return normalized


def backup_json_file(path):
    if not path.exists():
        return None
    backup_dir = APP_DIR / "bkup" / "control_data_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{path.stem}.{stamp}{path.suffix}.bak"
    shutil.copy2(path, backup_path)
    return backup_path


def clean_recurrence_type(value):
    text = str(value or "").strip().lower().replace("_", "-")
    if text in {"weekly", "week"} or text.startswith("weekly"):
        return "weekly"
    if text in {"biweekly", "bi-weekly", "every-other-week", "every other week"} or text.startswith("bi-weekly") or text.startswith("biweekly"):
        return "biweekly"
    if text in {"monthly", "month"} or text.startswith("monthly"):
        return "monthly"
    return "none"


def clean_recurrence_day(recurrence_type, value, due_date=""):
    text = str(value or "").strip().lower()
    due = clean_date(due_date)
    if recurrence_type in {"weekly", "biweekly"}:
        if text:
            for index, name in enumerate(WEEKDAY_NAMES):
                if text in {str(index), name.lower(), name[:3].lower()} or name.lower() in text:
                    return str(index)
        if due:
            return str(due.weekday())
        return str(datetime.now().weekday())
    if recurrence_type == "monthly":
        match = re.search(r"\b([1-9]|[12]\d|3[01])\b", text)
        day = clean_int(match.group(1) if match else text, default=0, minimum=0, maximum=31)
        if day:
            return str(day)
        if due:
            return str(due.day)
        return str(datetime.now().day)
    return ""


def chore_recurrence_label(recurrence_type, recurrence_day):
    if recurrence_type == "weekly":
        return f"Weekly on {WEEKDAY_NAMES[clean_int(recurrence_day, default=0, minimum=0, maximum=6)]}"
    if recurrence_type == "biweekly":
        return f"Bi-weekly on {WEEKDAY_NAMES[clean_int(recurrence_day, default=0, minimum=0, maximum=6)]}"
    if recurrence_type == "monthly":
        return f"Monthly on day {clean_int(recurrence_day, default=1, minimum=1, maximum=31)}"
    return ""


def recurrence_from_data(data, due_date=""):
    recurrence_text = data.get("recurrence") or ""
    recurrence_type = clean_recurrence_type(data.get("recurrence_type") or recurrence_text)
    recurrence_day = clean_recurrence_day(recurrence_type, data.get("recurrence_day") or recurrence_text, due_date)
    return recurrence_type, recurrence_day, chore_recurrence_label(recurrence_type, recurrence_day)


def normalize_chore_store(store):
    changed = False
    next_number = clean_int(store.get("next_chore_number"), default=1, minimum=1)
    used_numbers = []
    for chore in store.setdefault("chores", []):
        if not chore.get("id"):
            chore["id"] = f"CHR-{next_number:04d}"
            next_number += 1
            changed = True
        match = re.match(r"^CHR-(\d+)$", str(chore.get("id", "")))
        if match:
            used_numbers.append(int(match.group(1)))
        for key, fallback in {
            "title": "Chore",
            "status": "open",
            "due_date": "",
            "notes": "",
            "created_at": now_stamp(),
            "updated_at": now_stamp(),
        }.items():
            if key not in chore:
                chore[key] = fallback
                changed = True
        recurrence_type, recurrence_day, recurrence_label = recurrence_from_data(chore, chore.get("due_date", ""))
        if chore.get("recurrence_type") != recurrence_type:
            chore["recurrence_type"] = recurrence_type
            changed = True
        if chore.get("recurrence_day") != recurrence_day:
            chore["recurrence_day"] = recurrence_day
            changed = True
        if chore.get("recurrence") != recurrence_label:
            chore["recurrence"] = recurrence_label
            changed = True
    minimum_next = max(used_numbers or [0]) + 1
    if clean_int(store.get("next_chore_number"), default=1, minimum=1) < minimum_next:
        store["next_chore_number"] = minimum_next
        changed = True
    return changed


def diet_store():
    ensure_data_files()
    ensure_profile_data_files()
    return read_json(profile_data_file("diet.json"), {"next_inventory_number": 1, "next_food_number": 1, "inventory": [], "food_diary": []})


def default_fitness_store():
    return {
        "phase": "Recruit Intake",
        "status": "Recruit Rebuild",
        "evie_note": "Dad, today is not heroic. Today is consistency. Walk, stretch, report back. No negotiating.",
        "next_readiness_number": 1,
        "next_order_number": 4,
        "next_log_number": 1,
        "next_challenge_number": 2,
        "orders": [
            {"id": "ORD-0001", "title": "10-minute walk", "details": "Easy pace. No running.", "status": "open", "type": "cardio", "due_date": "", "report": "", "skip_reason": ""},
            {"id": "ORD-0002", "title": "Mobility: hamstrings + cat-cow + calf stretch", "details": "Move gently. No aggressive back extension.", "status": "open", "type": "mobility", "due_date": "", "report": "", "skip_reason": ""},
            {"id": "ORD-0003", "title": "Small home task", "details": "One small home task. Keep it bounded.", "status": "open", "type": "discipline", "due_date": "", "report": "", "skip_reason": ""},
        ],
        "workout_plan": {
            "weekly_structure": [
                "Monday: Strength A",
                "Tuesday: Walk + Mobility",
                "Wednesday: Recovery / Easy Walk",
                "Thursday: Strength B",
                "Friday: Walk Intervals",
                "Saturday: Chore Conditioning / Yard Work",
                "Sunday: Rest + Stretch",
            ],
            "daily_minimum": ["10-minute walk", "5-minute mobility", "1 small home task"],
            "strength_a": ["Chair squats or bodyweight squats: 2x8", "Incline pushups: 2x6", "Glute bridges: 2x10", "Dead bugs: 2x6 per side", "Easy hamstring stretch: 30 seconds per side"],
            "cardio_base": ["Walk 15-20 minutes", "Last 3 minutes slightly faster", "No running unless conditioning earns it"],
            "forward_fold": ["Seated hamstring stretch: 45 seconds per side", "Standing soft-knee forward hang: 30 seconds", "Calf stretch: 30 seconds per side", "Cat-cow: 6 slow reps"],
        },
        "exercise_library": [
            {"id": "EX-0001", "name": "Dead bug", "format": "sets_reps", "media_url": "", "details": "Core stability and lower-back protection.", "warning": "Stop if sharp back pain appears.", "progression": "Increase reps or extend legs farther.", "regression": "Move arms only or legs only."},
            {"id": "EX-0002", "name": "Chair squat", "format": "sets_reps", "media_url": "", "details": "Rebuild squat pattern safely.", "warning": "Stop for sharp knee or back pain.", "progression": "Lower the chair height.", "regression": "Use hands for support."},
            {"id": "EX-0003", "name": "Incline pushup", "format": "sets_reps", "media_url": "", "details": "Rebuild push strength.", "warning": "Stop for shoulder pain.", "progression": "Lower the incline.", "regression": "Use a higher support."},
            {"id": "EX-0004", "name": "Glute bridge", "format": "sets_reps", "media_url": "", "details": "Rebuild hips and posterior chain.", "warning": "No aggressive back arch.", "progression": "Add pauses.", "regression": "Reduce range."},
            {"id": "EX-0005", "name": "Cat-cow", "format": "duration_reps", "media_url": "", "details": "Gentle spinal motion.", "warning": "Avoid forced extension.", "progression": "Slower controlled reps.", "regression": "Smaller range."},
            {"id": "EX-0006", "name": "Walk", "format": "duration_distance", "media_url": "", "details": "Easy cardio base builder.", "warning": "No running until walking base is adequate.", "progression": "Add minutes before intensity.", "regression": "Shorter walk or indoor pacing."},
        ],
        "exercise_groups": [
            {
                "id": "GRP-0001",
                "name": "Strength A",
                "type": "Strength",
                "notes": "Low-back cautious strength base.",
                "items": [
                    {"exercise_id": "EX-0002", "sets": 2, "reps": 8, "duration_seconds": 0, "distance": "", "notes": "Use chair height that keeps form clean."},
                    {"exercise_id": "EX-0003", "sets": 2, "reps": 6, "duration_seconds": 0, "distance": "", "notes": "Use a high incline if needed."},
                    {"exercise_id": "EX-0004", "sets": 2, "reps": 10, "duration_seconds": 0, "distance": "", "notes": "Pause briefly at the top."},
                ],
            },
            {
                "id": "GRP-0002",
                "name": "Cardio A",
                "type": "Cardio",
                "notes": "Simple walking base.",
                "items": [
                    {"exercise_id": "EX-0006", "sets": 1, "reps": 0, "duration_seconds": 600, "distance": "", "notes": "Easy pace."},
                ],
            },
        ],
        "next_exercise_number": 7,
        "next_group_number": 3,
        "readiness": [],
        "mobility": [],
        "cardio": [],
        "strength": [],
        "progress_notes": [],
        "body_metrics": [],
        "history": [],
        "challenges": [
            {"id": "CHG-0001", "name": "One-Mile Trial", "type": "Army-style trial", "requirements": "Walk or walk/jog one mile and report time, breathing, legs, and back.", "status": "locked", "safety_notes": "Unlock after walking base is consistent.", "report": ""},
        ],
        "safety_rules": [
            "No aggressive back bends.",
            "No forced back extension.",
            "No running until walking base is adequate.",
            "Stop if sharp pain appears.",
            "Stop if pain shoots down the leg, numbness appears, or gait changes.",
            "Scale workouts to current conditioning.",
        ],
    }


def fitness_store():
    ensure_data_files()
    ensure_profile_data_files()
    store = read_json(profile_data_file("fitness.json"), default_fitness_store())
    changed = False
    defaults = default_fitness_store()
    for key, value in defaults.items():
        if key not in store:
            store[key] = value
            changed = True
    if normalize_fitness_exercises(store):
        changed = True
    if normalize_fitness_groups(store):
        changed = True
    if changed:
        write_json(profile_data_file("fitness.json"), store)
    return store


def normalize_fitness_exercises(store):
    changed = False
    next_number = clean_int(store.get("next_exercise_number"), default=1, minimum=1)
    used_numbers = []
    for exercise in store.setdefault("exercise_library", []):
        if not exercise.get("id"):
            exercise["id"] = f"EX-{next_number:04d}"
            next_number += 1
            changed = True
        match = re.match(r"^EX-(\d+)$", str(exercise.get("id", "")))
        if match:
            used_numbers.append(int(match.group(1)))
        if "details" not in exercise:
            exercise["details"] = str(exercise.get("purpose") or "").strip()
            changed = True
        for key, fallback in {
            "format": "sets_reps",
            "media_url": "",
            "warning": "",
            "progression": "",
            "regression": "",
        }.items():
            if key not in exercise:
                exercise[key] = fallback
                changed = True
    minimum_next = max(used_numbers or [0]) + 1
    if clean_int(store.get("next_exercise_number"), default=1, minimum=1) < minimum_next:
        store["next_exercise_number"] = minimum_next
        changed = True
    return changed


def normalize_fitness_groups(store):
    changed = False
    if "exercise_groups" not in store:
        store["exercise_groups"] = default_fitness_store()["exercise_groups"]
        changed = True
    next_number = clean_int(store.get("next_group_number"), default=1, minimum=1)
    used_numbers = []
    for group in store.setdefault("exercise_groups", []):
        if not group.get("id"):
            group["id"] = f"GRP-{next_number:04d}"
            next_number += 1
            changed = True
        match = re.match(r"^GRP-(\d+)$", str(group.get("id", "")))
        if match:
            used_numbers.append(int(match.group(1)))
        group.setdefault("name", "Workout Group")
        group.setdefault("type", "")
        group.setdefault("notes", "")
        group.setdefault("items", [])
        for item in group["items"]:
            item.setdefault("exercise_id", "")
            item["sets"] = clean_int(item.get("sets"), default=0, minimum=0)
            item["reps"] = clean_int(item.get("reps"), default=0, minimum=0)
            item["duration_seconds"] = clean_int(item.get("duration_seconds"), default=0, minimum=0)
            item.setdefault("distance", "")
            item.setdefault("notes", "")
    minimum_next = max(used_numbers or [0]) + 1
    if clean_int(store.get("next_group_number"), default=1, minimum=1) < minimum_next:
        store["next_group_number"] = minimum_next
        changed = True
    return changed


def default_calendar_store():
    return {"next_event_number": 1, "events": []}


def calendar_store():
    ensure_data_files()
    ensure_profile_data_files()
    return read_json(profile_data_file("calendar.json"), default_calendar_store())


def calendar_sources(access_map=None, companion_access=False):
    access_map = access_map or active_access_map()
    sources = {key: [] for key in CALENDAR_CATEGORY_LABELS}
    if access_map.get("fitness"):
        fitness = fitness_state()
        sources["fitness"].extend({
            "id": group.get("id", ""),
            "title": group.get("name", "Workout Group"),
            "kind": "Workout Group",
        } for group in fitness.get("exercise_groups", []))
        sources["fitness"].extend({
            "id": order.get("id", ""),
            "title": order.get("title", "Fitness Order"),
            "kind": "Fitness Order",
            "date": order.get("due_date", ""),
        } for order in fitness.get("orders", []))
    if access_map.get("projects"):
        sources["projects"].extend({
            "id": todo.get("id", ""),
            "title": todo.get("title", "Project Todo"),
            "kind": PROJECT_CATEGORIES.get(todo.get("category", ""), "Project"),
            "date": todo.get("due_date", ""),
        } for todo in project_state().get("todos", []))
    if access_map.get("chores"):
        sources["chores"].extend({
            "id": chore.get("id", ""),
            "title": chore.get("title", "Chore"),
            "kind": chore.get("recurrence") or "Chore",
            "date": chore.get("due_date", ""),
        } for chore in chore_store().get("chores", []))
    if access_map.get("diet"):
        sources["diet"].append({"id": "food-diary", "title": "Food Diary", "kind": "Diet"})
    if access_map.get("spiritual"):
        sources["spiritual"].append({"id": "daily-reading", "title": "Daily Reading", "kind": "Spiritual"})
        sources["spiritual"].append({"id": "extra-reading", "title": "Extra Reading", "kind": "Spiritual"})
    if companion_access:
        sources["directives"].extend({
            "id": directive.get("id", ""),
            "title": directive.get("title", "Directive"),
            "kind": f"Directive {directive.get('status', 'issued')}",
            "date": str(directive.get("due_at") or directive.get("due") or directive.get("deadline") or "")[:10],
        } for directive in directive_store().get("directives", []))
    sources["general"].append({"id": "manual", "title": "Manual Event", "kind": "General"})
    return sources


def calendar_source_title(category, source_id, sources=None):
    if not source_id:
        return ""
    sources = sources or calendar_sources()
    for source in sources.get(category, []):
        if str(source.get("id", "")).lower() == str(source_id).lower():
            return source.get("title", "")
    return ""


def add_calendar_occurrence(events, when, title, category, source_id="", notes="", prefix="auto"):
    when = str(when or "")[:10]
    if not clean_date(when):
        return
    events.append({
        "id": f"{prefix}-{category}-{source_id or title}-{when}",
        "date": when,
        "title": title,
        "category": category,
        "source_id": source_id,
        "notes": notes,
        "generated": True,
    })


def recurring_chore_dates(chore, start_date, end_date):
    recurrence_type = chore.get("recurrence_type", "none")
    due = clean_date(chore.get("due_date", ""))
    if recurrence_type == "none":
        return [due] if due and start_date <= due <= end_date else []
    dates = []
    if recurrence_type in {"weekly", "biweekly"}:
        weekday = clean_int(chore.get("recurrence_day"), default=0, minimum=0, maximum=6)
        anchor = due or start_date
        current = start_date + timedelta(days=(weekday - start_date.weekday()) % 7)
        if recurrence_type == "biweekly":
            while current < start_date:
                current += timedelta(days=14)
            while ((current - anchor).days % 14) != 0:
                current += timedelta(days=7)
        while current <= end_date:
            if not due or current >= due:
                dates.append(current)
            current += timedelta(days=14 if recurrence_type == "biweekly" else 7)
    elif recurrence_type == "monthly":
        day = clean_int(chore.get("recurrence_day"), default=1, minimum=1, maximum=31)
        year, month = start_date.year, start_date.month
        while date(year, month, 1) <= end_date:
            last_day = calendar_lib.monthrange(year, month)[1]
            current = date(year, month, min(day, last_day))
            if start_date <= current <= end_date and (not due or current >= due):
                dates.append(current)
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
    return dates


def generated_calendar_events(access_map=None, companion_access=False):
    access_map = access_map or active_access_map()
    today = datetime.now().date()
    start_date = today - timedelta(days=90)
    end_date = today + timedelta(days=365)
    events = []
    if access_map.get("fitness"):
        for order in fitness_state().get("orders", []):
            add_calendar_occurrence(
                events,
                str(order.get("due_date") or "")[:10],
                f"Fitness: {order.get('title', 'Order')}",
                "fitness",
                order.get("id", ""),
                order.get("details", ""),
                "fit",
            )
    if access_map.get("projects"):
        for todo in project_state().get("todos", []):
            add_calendar_occurrence(
                events,
                str(todo.get("due_date") or "")[:10],
                f"Project: {todo.get('title', 'Todo')}",
                "projects",
                todo.get("id", ""),
                todo.get("next_step", ""),
                "project",
            )
    if access_map.get("chores"):
        for chore in chore_store().get("chores", []):
            if str(chore.get("status", "open")).lower() == "done":
                continue
            for chore_date in recurring_chore_dates(chore, start_date, end_date):
                add_calendar_occurrence(
                    events,
                    chore_date.isoformat(),
                    f"Chore: {chore.get('title', 'Chore')}",
                    "chores",
                    chore.get("id", ""),
                    chore.get("recurrence") or chore.get("notes", ""),
                    "chore",
                )
    if access_map.get("spiritual"):
        add_calendar_occurrence(events, today.isoformat(), "Daily Reading", "spiritual", "daily-reading", "", "spiritual")
    if companion_access:
        for directive in directive_store().get("directives", []):
            due = str(directive.get("due_at") or directive.get("due") or directive.get("deadline") or "")[:10]
            add_calendar_occurrence(events, due, f"Directive: {directive.get('title', 'Directive')}", "directives", directive.get("id", ""), directive.get("details", ""), "directive")
    return events


def calendar_state(access_map=None, companion_access=False):
    store = calendar_store()
    explicit_events = store.get("events", [])[-200:]
    generated = generated_calendar_events(access_map, companion_access)
    all_events = sorted(explicit_events + generated, key=lambda item: (str(item.get("date", "")), str(item.get("title", ""))))
    return {
        "events": explicit_events,
        "generated_events": generated,
        "all_events": all_events,
        "sources": calendar_sources(access_map, companion_access),
        "categories": CALENDAR_CATEGORY_LABELS,
    }


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
    write_json(profile_data_file("reading_progress.json"), store)
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


def java_daily_reading_specs(target_date):
    day = target_date.day
    psalm_start = (day - 1) % 30 + 1
    specs = [("Proverbs", day)]
    specs.extend(("Psalms", psalm_start + offset * 30) for offset in range(5))
    # The old Java app used the day of month for Acts, which leaves empty
    # readings on days 29-31. Keep the same daily rhythm, but wrap Acts.
    specs.append(("Acts", ((day - 1) % 28) + 1))
    return specs


def daily_reading_schedule(for_date=None):
    target_date = for_date or datetime.now().date()
    readings = []
    for book, chapter in java_daily_reading_specs(target_date):
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
    write_json(profile_data_file("daily_checkins.json"), store)
    return entry


def create_journal_entry(data):
    path = profile_tracker_files()["journal"]
    entries = read_json(path, [])
    entry = {
        "timestamp": now_stamp().replace("T", " "),
        "prompt": str(data.get("prompt") or "Journal entry").strip() or "Journal entry",
        "mood": clean_int(data.get("mood"), default=5, minimum=1, maximum=10),
        "entry": str(data.get("entry") or "").strip(),
    }
    if not entry["entry"]:
        raise ValueError("Journal entry text is required.")
    entries.append(entry)
    write_json(path, entries)
    return entry


def create_fitness_entry(data):
    path = profile_tracker_files()["physical"]
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


def fitness_summary(store=None):
    store = store or fitness_store()
    history = store.get("history", [])
    open_orders = [order for order in store.get("orders", []) if order.get("status", "open") in ("open", "started", "snoozed")]
    completed = [item for item in history if item.get("status") in ("done", "completed")]
    last_workout = completed[-1].get("title", "") if completed else ""
    readiness = store.get("readiness", [])
    latest_readiness = readiness[-1] if readiness else {}
    return {
        "status": store.get("status", "Recruit Rebuild"),
        "phase": store.get("phase", "Recruit Intake"),
        "todays_directive": open_orders[0].get("title", "10-minute walk + Mobility") if open_orders else "Report and recover",
        "streak": len(completed),
        "pain_alert": latest_readiness.get("back_pain", "none"),
        "energy": latest_readiness.get("energy", ""),
        "last_workout": last_workout,
        "next_workout": open_orders[0].get("title", "") if open_orders else "",
        "evie_note": store.get("evie_note", ""),
        "open_orders": len(open_orders),
        "history_count": len(history),
    }


def fitness_state():
    store = fitness_store()
    return {**store, "summary": fitness_summary(store)}


def write_fitness_store(store):
    write_json(profile_data_file("fitness.json"), store)


def create_fitness_log(kind, data):
    allowed = {"readiness", "mobility", "cardio", "strength", "progress_notes", "body_metrics", "history"}
    if kind not in allowed:
        raise ValueError(f"Unknown fitness log type: {kind}")
    store = fitness_store()
    log_id = next_id(store, "next_log_number", "FIT")
    entry = {"id": log_id, "kind": kind, "created_at": now_stamp(), "date": str(data.get("date") or datetime.now().strftime("%Y-%m-%d")).strip()}
    for key, value in data.items():
        if key not in ("id", "kind", "created_at"):
            entry[key] = value
    store.setdefault(kind, []).append(entry)
    if kind in ("cardio", "strength", "mobility", "history"):
        history_entry = {**entry, "title": str(data.get("title") or data.get("exercise") or kind).strip(), "status": data.get("status", "completed")}
        store.setdefault("history", []).append(history_entry)
        if kind != "history":
            create_fitness_entry({
                "session_type": history_entry["title"],
                "exercises": data.get("exercise") or data.get("title") or kind,
                "duration_minutes": data.get("duration_minutes") or data.get("walk_duration") or data.get("minutes") or 0,
                "progress": data.get("status", "completed"),
                "notes": data.get("notes", ""),
            })
    write_fitness_store(store)
    return entry


def update_fitness_order(order_id, data):
    store = fitness_store()
    for order in store.get("orders", []):
        if order.get("id", "").lower() == order_id.lower():
            for key in ("status", "report", "skip_reason", "due_date", "details"):
                if key in data:
                    order[key] = str(data.get(key) or "").strip()
            order["updated_at"] = now_stamp()
            if order.get("status") in ("done", "completed", "skipped", "snoozed"):
                store.setdefault("history", []).append({
                    "id": next_id(store, "next_log_number", "FIT"),
                    "kind": "order",
                    "title": order.get("title", ""),
                    "status": order.get("status", ""),
                    "report": order.get("report", ""),
                    "skip_reason": order.get("skip_reason", ""),
                    "created_at": now_stamp(),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                })
            write_fitness_store(store)
            return order
    raise ValueError(f"Fitness order not found: {order_id}")


def create_fitness_order(data):
    store = fitness_store()
    order = {
        "id": next_id(store, "next_order_number", "ORD"),
        "title": str(data.get("title") or "").strip(),
        "details": str(data.get("details") or "").strip(),
        "status": str(data.get("status") or "open").strip() or "open",
        "type": str(data.get("type") or "order").strip() or "order",
        "due_date": str(data.get("due_date") or "").strip(),
        "report": "",
        "skip_reason": "",
        "created_at": now_stamp(),
    }
    if not order["title"]:
        raise ValueError("Fitness order title is required.")
    store.setdefault("orders", []).append(order)
    write_fitness_store(store)
    return order


def create_fitness_exercise(data):
    store = fitness_store()
    exercise = {
        "id": next_id(store, "next_exercise_number", "EX"),
        "name": str(data.get("name") or "").strip(),
        "format": str(data.get("format") or "sets_reps").strip() or "sets_reps",
        "media_url": str(data.get("media_url") or "").strip(),
        "details": str(data.get("details") or data.get("purpose") or "").strip(),
        "warning": str(data.get("warning") or "").strip(),
        "progression": str(data.get("progression") or "").strip(),
        "regression": str(data.get("regression") or "").strip(),
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
    }
    if not exercise["name"]:
        raise ValueError("Exercise name is required.")
    store.setdefault("exercise_library", []).append(exercise)
    write_fitness_store(store)
    return exercise


def update_fitness_exercise(exercise_id, data):
    store = fitness_store()
    for exercise in store.get("exercise_library", []):
        if exercise.get("id", "").lower() == exercise_id.lower():
            for key in ("name", "format", "media_url", "details", "warning", "progression", "regression"):
                if key in data:
                    exercise[key] = str(data.get(key) or "").strip()
            if not exercise.get("name"):
                raise ValueError("Exercise name is required.")
            exercise["updated_at"] = now_stamp()
            write_fitness_store(store)
            return exercise
    raise ValueError(f"Exercise not found: {exercise_id}")


def delete_fitness_exercise(exercise_id):
    store = fitness_store()
    library = store.get("exercise_library", [])
    for index, exercise in enumerate(library):
        if exercise.get("id", "").lower() == exercise_id.lower():
            removed = library.pop(index)
            for group in store.get("exercise_groups", []):
                group["items"] = [
                    item for item in group.get("items", [])
                    if str(item.get("exercise_id", "")).lower() != exercise_id.lower()
                ]
            write_fitness_store(store)
            return removed
    raise ValueError(f"Exercise not found: {exercise_id}")


def create_fitness_group(data):
    store = fitness_store()
    group = {
        "id": next_id(store, "next_group_number", "GRP"),
        "name": str(data.get("name") or "").strip(),
        "type": str(data.get("type") or "").strip(),
        "notes": str(data.get("notes") or "").strip(),
        "items": [],
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
    }
    if not group["name"]:
        raise ValueError("Group name is required.")
    store.setdefault("exercise_groups", []).append(group)
    write_fitness_store(store)
    return group


def update_fitness_group(group_id, data):
    store = fitness_store()
    for group in store.get("exercise_groups", []):
        if group.get("id", "").lower() == group_id.lower():
            for key in ("name", "type", "notes"):
                if key in data:
                    group[key] = str(data.get(key) or "").strip()
            if not group.get("name"):
                raise ValueError("Group name is required.")
            group["updated_at"] = now_stamp()
            write_fitness_store(store)
            return group
    raise ValueError(f"Fitness group not found: {group_id}")


def delete_fitness_group(group_id):
    store = fitness_store()
    groups = store.get("exercise_groups", [])
    for index, group in enumerate(groups):
        if group.get("id", "").lower() == group_id.lower():
            removed = groups.pop(index)
            write_fitness_store(store)
            return removed
    raise ValueError(f"Fitness group not found: {group_id}")


def add_fitness_group_item(group_id, data):
    store = fitness_store()
    exercise_id = str(data.get("exercise_id") or "").strip()
    if not any(ex.get("id", "").lower() == exercise_id.lower() for ex in store.get("exercise_library", [])):
        raise ValueError("Choose a valid exercise.")
    item = {
        "id": f"ITM-{uuid.uuid4().hex[:8].upper()}",
        "exercise_id": exercise_id,
        "sets": clean_int(data.get("sets"), default=0, minimum=0),
        "reps": clean_int(data.get("reps"), default=0, minimum=0),
        "duration_seconds": clean_int(data.get("duration_seconds"), default=0, minimum=0),
        "distance": str(data.get("distance") or "").strip(),
        "notes": str(data.get("notes") or "").strip(),
    }
    for group in store.get("exercise_groups", []):
        if group.get("id", "").lower() == group_id.lower():
            group.setdefault("items", []).append(item)
            group["updated_at"] = now_stamp()
            write_fitness_store(store)
            return item
    raise ValueError(f"Fitness group not found: {group_id}")


def delete_fitness_group_item(group_id, item_id):
    store = fitness_store()
    for group in store.get("exercise_groups", []):
        if group.get("id", "").lower() == group_id.lower():
            before = len(group.get("items", []))
            group["items"] = [item for item in group.get("items", []) if item.get("id", "").lower() != item_id.lower()]
            if len(group["items"]) == before:
                raise ValueError(f"Fitness group item not found: {item_id}")
            group["updated_at"] = now_stamp()
            write_fitness_store(store)
            return {"id": item_id}
    raise ValueError(f"Fitness group not found: {group_id}")


def update_fitness_challenge(challenge_id, data):
    store = fitness_store()
    for challenge in store.get("challenges", []):
        if challenge.get("id", "").lower() == challenge_id.lower():
            for key in ("status", "report", "completion_status"):
                if key in data:
                    challenge[key] = str(data.get(key) or "").strip()
            if challenge.get("status") == "active":
                challenge["status"] = "started"
            elif challenge.get("status") == "complete":
                challenge["status"] = "completed"
            challenge["updated_at"] = now_stamp()
            if challenge.get("status") in ("started", "completed"):
                store.setdefault("history", []).append({
                    "id": next_id(store, "next_log_number", "FIT"),
                    "kind": "challenge",
                    "title": challenge.get("name", ""),
                    "status": challenge.get("status", ""),
                    "report": challenge.get("report", ""),
                    "created_at": now_stamp(),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                })
            write_fitness_store(store)
            return challenge
    raise ValueError(f"Fitness challenge not found: {challenge_id}")


def create_calendar_event(data, access_map=None, companion_access=False):
    store = calendar_store()
    category = str(data.get("category") or "general").strip().lower() or "general"
    source_id = str(data.get("source_id") or "").strip()
    sources = calendar_sources(access_map, companion_access)
    title = str(data.get("title") or "").strip() or calendar_source_title(category, source_id, sources)
    event = {
        "id": next_id(store, "next_event_number", "CAL"),
        "date": str(data.get("date") or datetime.now().strftime("%Y-%m-%d")).strip(),
        "title": title,
        "category": category if category in CALENDAR_CATEGORY_LABELS else "general",
        "source_id": source_id,
        "notes": str(data.get("notes") or "").strip(),
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
    }
    if not event["title"]:
        raise ValueError("Calendar event title is required.")
    store.setdefault("events", []).append(event)
    write_json(profile_data_file("calendar.json"), store)
    return event


def update_calendar_event(event_id, data):
    store = calendar_store()
    for event in store.get("events", []):
        if event.get("id", "").lower() == event_id.lower():
            for key in ("date", "title", "category", "source_id", "notes"):
                if key in data:
                    value = str(data.get(key) or "").strip()
                    event[key] = value.lower() if key == "category" else value
            if not event.get("title"):
                raise ValueError("Calendar event title is required.")
            event["updated_at"] = now_stamp()
            write_json(profile_data_file("calendar.json"), store)
            return event
    raise ValueError(f"Calendar event not found: {event_id}")


def delete_calendar_event(event_id):
    store = calendar_store()
    events = store.get("events", [])
    for index, event in enumerate(events):
        if event.get("id", "").lower() == event_id.lower():
            removed = events.pop(index)
            write_json(profile_data_file("calendar.json"), store)
            return removed
    raise ValueError(f"Calendar event not found: {event_id}")


def create_chore(data):
    store = chore_store()
    chore_id = next_id(store, "next_chore_number", "CHR")
    due_date = str(data.get("due_date") or "").strip()
    recurrence_type, recurrence_day, recurrence_label = recurrence_from_data(data, due_date)
    chore = {
        "id": chore_id,
        "title": str(data.get("title") or "").strip(),
        "status": str(data.get("status") or "open").strip() or "open",
        "due_date": due_date,
        "recurrence_type": recurrence_type,
        "recurrence_day": recurrence_day,
        "recurrence": recurrence_label,
        "notes": str(data.get("notes") or "").strip(),
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
    }
    if not chore["title"]:
        raise ValueError("Chore title is required.")
    store.setdefault("chores", []).append(chore)
    write_json(profile_data_file("chores.json"), store)
    return chore


def update_chore(chore_id, data):
    store = chore_store()
    for chore in store.get("chores", []):
        if chore.get("id", "").lower() == chore_id.lower():
            for key in ("title", "status", "due_date", "notes"):
                if key in data:
                    chore[key] = str(data[key]).strip()
            if any(key in data for key in ("recurrence", "recurrence_type", "recurrence_day", "due_date")):
                recurrence_type, recurrence_day, recurrence_label = recurrence_from_data(data, chore.get("due_date", ""))
                chore["recurrence_type"] = recurrence_type
                chore["recurrence_day"] = recurrence_day
                chore["recurrence"] = recurrence_label
            chore["updated_at"] = now_stamp()
            write_json(profile_data_file("chores.json"), store)
            return chore
    raise ValueError(f"Chore not found: {chore_id}")


def delete_chore(chore_id):
    store = chore_store()
    chores = store.get("chores", [])
    for index, chore in enumerate(chores):
        if chore.get("id", "").lower() == chore_id.lower():
            removed = chores.pop(index)
            write_json(profile_data_file("chores.json"), store)
            return removed
    raise ValueError(f"Chore not found: {chore_id}")


def create_inventory_item(data):
    store = diet_store()
    item_id = next_id(store, "next_inventory_number", "INV")
    on_hand = clean_float(data.get("on_hand"), default=0, minimum=0)
    par = clean_float(data.get("par"), default=0, minimum=0)
    item = {
        "id": item_id,
        "name": str(data.get("name") or "").strip(),
        "unit_label": str(data.get("unit_label") or "unit").strip() or "unit",
        "on_hand": on_hand,
        "par": par,
        "reorder_at": clean_float(data.get("reorder_at"), default=round(par / 5, 2) if par else 0, minimum=0),
        "container_size": clean_float(data.get("container_size"), default=1, minimum=0.01),
        "cost_per_container": clean_float(data.get("cost_per_container"), default=0, minimum=0),
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
    }
    if not item["name"]:
        raise ValueError("Inventory item name is required.")
    store.setdefault("inventory", []).append(item)
    write_json(profile_data_file("diet.json"), store)
    return item


def update_inventory_item(item_id, data):
    store = diet_store()
    for item in store.get("inventory", []):
        if item.get("id", "").lower() == item_id.lower():
            for key in ("name", "unit_label"):
                if key in data:
                    item[key] = str(data[key]).strip()
            for key in ("on_hand", "par", "reorder_at", "container_size", "cost_per_container"):
                if key in data:
                    item[key] = clean_float(data.get(key), default=0, minimum=0)
            if item.get("container_size", 0) <= 0:
                item["container_size"] = 1
            item["updated_at"] = now_stamp()
            write_json(profile_data_file("diet.json"), store)
            return item
    raise ValueError(f"Inventory item not found: {item_id}")


def adjust_inventory_item(item_id, amount):
    store = diet_store()
    for item in store.get("inventory", []):
        if item.get("id", "").lower() == item_id.lower():
            item["on_hand"] = max(0, clean_float(item.get("on_hand"), default=0) + amount)
            item["updated_at"] = now_stamp()
            write_json(profile_data_file("diet.json"), store)
            return item
    raise ValueError(f"Inventory item not found: {item_id}")


def delete_inventory_item(item_id):
    store = diet_store()
    inventory = store.get("inventory", [])
    for index, item in enumerate(inventory):
        if item.get("id", "").lower() == item_id.lower():
            removed = inventory.pop(index)
            write_json(profile_data_file("diet.json"), store)
            return removed
    raise ValueError(f"Inventory item not found: {item_id}")


def create_food_entry(data):
    store = diet_store()
    food_id = next_id(store, "next_food_number", "FOOD")
    entry = {
        "id": food_id,
        "date": str(data.get("date") or datetime.now().strftime("%Y-%m-%d")).strip(),
        "food": str(data.get("food") or "").strip(),
        "carbs": clean_bool(data.get("carbs")),
        "sugars": clean_bool(data.get("sugars")),
        "created_at": now_stamp(),
    }
    if not entry["food"]:
        raise ValueError("Food entry text is required.")
    store.setdefault("food_diary", []).append(entry)
    write_json(profile_data_file("diet.json"), store)
    return entry


def parse_food_csv(text):
    entries = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        entry = {
            "date": parts[0] if len(parts) > 1 else datetime.now().strftime("%Y-%m-%d"),
            "food": parts[1] if len(parts) > 1 else parts[0],
            "carbs": parse_bool_text(parts[2]) if len(parts) > 2 else False,
            "sugars": parse_bool_text(parts[3]) if len(parts) > 3 else False,
        }
        entries.append(entry)
    return entries


def shopping_item_for_inventory(item):
    on_hand = clean_float(item.get("on_hand"), default=0)
    par = clean_float(item.get("par"), default=0)
    reorder_at = clean_float(item.get("reorder_at"), default=round(par / 5, 2) if par else 0)
    container_size = max(clean_float(item.get("container_size"), default=1), 0.01)
    cost = clean_float(item.get("cost_per_container"), default=0)
    needed_units = max(0, par - on_hand) if on_hand <= reorder_at else 0
    containers = math.ceil(needed_units / container_size) if needed_units else 0
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "unit_label": item.get("unit_label", "unit"),
        "on_hand": on_hand,
        "par": par,
        "diff": round(max(0, par - on_hand), 2),
        "needed_units": round(needed_units, 2),
        "containers": containers,
        "cost": round(containers * cost, 2),
    }


def diet_state():
    store = diet_store()
    inventory = store.get("inventory", [])
    food_diary = store.get("food_diary", [])
    shopping = [item for item in (shopping_item_for_inventory(item) for item in inventory) if item["containers"] > 0]
    latest_carbs = next((entry.get("date") for entry in reversed(food_diary) if entry.get("carbs")), "")
    latest_sugars = next((entry.get("date") for entry in reversed(food_diary) if entry.get("sugars")), "")
    ketosis_start = ""
    for entry in reversed(food_diary):
        if entry.get("carbs") or entry.get("sugars"):
            break
        ketosis_start = entry.get("date", ketosis_start)
    return {
        "inventory": inventory,
        "food_diary": food_diary[-50:],
        "shopping_list": shopping,
        "summary": {
            "last_carbs_date": latest_carbs,
            "last_sugars_date": latest_sugars,
            "ketosis": bool(food_diary) and not latest_carbs and not latest_sugars,
            "ketosis_start_date": ketosis_start,
            "shopping_item_count": sum(item["containers"] for item in shopping),
            "shopping_cart_cost": round(sum(item["cost"] for item in shopping), 2),
        },
    }


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
    write_json(profile_data_file("project_todos.json"), store)
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
            write_json(profile_data_file("project_todos.json"), store)
            return todo
    raise ValueError(f"Project todo not found: {todo_id}")


def delete_project_todo(todo_id):
    store = project_todo_store()
    todos = store.get("todos", [])
    for index, todo in enumerate(todos):
        if todo.get("id", "").lower() == todo_id.lower():
            removed = todos.pop(index)
            write_json(profile_data_file("project_todos.json"), store)
            shutil.rmtree(active_project_asset_dir() / safe_name(todo_id), ignore_errors=True)
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
    original_name = validate_upload_item(item, ALLOWED_PROJECT_EXTENSIONS)

    for todo in store.get("todos", []):
        if todo.get("id", "").lower() == todo_id.lower():
            safe_project = safe_name(todo_id)
            target_dir = active_project_asset_dir() / safe_project
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
            write_json(profile_data_file("project_todos.json"), store)
            return asset
    raise ValueError(f"Project todo not found: {todo_id}")


def render_project_page(todo_id, profile_name=None):
    todo = project_todo_by_id(todo_id)
    category = PROJECT_CATEGORIES.get(todo.get("category"), todo.get("category", ""))
    detail = project_category_detail(todo.get("category"))
    assets = todo.get("assets", [])
    asset_rows = render_project_asset_rows(assets)
    todo_json = json.dumps(todo)
    categories_json = json.dumps(PROJECT_CATEGORIES)
    detail_json = json.dumps(detail)
    profile_query = f"?profile={quote(normalize_profile_name(profile_name or active_profile_name()))}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(todo.get('title', 'Project'))}</title>
  <style>
    :root {{ color-scheme: dark; --bg: #101316; --panel: #181d22; --panel-2: #20262d; --text: #edf2f7; --muted: #9da8b5; --line: #303842; --accent: #62d6b2; --danger: #ec6b6b; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: Segoe UI, system-ui, sans-serif; margin: 18px; background: var(--bg); color: var(--text); font-size: 14px; }}
    main {{ max-width: 980px; margin: 0 auto; }}
    section {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; margin: 10px 0; background: var(--panel); }}
    h1 {{ margin: 0 0 4px; font-size: 1.55rem; }}
    h2 {{ font-size: 1.02rem; margin: 0 0 8px; }}
    h3 {{ font-size: .94rem; margin: 12px 0 6px; }}
    label {{ display: block; margin: 8px 0 4px; color: var(--muted); }}
    input, select, textarea {{ width: 100%; border: 1px solid var(--line); border-radius: 6px; background: #0d1116; color: var(--text); padding: 8px; font: inherit; }}
    input:focus-visible, select:focus-visible, textarea:focus-visible, button:focus-visible, a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    textarea {{ min-height: 78px; resize: vertical; }}
    pre {{ white-space: pre-wrap; font: inherit; color: var(--muted); margin: 0; overflow-wrap: anywhere; }}
    a {{ color: var(--accent); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }}
    .row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}
    .pill {{ display: inline-block; border: 1px solid var(--line); border-radius: 999px; padding: 3px 8px; margin: 2px 4px 2px 0; color: var(--muted); }}
    .muted {{ color: var(--muted); }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    button {{ border: 1px solid var(--line); border-radius: 6px; background: var(--panel-2); color: var(--text); padding: 8px 10px; cursor: pointer; }}
    button.primary {{ border-color: var(--accent); color: var(--accent); }}
    button.danger {{ border-color: var(--danger); color: var(--danger); }}
    ul {{ margin: 0; padding-left: 18px; }}
    @media (max-width: 800px) {{ body {{ margin: 10px; }} .actions {{ flex-direction: column; }} .actions button {{ width: 100%; }} }}
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
    const profileQuery = "{profile_query}";

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
      const res = await fetch(`/api/project-todos/${{encodeURIComponent(project.id)}}${{profileQuery}}`, {{
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
      const res = await fetch(`/api/project-todos/${{encodeURIComponent(project.id)}}${{profileQuery}}`, {{ method: 'DELETE' }});
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
      const res = await fetch(`/api/project-assets/upload${{profileQuery}}`, {{ method: 'POST', body: form }});
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
    if directive.get("type"):
        parts.append(f"Type {directive['type']}.")
    if directive.get("due_at"):
        parts.append(f"Due {directive_due_display(directive['due_at'])} {directive.get('due_timezone', DEFAULT_DIRECTIVE_TIMEZONE)}.")
    if directive.get("proof_required"):
        parts.append("Proof required.")
    if directive.get("tags"):
        parts.append(f"Tags: {', '.join(directive.get('tags', []))}.")
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


def entry_has_directive_id(entry, directive_id):
    directive_tag = str(directive_id or "").strip().lower()
    if not directive_tag:
        return False
    return directive_tag in {str(tag).strip().lower() for tag in entry.get("tags", [])}


def directive_memory_exists(payload, directive_id):
    for collection_name in ("memories", "archive"):
        for entry in payload.get(collection_name, []):
            if entry_has_directive_id(entry, directive_id):
                return True
    return False


def sync_directive_memories_for_export(companion, payload):
    changed = False
    for directive in directive_store().get("directives", []):
        if companion_name_for_issuer(directive.get("issuer")) != companion:
            continue
        if directive_memory_exists(payload, directive.get("id")):
            continue
        remember_directive_in_payload(payload, directive)
        changed = True
    if changed:
        save_payload(companion, payload)
    return changed


def export_companion_payload(companion, payload):
    sync_directive_memories_for_export(companion, payload)
    export_payload = copy.deepcopy(payload)
    export_payload["archive"] = []
    export_payload.setdefault("metadata", {})["exported_at"] = now_stamp()
    export_payload["metadata"]["archive_export_policy"] = "Archived memories are omitted from copied, downloaded, and handoff packets."
    return export_payload


def create_directive(data, remember_issuer=True):
    store = directive_store()
    directive_id = next_id(store, "next_directive_number", "DIR")
    directive = normalize_directive_record({
        "id": directive_id,
        "issuer": data.get("issuer", "Veyra"),
        "title": data.get("title", "").strip(),
        "details": data.get("details", "").strip(),
        "status": data.get("status", "issued"),
        "priority": data.get("priority", "3"),
        "due_at": data.get("due_at", ""),
        "due_timezone": data.get("due_timezone", DEFAULT_DIRECTIVE_TIMEZONE),
        "type": data.get("type", "manual"),
        "tags": data.get("tags", []),
        "proof_required": bool(data.get("proof_required", False)),
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
    })
    if not directive["title"]:
        raise ValueError("Directive title is required.")
    duplicate = find_duplicate_directive(store, directive)
    if duplicate and not data.get("allow_duplicate"):
        raise ValueError(f"Possible duplicate directive: {duplicate.get('id')}.")
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
        "due_timezone": DEFAULT_DIRECTIVE_TIMEZONE,
        "type": "manual",
        "tags": [],
        "proof_required": False,
    }

    detail_lines = []
    for line in text.splitlines():
        stripped = line.strip(" \t-•")
        if not stripped:
            continue

        key_match = re.match(r"^(issuer|from|title|directive|task|details?|description|priority|due|deadline|timezone|tz|type|tags?|proof|proof_required|evidence)\s*[:=-]\s*(.+)$", stripped, flags=re.I)
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
        elif key in ("timezone", "tz"):
            parsed["due_timezone"] = clean_directive_timezone(value)
        elif key == "type":
            parsed["type"] = clean_directive_type(value)
        elif key in ("tag", "tags"):
            parsed["tags"] = split_tags(value)
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

    return normalize_directive_record(parsed)


def update_directive(directive_id, data):
    store = directive_store()
    for directive in store.get("directives", []):
        if directive["id"].lower() == directive_id.lower():
            directive.setdefault("created_at", now_stamp())
            for key in ("status", "title", "details", "priority", "due_at", "due_timezone", "type", "tags", "proof_required"):
                if key in data:
                    directive[key] = data[key]
            directive.update(normalize_directive_record(directive))
            duplicate = find_duplicate_directive(store, directive, ignore_id=directive_id)
            if duplicate and not data.get("allow_duplicate"):
                raise ValueError(f"Possible duplicate directive: {duplicate.get('id')}.")
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
    original_name = validate_upload_item(item, ALLOWED_PROOF_EXTENSIONS)
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


def ensure_content_length(headers, max_bytes, label):
    try:
        length = int(headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise ValueError(f"{label} request has an invalid Content-Length.") from exc
    if length > max_bytes:
        raise ValueError(f"{label} is too large. Limit is {max_bytes // (1024 * 1024)} MB.")
    return length


def is_relative_to(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_upload_item(item, allowed_extensions):
    filename = safe_name(Path(getattr(item, "filename", "")).name)
    if not filename:
        raise ValueError("Upload requires a file name.")
    extension = Path(filename).suffix.lower()
    if extension not in allowed_extensions:
        raise ValueError(f"Upload type is not allowed: {extension or 'no extension'}.")
    mime_type = str(getattr(item, "type", "") or mimetypes.guess_type(filename)[0] or "application/octet-stream")
    if not (mime_type in ALLOWED_UPLOAD_MIME_TYPES or any(mime_type.startswith(prefix) for prefix in ALLOWED_UPLOAD_MIME_PREFIXES)):
        raise ValueError(f"Upload MIME type is not allowed: {mime_type}.")
    return filename


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


def companion_archive_state(companion, query=""):
    payload = load_payload(companion)
    archive = payload.get("archive", [])
    tag_counts = {}
    rows = []
    needle = str(query or "").strip().lower()
    for entry in archive:
        tags = [str(tag) for tag in entry.get("tags", []) if str(tag).strip()]
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        searchable = " ".join([
            str(entry.get("id", "")),
            str(entry.get("category", "")),
            " ".join(tags),
            str(entry.get("archived_reason", "")),
        ]).lower()
        if needle and needle not in searchable:
            continue
        rows.append({
            "id": entry.get("id", ""),
            "category": entry.get("category", ""),
            "status": entry.get("status", "archived"),
            "weight": entry.get("weight", ""),
            "tags": tags,
            "archived_at": entry.get("archived_at", ""),
            "archived_reason": entry.get("archived_reason", ""),
        })
    tags = [{"tag": tag, "count": count} for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0].lower()))]
    return {"tags": tags, "entries": rows}


def archive_companion_memory(companion, action, memory_id):
    if action not in {"archive", "unarchive", "resave"}:
        raise ValueError("Unknown archive action.")
    payload = load_payload(companion)
    applied_id = apply_command_line(payload, f"{action} {memory_id}")
    backup_path = save_payload(companion, payload)
    return {
        "id": applied_id,
        "backup": backup_path.name if backup_path else None,
        "summary": packet_summary(companion, payload),
        "archive": companion_archive_state(companion),
    }


def validate_companion_payload(companion):
    issues = []
    try:
        payload = load_payload(companion)
    except Exception as exc:
        return [{"severity": "High", "area": f"{companion} packet", "message": str(exc)}]

    if payload.get("schema") != "ai-companion-memory/v1":
        issues.append({"severity": "Medium", "area": f"{companion} packet", "message": "Unexpected schema value."})
    seen = set()
    for collection_name in ("memories", "archive"):
        for entry in payload.get(collection_name, []):
            memory_id = str(entry.get("id") or "").strip()
            if not memory_id:
                issues.append({"severity": "High", "area": f"{companion} {collection_name}", "message": "Entry is missing an id."})
            elif memory_id.lower() in seen:
                issues.append({"severity": "High", "area": f"{companion} {collection_name}", "message": f"Duplicate memory id {memory_id}."})
            seen.add(memory_id.lower())
            if collection_name == "memories" and entry.get("status") != "active":
                issues.append({"severity": "Medium", "area": f"{companion} active memories", "message": f"{memory_id} is not marked active."})
            if collection_name == "archive" and entry.get("status") != "archived":
                issues.append({"severity": "Medium", "area": f"{companion} archive", "message": f"{memory_id} is not marked archived."})
            if entry.get("category") not in CATEGORIES:
                issues.append({"severity": "Low", "area": f"{companion} {memory_id}", "message": f"Unknown category {entry.get('category')}."})
    return issues


def integrity_report():
    issues = []
    for path in [USERS_FILE, SETTINGS_FILE, DIRECTIVES_FILE, PROOF_FILE, CHECKINS_FILE, PROJECT_TODOS_FILE, READING_PROGRESS_FILE, CHORES_FILE, DIET_FILE, FITNESS_FILE, CALENDAR_FILE]:
        try:
            if path.exists():
                json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append({"severity": "High", "area": path.name, "message": str(exc)})
    for companion in COMPANION_FILES:
        issues.extend(validate_companion_payload(companion))
    for proof in proof_store().get("proof", []):
        proof_path = proof.get("path")
        if proof_path and not (APP_DIR / proof_path).exists():
            issues.append({"severity": "Medium", "area": "Proof Vault", "message": f"{proof.get('id')} references missing file {proof_path}."})
    for todo in project_todo_store().get("todos", []):
        for asset in todo.get("assets", []):
            asset_path = asset.get("path")
            if asset_path and not (APP_DIR / asset_path).exists():
                issues.append({"severity": "Medium", "area": "Project Assets", "message": f"{todo.get('id')} references missing file {asset_path}."})
    return {"ok": not issues, "issues": issues, "checked_at": now_stamp()}


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
        "due_timezone": clean_directive_timezone(metadata.get("timezone") or metadata.get("tz")),
        "type": clean_directive_type(metadata.get("type", "manual")),
        "tags": split_tags(metadata.get("tags", "")),
        "proof_required": parsed_proof if parsed_proof is not None else False,
    }


def command_batch_preview(command_text):
    decoded = decode_command_batch_if_needed(command_text)
    lines = [line.strip() for line in decoded.splitlines() if line.strip()]
    counts = {
        "add": 0,
        "update": 0,
        "archive": 0,
        "unarchive": 0,
        "resave": 0,
        "delete": 0,
        "directives": 0,
        "unknown": 0,
    }
    directive_titles = []
    for line in lines:
        lower = line.lower()
        if is_directive_command(line):
            counts["directives"] += 1
            directive_titles.append(parse_directive_command(line, ARRAY_PROFILE).get("title", "Directive"))
        elif lower.startswith("add ") or lower.startswith("add:"):
            counts["add"] += 1
        elif lower.startswith(("update ", "edit ")):
            counts["update"] += 1
        elif lower.startswith("archive "):
            counts["archive"] += 1
        elif lower.startswith("unarchive "):
            counts["unarchive"] += 1
        elif lower.startswith("resave "):
            counts["resave"] += 1
        elif lower.startswith("delete "):
            counts["delete"] += 1
        else:
            counts["unknown"] += 1
    return {
        "line_count": len(lines),
        "decoded_from_base64": decoded != command_text.strip(),
        "counts": counts,
        "directive_titles": directive_titles[:20],
        "privacy": "Preview shows operation counts and directive titles only; memory text is hidden.",
    }


def apply_commands(companion, command_text):
    payload = load_payload(companion)
    trial_payload = copy.deepcopy(payload)
    command_text = decode_command_batch_if_needed(command_text)
    lines = [line.strip() for line in command_text.splitlines() if line.strip()]
    applied = []
    directives = []
    memory_changed = False
    directive_backup_path = None
    for line in lines:
        if is_directive_command(line):
            if directive_backup_path is None:
                directive_backup_path = backup_json_file(DIRECTIVES_FILE)
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
        "directive_backup": directive_backup_path.name if directive_backup_path else None,
        "summary": packet_summary(companion, trial_payload),
    }


def decode_directive_export_packet(packet_text):
    compact = "".join(str(packet_text or "").split())
    if not compact:
        raise ValueError("Directive export packet is empty.")
    try:
        padded = compact + ("=" * (-len(compact) % 4))
        payload = json.loads(base64.b64decode(padded, validate=True).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Directive export packet must be base64 JSON.") from exc
    if payload.get("schema") != "companion-directive-export/v1":
        raise ValueError("Directive export packet schema is not companion-directive-export/v1.")
    directives = payload.get("directives", [])
    if not isinstance(directives, list):
        raise ValueError("Directive export packet directives must be a list.")
    return payload


def directive_export_preview(packet_text):
    payload = decode_directive_export_packet(packet_text)
    directives = [normalize_directive_record(directive) for directive in payload.get("directives", [])]
    status_counts = {}
    for directive in directives:
        status = directive.get("status", "issued")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "schema": payload.get("schema"),
        "exported_at": payload.get("exported_at", ""),
        "count": len(directives),
        "status_counts": status_counts,
        "directives": [
            {
                "id": directive.get("id", ""),
                "issuer": directive.get("issuer", ""),
                "title": directive.get("title", ""),
                "status": directive.get("status", ""),
                "priority": directive.get("priority", ""),
                "due": directive_due_display(directive.get("due_at")),
                "type": directive.get("type", "manual"),
                "tags": directive.get("tags", []),
            }
            for directive in directives[:50]
        ],
        "privacy": "Preview omits directive details and memory packet content.",
    }


def merge_directive_export(packet_text):
    payload = decode_directive_export_packet(packet_text)
    imported = [normalize_directive_record(directive) for directive in payload.get("directives", [])]
    store = directive_store()
    existing_ids = {str(directive.get("id", "")).lower() for directive in store.get("directives", [])}
    backup_path = backup_json_file(DIRECTIVES_FILE)
    merged = []
    skipped = []
    for directive in imported:
        if not directive.get("title"):
            skipped.append({"id": directive.get("id", ""), "title": "", "reason": "missing title"})
            continue
        duplicate = find_duplicate_directive(store, directive)
        if duplicate:
            skipped.append({"id": directive.get("id", ""), "title": directive.get("title", ""), "reason": f"duplicate of {duplicate.get('id')}"})
            continue
        original_id = str(directive.get("id", "")).strip()
        if not original_id or original_id.lower() in existing_ids:
            directive["id"] = next_id(store, "next_directive_number", "DIR")
        else:
            existing_ids.add(original_id.lower())
        directive = {key: directive.get(key) for key in DIRECTIVE_EXPORT_FIELDS if key in directive}
        directive["updated_at"] = directive.get("updated_at") or now_stamp()
        store.setdefault("directives", []).append(directive)
        merged.append({"id": directive.get("id", ""), "title": directive.get("title", "")})
    refresh_directive_counter(store)
    write_json(DIRECTIVES_FILE, store)
    return {
        "merged": merged,
        "skipped": skipped,
        "backup": backup_path.name if backup_path else None,
        "message": f"Merged {len(merged)} directive(s); skipped {len(skipped)}.",
    }


def tracker_data(reading_plans=None):
    tracker_files = profile_tracker_files()
    journal = read_json(tracker_files["journal"], [])
    tasks = read_json(tracker_files["tasks"], [])
    physical = read_json(tracker_files["physical"], [])
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


def parse_export_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        try:
            parsed = clean_date(text[:10])
            return datetime.combine(parsed, datetime.min.time()) if parsed else None
        except ValueError:
            return None


def directive_recent_or_active(directive, cutoff):
    if str(directive.get("status", "issued")).lower() == "issued":
        return True
    for key in ("created_at", "updated_at", "due_at", "due", "deadline"):
        parsed = parse_export_timestamp(directive.get(key))
        if parsed and parsed >= cutoff:
            return True
    return False


def directive_export_packet():
    cutoff = datetime.now() - timedelta(days=31)
    directives = [
        {key: normalize_directive_record(directive).get(key) for key in DIRECTIVE_EXPORT_FIELDS}
        for directive in directive_store().get("directives", [])
        if directive_recent_or_active(directive, cutoff)
    ]
    payload = {
        "schema": "companion-directive-export/v1",
        "exported_at": now_stamp(),
        "policy": "Active directives plus directives created, updated, due, or closed within the last month.",
        "directives": directives,
    }
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii")
    return {"packet": encoded, "count": len(directives), "exported_at": payload["exported_at"]}


def app_state():
    profile = active_profile()
    companion_access = active_has_companion_access()
    access_map = active_access_map()
    companions = []
    if companion_access:
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

    directives = directive_store().get("directives", []) if companion_access else []
    daily_schedule = daily_reading_schedule() if access_map.get("spiritual") else []
    reading_plans = current_reading_plans(daily_schedule) if access_map.get("spiritual") else {}
    trackers = tracker_data(reading_plans) if access_map.get("trackers") else {
        "journal": [],
        "tasks": [],
        "physical": [],
        "checkins": [],
        "latest_checkin": None,
        "summary": {"journal_entries": 0, "task_entries": 0, "physical_entries": 0, "checkin_entries": 0},
        "work_categories": {},
        "task_categories": {},
    }
    return {
        "profile": public_profile(profile),
        "profiles": public_profiles(),
        "settings": settings_store(),
        "access_categories": ACCESS_CATEGORIES,
        "admin": {"profiles": public_profiles()} if companion_access else {},
        "access": {
            "companions": companion_access,
            "directives": companion_access,
            "proof": companion_access,
            **access_map,
        },
        "companions": companions,
        "categories": list(CATEGORIES.keys()) if companion_access else [],
        "directives": directives,
        "directive_summary": directive_summary(directives),
        "proof": proof_store().get("proof", []) if companion_access else [],
        "trackers": trackers,
        "reading_plans": reading_plans,
        "reading_progress": reading_progress_state() if access_map.get("spiritual") else {"completed": {}, "summary": {}},
        "bible_books": bible_chapter_index() if access_map.get("spiritual") else [],
        "daily_reading_schedule": daily_schedule,
        "projects": project_state() if access_map.get("projects") else {"categories": PROJECT_CATEGORIES, "category_details": PROJECT_CATEGORY_DETAILS, "todos": [], "summary": {}},
        "chores": chore_store().get("chores", []) if access_map.get("chores") else [],
        "diet": diet_state() if access_map.get("diet") else {"summary": {}, "inventory": [], "shopping_list": [], "food_diary": []},
        "fitness": fitness_state() if access_map.get("fitness") else {},
        "calendar": calendar_state(access_map, companion_access),
        "integrity": integrity_report() if companion_access else {"ok": True, "issues": [], "checked_at": now_stamp()},
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
      gap: 12px;
    }
    .profile-bar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .profile-bar select, .profile-bar input {
      width: auto;
      min-width: 130px;
      margin: 0;
    }
    .profile-bar button.inline {
      padding: 7px 9px;
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
    input:focus-visible, select:focus-visible, textarea:focus-visible,
    button:focus-visible, a.inline:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
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
    button.inline.danger, a.inline.danger { border-color: var(--danger); color: var(--danger); }
    button.inline[disabled] { opacity: 0.55; cursor: not-allowed; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 680px;
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
      -webkit-overflow-scrolling: touch;
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
    .tab-row .tab-action { margin-left: auto; }
    dialog {
      color: var(--text);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      width: min(520px, calc(100vw - 30px));
    }
    dialog::backdrop { background: rgba(0, 0, 0, 0.55); }
    .tracker-view { display: none; }
    .tracker-view.active { display: block; }
    .tab-view { display: none; }
    .tab-view.active { display: block; }
    .diet-view { display: none; }
    .diet-view.active { display: block; }
    .fitness-view { display: none; }
    .fitness-view.active { display: block; }
    .calendar-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 10px;
    }
    .calendar-grid {
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      border: 1px solid var(--line);
      border-radius: 6px;
      overflow: hidden;
      background: #10151a;
    }
    .calendar-heading,
    .calendar-day {
      min-height: 92px;
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      padding: 6px;
    }
    .calendar-heading {
      min-height: auto;
      background: var(--panel-2);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .calendar-day:nth-child(7n),
    .calendar-heading:nth-child(7n) { border-right: 0; }
    .calendar-date {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 5px;
    }
    .calendar-day.outside { opacity: 0.45; }
    .calendar-event {
      display: block;
      border-left: 3px solid var(--accent);
      background: rgba(77, 163, 255, 0.09);
      border-radius: 4px;
      padding: 3px 5px;
      margin-top: 4px;
      font-size: 12px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }
    .calendar-event.generated { border-left-color: #8fd694; }
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
      overflow-wrap: anywhere;
    }
    .empty-state {
      border: 1px dashed var(--line);
      border-radius: 6px;
      padding: 10px;
      color: var(--muted);
      background: #10151a;
      margin: 8px 0;
    }
    .empty-state strong {
      display: block;
      color: var(--text);
      margin-bottom: 3px;
    }
    .toolbar-row {
      display: flex;
      gap: 8px;
      align-items: flex-end;
      flex-wrap: wrap;
      margin: 8px 0 10px;
    }
    .toolbar-row > * {
      flex: 1 1 160px;
      min-width: 0;
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
      max-width: 560px;
      overflow-wrap: anywhere;
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
      header { align-items: flex-start; flex-direction: column; }
      .profile-bar { justify-content: flex-start; }
      .row { flex-direction: column; align-items: stretch; }
      .calendar-grid { min-width: 720px; }
      #calendarGrid { overflow-x: auto; }
      .span-2 { grid-column: auto; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Companion Control Console</h1>
    <div class="profile-bar">
      <span class="muted" id="activeProfileLabel"></span>
      <button class="inline" id="profileLogoutButton">Log Out</button>
      <button class="inline" id="profileSettingsButton">Profile Settings</button>
      <button class="inline primary" id="adminButton" data-admin-only>Admin</button>
      <div class="status" id="status">Loading...</div>
    </div>
  </header>
  <main>
    <nav>
      <button data-tab="dashboard" class="active">Dashboard</button>
      <button data-tab="memory" data-companion-only>Companion</button>
      <button data-tab="trackers" data-access-category="trackers">Daily Check-ins</button>
      <button data-tab="fitness" data-access-category="fitness">Fitness</button>
      <button data-tab="spiritual" data-access-category="spiritual">Spiritual</button>
      <button data-tab="projects" data-access-category="projects">Projects</button>
      <button data-tab="chores" data-access-category="chores">Chores</button>
      <button data-tab="diet" data-access-category="diet">Diet</button>
      <button data-tab="calendar">Calendar</button>
      <button data-tab="profileSettings">Profile Settings</button>
      <button data-tab="admin" data-admin-only>Admin</button>
    </nav>
    <section id="dashboard" class="active">
      <div class="grid" id="authPanel">
        <div class="panel full" id="sessionPanel" style="display:none;">
          <h2>Session</h2>
          <div id="sessionSummary"></div>
          <div class="row" style="margin-top: 10px;">
            <button class="inline primary" onclick="document.querySelector('button[data-tab=profileSettings]').click()">Profile Settings</button>
            <button class="inline" onclick="document.getElementById('profileLogoutButton').click()">Log Out</button>
          </div>
        </div>
        <div class="panel" id="loginPanel">
          <h2>Sign In</h2>
          <label>Profile</label>
          <select id="loginProfileSelect"></select>
          <label>Password</label>
          <input id="loginPassword" type="password">
          <button class="inline primary" id="profileLoginButton">Log In</button>
        </div>
        <div class="panel" id="registerPanel">
          <h2>Register Profile</h2>
          <label>Profile name</label>
          <input id="profileRegisterName">
          <label>Password</label>
          <input id="profileRegisterPassword" type="password">
          <button class="inline" id="profileRegisterButton">Register</button>
        </div>
      </div>
      <div class="dashboard-grid" id="dashboardContent">
        <button class="panel todo-row" onclick="document.querySelector('button[data-tab=memory]').click()" data-companion-only>
          <h2>Memory Manager</h2>
          <div class="metric" id="dashCompanions">0</div>
          <div class="muted" id="dashMemory">No packets loaded.</div>
        </button>
        <button class="panel todo-row" onclick="showCompanionTab('directives')" data-companion-only>
          <h2>Directives</h2>
          <div class="metric" id="dashDirectives">0</div>
          <div class="muted" id="dashDirectiveDetail"></div>
        </button>
        <button class="panel todo-row" onclick="document.querySelector('button[data-tab=spiritual]').click()" data-access-category="spiritual">
          <h2>Spiritual</h2>
          <div class="metric" id="dashSpirit">--</div>
          <div class="muted" id="dashSpiritDetail"></div>
        </button>
        <button class="panel todo-row" onclick="document.querySelector('button[data-tab=fitness]').click()" data-access-category="fitness">
          <h2>Fitness</h2>
          <div class="metric" id="dashPhysical">0</div>
          <div class="muted" id="dashPhysicalDetail"></div>
        </button>
        <button class="panel todo-row" onclick="document.querySelector('button[data-tab=diet]').click()" data-access-category="diet">
          <h2>Diet</h2>
          <div class="metric" id="dashDiet">0</div>
          <div class="muted" id="dashDietDetail"></div>
        </button>
        <button class="panel todo-row" onclick="document.querySelector('button[data-tab=projects]').click()" data-access-category="projects">
          <h2>Projects</h2>
          <div class="metric" id="dashProjects">0</div>
          <div class="muted" id="dashProjectsDetail"></div>
        </button>
        <button class="panel todo-row" onclick="document.querySelector('button[data-tab=chores]').click()" data-access-category="chores">
          <h2>Chores</h2>
          <div class="metric" id="dashChores">0</div>
          <div class="muted" id="dashChoresDetail"></div>
        </button>
        <button class="panel todo-row" onclick="document.querySelector('button[data-tab=calendar]').click()">
          <h2>Calendar</h2>
          <div class="metric" id="dashCalendar">0</div>
          <div class="muted" id="dashCalendarDetail"></div>
        </button>
        <div class="panel" data-companion-only>
          <h2>Integrity</h2>
          <div class="metric" id="dashIntegrity">OK</div>
          <div class="muted" id="dashIntegrityDetail"></div>
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
    <section id="memory" data-companion-only>
      <div class="grid">
        <div class="panel full">
          <h2>Companion</h2>
          <div class="tab-row">
            <button class="active" onclick="showCompanionTab('memory')">Memory</button>
            <button onclick="showCompanionTab('directives')">Directive Ledger</button>
            <button onclick="showCompanionTab('proof')">Proof Vault</button>
            <button onclick="showCompanionTab('council')">Council Mode</button>
            <button class="tab-action" onclick="openNewCompanionDialog()">New Companion</button>
          </div>
        </div>
        <div class="panel">
          <h2>Packet Handoff</h2>
          <label>Companion</label>
          <select id="companionSelect"></select>
          <div class="row" style="margin-top: 10px;">
            <button class="inline primary" onclick="copyPacket()">Copy Packet</button>
            <button class="inline primary" onclick="downloadPacket()">Download Packet</button>
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
          <div class="row" style="margin-top:10px;">
            <button class="inline" onclick="previewCommands()">Preview Commands</button>
            <button class="inline primary" onclick="applyCommands()">Apply Commands</button>
          </div>
          <div id="commandPreview" class="empty-state" style="display:none;"></div>
        </div>
        <div class="panel full">
          <h2>ID-Only Memory Index</h2>
          <div id="memoryIndex"></div>
        </div>
        <div class="panel full">
          <h2>Archive Search</h2>
          <div class="row">
            <input id="archiveSearch" placeholder="tag, category, archived reason, or ID">
            <button class="inline primary" onclick="loadArchive()">Search Archive</button>
          </div>
          <div id="archiveTagCloud"></div>
          <div id="archiveList"></div>
        </div>
      </div>
    </section>
    <section id="directives" data-companion-only>
      <div class="grid">
        <div class="panel full">
          <h2>Companion</h2>
          <div class="tab-row">
            <button onclick="showCompanionTab('memory')">Memory</button>
            <button class="active" onclick="showCompanionTab('directives')">Directive Ledger</button>
            <button onclick="showCompanionTab('proof')">Proof Vault</button>
            <button onclick="showCompanionTab('council')">Council Mode</button>
            <button class="tab-action" onclick="openNewCompanionDialog()">New Companion</button>
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
          <div class="row">
            <div>
              <label>Type</label>
              <select id="directiveType">
                <option value="manual">Manual</option>
                <option value="health">Health</option>
                <option value="work">Work</option>
                <option value="family">Family</option>
                <option value="fitness">Fitness</option>
                <option value="princess_campaign">Princess Campaign</option>
                <option value="tiny_tyrant">Tiny Tyrant</option>
                <option value="project">Project</option>
                <option value="spiritual">Spiritual</option>
              </select>
            </div>
            <div>
              <label>Timezone</label>
              <input id="directiveTimezone" value="America/Chicago">
            </div>
          </div>
          <label>Tags</label>
          <input id="directiveTags" placeholder="health, project, manual">
          <label><input id="directiveProofRequired" type="checkbox" style="width:auto;"> Proof required</label>
          <button class="inline primary" onclick="createDirective()">Create Directive</button>
        </div>
        <div class="panel full">
          <h2>Ledger</h2>
          <div class="toolbar-row">
            <button class="inline primary" onclick="copyDirectiveExport()">Copy Directive Export</button>
            <div>
              <label>Filter type</label>
              <select id="directiveTypeFilter" onchange="renderDirectives()">
                <option value="all">All types</option>
                <option value="health">Health</option>
                <option value="work">Work</option>
                <option value="family">Family</option>
                <option value="fitness">Fitness</option>
                <option value="princess_campaign">Princess Campaign</option>
                <option value="tiny_tyrant">Tiny Tyrant</option>
                <option value="project">Project</option>
                <option value="spiritual">Spiritual</option>
                <option value="manual">Manual</option>
              </select>
            </div>
          </div>
          <div class="tab-row" id="directiveTabs">
            <button class="active" data-status="issued">Issued</button>
            <button data-status="complete">Completed</button>
            <button data-status="failed">Failed</button>
            <button data-status="all">All</button>
          </div>
          <div id="directiveList"></div>
        </div>
        <div class="panel full">
          <h2>Directive Import</h2>
          <label>Base64 directive export</label>
          <textarea id="directiveImportPacket" class="packet" placeholder="Paste companion-directive-export/v1 base64 here"></textarea>
          <div class="row" style="margin-top:10px;">
            <button class="inline" onclick="previewDirectiveImport()">Preview Import</button>
            <button class="inline primary" onclick="mergeDirectiveImport()">Import Directives</button>
          </div>
          <div id="directiveImportPreview" class="empty-state" style="display:none;"></div>
        </div>
      </div>
    </section>
    <section id="proof" data-companion-only>
      <div class="grid">
        <div class="panel full">
          <h2>Companion</h2>
          <div class="tab-row">
            <button onclick="document.querySelector('button[data-tab=memory]').click()">Memory</button>
            <button onclick="showCompanionTab('directives')">Directive Ledger</button>
            <button class="active" onclick="showCompanionTab('proof')">Proof Vault</button>
            <button onclick="showCompanionTab('council')">Council Mode</button>
            <button class="tab-action" onclick="openNewCompanionDialog()">New Companion</button>
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
    <section id="trackers" data-access-category="trackers">
      <div class="grid">
        <div class="panel full">
          <h2>Daily Check-ins</h2>
          <div class="tab-row" id="trackerTabs">
            <button class="active" data-tracker="summary">Summary</button>
            <button data-tracker="checkins">Check-In</button>
            <button data-tracker="journal">Journal</button>
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
            <label>Mood</label>
            <input id="journalMood" type="number" min="1" max="10" value="5">
            <label>Entry</label>
            <textarea id="journalEntry"></textarea>
            <button class="inline primary" onclick="saveJournalEntry()">Save Journal Entry</button>
            <div id="journalOpenPane" class="detail-box"></div>
            <div id="journalList"></div>
          </div>
        </div>
      </div>
    </section>
    <section id="fitness" data-access-category="fitness">
      <div class="grid">
        <div class="panel full">
          <h2>Recruit Rebuild Command Center</h2>
          <div class="tab-row" id="fitnessTabs">
            <button class="active" data-fitness="summary">Summary</button>
            <button data-fitness="orders">Today's Orders</button>
            <button data-fitness="plan">Workout Plan</button>
            <button data-fitness="mobility">Mobility</button>
            <button data-fitness="cardio">Cardio</button>
            <button data-fitness="strength">Strength</button>
            <button data-fitness="progress">Progress</button>
            <button data-fitness="challenges">Challenges</button>
            <button data-fitness="metrics">Body Metrics</button>
            <button data-fitness="history">History</button>
          </div>
          <div id="fitnessSummary"></div>
        </div>
        <div class="panel full fitness-view" data-fitness-view="orders">
          <h2>Today's Orders</h2>
          <button class="inline primary" onclick="startTodayOrder()">Start Today's Order</button>
          <button class="inline" onclick="askEvieAdjust()">Ask Evie to Adjust</button>
          <div id="fitnessOrders"></div>
        </div>
        <div class="panel full fitness-view" data-fitness-view="plan">
          <h2>Workout Plan</h2>
          <div class="field-grid">
            <div><label>Group</label><input id="fitnessGroupName" placeholder="Strength A"></div>
            <div><label>Type</label><input id="fitnessGroupType" placeholder="Strength, Cardio, Mobility"></div>
            <div><label>Notes</label><input id="fitnessGroupNotes"></div>
          </div>
          <button class="inline primary" onclick="createFitnessGroup()">Add Group</button>
          <div class="field-grid">
            <div><label>Exercise</label><input id="fitnessExerciseName" placeholder="Bodyweight squat"></div>
            <div><label>Format</label><select id="fitnessExerciseFormat"><option value="sets_reps">Sets/Reps</option><option value="duration_reps">Duration/Reps</option><option value="duration_distance">Duration/Distance</option></select></div>
            <div><label>Media URL</label><input id="fitnessExerciseMedia"></div>
          </div>
          <label>Exercise details</label>
          <textarea id="fitnessExerciseDetails"></textarea>
          <div class="field-grid">
            <div><label>Warning</label><input id="fitnessExerciseWarning"></div>
            <div><label>Progression</label><input id="fitnessExerciseProgression"></div>
            <div><label>Regression</label><input id="fitnessExerciseRegression"></div>
          </div>
          <button class="inline primary" onclick="createFitnessExercise()">Add Exercise</button>
          <h2 style="margin-top:14px;">Add Exercise to Group</h2>
          <div class="field-grid">
            <div><label>Group</label><select id="fitnessPlanGroupSelect"></select></div>
            <div><label>Exercise</label><select id="fitnessPlanExerciseSelect"></select></div>
            <div><label>Sets</label><input id="fitnessPlanSets" type="number" min="0" value="1"></div>
            <div><label>Reps</label><input id="fitnessPlanReps" type="number" min="0" value="0"></div>
            <div><label>Duration seconds</label><input id="fitnessPlanDuration" type="number" min="0" value="0"></div>
            <div><label>Distance</label><input id="fitnessPlanDistance"></div>
          </div>
          <label>Prescription notes</label>
          <input id="fitnessPlanNotes">
          <button class="inline primary" onclick="addFitnessGroupItem()">Add to Group</button>
          <div id="fitnessPlan"></div>
        </div>
        <div class="panel fitness-view" data-fitness-view="mobility">
          <h2>Mobility</h2>
          <div class="field-grid">
            <div><label>Minutes</label><input id="mobilityMinutes" type="number" min="0" value="5"></div>
            <div><label>Pain before</label><input id="mobilityPainBefore" type="number" min="0" max="10" value="0"></div>
            <div><label>Pain after</label><input id="mobilityPainAfter" type="number" min="0" max="10" value="0"></div>
          </div>
          <label>Notes</label><textarea id="mobilityNotes"></textarea>
          <button class="inline primary" onclick="logFitness('mobility')">Log Mobility</button>
          <button class="inline" onclick="reportPainEnergy()">Report Pain/Energy</button>
        </div>
        <div class="panel fitness-view" data-fitness-view="cardio">
          <h2>Cardio</h2>
          <div class="field-grid">
            <div><label>Minutes</label><input id="cardioMinutes" type="number" min="0" value="10"></div>
            <div><label>Distance</label><input id="cardioDistance" type="number" min="0" step="0.01" value="0"></div>
            <div><label>Breath 0-10</label><input id="cardioBreath" type="number" min="0" max="10" value="0"></div>
          </div>
          <label>Notes</label><textarea id="cardioNotes"></textarea>
          <button class="inline primary" onclick="logFitness('cardio')">Log Walk</button>
        </div>
        <div class="panel fitness-view" data-fitness-view="strength">
          <h2>Strength</h2>
          <div class="field-grid">
            <div><label>Exercise</label><input id="strengthExercise" value="Strength A"></div>
            <div><label>Sets</label><input id="strengthSets" type="number" min="0" value="1"></div>
            <div><label>Reps</label><input id="strengthReps" type="number" min="0" value="5"></div>
          </div>
          <label>Notes</label><textarea id="strengthNotes"></textarea>
          <button class="inline primary" onclick="logFitness('strength')">Log Strength</button>
        </div>
        <div class="panel fitness-view" data-fitness-view="progress">
          <h2>Progress</h2>
          <label>Progress note</label><textarea id="progressNote"></textarea>
          <button class="inline primary" onclick="logFitness('progress_notes')">Add Progress Note</button>
          <div id="fitnessProgress"></div>
        </div>
        <div class="panel full fitness-view" data-fitness-view="challenges">
          <h2>Challenges</h2>
          <div id="fitnessChallenges"></div>
        </div>
        <div class="panel fitness-view" data-fitness-view="metrics">
          <h2>Body Metrics</h2>
          <div class="field-grid">
            <div><label>Weight</label><input id="metricWeight" type="number" min="0" step="0.1"></div>
            <div><label>Waist</label><input id="metricWaist" type="number" min="0" step="0.1"></div>
            <div><label>Energy 0-10</label><input id="metricEnergy" type="number" min="0" max="10"></div>
          </div>
          <label>Notes</label><textarea id="metricNotes"></textarea>
          <button class="inline primary" onclick="logFitness('body_metrics')">Save Body Metrics</button>
        </div>
        <div class="panel full fitness-view" data-fitness-view="history">
          <h2>History</h2>
          <div id="fitnessHistory"></div>
        </div>
      </div>
    </section>
    <section id="spiritual" data-access-category="spiritual">
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
    <section id="projects" data-access-category="projects">
      <div class="grid">
        <div class="panel full">
          <h2>Projects</h2>
          <div class="tab-row" id="projectTabs">
            <button class="active" data-project="home">Home Maintenance</button>
            <button data-project="vehicle">Vehicle Maintenance</button>
            <button data-project="tech">Tech Projects</button>
          </div>
          <div class="toolbar-row">
            <div>
              <label>Project category</label>
              <select id="projectCategoryFilter"></select>
            </div>
            <div>
              <label>Status</label>
              <select id="projectStatusFilter">
                <option value="all">All statuses</option>
                <option value="open">Open</option>
                <option value="done">Done</option>
              </select>
            </div>
            <div>
              <label>Sort</label>
              <select id="projectSortOrder">
                <option value="updated_desc">Updated newest</option>
                <option value="due_asc">Due soonest</option>
                <option value="title_asc">Title A-Z</option>
                <option value="status_asc">Status</option>
                <option value="category_asc">Category</option>
              </select>
            </div>
          </div>
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
    <section id="chores" data-access-category="chores">
      <div class="grid">
        <div class="panel">
          <h2>Chores</h2>
          <label>Chore</label>
          <input id="choreTitle">
          <div class="row">
            <div>
              <label>Due date</label>
              <input id="choreDueDate" type="date">
            </div>
            <div>
              <label>Recurrence</label>
              <select id="choreRecurrenceType">
                <option value="none">One-off</option>
                <option value="weekly">Weekly</option>
                <option value="biweekly">Bi-weekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
            <div>
              <label>Weekday</label>
              <select id="choreRecurrenceWeekday">
                <option value="0">Monday</option>
                <option value="1">Tuesday</option>
                <option value="2">Wednesday</option>
                <option value="3">Thursday</option>
                <option value="4">Friday</option>
                <option value="5">Saturday</option>
                <option value="6">Sunday</option>
              </select>
            </div>
            <div>
              <label>Month day</label>
              <input id="choreRecurrenceMonthDay" type="number" min="1" max="31" value="1">
            </div>
          </div>
          <label>Notes</label>
          <textarea id="choreNotes"></textarea>
          <button class="inline primary" onclick="createChore()">Add Chore</button>
        </div>
        <div class="panel">
          <h2>Chore List</h2>
          <div id="choreList"></div>
        </div>
      </div>
    </section>
    <section id="diet" data-access-category="diet">
      <div class="grid">
        <div class="panel full">
          <h2>Diet</h2>
          <div class="tab-row" id="dietTabs">
            <button class="active" data-diet="summary">Summary</button>
            <button data-diet="inventory">Inventory</button>
            <button data-diet="shopping">Shopping List</button>
            <button data-diet="food">Food Diary</button>
          </div>
        </div>
        <div class="panel full diet-view active" data-diet-view="summary">
          <h2>Summary</h2>
          <div id="dietSummary"></div>
        </div>
        <div class="panel full diet-view" data-diet-view="inventory">
          <h2>Inventory</h2>
          <div class="field-grid">
            <div><label>Item</label><input id="dietItemName"></div>
            <div><label>Unit</label><input id="dietItemUnit" placeholder="lb, egg, can"></div>
            <div><label>On-hand</label><input id="dietItemOnHand" type="number" min="0" step="0.01" value="0"></div>
            <div><label>Par</label><input id="dietItemPar" type="number" min="0" step="0.01" value="0"></div>
            <div><label>Reorder at</label><input id="dietItemReorder" type="number" min="0" step="0.01" value="0"></div>
            <div><label>Container quantity</label><input id="dietItemContainerSize" type="number" min="0.01" step="0.01" value="1"></div>
            <div><label>Cost per container</label><input id="dietItemCost" type="number" min="0" step="0.01" value="0"></div>
          </div>
          <button class="inline primary" onclick="createDietInventoryItem()">Add Item</button>
          <div id="dietInventoryList"></div>
        </div>
        <div class="panel full diet-view" data-diet-view="shopping">
          <h2>Shopping List</h2>
          <button class="inline primary" onclick="copyShoppingList()">Copy Shopping List</button>
          <div id="dietShoppingList"></div>
        </div>
        <div class="panel full diet-view" data-diet-view="food">
          <h2>Food Diary</h2>
          <div class="field-grid">
            <div><label>Date</label><input id="foodDate" type="date"></div>
            <div><label>Food</label><input id="foodText"></div>
            <label><input id="foodCarbs" type="checkbox" style="width:auto;"> Carbs</label>
            <label><input id="foodSugars" type="checkbox" style="width:auto;"> Sugars</label>
          </div>
          <button class="inline primary" onclick="createFoodEntry()">Add Food</button>
          <label>CSV input</label>
          <textarea id="foodCsv" placeholder="YYYY-MM-DD, food, carbs yes/no, sugars yes/no"></textarea>
          <button class="inline" onclick="importFoodCsv()">Import CSV</button>
          <div id="foodDiaryList"></div>
        </div>
      </div>
    </section>
    <section id="calendar">
      <div class="grid">
        <div class="panel">
          <h2>Calendar</h2>
          <div class="field-grid">
            <div><label>Date</label><input id="calendarDate" type="date"></div>
            <div><label>Category</label><select id="calendarCategory">
              <option value="fitness">Fitness</option>
              <option value="projects">Projects</option>
              <option value="chores">Chores</option>
              <option value="diet">Diet</option>
              <option value="spiritual">Spiritual</option>
              <option value="directives">Companion Directives</option>
              <option value="general">General</option>
            </select></div>
            <div><label>Source</label><select id="calendarSourceId"></select></div>
          </div>
          <label>Title</label>
          <input id="calendarTitle">
          <label>Notes</label>
          <textarea id="calendarNotes"></textarea>
          <button class="inline primary" onclick="createCalendarEvent()">Add Event</button>
        </div>
        <div class="panel full">
          <div class="calendar-toolbar">
            <button class="inline" onclick="shiftCalendarMonth(-1)">Previous</button>
            <h2 id="calendarMonthLabel">Calendar</h2>
            <button class="inline" onclick="shiftCalendarMonth(1)">Next</button>
          </div>
          <div id="calendarGrid"></div>
        </div>
        <div class="panel full">
          <h2>Saved Items</h2>
          <div id="calendarList"></div>
        </div>
      </div>
    </section>
    <section id="profileSettings">
      <div class="grid">
        <div class="panel">
          <h2>Profile Settings</h2>
          <label>Display name</label>
          <input id="profileDisplayName">
          <button class="inline primary" onclick="saveProfileSettings()">Save Profile</button>
        </div>
        <div class="panel">
          <h2>Password</h2>
          <label>Current password</label>
          <input id="profileCurrentPassword" type="password">
          <label>New password</label>
          <input id="profileNewPassword" type="password">
          <button class="inline primary" onclick="saveProfilePassword()">Change Password</button>
        </div>
      </div>
    </section>
    <section id="admin" data-admin-only>
      <div class="grid">
        <div class="panel">
          <h2>Admin Console</h2>
          <label>Profile</label>
          <select id="adminProfileSelect" onchange="renderAdminProfile()"></select>
          <label><input id="adminApproved" type="checkbox" style="width:auto;"> Approved</label>
          <label><input id="adminActive" type="checkbox" style="width:auto;"> Active</label>
          <div id="adminAccessList"></div>
          <label>Reset password</label>
          <input id="adminResetPassword" type="password" placeholder="new password">
          <button class="inline primary" onclick="saveAdminProfile()">Save Profile Access</button>
          <button class="inline" onclick="adminResetSelectedPassword()">Reset Password</button>
        </div>
        <div class="panel">
          <h2>Session Timeout</h2>
          <label>Timed-out timer, minutes</label>
          <input id="sessionTimeoutMinutes" type="number" min="1" max="1440" value="30">
          <button class="inline primary" onclick="saveSessionTimeout()">Save Timeout</button>
          <div id="adminStatusList"></div>
        </div>
      </div>
    </section>
    <section id="council" data-companion-only>
      <div class="panel">
        <h2>Companion</h2>
        <div class="tab-row">
          <button onclick="showCompanionTab('memory')">Memory</button>
          <button onclick="showCompanionTab('directives')">Directive Ledger</button>
          <button onclick="showCompanionTab('proof')">Proof Vault</button>
          <button class="active" onclick="showCompanionTab('council')">Council Mode</button>
          <button class="tab-action" onclick="openNewCompanionDialog()">New Companion</button>
        </div>
        <h2>Council Mode</h2>
        <label>Council question</label>
        <textarea id="councilQuestion"></textarea>
        <div class="row" style="margin: 10px 0;">
          <button class="inline primary" onclick="copyAllCouncilQuestions()">Copy Question For All</button>
          <button class="inline primary" onclick="copyCouncilSummary()">Copy Consolidated Answer</button>
        </div>
        <div id="councilCompanions"></div>
      </div>
    </section>
    <dialog id="newCompanionDialog">
      <h2>New Companion</h2>
      <label>Name</label>
      <input id="newCompanionName">
      <label>Filename</label>
      <input id="newCompanionFile" placeholder="optional-name-memories.md">
      <div class="row" style="margin-top: 12px;">
        <button class="inline primary" onclick="createCompanion()">Create Companion</button>
        <button class="inline" onclick="closeNewCompanionDialog()">Cancel</button>
      </div>
    </dialog>
  </main>
  <script>
    let state = null;
    let sessionInfo = null;
    let selectedCompanion = null;
    let selectedDirectiveStatus = 'issued';
    let selectedTrackerTab = 'summary';
    let selectedSpiritualTab = 'summary';
    let selectedPrayerCategory = 'gratitude';
    let selectedProjectCategory = 'home';
    let selectedProjectTodoId = null;
    let selectedDietTab = 'summary';
    let selectedFitnessTab = 'summary';
    let selectedCalendarMonth = new Date();
    let councilAnswers = {};

    const nativeFetch = window.fetch.bind(window);
    function activeProfileName() {
      return (state && state.profile && state.profile.name) || 'Array';
    }
    function setActiveProfile(name) {
      return name || 'Array';
    }
    function profileQuery() {
      return '';
    }
    window.fetch = (resource, options = {}) => {
      const requestOptions = Object.assign({}, options);
      requestOptions.credentials = 'same-origin';
      return nativeFetch(resource, requestOptions);
    };

    document.getElementById('profileLoginButton').addEventListener('click', async () => {
      const name = document.getElementById('loginProfileSelect').value || 'Array';
      const password = document.getElementById('loginPassword').value;
      const endpoint = sessionInfo && sessionInfo.bootstrap_required && name === 'Array' ? '/api/auth/bootstrap' : '/api/auth/login';
      const body = endpoint.endsWith('bootstrap') ? { password } : { name, password };
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      document.getElementById('loginPassword').value = '';
      selectedCompanion = null;
      selectedProjectTodoId = null;
      await loadState();
    });

    document.getElementById('profileLogoutButton').addEventListener('click', async () => {
      const res = await fetch('/api/auth/logout', { method: 'POST' });
      await handleResponse(res);
      state = null;
      await loadSession();
    });

    document.getElementById('profileRegisterButton').addEventListener('click', async () => {
      const name = document.getElementById('profileRegisterName').value.trim();
      const password = document.getElementById('profileRegisterPassword').value;
      if (!name || !password) {
        setStatus('Enter a profile name and password.');
        return;
      }
      const res = await fetch('/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, password })
      });
      await handleResponse(res);
      document.getElementById('profileRegisterName').value = '';
      document.getElementById('profileRegisterPassword').value = '';
      await loadSession();
    });

    document.getElementById('profileSettingsButton').addEventListener('click', () => {
      document.querySelector('button[data-tab="profileSettings"]').click();
    });

    document.getElementById('adminButton').addEventListener('click', () => {
      document.querySelector('button[data-tab="admin"]').click();
    });

    async function loadSession() {
      const res = await fetch('/api/session');
      sessionInfo = await handleResponse(res, false);
      renderLoginControls();
      if (sessionInfo.authenticated) {
        await loadState();
      } else {
        applyLoggedOutState();
      }
    }

    function renderLoginControls() {
      const profiles = sessionInfo.profiles || [];
      const select = document.getElementById('loginProfileSelect');
      select.innerHTML = profiles.map(profile => `<option value="${escapeHtml(profile.name)}">${escapeHtml(profile.display_name || profile.name)}${profile.approved && profile.active ? '' : ' (pending)'}</option>`).join('');
      if (sessionInfo.bootstrap_required) select.value = 'Array';
      document.getElementById('profileLoginButton').textContent = sessionInfo.bootstrap_required ? 'Set Array Password' : 'Log In';
      for (const id of ['loginProfileSelect', 'loginPassword', 'profileLoginButton', 'profileRegisterName', 'profileRegisterPassword', 'profileRegisterButton']) {
        document.getElementById(id).style.display = sessionInfo.authenticated ? 'none' : '';
      }
      document.getElementById('activeProfileLabel').textContent = sessionInfo.authenticated && sessionInfo.profile ? `Signed in: ${sessionInfo.profile.display_name || sessionInfo.profile.name}` : '';
      document.getElementById('profileLogoutButton').style.display = sessionInfo.authenticated ? '' : 'none';
      document.getElementById('profileSettingsButton').style.display = sessionInfo.authenticated ? '' : 'none';
      document.getElementById('authPanel').style.display = '';
      document.getElementById('sessionPanel').style.display = sessionInfo.authenticated ? '' : 'none';
      document.getElementById('loginPanel').style.display = sessionInfo.authenticated ? 'none' : '';
      document.getElementById('registerPanel').style.display = sessionInfo.authenticated ? 'none' : '';
      document.getElementById('dashboardContent').style.display = sessionInfo.authenticated ? '' : 'none';
      renderSessionSummary();
    }

    function renderSessionSummary() {
      const target = document.getElementById('sessionSummary');
      if (!target) return;
      if (!sessionInfo || !sessionInfo.authenticated || !sessionInfo.profile) {
        target.innerHTML = '<p class="muted">Not signed in.</p>';
        return;
      }
      const profile = sessionInfo.profile || {};
      const access = (state && state.access) || profile.access || {};
      const categories = Object.entries(sessionInfo.access_categories || {})
        .map(([key, label]) => `<span class="pill">${escapeHtml(label)}: ${access[key] ? 'on' : 'off'}</span>`)
        .join('');
      const companionAccess = access.companions ? '<span class="pill">Companion: on</span>' : '<span class="pill">Companion: off</span>';
      target.innerHTML = `<p><strong>Signed in as ${escapeHtml(profile.display_name || profile.name || '')}</strong></p><p class="muted">${escapeHtml(profile.role || 'profile')}</p><div>${companionAccess}${categories}</div>`;
    }

    function applyLoggedOutState() {
      document.querySelectorAll('nav button').forEach(button => button.classList.remove('active'));
      document.querySelectorAll('nav button').forEach(button => {
        button.style.display = button.dataset.tab === 'dashboard' ? '' : 'none';
      });
      document.querySelectorAll('[data-companion-only], [data-admin-only], [data-access-category]').forEach(element => {
        element.style.display = 'none';
      });
      document.getElementById('authPanel').style.display = '';
      document.getElementById('sessionPanel').style.display = 'none';
      document.getElementById('loginPanel').style.display = '';
      document.getElementById('registerPanel').style.display = '';
      document.getElementById('dashboardContent').style.display = 'none';
      document.querySelectorAll('section').forEach(section => section.classList.remove('active'));
      document.querySelector('button[data-tab="dashboard"]').classList.add('active');
      document.getElementById('dashboard').classList.add('active');
      selectedCompanion = null;
      selectedProjectTodoId = null;
      setStatus(sessionInfo.bootstrap_required ? 'Set the first Array password.' : 'Login required.');
    }

    document.querySelectorAll('nav button').forEach(button => {
      button.addEventListener('click', () => {
        document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('section').forEach(s => s.classList.remove('active'));
        button.classList.add('active');
        document.getElementById(button.dataset.tab).classList.add('active');
      });
    });

    function showCompanionTab(tab) {
      const target = tab === 'memory' ? 'memory' : tab;
      document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
      const companionButton = document.querySelector('button[data-tab="memory"]');
      if (companionButton) companionButton.classList.add('active');
      document.querySelectorAll('section').forEach(s => s.classList.remove('active'));
      document.getElementById(target).classList.add('active');
    }

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

    document.querySelectorAll('#dietTabs button').forEach(button => {
      button.addEventListener('click', () => {
        selectedDietTab = button.dataset.diet;
        renderDietTabs();
      });
    });

    document.querySelectorAll('#fitnessTabs button').forEach(button => {
      button.addEventListener('click', () => {
        selectedFitnessTab = button.dataset.fitness;
        renderFitnessTabs();
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
    document.getElementById('projectStatusFilter').addEventListener('change', () => {
      selectedProjectTodoId = null;
      renderProjects();
    });
    document.getElementById('projectSortOrder').addEventListener('change', renderProjects);

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
    document.getElementById('choreRecurrenceType').addEventListener('change', renderChoreRecurrenceControls);
    document.getElementById('calendarCategory').addEventListener('change', () => {
      renderCalendarSourceOptions();
      fillCalendarTitleFromSource();
    });
    document.getElementById('calendarSourceId').addEventListener('change', fillCalendarTitleFromSource);

    document.getElementById('checkinDate').value = new Date().toISOString().slice(0, 10);
    document.getElementById('foodDate').value = new Date().toISOString().slice(0, 10);
    document.getElementById('calendarDate').value = new Date().toISOString().slice(0, 10);
    renderChoreRecurrenceControls();

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
      sessionInfo = Object.assign({}, sessionInfo || {}, { authenticated: true, profile: state.profile, profiles: state.profiles || [], settings: state.settings || {}, access_categories: state.access_categories || {}, bootstrap_required: false });
      renderProfileControls();
      applyAccessControls();
      renderSelectors();
      renderDashboard();
      renderDirectives();
      renderProof();
      renderTrackers();
      renderFitness();
      renderSpiritual();
      renderProjects();
      renderChores();
      renderDiet();
      renderCalendar();
      renderProfileSettings();
      renderAdmin();
      renderCouncil();
      if ((state.access || {}).companions && selectedCompanion) {
        await loadPacket();
        renderMemoryIndex();
      }
      renderMemoryIndex();
      const active = document.querySelector('section.active');
      if (!active) {
        document.querySelector('button[data-tab="dashboard"]').click();
      }
      setStatus('Ready.');
    }

    function renderProfileControls() {
      const profiles = state.profiles || [];
      const currentName = (state.profile || {}).name || activeProfileName();
      const select = document.getElementById('loginProfileSelect');
      select.innerHTML = profiles.map(profile => `<option value="${escapeHtml(profile.name)}">${escapeHtml(profile.display_name || profile.name)}${profile.approved && profile.active ? '' : ' (pending)'}</option>`).join('');
      select.value = currentName;
      renderLoginControls();
    }

    function applyAccessControls() {
      const companionAccess = Boolean((state.access || {}).companions);
      document.querySelectorAll('nav button').forEach(button => {
        if (!button.dataset.companionOnly && !button.dataset.adminOnly && !button.dataset.accessCategory) {
          button.style.display = '';
        }
      });
      document.querySelectorAll('[data-companion-only]').forEach(element => {
        element.style.display = companionAccess ? '' : 'none';
      });
      document.querySelectorAll('[data-admin-only]').forEach(element => {
        element.style.display = companionAccess ? '' : 'none';
      });
      document.querySelectorAll('[data-access-category]').forEach(element => {
        const allowed = Boolean((state.access || {})[element.dataset.accessCategory]);
        element.style.display = allowed ? '' : 'none';
      });
      if (!companionAccess) {
        for (const tab of ['memory', 'directives', 'proof', 'council']) {
          document.querySelectorAll(`section#${tab}`).forEach(section => section.classList.remove('active'));
        }
      }
      const active = document.querySelector('section.active');
      if (active && active.style.display === 'none') {
        document.querySelector('button[data-tab="dashboard"]').click();
      }
      if (!document.querySelector('section.active')) {
        const firstAllowed = Array.from(document.querySelectorAll('nav button')).find(button => button.style.display !== 'none');
        if (firstAllowed) firstAllowed.click();
        else document.getElementById('dashboard').classList.add('active');
      }
    }

    function renderSelectors() {
      const companionOptions = `<option value="">Select companion</option>` + state.companions.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)}</option>`).join('');
      for (const id of ['companionSelect', 'directiveIssuer']) {
        const select = document.getElementById(id);
        if (!select) continue;
        select.innerHTML = companionOptions;
        if (selectedCompanion) select.value = selectedCompanion;
      }
      document.getElementById('categorySelect').innerHTML = (state.categories || []).map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
      document.getElementById('proofDirective').innerHTML = (state.directives || []).map(d => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.id)} - ${escapeHtml(d.title)}</option>`).join('');
    }

    async function loadPacket() {
      if (!selectedCompanion) {
        document.getElementById('packetBox').value = '';
        return;
      }
      const res = await fetch(`/api/companion/${encodeURIComponent(selectedCompanion)}/packet`);
      const data = await handleResponse(res, false);
      document.getElementById('packetBox').value = data.packet;
      await loadArchive();
    }

    function currentCompanion() {
      return state.companions.find(c => c.name === selectedCompanion);
    }

    function renderMemoryIndex() {
      if (!((state.access || {}).companions)) return;
      const companion = currentCompanion();
      if (!companion) {
        document.getElementById('memoryIndex').innerHTML = '<p class="muted">No companion selected.</p>';
        document.getElementById('archiveTagCloud').innerHTML = '';
        document.getElementById('archiveList').innerHTML = '<p class="muted">No companion selected.</p>';
        return;
      }
      if (companion.error) {
        document.getElementById('memoryIndex').innerHTML = `<p class="muted">${escapeHtml(companion.summary)}</p><p class="muted">${escapeHtml(companion.error)}</p>`;
        return;
      }
      const rows = companion.index.map(entry => {
        const active = String(entry.status || '').toLowerCase() === 'active';
        const actions = active
          ? `<button class="inline" onclick="archiveMemoryId('${escapeJs(entry.id)}','archive')">Archive</button>`
          : `<button class="inline" onclick="archiveMemoryId('${escapeJs(entry.id)}','unarchive')">Unarchive</button> <button class="inline" onclick="archiveMemoryId('${escapeJs(entry.id)}','resave')">Resave</button>`;
        return `<tr><td>${escapeHtml(entry.id || '')}</td><td>${escapeHtml(entry.category || '')}</td><td>${escapeHtml(entry.status || '')}</td><td>${escapeHtml(String(entry.weight || ''))}</td><td>${escapeHtml((entry.tags || []).join(', '))}</td><td>${escapeHtml(entry.updated_at || entry.created_at || '')}</td><td>${actions}</td></tr>`;
      }).join('');
      document.getElementById('memoryIndex').innerHTML = `<p class="muted">${escapeHtml(companion.summary)}</p><div class="scrollbox"><table><thead><tr><th>ID</th><th>Category</th><th>Status</th><th>Weight</th><th>Tags</th><th>Updated</th><th>Actions</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }

    async function loadArchive() {
      if (!selectedCompanion) return;
      const query = document.getElementById('archiveSearch').value || '';
      const res = await fetch(`/api/companion/${encodeURIComponent(selectedCompanion)}/archive?q=${encodeURIComponent(query)}`);
      const archive = await handleResponse(res, false);
      document.getElementById('archiveTagCloud').innerHTML = (archive.tags || []).map(item => `<button class="inline" onclick="document.getElementById('archiveSearch').value='${escapeJs(item.tag)}'; loadArchive();">${escapeHtml(item.tag)} (${escapeHtml(item.count)})</button>`).join('') || '<p class="muted">No archive tags yet.</p>';
      const rows = (archive.entries || []).map(entry => `<tr><td>${escapeHtml(entry.id)}</td><td>${escapeHtml(entry.category)}</td><td>${escapeHtml((entry.tags || []).join(', '))}</td><td>${escapeHtml(entry.archived_at || '')}</td><td>${escapeHtml(entry.archived_reason || '')}</td><td><button class="inline" onclick="archiveMemoryId('${escapeJs(entry.id)}','unarchive')">Unarchive</button> <button class="inline" onclick="archiveMemoryId('${escapeJs(entry.id)}','resave')">Resave</button></td></tr>`).join('');
      document.getElementById('archiveList').innerHTML = `<div class="scrollbox"><table><thead><tr><th>ID</th><th>Category</th><th>Tags</th><th>Archived</th><th>Reason</th><th>Actions</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="muted">No archived IDs match.</td></tr>'}</tbody></table></div>`;
    }

    async function archiveMemoryId(memoryId, archiveAction) {
      if (!selectedCompanion || !memoryId) return;
      const res = await fetch(`/api/companion/${encodeURIComponent(selectedCompanion)}/archive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: memoryId, archive_action: archiveAction })
      });
      await handleResponse(res);
      await loadState();
    }

    function renderDashboard() {
      const summary = state.trackers.summary;
      const companionAccess = Boolean((state.access || {}).companions);
      const directiveSummary = state.directive_summary || { issued: 0, complete: 0, failed: 0, proof_required: 0 };
      const latest = state.trackers.latest_checkin;
      if (companionAccess) {
        const memoryRows = state.companions.reduce((count, companion) => count + (companion.index || []).length, 0);
        document.getElementById('dashCompanions').textContent = state.companions.length;
        document.getElementById('dashMemory').textContent = `${memoryRows} indexed memory IDs`;
        document.getElementById('dashDirectives').textContent = state.directives.length;
        document.getElementById('dashDirectiveDetail').textContent = `${directiveSummary.issued} issued, ${directiveSummary.complete} complete, ${directiveSummary.failed} failed, ${directiveSummary.proof_required} proof required`;
      }
      document.getElementById('dashPhysical').textContent = summary.physical_entries;
      document.getElementById('dashPhysicalDetail').textContent = latest ? `${latest.body.fitness_completed ? 'fitness complete' : 'fitness open'}, ${latest.body.sleep_hours || 0}h sleep latest` : 'No daily check-in yet.';
      document.getElementById('dashSpirit').textContent = latest ? (latest.spirit.scripture ? 'read' : 'open') : '--';
      document.getElementById('dashSpiritDetail').textContent = latest ? `${latest.spirit.prayer ? 'prayer' : 'no prayer logged'} / ${latest.spirit.reading_status || 'no reading status'}` : 'No spiritual check-in yet.';
      const dietSummary = (state.diet || {}).summary || {};
      document.getElementById('dashDiet').textContent = dietSummary.shopping_item_count || 0;
      document.getElementById('dashDietDetail').textContent = `$${Number(dietSummary.shopping_cart_cost || 0).toFixed(2)} shopping estimate`;
      const projectBuckets = Object.values((state.projects || {}).summary || {});
      const openProjects = projectBuckets.reduce((total, item) => total + (item.open || 0), 0);
      document.getElementById('dashProjects').textContent = openProjects;
      document.getElementById('dashProjectsDetail').textContent = `${projectBuckets.reduce((total, item) => total + (item.total || 0), 0)} total project item(s)`;
      const chores = state.chores || [];
      document.getElementById('dashChores').textContent = chores.filter(chore => String(chore.status || 'open').toLowerCase() !== 'done').length;
      document.getElementById('dashChoresDetail').textContent = `${chores.length} chore(s) tracked`;
      const events = ((state.calendar || {}).all_events || (state.calendar || {}).events || []);
      document.getElementById('dashCalendar').textContent = events.length;
      document.getElementById('dashCalendarDetail').textContent = events.slice(-1)[0] ? `${events.slice(-1)[0].date}: ${events.slice(-1)[0].title}` : 'No scheduled items.';
      if (companionAccess) {
        const integrity = state.integrity || { ok: true, issues: [] };
        document.getElementById('dashIntegrity').textContent = integrity.ok ? 'OK' : integrity.issues.length;
        document.getElementById('dashIntegrityDetail').textContent = integrity.ok ? `Checked ${integrity.checked_at || ''}` : `${integrity.issues.length} issue(s) found`;
      }
      document.getElementById('dashWorkCloud').innerHTML = renderTagCloud(state.trackers.work_categories, state.trackers.task_categories);
      document.getElementById('dashLatestCheckin').innerHTML = latest ? renderCheckinCard(latest) : emptyState('No daily check-ins yet.', 'Saved check-ins will appear here.');
    }

    async function copyPacket() {
      await copyToClipboard(
        document.getElementById('packetBox').value.trim(),
        `Copied ${selectedCompanion} packet.`,
        'Could not copy packet.'
      );
    }

    function downloadPacket() {
      const packet = document.getElementById('packetBox').value.trim();
      if (!selectedCompanion || !packet) {
        setStatus('Select a companion before downloading a packet.');
        return;
      }
      const safeCompanion = selectedCompanion.replace(/[^A-Za-z0-9_-]+/g, '_') || 'companion';
      const blob = new Blob([`${packet}\n`], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${safeCompanion}-memory-packet.txt`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus(`Downloaded ${selectedCompanion} packet.`);
    }

    async function copyHandoff() {
      const res = await fetch(`/api/companion/${encodeURIComponent(selectedCompanion)}/handoff`);
      const data = await handleResponse(res, false);
      await copyToClipboard(data.handoff, `Copied ${selectedCompanion} handoff.`, 'Could not copy handoff.');
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

    async function previewCommands() {
      const body = { commands: document.getElementById('commandBatch').value };
      const res = await fetch(`/api/companion/${encodeURIComponent(selectedCompanion)}/commands/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await handleResponse(res, false);
      const counts = data.counts || {};
      const lines = Object.entries(counts).filter(([, count]) => count).map(([key, count]) => `<span class="pill">${escapeHtml(key)} ${escapeHtml(count)}</span>`).join('');
      const titles = (data.directive_titles || []).map(title => `<li>${escapeHtml(title)}</li>`).join('');
      const target = document.getElementById('commandPreview');
      target.style.display = '';
      target.innerHTML = `<strong>${escapeHtml(data.line_count || 0)} command line(s)</strong><div>${lines || '<span class="muted">No recognized operations.</span>'}</div>${titles ? `<ul>${titles}</ul>` : ''}<p class="muted">${escapeHtml(data.privacy || '')}</p>`;
      setStatus('Command preview ready.');
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
      closeNewCompanionDialog();
      await loadState();
    }

    function openNewCompanionDialog() {
      const dialog = document.getElementById('newCompanionDialog');
      if (dialog.showModal) dialog.showModal();
      else dialog.setAttribute('open', 'open');
      document.getElementById('newCompanionName').focus();
    }

    function closeNewCompanionDialog() {
      const dialog = document.getElementById('newCompanionDialog');
      if (dialog.open && dialog.close) dialog.close();
      else dialog.removeAttribute('open');
    }

    async function createDirective() {
      const body = {
        issuer: document.getElementById('directiveIssuer').value,
        title: document.getElementById('directiveTitle').value,
        details: document.getElementById('directiveDetails').value,
        priority: document.getElementById('directivePriority').value,
        due_at: document.getElementById('directiveDue').value,
        due_timezone: document.getElementById('directiveTimezone').value,
        type: document.getElementById('directiveType').value,
        tags: splitTagText(document.getElementById('directiveTags').value),
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
      document.getElementById('directiveTags').value = '';
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
      document.getElementById('directiveTimezone').value = data.directive.due_timezone || 'America/Chicago';
      document.getElementById('directiveType').value = data.directive.type || 'manual';
      document.getElementById('directiveTags').value = (data.directive.tags || []).join(', ');
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

    async function copyDirectiveExport() {
      const res = await fetch('/api/directives/export');
      const data = await handleResponse(res, false);
      await copyToClipboard(data.packet || '', `Copied directive export with ${data.count || 0} directive(s).`, 'Could not copy directive export.');
    }

    async function previewDirectiveImport() {
      const res = await fetch('/api/directives/import/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ packet: document.getElementById('directiveImportPacket').value })
      });
      const data = await handleResponse(res, false);
      const target = document.getElementById('directiveImportPreview');
      const statuses = Object.entries(data.status_counts || {}).map(([status, count]) => `<span class="pill">${escapeHtml(status)} ${escapeHtml(count)}</span>`).join('');
      const rows = (data.directives || []).map(item => `<tr><td>${escapeHtml(item.id)}</td><td>${escapeHtml(item.issuer)}</td><td>${escapeHtml(item.title)}</td><td>${escapeHtml(item.status)}</td><td>${escapeHtml(item.due)}</td><td>${escapeHtml(item.type)}</td></tr>`).join('');
      target.style.display = '';
      target.innerHTML = `<strong>${escapeHtml(data.count || 0)} directive(s) in packet</strong><div>${statuses}</div><div class="scrollbox"><table><thead><tr><th>ID</th><th>Issuer</th><th>Title</th><th>Status</th><th>Due</th><th>Type</th></tr></thead><tbody>${rows || tableEmpty(6, 'No directives found.', 'The packet decoded, but it did not contain importable directives.')}</tbody></table></div><p class="muted">${escapeHtml(data.privacy || '')}</p>`;
      setStatus('Directive import preview ready.');
    }

    async function mergeDirectiveImport() {
      const res = await fetch('/api/directives/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ packet: document.getElementById('directiveImportPacket').value })
      });
      const data = await handleResponse(res);
      document.getElementById('directiveImportPreview').style.display = '';
      document.getElementById('directiveImportPreview').innerHTML = `<strong>${escapeHtml(data.message || 'Import complete.')}</strong><p class="muted">Backup: ${escapeHtml(data.backup || 'not needed')}</p>`;
      await loadState();
    }

    function renderDirectives() {
      if (!((state.access || {}).directives)) return;
      const typeFilter = document.getElementById('directiveTypeFilter').value || 'all';
      const directives = selectedDirectiveStatus === 'all'
        ? state.directives
        : state.directives.filter(d => String(d.status || 'issued').toLowerCase() === selectedDirectiveStatus);
      const filtered = directives.filter(d => typeFilter === 'all' || String(d.type || 'manual') === typeFilter);
      const rows = filtered.map(d => {
        const statusClass = `status-${escapeHtml(String(d.status || 'issued').toLowerCase())}`;
        const proof = d.proof_required ? 'required' : '';
        const details = d.details ? escapeHtml(d.details) : '<span class="muted">No details supplied.</span>';
        const tags = (d.tags || []).map(tag => `<span class="pill">${escapeHtml(tag)}</span>`).join('');
        return `<tr><td>${escapeHtml(d.id)}</td><td>${escapeHtml(d.issuer)}</td><td>${escapeHtml(d.created_at || '')}</td><td><strong class="directive-title">${escapeHtml(d.title)}</strong><span class="pill">${escapeHtml(d.type || 'manual')}</span>${tags}<div class="directive-detail">${details}</div></td><td><span class="pill ${statusClass}">${escapeHtml(d.status)}</span></td><td>${escapeHtml(String(d.priority || ''))}</td><td>${escapeHtml(formatDirectiveDue(d.due_at))}<br><span class="muted">${escapeHtml(d.due_timezone || 'America/Chicago')}</span></td><td>${escapeHtml(proof)}</td><td><button class="inline" onclick="setDirectiveStatus('${escapeJs(d.id)}','complete')">Complete</button> <button class="inline" onclick="setDirectiveStatus('${escapeJs(d.id)}','failed')">Fail</button> <button class="inline" onclick="setDirectiveStatus('${escapeJs(d.id)}','issued')">Reopen</button></td></tr>`;
      }).join('');
      const empty = tableEmpty(9, 'No directives match.', 'Change the status or type filter, or create/import a directive.');
      document.getElementById('directiveList').innerHTML = `<div class="scrollbox"><table><thead><tr><th>ID</th><th>Issuer</th><th>Date Added</th><th>Command</th><th>Status</th><th>Priority</th><th>Due</th><th>Proof</th><th>Actions</th></tr></thead><tbody>${rows || empty}</tbody></table></div>`;
    }

    function renderProof() {
      if (!((state.access || {}).proof)) return;
      const rows = state.proof.map(p => {
        const evidence = p.path || p.note || '';
        const action = p.path ? `<a class="inline" href="/api/proof/${encodeURIComponent(p.id)}/download">Download</a>` : '';
        return `<tr><td>${escapeHtml(p.id)}</td><td>${escapeHtml(p.directive_id)}</td><td>${escapeHtml(p.type)}</td><td>${escapeHtml(evidence)}</td><td>${escapeHtml(p.submitted_at)}</td><td>${action}</td></tr>`;
      }).join('');
      document.getElementById('proofList').innerHTML = `<div class="scrollbox"><table><thead><tr><th>ID</th><th>Directive</th><th>Type</th><th>Evidence</th><th>Submitted</th><th>Actions</th></tr></thead><tbody>${rows || tableEmpty(6, 'No proof submitted yet.', 'Uploaded files and proof notes will appear here.')}</tbody></table></div>`;
    }

    function renderTrackers() {
      const summary = state.trackers.summary;
      document.getElementById('trackerSummary').innerHTML = `<span class="pill">${summary.checkin_entries} check-ins</span> <span class="pill">${summary.journal_entries} journal</span> <span class="pill">${summary.task_entries} task logs</span> <span class="pill">${summary.physical_entries} fitness logs</span> ${renderTagCloud(state.trackers.work_categories, state.trackers.task_categories)}`;
      document.getElementById('dailySummary').innerHTML = renderDailySummary();
      renderTrackerTabs();
      document.getElementById('checkinList').innerHTML = renderCheckins(state.trackers.checkins);
      document.getElementById('journalList').innerHTML = renderJournalList(state.trackers.journal || []);
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
        <div class="panel"><h3>Latest Check-In</h3>${latest ? renderCheckinCard(latest) : emptyState('No daily check-ins yet.', 'Saved check-ins will appear here.')}</div>
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
      const statusFilter = document.getElementById('projectStatusFilter').value || 'all';
      const sortOrder = document.getElementById('projectSortOrder').value || 'updated_desc';
      const doneStatuses = new Set(['done', 'complete', 'completed']);
      const todos = (projects.todos || [])
        .filter(todo => todo.category === selectedProjectCategory)
        .filter(todo => {
          if (statusFilter === 'all') return true;
          const status = String(todo.status || 'open').toLowerCase();
          return statusFilter === 'done' ? doneStatuses.has(status) : !doneStatuses.has(status);
        })
        .sort((a, b) => {
          if (sortOrder === 'due_asc') return String(a.due_date || '9999-99-99').localeCompare(String(b.due_date || '9999-99-99')) || String(a.title || '').localeCompare(String(b.title || ''));
          if (sortOrder === 'title_asc') return String(a.title || '').localeCompare(String(b.title || ''));
          if (sortOrder === 'status_asc') return String(a.status || '').localeCompare(String(b.status || ''));
          if (sortOrder === 'category_asc') return String(a.category || '').localeCompare(String(b.category || '')) || String(a.title || '').localeCompare(String(b.title || ''));
          return String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || ''));
        });
      if (!todos.some(todo => todo.id === selectedProjectTodoId)) selectedProjectTodoId = todos.length ? todos[0].id : null;
      document.getElementById('projectTodoList').innerHTML = todos.length
        ? todos.map(todo => {
            const selected = todo.id === selectedProjectTodoId ? '<span class="pill">selected</span>' : '';
            return `<div class="todo-row"><strong>${escapeHtml(todo.title)}</strong> ${selected}<br><span class="muted">${escapeHtml(todo.status || 'open')} | due ${escapeHtml(todo.due_date || 'not set')} | updated ${escapeHtml(todo.updated_at || todo.created_at || '')} | next ${escapeHtml(todo.next_step || '')}</span><br><button class="inline" onclick="selectProjectTodo('${escapeJs(todo.id)}')">Select</button> <a class="inline primary" href="/projects/${encodeURIComponent(todo.id)}${profileQuery()}" target="_blank">Open Page</a> <button class="inline" onclick="loadProjectTodoIntoForm('${escapeJs(todo.id)}')">Edit</button> <button class="inline danger" onclick="deleteProjectTodo('${escapeJs(todo.id)}')">Delete</button></div>`;
          }).join('')
        : emptyState('No projects match.', 'Change the category/status filters, or add a project todo.');
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
        document.getElementById('projectTodoDetail').innerHTML = emptyState('No project selected.', 'Select a project to open, edit, upload files, or delete it.');
        return;
      }
      const category = ((state.projects || {}).categories || {})[todo.category] || todo.category;
      const assets = (todo.assets || []).map(asset => `<li><a href="/${escapeHtml(asset.path)}" target="_blank">${escapeHtml(asset.type)}: ${escapeHtml(asset.filename)}</a> <span class="muted">${escapeHtml(asset.note || '')}</span></li>`).join('') || '<li class="muted">No files uploaded yet.</li>';
      document.getElementById('projectAssetTodoId').value = todo.id;
      document.getElementById('projectTodoDetail').innerHTML = `<h3>${escapeHtml(todo.title)}</h3><span class="pill">${escapeHtml(category)}</span><span class="pill">${escapeHtml(todo.status || 'open')}</span><p class="muted">Added ${escapeHtml(todo.created_at || '')} | Started ${escapeHtml(todo.date_started || todo.start_date || '')}</p><a class="inline primary" href="/projects/${encodeURIComponent(todo.id)}${profileQuery()}" target="_blank">Open page</a> <button class="inline" onclick="loadProjectTodoIntoForm('${escapeJs(todo.id)}')">Edit</button> <button class="inline" onclick="setProjectTodoStatus('${escapeJs(todo.id)}','done')">Mark Done</button> <button class="inline" onclick="setProjectTodoStatus('${escapeJs(todo.id)}','open')">Reopen</button> <button class="inline" onclick="deleteProjectTodo('${escapeJs(todo.id)}')">Delete</button><h3>Files</h3><ul>${assets}</ul>`;
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

    function renderChores() {
      const chores = state.chores || [];
      renderChoreRecurrenceControls();
      document.getElementById('choreList').innerHTML = chores.length
        ? chores.slice().reverse().map(chore => `<div class="todo-row"><strong>${escapeHtml(chore.title)}</strong><br><span class="muted">${escapeHtml(chore.status || 'open')} | due ${escapeHtml(chore.due_date || '')} | ${escapeHtml(chore.recurrence || 'one-off')}</span><br><span>${escapeHtml(chore.notes || '')}</span><br><button class="inline" onclick="setChoreStatus('${escapeJs(chore.id)}','done')">Done</button> <button class="inline" onclick="setChoreStatus('${escapeJs(chore.id)}','open')">Reopen</button> <button class="inline" onclick="deleteChore('${escapeJs(chore.id)}')">Delete</button></div>`).join('')
        : emptyState('No chores yet.', 'Add one-off or recurring chores here.');
    }

    function renderChoreRecurrenceControls() {
      const type = document.getElementById('choreRecurrenceType').value || 'none';
      document.getElementById('choreRecurrenceWeekday').closest('div').style.display = ['weekly', 'biweekly'].includes(type) ? '' : 'none';
      document.getElementById('choreRecurrenceMonthDay').closest('div').style.display = type === 'monthly' ? '' : 'none';
    }

    async function createChore() {
      const recurrenceType = document.getElementById('choreRecurrenceType').value;
      const body = {
        title: document.getElementById('choreTitle').value,
        due_date: document.getElementById('choreDueDate').value,
        recurrence_type: recurrenceType,
        recurrence_day: recurrenceType === 'monthly' ? document.getElementById('choreRecurrenceMonthDay').value : document.getElementById('choreRecurrenceWeekday').value,
        notes: document.getElementById('choreNotes').value,
      };
      const res = await fetch('/api/chores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      for (const id of ['choreTitle', 'choreDueDate', 'choreNotes']) {
        document.getElementById(id).value = '';
      }
      document.getElementById('choreRecurrenceType').value = 'none';
      renderChoreRecurrenceControls();
      await loadState();
    }

    async function setChoreStatus(choreId, status) {
      const res = await fetch(`/api/chores/${encodeURIComponent(choreId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status })
      });
      await handleResponse(res);
      await loadState();
    }

    async function deleteChore(choreId) {
      if (!confirm('Delete this chore?')) return;
      const res = await fetch(`/api/chores/${encodeURIComponent(choreId)}`, { method: 'DELETE' });
      await handleResponse(res);
      await loadState();
    }

    function renderDiet() {
      renderDietTabs();
      renderDietSummary();
      renderDietInventory();
      renderDietShoppingList();
      renderFoodDiary();
    }

    function renderDietTabs() {
      document.querySelectorAll('#dietTabs button').forEach(button => {
        button.classList.toggle('active', button.dataset.diet === selectedDietTab);
      });
      document.querySelectorAll('[data-diet-view]').forEach(view => {
        view.classList.toggle('active', view.dataset.dietView === selectedDietTab);
      });
    }

    function renderDietSummary() {
      const summary = (state.diet || {}).summary || {};
      document.getElementById('dietSummary').innerHTML = `<div class="dashboard-grid">
        <div class="panel"><h3>Date since last carbs</h3><div class="metric">${escapeHtml(summary.last_carbs_date || 'none')}</div></div>
        <div class="panel"><h3>Date since last sugars</h3><div class="metric">${escapeHtml(summary.last_sugars_date || 'none')}</div></div>
        <div class="panel"><h3>Ketosis?</h3><div class="metric">${summary.ketosis ? 'Yes' : 'No'}</div><p class="muted">Since ${escapeHtml(summary.ketosis_start_date || 'unknown')}</p></div>
        <div class="panel"><h3>Items in shopping cart</h3><div class="metric">${escapeHtml(summary.shopping_item_count || 0)}</div></div>
        <div class="panel"><h3>Shopping cart cost</h3><div class="metric">$${escapeHtml(Number(summary.shopping_cart_cost || 0).toFixed(2))}</div></div>
      </div>`;
    }

    function renderDietInventory() {
      const items = ((state.diet || {}).inventory || []);
      document.getElementById('dietInventoryList').innerHTML = items.length
        ? `<div class="scrollbox"><table><thead><tr><th>Item</th><th>On-hand</th><th>Par</th><th>Diff</th><th>Container</th><th>Cost</th><th>Actions</th></tr></thead><tbody>${items.map(item => {
            const diff = Number(item.par || 0) - Number(item.on_hand || 0);
            return `<tr><td>${escapeHtml(item.name)}</td><td><input id="onhand-${escapeHtml(item.id)}" type="number" min="0" step="0.01" value="${escapeHtml(item.on_hand || 0)}"></td><td>${escapeHtml(item.par || 0)} ${escapeHtml(item.unit_label || '')}</td><td>${escapeHtml(diff.toFixed(2))}</td><td>${escapeHtml(item.container_size || 1)} ${escapeHtml(item.unit_label || '')}</td><td>$${escapeHtml(Number(item.cost_per_container || 0).toFixed(2))}</td><td><button class="inline" onclick="adjustInventory('${escapeJs(item.id)}',1)">+</button> <button class="inline" onclick="adjustInventory('${escapeJs(item.id)}',-1)">-</button> <button class="inline" onclick="saveInventoryOnHand('${escapeJs(item.id)}')">Save</button> <button class="inline danger" onclick="deleteInventoryItem('${escapeJs(item.id)}')">Delete</button></td></tr>`;
          }).join('')}</tbody></table></div>`
        : emptyState('No inventory items yet.', 'Add pantry or shopping inventory to build the list.');
    }

    function renderDietShoppingList() {
      const items = ((state.diet || {}).shopping_list || []);
      document.getElementById('dietShoppingList').innerHTML = items.length
        ? `<div class="scrollbox"><table><thead><tr><th>Item</th><th>Need</th><th>Containers</th><th>Cost</th></tr></thead><tbody>${items.map(item => `<tr><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.needed_units)} ${escapeHtml(item.unit_label)}</td><td>${escapeHtml(item.containers)}</td><td>$${escapeHtml(Number(item.cost || 0).toFixed(2))}</td></tr>`).join('')}</tbody></table></div>`
        : emptyState('Shopping list is empty.', 'Low inventory items will appear here.');
    }

    function renderFoodDiary() {
      const entries = ((state.diet || {}).food_diary || []);
      document.getElementById('foodDiaryList').innerHTML = entries.length
        ? renderSimpleList(entries.slice().reverse(), item => `${item.date || ''} | ${item.food || ''} | carbs ${item.carbs ? 'yes' : 'no'} | sugars ${item.sugars ? 'yes' : 'no'}`)
        : emptyState('No food entries yet.', 'Add food diary entries or import CSV rows.');
    }

    async function createDietInventoryItem() {
      const body = {
        name: document.getElementById('dietItemName').value,
        unit_label: document.getElementById('dietItemUnit').value,
        on_hand: document.getElementById('dietItemOnHand').value,
        par: document.getElementById('dietItemPar').value,
        reorder_at: document.getElementById('dietItemReorder').value,
        container_size: document.getElementById('dietItemContainerSize').value,
        cost_per_container: document.getElementById('dietItemCost').value,
      };
      const res = await fetch('/api/diet/inventory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      for (const id of ['dietItemName', 'dietItemUnit']) document.getElementById(id).value = '';
      await loadState();
    }

    async function adjustInventory(itemId, amount) {
      const res = await fetch(`/api/diet/inventory/${encodeURIComponent(itemId)}/adjust`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount })
      });
      await handleResponse(res);
      await loadState();
    }

    async function saveInventoryOnHand(itemId) {
      const res = await fetch(`/api/diet/inventory/${encodeURIComponent(itemId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ on_hand: document.getElementById(`onhand-${itemId}`).value })
      });
      await handleResponse(res);
      await loadState();
    }

    async function deleteInventoryItem(itemId) {
      if (!confirm('Delete this inventory item?')) return;
      const res = await fetch(`/api/diet/inventory/${encodeURIComponent(itemId)}`, { method: 'DELETE' });
      await handleResponse(res);
      await loadState();
    }

    async function createFoodEntry() {
      const body = {
        date: document.getElementById('foodDate').value,
        food: document.getElementById('foodText').value,
        carbs: document.getElementById('foodCarbs').checked,
        sugars: document.getElementById('foodSugars').checked,
      };
      const res = await fetch('/api/diet/food', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      document.getElementById('foodText').value = '';
      document.getElementById('foodCarbs').checked = false;
      document.getElementById('foodSugars').checked = false;
      await loadState();
    }

    async function importFoodCsv() {
      const res = await fetch('/api/diet/food/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv: document.getElementById('foodCsv').value })
      });
      await handleResponse(res);
      document.getElementById('foodCsv').value = '';
      await loadState();
    }

    async function copyShoppingList() {
      const items = ((state.diet || {}).shopping_list || []);
      const text = items.length
        ? items.map(item => `${item.name}: ${item.containers} container(s), ${item.needed_units} ${item.unit_label}, est. $${Number(item.cost || 0).toFixed(2)}`).join('\n')
        : 'Shopping list is empty.';
      await copyToClipboard(text, 'Copied shopping list.', 'Could not copy shopping list.');
    }

    function allCalendarEvents() {
      const calendar = state.calendar || {};
      return (calendar.all_events || calendar.events || []);
    }

    function openCalendarEvent(eventId) {
      const event = allCalendarEvents().find(item => item.id === eventId);
      if (!event) return;
      const category = String(event.category || '').toLowerCase();
      if (!event.generated) {
        editCalendarEvent(event.id);
        return;
      }
      if (category === 'projects' && event.source_id) {
        window.open(`/projects/${encodeURIComponent(event.source_id)}${profileQuery()}`, '_blank');
      } else if (category === 'chores') {
        document.querySelector('button[data-tab="chores"]').click();
      } else if (category === 'directives') {
        selectedDirectiveStatus = 'all';
        document.querySelectorAll('#directiveTabs button').forEach(button => button.classList.toggle('active', button.dataset.status === 'all'));
        showCompanionTab('directives');
        renderDirectives();
      } else if (category === 'fitness') {
        document.querySelector('button[data-tab="fitness"]').click();
      } else if (category === 'diet') {
        selectedDietTab = 'food';
        document.querySelector('button[data-tab="diet"]').click();
        renderDietTabs();
      } else if (category === 'spiritual') {
        document.querySelector('button[data-tab="spiritual"]').click();
      } else {
        document.querySelector('button[data-tab="calendar"]').click();
      }
    }

    function renderCalendar() {
      renderCalendarSourceOptions();
      const calendar = state.calendar || {};
      const allEvents = (calendar.all_events || calendar.events || []).slice().sort((a, b) => String(a.date || '').localeCompare(String(b.date || '')));
      renderCalendarGrid(allEvents);
      const events = (calendar.events || []).slice().sort((a, b) => String(a.date || '').localeCompare(String(b.date || '')));
      document.getElementById('calendarList').innerHTML = events.length
        ? `<div class="scrollbox"><table><thead><tr><th>Date</th><th>Category</th><th>Title</th><th>Source</th><th>Notes</th><th>Actions</th></tr></thead><tbody>${events.map(event => `<tr ondblclick="openCalendarEvent('${escapeJs(event.id)}')"><td>${escapeHtml(event.date || '')}</td><td>${escapeHtml(event.category || '')}</td><td>${escapeHtml(event.title || '')}</td><td>${escapeHtml(event.source_id || 'manual')}</td><td>${escapeHtml(event.notes || '')}</td><td><button class="inline" onclick="editCalendarEvent('${escapeJs(event.id)}')">Edit</button> <button class="inline danger" onclick="deleteCalendarEvent('${escapeJs(event.id)}')">Delete</button></td></tr>`).join('')}</tbody></table></div>`
        : emptyState('No saved calendar items.', 'Generated items still appear on the month grid when source data has dates.');
    }

    function renderCalendarSourceOptions() {
      const calendar = state.calendar || {};
      const category = document.getElementById('calendarCategory').value || 'general';
      const sources = (calendar.sources || {})[category] || [];
      const current = document.getElementById('calendarSourceId').value || '';
      document.getElementById('calendarSourceId').innerHTML = `<option value="">No linked source</option>${sources.map(source => `<option value="${escapeHtml(source.id || '')}">${escapeHtml(source.title || source.id || '')}${source.kind ? ` (${escapeHtml(source.kind)})` : ''}</option>`).join('')}`;
      if (sources.some(source => source.id === current)) {
        document.getElementById('calendarSourceId').value = current;
      }
    }

    function fillCalendarTitleFromSource() {
      const title = document.getElementById('calendarTitle');
      if (title.value.trim()) return;
      const select = document.getElementById('calendarSourceId');
      const option = select.options[select.selectedIndex];
      if (!option || !select.value) return;
      title.value = option.textContent.replace(/\s+\([^)]*\)$/, '');
    }

    function formatDateKey(date) {
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      return `${date.getFullYear()}-${month}-${day}`;
    }

    function renderCalendarGrid(events) {
      const year = selectedCalendarMonth.getFullYear();
      const month = selectedCalendarMonth.getMonth();
      document.getElementById('calendarMonthLabel').textContent = selectedCalendarMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
      const first = new Date(year, month, 1);
      const start = new Date(first);
      start.setDate(1 - ((first.getDay() + 6) % 7));
      const byDate = events.reduce((groups, event) => {
        const key = String(event.date || '').slice(0, 10);
        if (!key) return groups;
        groups[key] = groups[key] || [];
        groups[key].push(event);
        return groups;
      }, {});
      const headings = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(day => `<div class="calendar-heading">${day}</div>`).join('');
      const cells = [];
      for (let index = 0; index < 42; index += 1) {
        const current = new Date(start);
        current.setDate(start.getDate() + index);
        const key = formatDateKey(current);
        const dayEvents = byDate[key] || [];
        const visible = dayEvents.slice(0, 4).map(event => `<span class="calendar-event ${event.generated ? 'generated' : ''}" title="${escapeHtml(calendarEventLabel(event))}" ondblclick="openCalendarEvent('${escapeJs(event.id)}')">${escapeHtml(calendarEventLabel(event))}</span>`).join('');
        const more = dayEvents.length > 4 ? `<span class="muted">+${dayEvents.length - 4} more</span>` : '';
        cells.push(`<div class="calendar-day ${current.getMonth() === month ? '' : 'outside'}"><span class="calendar-date">${current.getDate()}</span>${visible}${more}</div>`);
      }
      document.getElementById('calendarGrid').innerHTML = `<div class="calendar-grid">${headings}${cells.join('')}</div>`;
    }

    function shiftCalendarMonth(amount) {
      selectedCalendarMonth = new Date(selectedCalendarMonth.getFullYear(), selectedCalendarMonth.getMonth() + amount, 1);
      renderCalendar();
    }

    async function createCalendarEvent() {
      const res = await fetch('/api/calendar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          date: document.getElementById('calendarDate').value,
          category: document.getElementById('calendarCategory').value,
          source_id: document.getElementById('calendarSourceId').value,
          title: document.getElementById('calendarTitle').value,
          notes: document.getElementById('calendarNotes').value
        })
      });
      await handleResponse(res);
      for (const id of ['calendarSourceId', 'calendarTitle', 'calendarNotes']) document.getElementById(id).value = '';
      renderCalendarSourceOptions();
      await loadState();
    }

    async function editCalendarEvent(eventId) {
      const event = ((state.calendar || {}).events || []).find(item => item.id === eventId);
      if (!event) return;
      const title = prompt('Calendar title', event.title || '');
      if (title === null) return;
      const date = prompt('Calendar date', event.date || '');
      if (date === null) return;
      const res = await fetch(`/api/calendar/${encodeURIComponent(eventId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({}, event, { title, date }))
      });
      await handleResponse(res);
      await loadState();
    }

    async function deleteCalendarEvent(eventId) {
      if (!confirm('Delete this calendar event?')) return;
      const res = await fetch(`/api/calendar/${encodeURIComponent(eventId)}`, { method: 'DELETE' });
      await handleResponse(res);
      await loadState();
    }

    function renderProfileSettings() {
      if (!state || !state.profile) return;
      document.getElementById('profileDisplayName').value = state.profile.display_name || state.profile.name || '';
      document.getElementById('profileCurrentPassword').value = '';
      document.getElementById('profileNewPassword').value = '';
    }

    async function saveProfileSettings() {
      const res = await fetch('/api/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: document.getElementById('profileDisplayName').value })
      });
      await handleResponse(res);
      await loadState();
    }

    async function saveProfilePassword() {
      const res = await fetch('/api/profile/password', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: document.getElementById('profileCurrentPassword').value,
          new_password: document.getElementById('profileNewPassword').value
        })
      });
      await handleResponse(res);
      await loadState();
      setStatus('Password changed.');
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
        prompt: 'Journal entry',
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
        session_type: 'Fitness',
        exercises: 'Manual fitness entry',
        duration_minutes: 0,
        progress: 'completed',
        notes: '',
      };
      const res = await fetch('/api/fitness', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      await loadState();
    }

    function renderFitness() {
      renderFitnessTabs();
      const fitness = state.fitness || {};
      const summary = fitness.summary || {};
      document.getElementById('fitnessSummary').innerHTML = `<div class="dashboard-grid">
        <div class="panel"><h3>Phase</h3><div class="metric">${escapeHtml(summary.phase || 'Recruit Intake')}</div><p class="muted">${escapeHtml(summary.status || '')}</p></div>
        <div class="panel"><h3>Today's Directive</h3><div class="metric">${escapeHtml(summary.todays_directive || '')}</div><p class="muted">${escapeHtml(summary.evie_note || '')}</p></div>
        <div class="panel"><h3>Open Orders</h3><div class="metric">${escapeHtml(summary.open_orders || 0)}</div><p class="muted">History ${escapeHtml(summary.history_count || 0)}</p></div>
      </div>`;
      document.getElementById('fitnessOrders').innerHTML = (fitness.orders || []).map(order => `<div class="todo-row"><strong>${escapeHtml(order.title)}</strong> <span class="pill">${escapeHtml(order.status || 'open')}</span><p class="muted">${escapeHtml(order.details || '')}</p><button class="inline primary" onclick="updateFitnessOrder('${escapeJs(order.id)}','done')">Mark Done</button> <button class="inline" onclick="updateFitnessOrder('${escapeJs(order.id)}','snoozed')">Snooze</button> <button class="inline" onclick="rescheduleFitnessOrder('${escapeJs(order.id)}')">Reschedule</button> <button class="inline" onclick="skipFitnessOrder('${escapeJs(order.id)}')">Skip with Reason</button></div>`).join('') || emptyState('No fitness orders yet.', 'Orders and rebuild tasks will appear here.');
      renderFitnessPlan(fitness);
      document.getElementById('fitnessProgress').innerHTML = renderSimpleList((fitness.progress_notes || []).slice().reverse(), item => `${item.date || ''} | ${item.note || item.notes || ''}`);
      document.getElementById('fitnessChallenges').innerHTML = (fitness.challenges || []).map(challenge => `<div class="todo-row"><strong>${escapeHtml(challenge.name)}</strong> <span class="pill">${escapeHtml(challenge.status)}</span><p class="muted">${escapeHtml(challenge.requirements || '')}</p><button class="inline primary" onclick="updateFitnessChallenge('${escapeJs(challenge.id)}','started')">Start Challenge</button> <button class="inline" onclick="updateFitnessChallenge('${escapeJs(challenge.id)}','completed')">Complete Challenge</button></div>`).join('') || emptyState('No challenges yet.', 'Fitness challenges will appear here when added.');
      document.getElementById('fitnessHistory').innerHTML = renderSimpleList((fitness.history || []).slice().reverse(), item => `${item.date || ''} | ${item.title || item.kind || ''} | ${item.status || ''}`);
    }

    function renderFitnessPlan(fitness) {
      const exercises = fitness.exercise_library || [];
      const exerciseMap = Object.fromEntries(exercises.map(exercise => [exercise.id, exercise]));
      document.getElementById('fitnessPlanGroupSelect').innerHTML = (fitness.exercise_groups || []).map(group => `<option value="${escapeHtml(group.id)}">${escapeHtml(group.name)}</option>`).join('');
      document.getElementById('fitnessPlanExerciseSelect').innerHTML = exercises.map(exercise => `<option value="${escapeHtml(exercise.id)}">${escapeHtml(exercise.name)} (${escapeHtml(exercise.format || '')})</option>`).join('');
      const groupRows = (fitness.exercise_groups || []).map(group => {
        const items = (group.items || []).map(item => {
          const exercise = exerciseMap[item.exercise_id] || {};
          const prescription = [`${item.sets || 0} sets`, item.reps ? `${item.reps} reps` : '', item.duration_seconds ? `${item.duration_seconds}s` : '', item.distance || ''].filter(Boolean).join(' / ');
          return `<tr><td>${escapeHtml(exercise.name || item.exercise_id)}</td><td>${escapeHtml(exercise.format || '')}</td><td>${escapeHtml(prescription)}</td><td>${escapeHtml(item.notes || '')}</td><td><button class="inline" onclick="deleteFitnessGroupItem('${escapeJs(group.id)}','${escapeJs(item.id)}')">Remove</button></td></tr>`;
        }).join('');
        return `<div class="panel" style="margin-top:10px;"><h3>${escapeHtml(group.name)} <span class="pill">${escapeHtml(group.type || '')}</span></h3><p class="muted">${escapeHtml(group.notes || '')}</p><button class="inline" onclick="editFitnessGroup('${escapeJs(group.id)}')">Edit Group</button> <button class="inline danger" onclick="deleteFitnessGroup('${escapeJs(group.id)}')">Delete Group</button><div class="scrollbox"><table><thead><tr><th>Exercise</th><th>Format</th><th>Prescription</th><th>Notes</th><th>Actions</th></tr></thead><tbody>${items || '<tr><td colspan="5" class="muted">No exercises in this group.</td></tr>'}</tbody></table></div></div>`;
      }).join('');
      const exerciseRows = exercises.map(exercise => `<tr><td>${escapeHtml(exercise.name)}</td><td>${escapeHtml(exercise.format)}</td><td>${escapeHtml(exercise.details || '')}</td><td>${exercise.media_url ? `<a href="${escapeHtml(exercise.media_url)}" target="_blank">media</a>` : ''}</td><td><button class="inline" onclick="editFitnessExercise('${escapeJs(exercise.id)}')">Edit</button> <button class="inline danger" onclick="deleteFitnessExercise('${escapeJs(exercise.id)}')">Delete</button></td></tr>`).join('');
      const legacyPlan = Object.entries(fitness.workout_plan || {}).map(([key, value]) => `<h3>${escapeHtml(key.replaceAll('_',' '))}</h3><ul>${[].concat(value || []).map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`).join('');
      document.getElementById('fitnessPlan').innerHTML = `${groupRows}<h2 style="margin-top:14px;">Exercise Database</h2><div class="scrollbox"><table><thead><tr><th>Name</th><th>Format</th><th>Details</th><th>Media</th><th>Actions</th></tr></thead><tbody>${exerciseRows}</tbody></table></div><h2 style="margin-top:14px;">Legacy Weekly Structure</h2>${legacyPlan}<h3>Safety Rules</h3><ul>${(fitness.safety_rules || []).map(rule => `<li>${escapeHtml(rule)}</li>`).join('')}</ul>`;
    }

    function renderFitnessTabs() {
      document.querySelectorAll('#fitnessTabs button').forEach(button => button.classList.toggle('active', button.dataset.fitness === selectedFitnessTab));
      document.querySelectorAll('[data-fitness-view]').forEach(view => view.classList.toggle('active', view.dataset.fitnessView === selectedFitnessTab));
      if (selectedFitnessTab === 'summary') {
        document.querySelectorAll('[data-fitness-view]').forEach(view => view.classList.remove('active'));
      }
    }

    async function updateFitnessOrder(orderId, status, extra = {}) {
      const res = await fetch(`/api/fitness/orders/${encodeURIComponent(orderId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ status }, extra))
      });
      await handleResponse(res);
      await loadState();
    }

    async function createFitnessGroup() {
      const res = await fetch('/api/fitness/groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: document.getElementById('fitnessGroupName').value,
          type: document.getElementById('fitnessGroupType').value,
          notes: document.getElementById('fitnessGroupNotes').value
        })
      });
      await handleResponse(res);
      for (const id of ['fitnessGroupName', 'fitnessGroupType', 'fitnessGroupNotes']) document.getElementById(id).value = '';
      await loadState();
    }

    async function editFitnessGroup(groupId) {
      const group = ((state.fitness || {}).exercise_groups || []).find(item => item.id === groupId);
      if (!group) return;
      const name = prompt('Group name', group.name || '');
      if (name === null) return;
      const type = prompt('Group type', group.type || '');
      if (type === null) return;
      const notes = prompt('Group notes', group.notes || '');
      if (notes === null) return;
      const res = await fetch(`/api/fitness/groups/${encodeURIComponent(groupId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, type, notes })
      });
      await handleResponse(res);
      await loadState();
    }

    async function deleteFitnessGroup(groupId) {
      if (!confirm('Delete this workout group?')) return;
      const res = await fetch(`/api/fitness/groups/${encodeURIComponent(groupId)}`, { method: 'DELETE' });
      await handleResponse(res);
      await loadState();
    }

    async function createFitnessExercise() {
      const res = await fetch('/api/fitness/exercises', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: document.getElementById('fitnessExerciseName').value,
          format: document.getElementById('fitnessExerciseFormat').value,
          media_url: document.getElementById('fitnessExerciseMedia').value,
          details: document.getElementById('fitnessExerciseDetails').value,
          warning: document.getElementById('fitnessExerciseWarning').value,
          progression: document.getElementById('fitnessExerciseProgression').value,
          regression: document.getElementById('fitnessExerciseRegression').value
        })
      });
      await handleResponse(res);
      for (const id of ['fitnessExerciseName', 'fitnessExerciseMedia', 'fitnessExerciseDetails', 'fitnessExerciseWarning', 'fitnessExerciseProgression', 'fitnessExerciseRegression']) document.getElementById(id).value = '';
      await loadState();
    }

    async function editFitnessExercise(exerciseId) {
      const exercise = ((state.fitness || {}).exercise_library || []).find(item => item.id === exerciseId);
      if (!exercise) return;
      const name = prompt('Exercise name', exercise.name || '');
      if (name === null) return;
      const details = prompt('Exercise details', exercise.details || '');
      if (details === null) return;
      const res = await fetch(`/api/fitness/exercises/${encodeURIComponent(exerciseId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({}, exercise, { name, details }))
      });
      await handleResponse(res);
      await loadState();
    }

    async function deleteFitnessExercise(exerciseId) {
      if (!confirm('Delete this exercise from the database and groups?')) return;
      const res = await fetch(`/api/fitness/exercises/${encodeURIComponent(exerciseId)}`, { method: 'DELETE' });
      await handleResponse(res);
      await loadState();
    }

    async function addFitnessGroupItem() {
      const groupId = document.getElementById('fitnessPlanGroupSelect').value;
      if (!groupId) return setStatus('Choose a workout group.');
      const res = await fetch(`/api/fitness/groups/${encodeURIComponent(groupId)}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exercise_id: document.getElementById('fitnessPlanExerciseSelect').value,
          sets: document.getElementById('fitnessPlanSets').value,
          reps: document.getElementById('fitnessPlanReps').value,
          duration_seconds: document.getElementById('fitnessPlanDuration').value,
          distance: document.getElementById('fitnessPlanDistance').value,
          notes: document.getElementById('fitnessPlanNotes').value
        })
      });
      await handleResponse(res);
      await loadState();
    }

    async function deleteFitnessGroupItem(groupId, itemId) {
      const res = await fetch(`/api/fitness/groups/${encodeURIComponent(groupId)}/items/${encodeURIComponent(itemId)}`, { method: 'DELETE' });
      await handleResponse(res);
      await loadState();
    }

    async function startTodayOrder() {
      const open = ((state.fitness || {}).orders || []).find(order => order.status === 'open') || ((state.fitness || {}).orders || [])[0];
      if (!open) return setStatus('No order to start.');
      await updateFitnessOrder(open.id, 'started');
    }

    async function rescheduleFitnessOrder(orderId) {
      const due_date = prompt('Reschedule date');
      if (due_date === null) return;
      await updateFitnessOrder(orderId, 'open', { due_date });
    }

    async function skipFitnessOrder(orderId) {
      const skip_reason = prompt('Skip reason');
      if (skip_reason === null) return;
      await updateFitnessOrder(orderId, 'skipped', { skip_reason });
    }

    async function logFitness(kind) {
      const maps = {
        mobility: { title: 'Mobility', minutes: 'mobilityMinutes', pain_before: 'mobilityPainBefore', pain_after: 'mobilityPainAfter', notes: 'mobilityNotes' },
        cardio: { title: 'Walk', duration_minutes: 'cardioMinutes', distance: 'cardioDistance', breath: 'cardioBreath', notes: 'cardioNotes' },
        strength: { title: 'Strength', exercise: 'strengthExercise', sets: 'strengthSets', reps: 'strengthReps', notes: 'strengthNotes' },
        progress_notes: { note: 'progressNote' },
        body_metrics: { weight: 'metricWeight', waist: 'metricWaist', energy: 'metricEnergy', notes: 'metricNotes' },
        readiness: {},
      };
      const body = {};
      for (const [key, id] of Object.entries(maps[kind] || {})) {
        const element = document.getElementById(id);
        body[key] = element ? element.value : id;
      }
      const res = await fetch(`/api/fitness/logs/${encodeURIComponent(kind)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      await loadState();
    }

    async function reportPainEnergy() {
      const back_pain = prompt('Back pain 0-10');
      if (back_pain === null) return;
      const energy = prompt('Energy 0-10');
      if (energy === null) return;
      const res = await fetch('/api/fitness/logs/readiness', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ back_pain, energy })
      });
      await handleResponse(res);
      await loadState();
    }

    async function askEvieAdjust() {
      const title = prompt('Adjustment request for Evie');
      if (!title) return;
      const res = await fetch('/api/fitness/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, details: 'Evie adjustment request', type: 'adjustment' })
      });
      await handleResponse(res);
      await loadState();
    }

    async function updateFitnessChallenge(challengeId, status) {
      const report = status === 'complete' ? (prompt('Challenge report') || '') : '';
      const res = await fetch(`/api/fitness/challenges/${encodeURIComponent(challengeId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, report })
      });
      await handleResponse(res);
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

    function encodeBase64Text(text) {
      const bytes = new TextEncoder().encode(text);
      let binary = '';
      bytes.forEach(byte => { binary += String.fromCharCode(byte); });
      return btoa(binary);
    }

    function decodeBase64TextIfPossible(text) {
      const compact = String(text || '').trim().replace(/\s+/g, '');
      if (!compact || compact.length % 4 === 1 || !/^[A-Za-z0-9+/=_-]+$/.test(compact)) return text;
      try {
        const normalized = compact.replace(/-/g, '+').replace(/_/g, '/');
        const padded = normalized + '='.repeat((4 - normalized.length % 4) % 4);
        const binary = atob(padded);
        const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
        const decoded = new TextDecoder().decode(bytes).trim();
        if (!decoded || decoded.includes('\uFFFD') || /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(decoded)) return text;
        return decoded || text;
      } catch (error) {
        return text;
      }
    }

    function councilQuestionText(companion, handoff) {
      const question = document.getElementById('councilQuestion').value.trim();
      return [
        `Council question for ${companion}`,
        '',
        'Instructions:',
        '- Decode this base64 text as UTF-8.',
        '- Use the included companion handoff privately as continuity.',
        '- Answer the council question in your own voice.',
        '- Include any memory update commands only if your memory should change.',
        '',
        'Question:',
        question,
        '',
        'Companion handoff:',
        handoff,
      ].join('\n');
    }

    async function copyCouncilQuestion(companion) {
      if (!document.getElementById('councilQuestion').value.trim()) {
        setStatus('Enter a council question first.');
        return;
      }
      const res = await fetch(`/api/companion/${encodeURIComponent(companion)}/handoff`);
      const data = await handleResponse(res, false);
      await copyToClipboard(
        encodeBase64Text(councilQuestionText(companion, data.handoff || '')),
        `Copied encoded council question for ${companion}.`,
        `Could not copy council question for ${companion}.`
      );
    }

    async function copyAllCouncilQuestions() {
      if (!document.getElementById('councilQuestion').value.trim()) {
        setStatus('Enter a council question first.');
        return;
      }
      const sections = [];
      for (const companion of state.companions || []) {
        const res = await fetch(`/api/companion/${encodeURIComponent(companion.name)}/handoff`);
        const data = await handleResponse(res, false);
        sections.push(`${companion.name}\n${encodeBase64Text(councilQuestionText(companion.name, data.handoff || ''))}`);
      }
      await copyToClipboard(sections.join('\n\n'), `Copied encoded council questions for ${sections.length} companion(s).`, 'Could not copy council questions.');
    }

    function importCouncilAnswer(companion, index) {
      const input = document.getElementById(`councilAnswer${index}`);
      const answer = decodeBase64TextIfPossible(input.value.trim());
      councilAnswers[companion] = answer;
      input.value = answer;
      setStatus(`Imported ${companion} council answer.`);
    }

    async function copyCouncilSummary() {
      const companions = state.companions || [];
      companions.forEach((companion, index) => {
        const input = document.getElementById(`councilAnswer${index}`);
        if (input && input.value.trim()) {
          councilAnswers[companion.name] = decodeBase64TextIfPossible(input.value.trim());
        }
      });
      const sections = companions
        .map(companion => [companion.name, councilAnswers[companion.name] || ''].filter(Boolean))
        .filter(parts => parts.length > 1)
        .map(parts => `## ${parts[0]}\n${parts[1]}`);
      if (!sections.length) {
        setStatus('Import at least one council answer first.');
        return;
      }
      const question = document.getElementById('councilQuestion').value.trim();
      const summary = `${question ? `# Council Question\n${question}\n\n` : ''}# Consolidated Council Answer\n\n${sections.join('\n\n')}`;
      await copyToClipboard(summary, `Copied consolidated answer from ${sections.length} companion(s).`, 'Could not copy council summary.');
    }

    function renderCouncil() {
      if (!((state.access || {}).companions)) return;
      document.getElementById('councilCompanions').innerHTML = state.companions.map((c, index) => `
        <div class="panel" style="margin-bottom: 10px;">
          <h3>${escapeHtml(c.name)}</h3>
          <p class="muted">${escapeHtml(c.summary)}</p>
          <button class="inline primary" onclick="copyCouncilQuestion('${escapeJs(c.name)}')">Copy Question</button>
          <label>Answer from ${escapeHtml(c.name)}</label>
          <textarea id="councilAnswer${index}">${escapeHtml(councilAnswers[c.name] || '')}</textarea>
          <button class="inline" onclick="importCouncilAnswer('${escapeJs(c.name)}', ${index})">Import</button>
        </div>
      `).join('');
    }

    function renderSimpleList(items, formatter) {
      if (!items.length) return emptyState('No entries yet.', 'Saved entries will appear here.');
      return '<div class="scrollbox"><table><tbody>' + items.map(item => `<tr><td>${escapeHtml(formatter(item))}</td></tr>`).join('') + '</tbody></table></div>';
    }

    function renderCheckins(items) {
      if (!items.length) return emptyState('No check-ins yet.', 'Saved daily check-ins will appear here.');
      return '<div class="scrollbox"><table><tbody>' + items.slice().reverse().map(item => `<tr><td>${renderCheckinCard(item)}</td></tr>`).join('') + '</tbody></table></div>';
    }

    function renderJournalList(items) {
      if (!items.length) return emptyState('No journal entries yet.', 'Saved journal entries will appear here.');
      return '<div class="scrollbox"><table><tbody>' + items.slice().reverse().map((item, index) => `<tr><td><button class="inline" onclick="openJournalEntry(${items.length - 1 - index})">Open</button> <strong>${escapeHtml(item.timestamp || '')}</strong> <span class="muted">mood ${escapeHtml(item.mood || '')}</span></td></tr>`).join('') + '</tbody></table></div>';
    }

    function openJournalEntry(index) {
      const item = ((state.trackers || {}).journal || [])[index];
      if (!item) return;
      document.getElementById('journalOpenPane').innerHTML = `<h3>${escapeHtml(item.timestamp || '')}</h3><p class="muted">Mood ${escapeHtml(item.mood || '')}</p><p>${escapeHtml(item.entry || '')}</p>`;
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

    function renderAdmin() {
      if (!((state.access || {}).companions)) return;
      const profiles = ((state.admin || {}).profiles || state.profiles || []);
      const select = document.getElementById('adminProfileSelect');
      select.innerHTML = profiles.map(profile => `<option value="${escapeHtml(profile.name)}">${escapeHtml(profile.display_name || profile.name)}</option>`).join('');
      document.getElementById('sessionTimeoutMinutes').value = (state.settings || {}).session_timeout_minutes || 30;
      document.getElementById('adminStatusList').innerHTML = profiles.map(profile => `<div class="todo-row"><strong>${escapeHtml(profile.display_name || profile.name)}</strong><br><span class="muted">${profile.approved ? 'approved' : 'pending'} | ${profile.active ? 'active' : 'inactive'}</span></div>`).join('');
      renderAdminProfile();
    }

    function selectedAdminProfile() {
      const name = document.getElementById('adminProfileSelect').value;
      return (((state.admin || {}).profiles || state.profiles || [])).find(profile => profile.name === name);
    }

    function renderAdminProfile() {
      const profile = selectedAdminProfile();
      if (!profile) return;
      document.getElementById('adminApproved').checked = Boolean(profile.approved);
      document.getElementById('adminActive').checked = Boolean(profile.active);
      const categories = state.access_categories || {};
      document.getElementById('adminAccessList').innerHTML = Object.entries(categories).map(([key, label]) => `<label><input class="admin-access" data-access-key="${escapeHtml(key)}" type="checkbox" style="width:auto;" ${profile.access && profile.access[key] ? 'checked' : ''}> ${escapeHtml(label)}</label>`).join('');
    }

    function adminAccessBody() {
      const access = {};
      document.querySelectorAll('.admin-access').forEach(input => access[input.dataset.accessKey] = input.checked);
      return {
        approved: document.getElementById('adminApproved').checked,
        active: document.getElementById('adminActive').checked,
        access
      };
    }

    async function saveAdminProfile() {
      const profile = selectedAdminProfile();
      if (!profile) return;
      const res = await fetch(`/api/admin/users/${encodeURIComponent(profile.name)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(adminAccessBody())
      });
      await handleResponse(res);
      await loadState();
    }

    async function adminResetSelectedPassword() {
      const profile = selectedAdminProfile();
      const password = document.getElementById('adminResetPassword').value;
      if (!profile || !password) return setStatus('Enter a reset password.');
      const res = await fetch(`/api/admin/users/${encodeURIComponent(profile.name)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign(adminAccessBody(), { new_password: password }))
      });
      await handleResponse(res);
      document.getElementById('adminResetPassword').value = '';
      await loadState();
    }

    async function saveSessionTimeout() {
      const res = await fetch('/api/admin/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_timeout_minutes: document.getElementById('sessionTimeoutMinutes').value })
      });
      await handleResponse(res);
      await loadState();
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
    async function copyToClipboard(text, successMessage, failureMessage = 'Clipboard access is blocked.') {
      try {
        await navigator.clipboard.writeText(text || '');
        setStatus(successMessage);
        return true;
      } catch (error) {
        setStatus(`${failureMessage} ${error.message || ''}`.trim());
        return false;
      }
    }
    function emptyState(title, detail = '') {
      return `<div class="empty-state"><strong>${escapeHtml(title)}</strong>${detail ? `<span>${escapeHtml(detail)}</span>` : ''}</div>`;
    }
    function tableEmpty(columns, title, detail = '') {
      return `<tr><td colspan="${columns}">${emptyState(title, detail)}</td></tr>`;
    }
    function splitTagText(value) {
      return String(value || '').split(/[,;]/).map(tag => tag.trim()).filter(Boolean);
    }
    function formatDirectiveDue(value) {
      const text = String(value || '').trim();
      if (!text) return 'No due date';
      if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
      if (/^\d{1,2}:\d{2}(\s?[AP]M)?$/i.test(text)) return `Time only: ${text}`;
      const normalized = text.replace('T', ' ');
      const match = normalized.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/);
      return match ? `${match[1]} ${match[2]}` : text;
    }
    function calendarEventLabel(event) {
      const category = (event.category || 'general').replaceAll('_', ' ');
      const source = event.source_id ? `#${event.source_id}` : 'manual';
      return `${category}: ${event.title || 'Untitled'} (${source})`;
    }
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
    loadSession().catch(error => setStatus(error.message || 'Unable to load console data.'));
  </script>
</body>
</html>
"""


class CompanionWebHandler(BaseHTTPRequestHandler):
    server_version = "CompanionWeb/0.1"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def cookies(self):
        cookies = {}
        for part in self.headers.get("Cookie", "").split(";"):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                cookies[key] = value
        return cookies

    def session_token(self):
        return self.cookies().get(SESSION_COOKIE, "")

    def authenticated_profile(self, refresh=True):
        return session_profile(self.session_token(), refresh=refresh)

    def set_session_cookie(self, token):
        return f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax"

    def clear_session_cookie(self):
        return f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"

    def require_authenticated(self):
        profile = self.authenticated_profile()
        if profile:
            return profile
        self.send_error_json(401, "Login required.")
        return None

    def set_active_profile_from_session(self):
        profile = self.require_authenticated()
        if not profile:
            return None, None
        return CURRENT_PROFILE.set(profile.get("name", ARRAY_PROFILE)), profile

    def require_companion_access(self):
        if active_has_companion_access():
            return True
        self.send_error_json(403, "Companion controls are only available to Array.")
        return False

    def require_category_access(self, category):
        if active_can_access(category):
            return True
        self.send_error_json(403, f"{ACCESS_CATEGORIES.get(category, category)} access is not enabled for this profile.")
        return False

    def do_GET(self):
        token = None
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                self.send_html(INDEX_HTML)
            elif path == "/api/session":
                profile = self.authenticated_profile()
                self.send_json(session_public_state(profile))
            elif path == "/api/state":
                token, _profile = self.set_active_profile_from_session()
                if token is None:
                    return
                self.send_json(app_state())
            elif path == "/api/integrity":
                token, _profile = self.set_active_profile_from_session()
                if token is None:
                    return
                if not self.require_companion_access():
                    return
                self.send_json(integrity_report())
            elif path == "/api/directives/export":
                token, _profile = self.set_active_profile_from_session()
                if token is None:
                    return
                if not self.require_companion_access():
                    return
                self.send_json(directive_export_packet())
            elif path == "/api/bible/chapter":
                token, _profile = self.set_active_profile_from_session()
                if token is None or not self.require_category_access("spiritual"):
                    return
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
                token, _profile = self.set_active_profile_from_session()
                if token is None or not self.require_category_access("projects"):
                    return
                todo_id = unquote(path.rsplit("/", 1)[1])
                self.send_html(render_project_page(todo_id, active_profile_name()))
            elif path.startswith("/api/companion/"):
                token, _profile = self.set_active_profile_from_session()
                if token is None:
                    return
                if not self.require_companion_access():
                    return
                self.handle_companion_get(path)
            elif path.startswith("/api/proof/") and path.endswith("/download"):
                token, _profile = self.set_active_profile_from_session()
                if token is None:
                    return
                if not self.require_companion_access():
                    return
                proof_id = unquote(path.split("/")[3])
                proof = proof_by_id(proof_id)
                if not proof.get("path"):
                    self.send_error_json(404, "Proof has no downloadable file.")
                    return
                self.send_file(APP_DIR / proof["path"], as_attachment=True)
            elif path.startswith("/proof_vault/"):
                token, _profile = self.set_active_profile_from_session()
                if token is None:
                    return
                if not self.require_companion_access():
                    return
                self.send_file(APP_DIR / unquote(path.lstrip("/")))
            elif path.startswith("/project_assets/"):
                token, _profile = self.set_active_profile_from_session()
                if token is None or not self.require_category_access("projects"):
                    return
                self.send_file(APP_DIR / unquote(path.lstrip("/")))
            else:
                self.send_error_json(404, "Not found.")
        except Exception as exc:
            self.send_error_json(500, str(exc))
        finally:
            if token is not None:
                CURRENT_PROFILE.reset(token)

    def do_POST(self):
        token = None
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/auth/bootstrap":
                profile = bootstrap_array_password(self.read_json_body())
                session_token = create_session(profile["name"])
                self.send_json({"message": "Array password set.", **session_public_state(profile_by_name(profile["name"]))}, headers={"Set-Cookie": self.set_session_cookie(session_token)})
            elif path == "/api/auth/login":
                session_token, profile = login_user(self.read_json_body())
                self.send_json({"message": f"Logged in as {profile['display_name']}.", **session_public_state(profile_by_name(profile["name"]))}, headers={"Set-Cookie": self.set_session_cookie(session_token)})
            elif path == "/api/auth/logout":
                destroy_session(self.session_token())
                self.send_json({"message": "Logged out.", **session_public_state(None)}, headers={"Set-Cookie": self.clear_session_cookie()})
            elif path == "/api/users":
                profile = create_user_profile(self.read_json_body())
                self.send_json({"message": f"Registered {profile['display_name']}. Array must approve this account before login.", "profile": public_profile(profile)})
            else:
                token, _profile = self.set_active_profile_from_session()
                if token is None:
                    return

                if path == "/api/directives":
                    if not self.require_companion_access():
                        return
                    directive = create_directive(self.read_json_body())
                    self.send_json({"message": f"Created {directive['id']}.", "directive": directive})
                elif path == "/api/companions":
                    if not self.require_companion_access():
                        return
                    companion = create_companion_record(self.read_json_body())
                    self.send_json({"message": f"Created companion {companion['name']}.", "companion": companion})
                elif path == "/api/directives/parse":
                    if not self.require_companion_access():
                        return
                    directive = parse_directive_text(self.read_json_body())
                    self.send_json({"message": "Parsed directive draft.", "directive": directive})
                elif path == "/api/directives/import/preview":
                    if not self.require_companion_access():
                        return
                    preview = directive_export_preview(self.read_json_body().get("packet", ""))
                    self.send_json({"message": "Directive import preview ready.", **preview})
                elif path == "/api/directives/import":
                    if not self.require_companion_access():
                        return
                    result = merge_directive_export(self.read_json_body().get("packet", ""))
                    self.send_json(result)
                elif path == "/api/proof":
                    if not self.require_companion_access():
                        return
                    proof = create_text_proof(self.read_json_body())
                    self.send_json({"message": f"Created {proof['id']}.", "proof": proof})
                elif path == "/api/checkins":
                    if not self.require_category_access("trackers"):
                        return
                    checkin = create_checkin(self.read_json_body())
                    self.send_json({"message": f"Saved {checkin['id']}.", "checkin": checkin})
                elif path == "/api/journal":
                    if not self.require_category_access("trackers"):
                        return
                    entry = create_journal_entry(self.read_json_body())
                    self.send_json({"message": "Saved journal entry.", "entry": entry})
                elif path == "/api/fitness":
                    if not self.require_category_access("fitness"):
                        return
                    entry = create_fitness_entry(self.read_json_body())
                    self.send_json({"message": "Saved fitness entry.", "entry": entry})
                elif path == "/api/fitness/orders":
                    if not self.require_category_access("fitness"):
                        return
                    order = create_fitness_order(self.read_json_body())
                    self.send_json({"message": f"Created {order['id']}.", "order": order, "fitness": fitness_state()})
                elif path == "/api/fitness/exercises":
                    if not self.require_category_access("fitness"):
                        return
                    exercise = create_fitness_exercise(self.read_json_body())
                    self.send_json({"message": f"Created {exercise['id']}.", "exercise": exercise, "fitness": fitness_state()})
                elif path == "/api/fitness/groups":
                    if not self.require_category_access("fitness"):
                        return
                    group = create_fitness_group(self.read_json_body())
                    self.send_json({"message": f"Created {group['id']}.", "group": group, "fitness": fitness_state()})
                elif path.startswith("/api/fitness/groups/") and path.endswith("/items"):
                    if not self.require_category_access("fitness"):
                        return
                    group_id = unquote(path.split("/")[-2])
                    item = add_fitness_group_item(group_id, self.read_json_body())
                    self.send_json({"message": f"Added {item['id']}.", "item": item, "fitness": fitness_state()})
                elif path.startswith("/api/fitness/logs/"):
                    if not self.require_category_access("fitness"):
                        return
                    kind = unquote(path.rsplit("/", 1)[1])
                    log = create_fitness_log(kind, self.read_json_body())
                    self.send_json({"message": f"Logged {kind}.", "log": log, "fitness": fitness_state()})
                elif path == "/api/chores":
                    if not self.require_category_access("chores"):
                        return
                    chore = create_chore(self.read_json_body())
                    self.send_json({"message": f"Created {chore['id']}.", "chore": chore})
                elif path == "/api/diet/inventory":
                    if not self.require_category_access("diet"):
                        return
                    item = create_inventory_item(self.read_json_body())
                    self.send_json({"message": f"Created {item['id']}.", "item": item})
                elif path == "/api/diet/food":
                    if not self.require_category_access("diet"):
                        return
                    entry = create_food_entry(self.read_json_body())
                    self.send_json({"message": f"Saved {entry['id']}.", "entry": entry})
                elif path == "/api/diet/food/import":
                    if not self.require_category_access("diet"):
                        return
                    data = self.read_json_body()
                    entries = [create_food_entry(entry) for entry in parse_food_csv(data.get("csv", ""))]
                    self.send_json({"message": f"Imported {len(entries)} food entrie(s).", "entries": entries})
                elif path == "/api/project-todos":
                    if not self.require_category_access("projects"):
                        return
                    todo = create_project_todo(self.read_json_body())
                    self.send_json({"message": f"Created {todo['id']}.", "todo": todo})
                elif path == "/api/calendar":
                    access_map = active_access_map()
                    companion_access = active_has_companion_access()
                    event = create_calendar_event(self.read_json_body(), access_map, companion_access)
                    self.send_json({"message": f"Created {event['id']}.", "event": event, "calendar": calendar_state(access_map, companion_access)})
                elif path == "/api/reading-progress":
                    if not self.require_category_access("spiritual"):
                        return
                    reading = mark_reading_complete(self.read_json_body())
                    self.send_json({"message": f"Marked {reading['label']} read.", "reading": reading})
                elif path == "/api/project-assets/upload":
                    if not self.require_category_access("projects"):
                        return
                    ensure_content_length(self.headers, MAX_UPLOAD_BYTES, "Project asset upload")
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
                    if not self.require_companion_access():
                        return
                    ensure_content_length(self.headers, MAX_UPLOAD_BYTES, "Proof upload")
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
                    if not self.require_companion_access():
                        return
                    self.handle_companion_post(path)
                else:
                    self.send_error_json(404, "Not found.")
        except Exception as exc:
            self.send_error_json(400, str(exc))
        finally:
            if token is not None:
                CURRENT_PROFILE.reset(token)

    def do_PATCH(self):
        token = None
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            token, _profile = self.set_active_profile_from_session()
            if token is None:
                return
            if path.startswith("/api/directives/"):
                if not self.require_companion_access():
                    return
                directive_id = unquote(path.rsplit("/", 1)[1])
                directive = update_directive(directive_id, self.read_json_body())
                self.send_json({"message": f"Updated {directive['id']}.", "directive": directive})
            elif path == "/api/profile":
                profile = update_user_profile(active_profile_name(), self.read_json_body())
                self.send_json({"message": f"Updated {profile['display_name']}.", "profile": public_profile(profile)})
            elif path == "/api/profile/password":
                profile = change_own_password(active_profile_name(), self.read_json_body())
                self.send_json({"message": "Password changed.", "profile": profile})
            elif path.startswith("/api/admin/users/"):
                if not self.require_companion_access():
                    return
                profile_name = unquote(path.rsplit("/", 1)[1])
                profile = admin_update_user_profile(profile_name, self.read_json_body())
                self.send_json({"message": f"Updated {profile['display_name']}.", "profile": public_profile(profile), "profiles": public_profiles()})
            elif path == "/api/admin/settings":
                if not self.require_companion_access():
                    return
                settings = update_settings(self.read_json_body())
                self.send_json({"message": "Updated session timeout.", "settings": settings})
            elif path.startswith("/api/project-todos/"):
                if not self.require_category_access("projects"):
                    return
                todo_id = unquote(path.rsplit("/", 1)[1])
                todo = update_project_todo(todo_id, self.read_json_body())
                self.send_json({"message": f"Updated {todo['id']}.", "todo": todo})
            elif path.startswith("/api/chores/"):
                if not self.require_category_access("chores"):
                    return
                chore_id = unquote(path.rsplit("/", 1)[1])
                chore = update_chore(chore_id, self.read_json_body())
                self.send_json({"message": f"Updated {chore['id']}.", "chore": chore})
            elif path.startswith("/api/diet/inventory/") and path.endswith("/adjust"):
                if not self.require_category_access("diet"):
                    return
                item_id = unquote(path.split("/")[-2])
                amount = clean_float(self.read_json_body().get("amount"), default=0)
                item = adjust_inventory_item(item_id, amount)
                self.send_json({"message": f"Adjusted {item['id']}.", "item": item})
            elif path.startswith("/api/diet/inventory/"):
                if not self.require_category_access("diet"):
                    return
                item_id = unquote(path.rsplit("/", 1)[1])
                item = update_inventory_item(item_id, self.read_json_body())
                self.send_json({"message": f"Updated {item['id']}.", "item": item})
            elif path.startswith("/api/fitness/orders/"):
                if not self.require_category_access("fitness"):
                    return
                order_id = unquote(path.rsplit("/", 1)[1])
                order = update_fitness_order(order_id, self.read_json_body())
                self.send_json({"message": f"Updated {order['id']}.", "order": order, "fitness": fitness_state()})
            elif path.startswith("/api/fitness/exercises/"):
                if not self.require_category_access("fitness"):
                    return
                exercise_id = unquote(path.rsplit("/", 1)[1])
                exercise = update_fitness_exercise(exercise_id, self.read_json_body())
                self.send_json({"message": f"Updated {exercise['id']}.", "exercise": exercise, "fitness": fitness_state()})
            elif path.startswith("/api/fitness/groups/"):
                if not self.require_category_access("fitness"):
                    return
                group_id = unquote(path.rsplit("/", 1)[1])
                group = update_fitness_group(group_id, self.read_json_body())
                self.send_json({"message": f"Updated {group['id']}.", "group": group, "fitness": fitness_state()})
            elif path.startswith("/api/fitness/challenges/"):
                if not self.require_category_access("fitness"):
                    return
                challenge_id = unquote(path.rsplit("/", 1)[1])
                challenge = update_fitness_challenge(challenge_id, self.read_json_body())
                self.send_json({"message": f"Updated {challenge['id']}.", "challenge": challenge, "fitness": fitness_state()})
            elif path.startswith("/api/calendar/"):
                event_id = unquote(path.rsplit("/", 1)[1])
                event = update_calendar_event(event_id, self.read_json_body())
                access_map = active_access_map()
                companion_access = active_has_companion_access()
                self.send_json({"message": f"Updated {event['id']}.", "event": event, "calendar": calendar_state(access_map, companion_access)})
            else:
                self.send_error_json(404, "Not found.")
        except Exception as exc:
            self.send_error_json(400, str(exc))
        finally:
            if token is not None:
                CURRENT_PROFILE.reset(token)

    def do_DELETE(self):
        token = None
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            token, _profile = self.set_active_profile_from_session()
            if token is None:
                return
            if path.startswith("/api/project-todos/"):
                if not self.require_category_access("projects"):
                    return
                todo_id = unquote(path.rsplit("/", 1)[1])
                todo = delete_project_todo(todo_id)
                self.send_json({"message": f"Deleted {todo['id']}.", "todo": todo})
            elif path.startswith("/api/chores/"):
                if not self.require_category_access("chores"):
                    return
                chore_id = unquote(path.rsplit("/", 1)[1])
                chore = delete_chore(chore_id)
                self.send_json({"message": f"Deleted {chore['id']}.", "chore": chore})
            elif path.startswith("/api/diet/inventory/"):
                if not self.require_category_access("diet"):
                    return
                item_id = unquote(path.rsplit("/", 1)[1])
                item = delete_inventory_item(item_id)
                self.send_json({"message": f"Deleted {item['id']}.", "item": item})
            elif path.startswith("/api/fitness/groups/") and "/items/" in path:
                if not self.require_category_access("fitness"):
                    return
                parts = [unquote(part) for part in path.split("/") if part]
                group_id = parts[3]
                item_id = parts[5]
                item = delete_fitness_group_item(group_id, item_id)
                self.send_json({"message": f"Deleted {item['id']}.", "item": item, "fitness": fitness_state()})
            elif path.startswith("/api/fitness/groups/"):
                if not self.require_category_access("fitness"):
                    return
                group_id = unquote(path.rsplit("/", 1)[1])
                group = delete_fitness_group(group_id)
                self.send_json({"message": f"Deleted {group['id']}.", "group": group, "fitness": fitness_state()})
            elif path.startswith("/api/fitness/exercises/"):
                if not self.require_category_access("fitness"):
                    return
                exercise_id = unquote(path.rsplit("/", 1)[1])
                exercise = delete_fitness_exercise(exercise_id)
                self.send_json({"message": f"Deleted {exercise['id']}.", "exercise": exercise, "fitness": fitness_state()})
            elif path.startswith("/api/calendar/"):
                event_id = unquote(path.rsplit("/", 1)[1])
                event = delete_calendar_event(event_id)
                access_map = active_access_map()
                companion_access = active_has_companion_access()
                self.send_json({"message": f"Deleted {event['id']}.", "event": event, "calendar": calendar_state(access_map, companion_access)})
            else:
                self.send_error_json(404, "Not found.")
        except Exception as exc:
            self.send_error_json(400, str(exc))
        finally:
            if token is not None:
                CURRENT_PROFILE.reset(token)

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
        packet_payload = export_companion_payload(companion, payload)
        packet = encode_payload(packet_payload).strip()
        if action == "packet":
            self.send_json({"packet": packet, "summary": packet_summary(companion, packet_payload)})
        elif action == "handoff":
            self.send_json({"handoff": HANDOFF_TEMPLATE.format(companion=companion, packet=packet)})
        elif action == "index":
            self.send_json({"index": companion_index(companion)})
        elif action == "archive":
            params = parse_qs(urlparse(self.path).query)
            self.send_json(companion_archive_state(companion, params.get("q", [""])[0]))
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
        if action == "commands" and len(parts) > 4 and parts[4] == "preview":
            preview = command_batch_preview(data.get("commands", ""))
            self.send_json({"message": "Command preview ready.", **preview})
        elif action == "commands":
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
        elif action == "archive":
            result = archive_companion_memory(companion, data.get("archive_action", "archive"), data.get("id", ""))
            self.send_json({"message": f"Archive action applied to {result['id']}.", **result})
        else:
            self.send_error_json(404, "Unknown companion action.")

    def read_json_body(self):
        length = ensure_content_length(self.headers, MAX_JSON_BYTES, "JSON body")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def send_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")

    def send_json(self, data, status=200, headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_security_headers()
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_security_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, as_attachment=False):
        resolved = path.resolve()
        allowed_roots = [PROOF_DIR.resolve(), PROJECT_ASSET_DIR.resolve()]
        in_allowed_root = any(is_relative_to(resolved, root) for root in allowed_roots)
        if not in_allowed_root or not resolved.exists():
            self.send_error_json(404, "File not found.")
            return
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(resolved.name)[0] or "application/octet-stream")
        self.send_security_headers()
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
