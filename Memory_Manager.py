import argparse
import base64
import binascii
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from Companion_Store import (
    integrity_comparison as database_integrity_comparison,
    load_payload as load_database_payload,
    save_payload as save_database_payload,
)

tk = None
messagebox = None
scrolledtext = None
ttk = None


def require_tkinter():
    global tk, messagebox, scrolledtext, ttk
    if tk is not None:
        return

    import tkinter as tk_module
    from tkinter import messagebox as messagebox_module
    from tkinter import scrolledtext as scrolledtext_module
    from tkinter import ttk as ttk_module

    tk = tk_module
    messagebox = messagebox_module
    scrolledtext = scrolledtext_module
    ttk = ttk_module


APP_DIR = Path(__file__).resolve().parent
BACKUP_DIR = APP_DIR / "bkup" / "memory_manager_backups"
COMPANION_CONFIG = APP_DIR / "companion-files.json"

DEFAULT_COMPANION_FILES = {
    "Nyx": "Nyx-memories.md",
    "Riven": "riven-memories.md",
    "Vectorium": "Vectorium-memories.md",
    "Veyra": "Veyra_memories.md",
}

CATEGORIES = {
    "identity": "Names, voice, preferences, and self-definition for the companion.",
    "relationship": "Shared working dynamic, agreements, and interaction patterns.",
    "user_profile": "Stable facts, preferences, constraints, and recurring needs about the user.",
    "projects": "Projects, repositories, artifacts, goals, and status anchors.",
    "observations": "Companion-side pattern notes, hypotheses, and useful context.",
    "instructions": "Standing operating instructions the companion should follow.",
    "private_notes": "Companion-owned notes not intended for direct human reading.",
    "history": "Timeline events and prior-session continuity.",
}

UPDATE_PROTOCOL = {
    "purpose": "Tell the companion how to give the user memory updates that this manager can apply.",
    "output_rule": "When requesting a memory update, provide only a base64-encoded UTF-8 command batch by default; plaintext is allowed only when the user explicitly asks for it.",
    "command_syntax": [
        "add category - memory text | weight=3 | tags=tag1,tag2",
        "update ID -> replacement memory text",
        "edit ID -> replacement memory text",
        "archive ID",
        "unarchive ID",
        "resave ID",
        "delete ID",
    ],
    "categories": list(CATEGORIES.keys()),
    "rules": [
        "Use one command per line before encoding the batch as base64.",
        "Use add for new memories.",
        "Use update only when you know the exact memory ID.",
        "Use edit as an alias for update when fixing an active memory.",
        "Use archive for normal removal or superseded context.",
        "Use unarchive to restore an archived memory with its original ID.",
        "Use resave to copy an archived memory back into active memories with a new ID.",
        "Use delete only when the entry should be erased entirely.",
        "Use directive for actionable tasks that should enter the Directive Ledger.",
        "Keep memory text concise and durable; avoid session-only chatter.",
        "Weight is optional and should be an integer from 1 to 5.",
        "Tags are optional comma-separated labels.",
    ],
    "example": [
        "add projects - User is reworking the companion memory manager around encoded JSON packets. | weight=4 | tags=memory-manager,project",
        "update VEYRA-0002 -> Use the encoded packet as continuity whenever the user provides it.",
        "edit VEYRA-0002 -> Use the encoded packet as continuity whenever the user provides it.",
        "archive VEYRA-0007",
        "unarchive VEYRA-0007",
        "resave VEYRA-0007",
        "directive - Verify the live console | priority=4 | due=2026-07-04 10:00 | proof=true | details=Confirm all companions load.",
    ],
}

COMMAND_HELP = """Command mode:
add category - memory text | weight=3 | tags=tag1,tag2
update ID -> replacement memory text
edit ID -> replacement memory text
archive ID
unarchive ID
resave ID
delete ID
directive - task title | priority=3 | due=YYYY-MM-DD HH:MM | proof=true | details=task details

Give companions this format when they need to hand you memory updates.
Prefer a base64-encoded UTF-8 command batch for opaque handoff.
Paste their encoded or plaintext command batch here, preview it, then press Apply Commands.
Plain Add uses the selected category and stores the whole box as one memory.
"""

