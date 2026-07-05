import cgi
import argparse
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
from datetime import datetime
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
KJV_FILE = APP_DIR / "kjv.txt"
DAILY_SCHEDULE_PLAN = "KJV Daily Schedule"
ARRAY_PROFILE = "Array"
CURRENT_PROFILE = contextvars.ContextVar("current_profile", default=ARRAY_PROFILE)
SESSION_COOKIE = "companion_session"
PASSWORD_ITERATIONS = 260000
SESSIONS = {}
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
    return {
        "name": normalized.get("name", ""),
        "display_name": normalized.get("display_name") or normalized.get("name", ""),
        "role": normalized.get("role", "user"),
        "approved": clean_bool(normalized.get("approved")),
        "active": clean_bool(normalized.get("active")),
        "access": normalized.get("access", default_access(normalized.get("name"))),
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


def active_profile_name():
    return normalize_profile_name(CURRENT_PROFILE.get())


def active_profile():
    return ensure_user_profile(active_profile_name())


def active_has_companion_access():
    return is_array_profile(active_profile_name())


def active_access_map():
    profile = active_profile()
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
    return read_json(profile_data_file("chores.json"), {"next_chore_number": 1, "chores": []})


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
            {"name": "Dead bug", "purpose": "Core stability and lower-back protection.", "warning": "Stop if sharp back pain appears.", "progression": "Increase reps or extend legs farther.", "regression": "Move arms only or legs only."},
            {"name": "Chair squat", "purpose": "Rebuild squat pattern safely.", "warning": "Stop for sharp knee or back pain.", "progression": "Lower the chair height.", "regression": "Use hands for support."},
            {"name": "Incline pushup", "purpose": "Rebuild push strength.", "warning": "Stop for shoulder pain.", "progression": "Lower the incline.", "regression": "Use a higher support."},
            {"name": "Glute bridge", "purpose": "Rebuild hips and posterior chain.", "warning": "No aggressive back arch.", "progression": "Add pauses.", "regression": "Reduce range."},
            {"name": "Cat-cow", "purpose": "Gentle spinal motion.", "warning": "Avoid forced extension.", "progression": "Slower controlled reps.", "regression": "Smaller range."},
        ],
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
    if changed:
        write_json(profile_data_file("fitness.json"), store)
    return store


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


def update_fitness_challenge(challenge_id, data):
    store = fitness_store()
    for challenge in store.get("challenges", []):
        if challenge.get("id", "").lower() == challenge_id.lower():
            for key in ("status", "report", "completion_status"):
                if key in data:
                    challenge[key] = str(data.get(key) or "").strip()
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


