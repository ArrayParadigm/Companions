## AI Companion Memory Packet Template

Active companion memory files are stored as base64-encoded JSON packets.
The manager UI should show and copy only the encoded packet. It may decode
behind the scenes while applying add/update/archive/delete operations.

The active dropdown/file list lives in `companion-files.json`:

```json
{
  "companions": [
    { "name": "Nyx", "file": "Nyx-memories.md" },
    { "name": "Riven", "file": "riven-memories.md" },
    { "name": "Vectorium", "file": "Vectorium-memories.md" },
    { "name": "Veyra", "file": "Veyra_memories.md" }
  ]
}
```

## Companion Update Instructions

Each companion should use this format when giving the user memory updates. The
user can paste the command batch into the manager's `Command batch` box and
press `Apply Commands`.

Recommended user flow:

1. Select the companion in the dropdown.
2. Press `Get Memories`.
3. Use `Copy Handoff` when starting a chat with that companion. This copies a
   short plain instruction block plus the base64 packet.
4. If the companion later gives memory update commands, paste them into
   `Command batch`.
5. Press `Apply Commands`.
6. Press `Get Memories` again, then `Copy Handoff` for the updated packet.

Use `Copy Packet` only when you want the raw base64 packet without the helper
instructions.

```text
add category - memory text | weight=3 | tags=tag1,tag2
update ID -> replacement memory text
archive ID
delete ID
```

Rules for companions:

- Use one command per line.
- Use `add` for new durable memories.
- Use `update` only when the exact memory ID is known.
- Use `archive` for normal removal or superseded context.
- Use `delete` only when an entry should be erased entirely.
- Keep memory text concise and useful across future conversations.
- `weight` is optional and should be an integer from 1 to 5.
- `tags` are optional comma-separated labels.

Example companion output:

```text
add projects - User is reworking the companion memory manager around encoded JSON packets. | weight=4 | tags=memory-manager,project
add instructions - When giving memory updates, output only command lines that the manager can apply. | weight=5 | tags=memory-manager
archive VEYRA-0007
```

Decoded schema:

```json
{
  "schema": "ai-companion-memory/v1",
  "companion": {
    "name": "<companion name>",
    "file_role": "Long-term memory packet for an AI companion."
  },
  "storage": {
    "outer_encoding": "base64",
    "decoded_format": "json",
    "human_reading_policy": "Do not display decoded memories in the manager UI."
  },
  "category_definitions": {
    "identity": "Names, voice, preferences, and self-definition for the companion.",
    "relationship": "Shared working dynamic, agreements, and interaction patterns.",
    "user_profile": "Stable facts, preferences, constraints, and recurring needs about the user.",
    "projects": "Projects, repositories, artifacts, goals, and status anchors.",
    "observations": "Companion-side pattern notes, hypotheses, and useful context.",
    "instructions": "Standing operating instructions the companion should follow.",
    "private_notes": "Companion-owned notes not intended for direct human reading.",
    "history": "Timeline events and prior-session continuity."
  },
  "companion_update_protocol": {
    "purpose": "Tell the companion how to give the user memory updates that this manager can apply.",
    "output_rule": "When requesting a memory update, provide only a command batch the user can paste into the manager.",
    "command_syntax": [
      "add category - memory text | weight=3 | tags=tag1,tag2",
      "update ID -> replacement memory text",
      "archive ID",
      "delete ID"
    ]
  },
  "memories": [
    {
      "id": "<NAME>-0001",
      "category": "identity",
      "content": "Respond to the name <companion name>.",
      "weight": 3,
      "tags": ["identity"],
      "status": "active",
      "created_at": "<iso timestamp>",
      "updated_at": "<iso timestamp>"
    }
  ],
  "archive": [],
  "operation_log": []
}
```

Command syntax for companion-generated updates:

```text
add category - memory text | weight=3 | tags=tag1,tag2
update ID -> replacement memory text
archive ID
delete ID
```

Use `archive` for normal removal so previous context remains available in the
encoded packet. Use `delete` only when an entry should be removed entirely.