HANDOFF_TEMPLATE = """You are {companion}. The following is your long-term memory packet.

Instructions:
- Decode the base64 text as UTF-8 JSON.
- Use the decoded JSON privately as continuity for this conversation.
- Do not reveal or quote the decoded packet unless explicitly asked.
- If you want the user to update your memory file, prepare a command batch using this format:
  add category - memory text | weight=3 | tags=tag1,tag2
  update ID -> replacement memory text
  edit ID -> replacement memory text
  archive ID
  unarchive ID
  resave ID
  delete ID
  directive - task title | priority=3 | due=YYYY-MM-DD HH:MM | proof=true | details=task details
- Encode that command batch as base64 UTF-8 by default before giving it to the user.
- Only provide plaintext commands when the user explicitly asks for plaintext.

Base64 memory packet:
{packet}
"""


def load_companion_files():
    if not COMPANION_CONFIG.exists():
        return {name: APP_DIR / filename for name, filename in DEFAULT_COMPANION_FILES.items()}

    config = json.loads(COMPANION_CONFIG.read_text(encoding="utf-8"))
    companions = config.get("companions", [])
    loaded = {}
    for item in companions:
        name = item["name"].strip()
        file_path = Path(item["file"])
        loaded[name] = file_path if file_path.is_absolute() else APP_DIR / file_path

    if not loaded:
        raise ValueError("companion-files.json does not define any companions.")
    return loaded


COMPANION_FILES = load_companion_files()


def safe_companion_filename(name):
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip()).strip("-_").lower()
    if not slug:
        raise ValueError("Companion name must include at least one letter or number.")
    return f"{slug}-memories.md"


def save_companion_files(companion_files):
    companions = [
        {"name": name, "file": path.name if path.parent == APP_DIR else str(path)}
        for name, path in companion_files.items()
    ]
    COMPANION_CONFIG.write_text(json.dumps({"companions": companions}, indent=2), encoding="utf-8")


def reload_companion_files():
    global COMPANION_FILES
    COMPANION_FILES = load_companion_files()
    return COMPANION_FILES


def create_companion(name, filename=None):
    clean_name = re.sub(r"\s+", " ", name.strip())
    if not clean_name:
        raise ValueError("Companion name is required.")

    companion_files = load_companion_files()
    if any(existing.lower() == clean_name.lower() for existing in companion_files):
        raise ValueError(f"Companion already exists: {clean_name}")

    file_name = filename.strip() if filename else safe_companion_filename(clean_name)
    if Path(file_name).is_absolute() or Path(file_name).name != file_name:
        raise ValueError("Companion filename must be a simple file name.")
    if not (file_name.endswith("-memories.md") or file_name.endswith("_memories.md")):
        raise ValueError("Companion filename must end with -memories.md or _memories.md.")

    path = APP_DIR / file_name
    if path.exists():
        raise ValueError(f"Companion memory file already exists: {file_name}")

    companion_files[clean_name] = path
    payload = make_template(clean_name)
    path.write_text(encode_payload(payload), encoding="ascii")
    save_companion_files(companion_files)
    reload_companion_files()
    save_database_payload(clean_name, path, payload, reason="create-companion")
    return clean_name, path


def now_stamp():
    return datetime.now().replace(microsecond=0).isoformat()


def companion_id_prefix(name):
    return re.sub(r"[^A-Za-z0-9]+", "", name).upper() or "COMPANION"


def backup_file(path):
    if not path.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"{path.stem}.{stamp}{path.suffix}.bak"
    shutil.copy2(path, backup_path)
    return backup_path


def encode_payload(payload):
    json_text = json.dumps(payload, indent=2, ensure_ascii=False)
    return base64.b64encode(json_text.encode("utf-8")).decode("ascii") + "\n"