def create_chore(data):
    store = chore_store()
    chore_id = next_id(store, "next_chore_number", "CHR")
    chore = {
        "id": chore_id,
        "title": str(data.get("title") or "").strip(),
        "status": str(data.get("status") or "open").strip() or "open",
        "due_date": str(data.get("due_date") or "").strip(),
        "recurrence": str(data.get("recurrence") or "").strip(),
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
            for key in ("title", "status", "due_date", "recurrence", "notes"):
                if key in data:
                    chore[key] = str(data[key]).strip()
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
        "diff": round(par - on_hand, 2),
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

    for todo in store.get("todos", []):
        if todo.get("id", "").lower() == todo_id.lower():
            safe_project = safe_name(todo_id)
            original_name = safe_name(Path(item.filename).name)
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
    .diet-view { display: none; }
    .diet-view.active { display: block; }
    .fitness-view { display: none; }
    .fitness-view.active { display: block; }
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
    <div class="profile-bar">
      <select id="loginProfileSelect"></select>
      <input id="loginPassword" type="password" placeholder="password">
      <input id="profileRegisterName" placeholder="new profile">
      <input id="profileRegisterPassword" type="password" placeholder="new password">
      <button class="inline" id="profileLoginButton">Log In</button>
      <button class="inline" id="profileLogoutButton">Log Out</button>
      <button class="inline" id="profileRegisterButton">Register</button>
      <button class="inline" id="profileSettingsButton">Profile Settings</button>
      <button class="inline" id="changePasswordButton">Change Password</button>
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
      <button data-tab="admin" data-admin-only>Admin</button>
    </nav>
    <section id="dashboard" class="active">
      <div class="dashboard-grid">
        <div class="panel" data-companion-only>
          <h2>Memory Manager</h2>
          <div class="metric" id="dashCompanions">0</div>
          <div class="muted" id="dashMemory">No packets loaded.</div>
        </div>
        <div class="panel" data-companion-only>
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
    <section id="memory" data-companion-only>
      <div class="grid">
        <div class="panel full">
          <h2>Companion</h2>
          <div class="tab-row">
            <button class="active" onclick="showCompanionTab('memory')">Memory</button>
            <button onclick="showCompanionTab('directives')">Directive Ledger</button>
            <button onclick="showCompanionTab('proof')">Proof Vault</button>
            <button onclick="showCompanionTab('council')">Council Mode</button>
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
    <section id="directives" data-companion-only>
      <div class="grid">
        <div class="panel full">
          <h2>Companion</h2>
          <div class="tab-row">
            <button onclick="showCompanionTab('memory')">Memory</button>
            <button class="active" onclick="showCompanionTab('directives')">Directive Ledger</button>
            <button onclick="showCompanionTab('proof')">Proof Vault</button>
            <button onclick="showCompanionTab('council')">Council Mode</button>
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
    <section id="proof" data-companion-only>
      <div class="grid">
        <div class="panel full">
          <h2>Companion</h2>
          <div class="tab-row">
            <button onclick="document.querySelector('button[data-tab=memory]').click()">Memory</button>
            <button onclick="showCompanionTab('directives')">Directive Ledger</button>
            <button class="active" onclick="showCompanionTab('proof')">Proof Vault</button>
            <button onclick="showCompanionTab('council')">Council Mode</button>
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
              <input id="choreRecurrence" placeholder="daily, weekly, monthly">
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
        </div>
        <h2>Council Mode</h2>
        <p class="muted">Use this as the collection point: copy handoffs for each companion, ask the same question, then paste each companion's command batch back into the Memory tab for that companion. This preserves separate private stances.</p>
        <div id="councilCompanions"></div>
      </div>
    </section>
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

    document.getElementById('changePasswordButton').addEventListener('click', async () => {
      const current = prompt('Current password');
      if (current === null) return;
      const next = prompt('New password');
      if (next === null) return;
      const res = await fetch('/api/profile/password', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: current, new_password: next })
      });
      await handleResponse(res);
      setStatus('Password changed.');
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
      document.getElementById('profileLogoutButton').style.display = sessionInfo.authenticated ? '' : 'none';
      document.getElementById('profileSettingsButton').style.display = sessionInfo.authenticated ? '' : 'none';
      document.getElementById('changePasswordButton').style.display = sessionInfo.authenticated ? '' : 'none';
    }

    function applyLoggedOutState() {
      document.querySelectorAll('nav button').forEach(button => {
        button.style.display = button.dataset.tab === 'dashboard' ? '' : 'none';
      });
      document.querySelectorAll('section').forEach(section => section.classList.remove('active'));
      document.getElementById('dashboard').classList.add('active');
      selectedCompanion = null;
      selectedProjectTodoId = null;
      setStatus(sessionInfo.bootstrap_required ? 'Set the first Array password.' : 'Login required.');
    }

    document.getElementById('profileSettingsButton').addEventListener('click', async () => {
      const current = state && state.profile ? state.profile.display_name : activeProfileName();
      const displayName = prompt('Display name', current || activeProfileName());
      if (displayName === null) return;
      const res = await fetch('/api/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: displayName })
      });
      await handleResponse(res);
      await loadState();
    });

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
    document.getElementById('foodDate').value = new Date().toISOString().slice(0, 10);

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
      selectedCompanion = state.companions.length ? (selectedCompanion || state.companions[0].name) : null;
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
      renderAdmin();
      renderCouncil();
      if ((state.access || {}).companions && selectedCompanion) {
        await loadPacket();
        renderMemoryIndex();
      }
      renderMemoryIndex();
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
      const companionOptions = state.companions.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)}</option>`).join('');
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
      if (!selectedCompanion) return;
      const res = await fetch(`/api/companion/${encodeURIComponent(selectedCompanion)}/packet`);
      const data = await handleResponse(res, false);
      document.getElementById('packetBox').value = data.packet;
    }

    function currentCompanion() {
      return state.companions.find(c => c.name === selectedCompanion);
    }

    function renderMemoryIndex() {
      if (!((state.access || {}).companions)) return;
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
      if (!((state.access || {}).directives)) return;
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
      if (!((state.access || {}).proof)) return;
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
            return `<div class="todo-row"><strong>${escapeHtml(todo.title)}</strong> ${selected}<br><span class="muted">${escapeHtml(todo.status || 'open')} | added ${escapeHtml(todo.created_at || '')} | started ${escapeHtml(todo.date_started || todo.start_date || '')} | next ${escapeHtml(todo.next_step || '')}</span><br><button class="inline" onclick="selectProjectTodo('${escapeJs(todo.id)}')">Select</button> <a class="inline primary" href="/projects/${encodeURIComponent(todo.id)}${profileQuery()}" target="_blank">Open page</a> <button class="inline" onclick="loadProjectTodoIntoForm('${escapeJs(todo.id)}')">Edit</button> <button class="inline" onclick="deleteProjectTodo('${escapeJs(todo.id)}')">Delete</button></div>`;
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
      document.getElementById('choreList').innerHTML = chores.length
        ? chores.slice().reverse().map(chore => `<div class="todo-row"><strong>${escapeHtml(chore.title)}</strong><br><span class="muted">${escapeHtml(chore.status || 'open')} | due ${escapeHtml(chore.due_date || '')} | ${escapeHtml(chore.recurrence || '')}</span><br><span>${escapeHtml(chore.notes || '')}</span><br><button class="inline" onclick="setChoreStatus('${escapeJs(chore.id)}','done')">Done</button> <button class="inline" onclick="setChoreStatus('${escapeJs(chore.id)}','open')">Reopen</button> <button class="inline" onclick="deleteChore('${escapeJs(chore.id)}')">Delete</button></div>`).join('')
        : '<p class="muted">No chores yet.</p>';
    }

    async function createChore() {
      const body = {
        title: document.getElementById('choreTitle').value,
        due_date: document.getElementById('choreDueDate').value,
        recurrence: document.getElementById('choreRecurrence').value,
        notes: document.getElementById('choreNotes').value,
      };
      const res = await fetch('/api/chores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      await handleResponse(res);
      for (const id of ['choreTitle', 'choreDueDate', 'choreRecurrence', 'choreNotes']) {
        document.getElementById(id).value = '';
      }
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
        : '<p class="muted">No inventory items yet.</p>';
    }

    function renderDietShoppingList() {
      const items = ((state.diet || {}).shopping_list || []);
      document.getElementById('dietShoppingList').innerHTML = items.length
        ? `<div class="scrollbox"><table><thead><tr><th>Item</th><th>Need</th><th>Containers</th><th>Cost</th></tr></thead><tbody>${items.map(item => `<tr><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.needed_units)} ${escapeHtml(item.unit_label)}</td><td>${escapeHtml(item.containers)}</td><td>$${escapeHtml(Number(item.cost || 0).toFixed(2))}</td></tr>`).join('')}</tbody></table></div>`
        : '<p class="muted">Shopping list is empty.</p>';
    }

    function renderFoodDiary() {
      const entries = ((state.diet || {}).food_diary || []);
      document.getElementById('foodDiaryList').innerHTML = entries.length
        ? renderSimpleList(entries.slice().reverse(), item => `${item.date || ''} | ${item.food || ''} | carbs ${item.carbs ? 'yes' : 'no'} | sugars ${item.sugars ? 'yes' : 'no'}`)
        : '<p class="muted">No food entries yet.</p>';
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
      await navigator.clipboard.writeText(text);
      setStatus('Shopping list copied.');
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
      document.getElementById('fitnessOrders').innerHTML = (fitness.orders || []).map(order => `<div class="todo-row"><strong>${escapeHtml(order.title)}</strong> <span class="pill">${escapeHtml(order.status || 'open')}</span><p class="muted">${escapeHtml(order.details || '')}</p><button class="inline primary" onclick="updateFitnessOrder('${escapeJs(order.id)}','done')">Mark Done</button> <button class="inline" onclick="updateFitnessOrder('${escapeJs(order.id)}','snoozed')">Snooze</button> <button class="inline" onclick="rescheduleFitnessOrder('${escapeJs(order.id)}')">Reschedule</button> <button class="inline" onclick="skipFitnessOrder('${escapeJs(order.id)}')">Skip with Reason</button></div>`).join('') || '<p class="muted">No orders.</p>';
      const plan = fitness.workout_plan || {};
      document.getElementById('fitnessPlan').innerHTML = Object.entries(plan).map(([key, value]) => `<h3>${escapeHtml(key.replaceAll('_',' '))}</h3><ul>${[].concat(value || []).map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`).join('') + `<h3>Safety Rules</h3><ul>${(fitness.safety_rules || []).map(rule => `<li>${escapeHtml(rule)}</li>`).join('')}</ul>`;
      document.getElementById('fitnessProgress').innerHTML = renderSimpleList((fitness.progress_notes || []).slice().reverse(), item => `${item.date || ''} | ${item.note || item.notes || ''}`);
      document.getElementById('fitnessChallenges').innerHTML = (fitness.challenges || []).map(challenge => `<div class="todo-row"><strong>${escapeHtml(challenge.name)}</strong> <span class="pill">${escapeHtml(challenge.status)}</span><p class="muted">${escapeHtml(challenge.requirements || '')}</p><button class="inline primary" onclick="updateFitnessChallenge('${escapeJs(challenge.id)}','active')">Start Challenge</button> <button class="inline" onclick="updateFitnessChallenge('${escapeJs(challenge.id)}','complete')">Complete Challenge</button></div>`).join('') || '<p class="muted">No challenges.</p>';
      document.getElementById('fitnessHistory').innerHTML = renderSimpleList((fitness.history || []).slice().reverse(), item => `${item.date || ''} | ${item.title || item.kind || ''} | ${item.status || ''}`);
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

    function renderCouncil() {
      if (!((state.access || {}).companions)) return;
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

    function renderJournalList(items) {
      if (!items.length) return '<p class="muted">No entries.</p>';
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
        timeout = settings_store().get("session_timeout_minutes", 30) * 60
        return f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={timeout}"

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
                elif path == "/api/reading-progress":
                    if not self.require_category_access("spiritual"):
                        return
                    reading = mark_reading_complete(self.read_json_body())
                    self.send_json({"message": f"Marked {reading['label']} read.", "reading": reading})
                elif path == "/api/project-assets/upload":
                    if not self.require_category_access("projects"):
                        return
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
            elif path.startswith("/api/fitness/challenges/"):
                if not self.require_category_access("fitness"):
                    return
                challenge_id = unquote(path.rsplit("/", 1)[1])
                challenge = update_fitness_challenge(challenge_id, self.read_json_body())
                self.send_json({"message": f"Updated {challenge['id']}.", "challenge": challenge, "fitness": fitness_state()})
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

    def send_json(self, data, status=200, headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
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
        allowed_roots = [PROOF_DIR.resolve(), PROJECT_ASSET_DIR.resolve()]
        in_allowed_root = any(str(resolved).lower().startswith(str(root).lower()) for root in allowed_roots)
        if not in_allowed_root or not resolved.exists():
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
