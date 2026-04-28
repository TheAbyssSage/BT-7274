"""
Protocol Brief for BT-7274 Voice Assistant.

Manages pilot to-do lists and personal notes.
- To-do list: logs/pilot_todo/<name>_todo.json
- Notes: logs/pilot_notes/<name>_notes.jsonl

Command: "BT, protocol brief."
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


class ProtocolBrief:
    """Manages pilot to-do lists and personal notes."""

    def __init__(self, base_log_dir: Optional[str] = None):
        if base_log_dir is None:
            base_log_dir = str(Path(__file__).parent.parent / "logs")
        self.base_log_dir = Path(base_log_dir)
        self.todo_dir = self.base_log_dir / "pilot_todo"
        self.notes_dir = self.base_log_dir / "pilot_notes"
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure log directories exist."""
        self.todo_dir.mkdir(parents=True, exist_ok=True)
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_name(self, name: str) -> str:
        """Sanitize a name for use in filenames."""
        sanitized = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_').lower()
        return sanitized or "pilot"

    # ─── To-Do List ─────────────────────────────────────────────────────

    def _todo_path(self, name: str) -> Path:
        safe_name = self._sanitize_name(name)
        return self.todo_dir / f"{safe_name}_todo.json"

    def _load_todo(self, name: str) -> list[dict]:
        path = self._todo_path(name)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save_todo(self, name: str, items: list[dict]):
        path = self._todo_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

    def add_todo(self, text: str, name: str = "pilot", priority: str = "normal") -> str:
        """Add a new to-do item."""
        items = self._load_todo(name)
        item = {
            "id": len(items) + 1,
            "text": text,
            "priority": priority,
            "created": datetime.now().isoformat(),
            "completed": False,
            "completed_at": None,
        }
        items.append(item)
        self._save_todo(name, items)
        return f"To-do added: {text}"

    def complete_todo(self, item_id: int, name: str = "pilot") -> str:
        """Mark a to-do item as completed."""
        items = self._load_todo(name)
        for item in items:
            if item["id"] == item_id:
                item["completed"] = True
                item["completed_at"] = datetime.now().isoformat()
                self._save_todo(name, items)
                return f"To-do completed: {item['text']}"
        return f"To-do item {item_id} not found."

    def remove_todo(self, item_id: int, name: str = "pilot") -> str:
        """Remove a to-do item."""
        items = self._load_todo(name)
        for i, item in enumerate(items):
            if item["id"] == item_id:
                removed = items.pop(i)
                # Re-number remaining items
                for idx, it in enumerate(items, start=1):
                    it["id"] = idx
                self._save_todo(name, items)
                return f"To-do removed: {removed['text']}"
        return f"To-do item {item_id} not found."

    def list_todo(self, name: str = "pilot", show_completed: bool = False) -> str:
        """List to-do items."""
        items = self._load_todo(name)
        if not items:
            return "No to-do items found, Pilot."

        active = [it for it in items if not it["completed"]]
        completed = [it for it in items if it["completed"]]

        lines = []
        if active:
            lines.append(f"Active tasks ({len(active)}):")
            for it in active:
                priority = it.get("priority", "normal")
                p_marker = "[!]" if priority == "high" else "[ ]" if priority == "low" else "[-]"
                lines.append(f"  {p_marker} #{it['id']}: {it['text']}")
        else:
            lines.append("No active tasks.")

        if show_completed and completed:
            lines.append(f"\nCompleted ({len(completed)}):")
            for it in completed:
                lines.append(f"  [x] #{it['id']}: {it['text']}")

        return "\n".join(lines)

    def clear_todo(self, name: str = "pilot") -> str:
        """Clear all completed to-do items."""
        items = self._load_todo(name)
        active = [it for it in items if not it["completed"]]
        if len(active) == len(items):
            return "No completed items to clear."
        self._save_todo(name, active)
        return f"Cleared {len(items) - len(active)} completed items."

    # ─── Notes ──────────────────────────────────────────────────────────

    def _notes_path(self, name: str) -> Path:
        safe_name = self._sanitize_name(name)
        return self.notes_dir / f"{safe_name}_notes.jsonl"

    def add_note(self, text: str, name: str = "pilot", tags: Optional[list[str]] = None) -> str:
        """Append a note to the personal log."""
        path = self._notes_path(name)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "text": text,
            "tags": tags or [],
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return f"Note saved."

    def list_notes(self, name: str = "pilot", lines: int = 10, tag: Optional[str] = None) -> str:
        """Read recent notes."""
        path = self._notes_path(name)
        if not path.exists():
            return "No notes found, Pilot."

        all_entries = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if tag and tag not in entry.get("tags", []):
                            continue
                        all_entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except IOError:
            return "Unable to read notes."

        if not all_entries:
            return "No notes found, Pilot."

        # Sort by timestamp descending
        all_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        selected = all_entries[:lines]

        lines_out = [f"Recent notes ({len(selected)} of {len(all_entries)}):"]
        for entry in selected:
            ts = entry.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    ts = dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass
            text = entry.get("text", "")
            tags = entry.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines_out.append(f"  [{ts}]{tag_str} {text}")

        return "\n".join(lines_out)

    # ─── Protocol Brief Summary ─────────────────────────────────────────

    def get_brief(self, name: str = "pilot") -> str:
        """Generate a protocol brief summary."""
        items = self._load_todo(name)
        active = [it for it in items if not it["completed"]]
        completed = [it for it in items if it["completed"]]

        lines = ["PROTOCOL BRIEF"]
        lines.append(f"Active tasks: {len(active)}")
        if active:
            for it in active[:5]:
                p = it.get("priority", "normal")
                p_marker = "[!]" if p == "high" else "[-]"
                lines.append(f"  {p_marker} #{it['id']}: {it['text']}")
            if len(active) > 5:
                lines.append(f"  ... and {len(active) - 5} more")

        lines.append(f"\nCompleted today: {len(completed)}")

        # Count notes
        notes_path = self._notes_path(name)
        note_count = 0
        if notes_path.exists():
            try:
                with open(notes_path, "r", encoding="utf-8") as f:
                    note_count = sum(1 for line in f if line.strip())
            except IOError:
                pass
        lines.append(f"Total notes: {note_count}")

        return "\n".join(lines)

    def set_mission(self, mission_text: str, name: str = "pilot") -> str:
        """Set or update the current mission briefing.

        Args:
            mission_text: The mission description.
            name: Pilot name.

        Returns:
            Confirmation message.
        """
        mission_path = self.todo_dir / f"{self._sanitize_name(name)}_mission.json"
        mission_data = {
            "text": mission_text,
            "updated": datetime.now().isoformat(),
        }
        with open(mission_path, "w", encoding="utf-8") as f:
            json.dump(mission_data, f, indent=2, ensure_ascii=False)
        return f"Mission updated: {mission_text}"

    def get_mission(self, name: str = "pilot") -> Optional[str]:
        """Retrieve the current mission briefing.

        Args:
            name: Pilot name.

        Returns:
            Mission text or None if no mission is set.
        """
        mission_path = self.todo_dir / f"{self._sanitize_name(name)}_mission.json"
        if not mission_path.exists():
            return None
        try:
            with open(mission_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("text")
        except (json.JSONDecodeError, IOError):
            return None

    def clear_mission(self, name: str = "pilot") -> str:
        """Clear the current mission briefing.

        Args:
            name: Pilot name.

        Returns:
            Confirmation message.
        """
        mission_path = self.todo_dir / f"{self._sanitize_name(name)}_mission.json"
        if mission_path.exists():
            mission_path.unlink()
            return "Mission briefing cleared, Pilot."
        return "No active mission briefing to clear."