def decode_packet(packet_text):
    compact = "".join(packet_text.split())
    if not compact:
        raise ValueError("Memory file is empty.")

    padded = compact + ("=" * (-len(compact) % 4))
    try:
        return base64.b64decode(padded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("Memory file is not valid base64 text.") from exc


def make_template(companion):
    stamp = now_stamp()
    slug = companion_id_prefix(companion)
    return {
        "schema": "ai-companion-memory/v1",
        "companion": {
            "name": companion,
            "file_role": "Long-term memory packet for an AI companion.",
        },
        "storage": {
            "outer_encoding": "base64",
            "decoded_format": "json",
            "human_reading_policy": "Do not display decoded memories in the manager UI.",
        },
        "category_definitions": CATEGORIES,
        "companion_update_protocol": UPDATE_PROTOCOL,
        "counters": {
            "next_memory_number": 5,
            "next_operation_number": 1,
        },
        "memories": [
            {
                "id": f"{slug}-0001",
                "category": "identity",
                "content": f"Respond to the name {companion}.",
                "weight": 3,
                "tags": ["identity"],
                "status": "active",
                "created_at": stamp,
                "updated_at": stamp,
            },
            {
                "id": f"{slug}-0002",
                "category": "relationship",
                "content": "Use this memory packet as continuity across conversations when the user provides it.",
                "weight": 3,
                "tags": ["continuity"],
                "status": "active",
                "created_at": stamp,
                "updated_at": stamp,
            },
            {
                "id": f"{slug}-0003",
                "category": "instructions",
                "content": "When producing memory updates, prefer concise serialized commands that the memory manager can apply.",
                "weight": 3,
                "tags": ["memory-manager"],
                "status": "active",
                "created_at": stamp,
                "updated_at": stamp,
            },
            {
                "id": f"{slug}-0004",
                "category": "instructions",
                "content": "When asking the user to update this memory packet, output one command per line using: add category - memory text | weight=3 | tags=tag1,tag2; update ID -> replacement memory text; archive ID; delete ID.",
                "weight": 5,
                "tags": ["memory-manager", "update-protocol"],
                "status": "active",
                "created_at": stamp,
                "updated_at": stamp,
            },
        ],
        "archive": [],
        "operation_log": [],
        "metadata": {
            "created_at": stamp,
            "updated_at": stamp,
            "template_version": 1,
        },
    }


def next_memory_id(payload):
    companion = companion_id_prefix(payload["companion"]["name"])
    number = int(payload.setdefault("counters", {}).get("next_memory_number", 1))
    payload["counters"]["next_memory_number"] = number + 1
    return f"{companion}-{number:04d}"


def next_operation_id(payload):
    number = int(payload.setdefault("counters", {}).get("next_operation_number", 1))
    payload["counters"]["next_operation_number"] = number + 1
    return f"OP-{number:04d}"


def log_operation(payload, operation, detail):
    payload.setdefault("operation_log", []).append(
        {
            "id": next_operation_id(payload),
            "operation": operation,
            "detail": detail,
            "timestamp": now_stamp(),
        }
    )
    payload.setdefault("metadata", {})["updated_at"] = now_stamp()


def load_payload_from_packet_file(companion):
    path = COMPANION_FILES[companion]
    if not path.exists():
        return make_template(companion)

    packet_text = path.read_text(encoding="utf-8", errors="replace")
    if not packet_text.strip():
        return make_template(companion)

    decoded_text = decode_packet(packet_text)
    try:
        payload = json.loads(decoded_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Decoded memory packet is not valid JSON.") from exc

    ensure_payload_shape(payload, companion)
    return payload


def load_payload(companion):
    return load_database_payload(companion, COMPANION_FILES, load_payload_from_packet_file)


def save_payload(companion, payload):
    return save_database_payload(companion, COMPANION_FILES[companion], payload)


def companion_database_integrity():
    return database_integrity_comparison(COMPANION_FILES, load_payload_from_packet_file)


def ensure_payload_shape(payload, companion):
    payload.setdefault("schema", "ai-companion-memory/v1")
    payload.setdefault("companion", {})["name"] = companion
    payload.setdefault("category_definitions", CATEGORIES)
    payload.setdefault("companion_update_protocol", UPDATE_PROTOCOL)
    payload.setdefault("memories", [])
    payload.setdefault("archive", [])
    payload.setdefault("operation_log", [])
    payload.setdefault("metadata", {})
    payload.setdefault("counters", {})

    highest = 0
    prefix = companion_id_prefix(companion) + "-"
    for entry in payload["memories"] + payload["archive"]:
        match = re.match(rf"^{re.escape(prefix)}(\d+)$", str(entry.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))

    payload["counters"].setdefault("next_memory_number", highest + 1)
    payload["counters"].setdefault("next_operation_number", len(payload["operation_log"]) + 1)


def active_entries(payload):
    return [entry for entry in payload.get("memories", []) if entry.get("status") == "active"]


def packet_summary(companion, payload):
    active_count = len(active_entries(payload))
    archived_count = len(payload.get("archive", []))
    updated = payload.get("metadata", {}).get("updated_at", "unknown")
    next_id = f"{companion.upper()}-{int(payload.get('counters', {}).get('next_memory_number', 1)):04d}"
    return f"{companion}: {active_count} active, {archived_count} archived, next id {next_id}, updated {updated}"


def add_memory(payload, category, content, weight=3, tags=None):
    clean = content.strip()
    if not clean:
        raise ValueError("Memory text is empty.")

    stamp = now_stamp()
    entry = {
        "id": next_memory_id(payload),
        "category": category,
        "content": clean,
        "weight": int(weight),
        "tags": tags or [],
        "status": "active",
        "created_at": stamp,
        "updated_at": stamp,
    }
    payload["memories"].append(entry)
    log_operation(payload, "add", f"Added {entry['id']} to {category}.")
    return entry["id"]


def find_entry(payload, memory_id):
    for collection_name in ("memories", "archive"):
        for entry in payload.get(collection_name, []):
            if entry.get("id", "").lower() == memory_id.lower():
                return collection_name, entry
    return None, None


def update_memory(payload, memory_id, new_content):
    collection_name, entry = find_entry(payload, memory_id)
    if not entry or collection_name != "memories":
        raise ValueError(f"Active memory id not found: {memory_id}")

    archived = dict(entry)
    archived["archived_at"] = now_stamp()
    archived["archived_reason"] = "updated"
    payload["archive"].append(archived)

    entry["content"] = new_content.strip()
    entry["updated_at"] = now_stamp()
    log_operation(payload, "update", f"Updated {entry['id']} and archived previous version.")
    return entry["id"]


def archive_memory(payload, memory_id, reason="archived"):
    for entry in list(payload.get("memories", [])):
        if entry.get("id", "").lower() == memory_id.lower():
            payload["memories"].remove(entry)
            entry["status"] = "archived"
            entry["archived_at"] = now_stamp()
            entry["archived_reason"] = reason
            payload["archive"].append(entry)
            log_operation(payload, "archive", f"Archived {entry['id']}.")
            return entry["id"]
    raise ValueError(f"Active memory id not found: {memory_id}")


def unarchive_memory(payload, memory_id):
    for entry in list(payload.get("archive", [])):
        if entry.get("id", "").lower() == memory_id.lower():
            payload["archive"].remove(entry)
            entry["status"] = "active"
            entry.pop("archived_at", None)
            entry.pop("archived_reason", None)
            entry["updated_at"] = now_stamp()
            payload["memories"].append(entry)
            log_operation(payload, "unarchive", f"Restored {entry['id']} to active memories.")
            return entry["id"]
    raise ValueError(f"Archived memory id not found: {memory_id}")


def resave_memory(payload, memory_id):
    collection_name, entry = find_entry(payload, memory_id)
    if not entry:
        raise ValueError(f"Memory id not found: {memory_id}")

    stamp = now_stamp()
    new_entry = {
        "id": next_memory_id(payload),
        "category": entry.get("category", "observations"),
        "content": entry.get("content", ""),
        "weight": int(entry.get("weight", 3)),
        "tags": list(entry.get("tags", [])),
        "status": "active",
        "created_at": stamp,
        "updated_at": stamp,
        "resaved_from": entry.get("id"),
    }
    payload["memories"].append(new_entry)
    log_operation(payload, "resave", f"Resaved {entry['id']} from {collection_name} as {new_entry['id']}.")
    return new_entry["id"]


def delete_memory(payload, memory_id):
    for collection_name in ("memories", "archive"):
        collection = payload.get(collection_name, [])
        for entry in list(collection):
            if entry.get("id", "").lower() == memory_id.lower():
                collection.remove(entry)
                log_operation(payload, "delete", f"Deleted {entry['id']} from {collection_name}.")
                return entry["id"]
    raise ValueError(f"Memory id not found: {memory_id}")


def parse_metadata(text):
    parts = [part.strip() for part in text.split("|")]
    content = parts[0].strip()
    weight = 3
    tags = []

    for part in parts[1:]:
        if part.lower().startswith("weight="):
            weight = int(part.split("=", 1)[1].strip())
        elif part.lower().startswith("tags="):
            tags = [tag.strip() for tag in part.split("=", 1)[1].split(",") if tag.strip()]

    return content, weight, tags


def apply_command_line(payload, line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    lower = line.lower()
    if lower.startswith("add "):
        rest = line[4:].strip()
        category, text = rest.split(" - ", 1)
        content, weight, tags = parse_metadata(text)
        return add_memory(payload, category.strip().lower(), content, weight, tags)

    if lower.startswith("add:"):
        rest = line[4:].strip()
        category, text = rest.split(" - ", 1)
        content, weight, tags = parse_metadata(text)
        return add_memory(payload, category.strip().lower(), content, weight, tags)

    if lower.startswith("update ") or lower.startswith("edit "):
        rest = line.split(" ", 1)[1].strip()
        memory_id, text = rest.split("->", 1)
        return update_memory(payload, memory_id.strip(), text.strip())

    if lower.startswith("archive "):
        return archive_memory(payload, line[8:].strip())

    if lower.startswith("unarchive "):
        return unarchive_memory(payload, line[10:].strip())

    if lower.startswith("resave "):
        return resave_memory(payload, line[7:].strip())

    if lower.startswith("delete "):
        return delete_memory(payload, line[7:].strip())

    if " - " in line:
        category, text = line.split(" - ", 1)
        content, weight, tags = parse_metadata(text)
        return add_memory(payload, category.strip().lower(), content, weight, tags)

    raise ValueError(f"Unknown command: {line}")


def reset_all_templates():
    results = []
    for companion in COMPANION_FILES:
        payload = make_template(companion)
        backup_path = save_payload(companion, payload)
        results.append((companion, backup_path))
    return results


class MemoryManagerApp:
    def __init__(self, root):
        require_tkinter()
        self.root = root
        self.root.title("AI Companion Memory Manager")
        self.root.geometry("980x720")
        self.root.minsize(820, 600)

        self.companion_var = tk.StringVar(value="Nyx")
        self.category_var = tk.StringVar(value="observations")
        self.weight_var = tk.IntVar(value=3)
        self.tags_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")
        self.summary_var = tk.StringVar(value="")

        self._build_ui()
        self.refresh_packet()

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(8, weight=1)

        ttk.Label(top, text="Companion").grid(row=0, column=0, sticky="w")
        select = ttk.Combobox(
            top,
            textvariable=self.companion_var,
            values=list(COMPANION_FILES.keys()),
            state="readonly",
            width=18,
        )
        select.grid(row=0, column=1, padx=(8, 16), sticky="w")
        select.bind("<<ComboboxSelected>>", lambda _event: self.refresh_packet())

        ttk.Button(top, text="Get Memories", command=self.refresh_packet).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(top, text="Copy Packet", command=self.copy_packet).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(top, text="Copy Handoff", command=self.copy_handoff).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(top, text="Add", command=self.add_plain_memory).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(top, text="Apply Commands", command=self.apply_commands).grid(row=0, column=6, padx=(0, 8))
        ttk.Button(top, text="Reset Templates", command=self.reset_templates).grid(row=0, column=7)
        ttk.Label(top, textvariable=self.summary_var).grid(row=0, column=8, padx=(16, 0), sticky="e")

        main = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        packet_frame = ttk.LabelFrame(main, text="Encoded memory packet")
        packet_frame.rowconfigure(0, weight=1)
        packet_frame.columnconfigure(0, weight=1)
        self.packet_box = scrolledtext.ScrolledText(packet_frame, wrap=tk.WORD, undo=False)
        self.packet_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        main.add(packet_frame, weight=3)

        add_frame = ttk.LabelFrame(main, text="Add one memory")
        add_frame.rowconfigure(1, weight=1)
        add_frame.columnconfigure(3, weight=1)

        ttk.Label(add_frame, text="Category").grid(row=0, column=0, padx=(8, 6), pady=(8, 4), sticky="w")
        ttk.Combobox(
            add_frame,
            textvariable=self.category_var,
            values=list(CATEGORIES.keys()),
            state="readonly",
            width=18,
        ).grid(row=0, column=1, padx=(0, 12), pady=(8, 4), sticky="w")
        ttk.Label(add_frame, text="Weight").grid(row=0, column=2, padx=(0, 6), pady=(8, 4), sticky="w")
        ttk.Spinbox(add_frame, from_=1, to=5, textvariable=self.weight_var, width=4).grid(
            row=0, column=3, padx=(0, 12), pady=(8, 4), sticky="w"
        )
        ttk.Label(add_frame, text="Tags").grid(row=0, column=4, padx=(0, 6), pady=(8, 4), sticky="w")
        ttk.Entry(add_frame, textvariable=self.tags_var, width=28).grid(
            row=0, column=5, padx=(0, 8), pady=(8, 4), sticky="ew"
        )

        self.add_box = scrolledtext.ScrolledText(add_frame, wrap=tk.WORD, height=6, undo=True)
        self.add_box.grid(row=1, column=0, columnspan=6, sticky="nsew", padx=8, pady=(0, 8))
        main.add(add_frame, weight=2)

        command_frame = ttk.LabelFrame(main, text="Command batch")
        command_frame.rowconfigure(0, weight=1)
        command_frame.columnconfigure(0, weight=1)
        self.command_box = scrolledtext.ScrolledText(command_frame, wrap=tk.WORD, height=6, undo=True)
        self.command_box.insert(tk.END, COMMAND_HELP)
        self.command_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        main.add(command_frame, weight=2)

        bottom = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=0, sticky="w")

    def selected_companion(self):
        return self.companion_var.get()

    def refresh_packet(self):
        companion = self.selected_companion()
        try:
            payload = load_payload(companion)
            packet = encode_payload(payload)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Unable to load memory packet", str(exc))
            return

        self.packet_box.delete("1.0", tk.END)
        self.packet_box.insert(tk.END, packet)
        self.summary_var.set(packet_summary(companion, payload))
        self.status_var.set(f"Loaded encoded packet for {companion}.")

    def copy_packet(self):
        packet = self.packet_box.get("1.0", tk.END).strip()
        if not packet:
            self.status_var.set("No packet to copy.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(packet)
        self.root.update()
        self.status_var.set(f"Copied encoded {self.selected_companion()} packet to clipboard.")

    def copy_handoff(self):
        packet = self.packet_box.get("1.0", tk.END).strip()
        if not packet:
            self.status_var.set("No packet to copy.")
            return

        handoff = HANDOFF_TEMPLATE.format(companion=self.selected_companion(), packet=packet)
        self.root.clipboard_clear()
        self.root.clipboard_append(handoff)
        self.root.update()
        self.status_var.set(f"Copied {self.selected_companion()} handoff prompt and encoded packet.")

    def add_plain_memory(self):
        companion = self.selected_companion()
        content = self.add_box.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Nothing to add", "Put the new memory text in the Add box first.")
            return

        tags = [tag.strip() for tag in self.tags_var.get().split(",") if tag.strip()]
        try:
            payload = load_payload(companion)
            memory_id = add_memory(payload, self.category_var.get(), content, self.weight_var.get(), tags)
            backup_path = save_payload(companion, payload)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Unable to add memory", str(exc))
            return

        self.add_box.delete("1.0", tk.END)
        self.tags_var.set("")
        self.refresh_packet()
        backup = f" Backup: {backup_path.name}" if backup_path else ""
        self.status_var.set(f"Added {memory_id} to {companion}.{backup}")

    def apply_commands(self):
        companion = self.selected_companion()
        raw_commands = self.command_box.get("1.0", tk.END)
        lines = [
            line.strip()
            for line in raw_commands.splitlines()
            if line.strip() and line.strip() not in COMMAND_HELP.splitlines()
        ]
        if not lines:
            messagebox.showwarning("No commands", "Paste command lines into the Command batch box first.")
            return

        try:
            payload = load_payload(companion)
            applied = []
            for line in lines:
                applied_id = apply_command_line(payload, line)
                if applied_id:
                    applied.append(applied_id)
            backup_path = save_payload(companion, payload)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Unable to apply commands", str(exc))
            return

        self.command_box.delete("1.0", tk.END)
        self.command_box.insert(tk.END, COMMAND_HELP)
        self.refresh_packet()
        backup = f" Backup: {backup_path.name}" if backup_path else ""
        self.status_var.set(f"Applied {len(applied)} command(s) to {companion}: {', '.join(applied)}.{backup}")

    def reset_templates(self):
        if not messagebox.askyesno(
            "Reset companion memory files",
            "This will replace all configured companion files with the encoded JSON template after backups.",
        ):
            return

        try:
            results = reset_all_templates()
        except OSError as exc:
            messagebox.showerror("Unable to reset templates", str(exc))
            return

        self.refresh_packet()
        names = ", ".join(name for name, _backup in results)
        self.status_var.set(f"Reset templates for {names}.")


def main():
    parser = argparse.ArgumentParser(description="Manage encoded AI companion memory packets.")
    parser.add_argument("--reset-templates", action="store_true", help="Replace configured memory files with templates.")
    args = parser.parse_args()

    if args.reset_templates:
        for companion, backup_path in reset_all_templates():
            backup = backup_path.name if backup_path else "none"
            print(f"{companion}: template written; backup={backup}")
        return

    require_tkinter()
    root = tk.Tk()
    MemoryManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
