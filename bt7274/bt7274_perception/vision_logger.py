"""
Vision Logger for BT-7274 Perception.

Logs all visual observations to logs/vision/ with timestamps,
image references, and analysis results.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from bt7274.bt7274_workstation.log_manager import get_vision_dir


class VisionLogger:
    """Logger for BT-7274's visual observations."""

    def __init__(self, log_dir: Optional[str] = None):
        if log_dir is None:
            log_dir = str(get_vision_dir())
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_day = None
        self._current_log_file = None
        self._current_image_dir = None
        self._max_image_age_days: int = 7  # Auto-clean images older than 7 days
        self._update_paths()
        self._cleanup_old_images()

    def _update_paths(self):
        """Update daily log file and image directory."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._current_day != today:
            self._current_day = today
            self._current_log_file = self.log_dir / f"bt_vision_{today}.jsonl"
            self._current_image_dir = self.log_dir / "images" / today
            self._current_image_dir.mkdir(parents=True, exist_ok=True)

    def _format_timestamp(self) -> str:
        """ISO timestamp for log entries."""
        return datetime.now().isoformat()

    def _format_human_time(self) -> str:
        """Human-readable time string."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def log_observation(
        self,
        description: str,
        image_path: Optional[str] = None,
        model: str = "unknown",
        response_time: float = 0.0,
        trigger: str = "manual",
        pilot_query: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Log a visual observation.

        Args:
            description: The vision model's description of the scene.
            image_path: Optional path to the captured image (will be archived).
            model: Vision model used.
            response_time: How long analysis took.
            trigger: What triggered the observation (e.g. 'manual', 'voice_command', 'auto_scan').
            pilot_query: The Pilot's query that triggered this, if any.
            metadata: Extra dict data to attach.

        Returns:
            Dict with the logged entry and archived_image_path.
        """
        self._update_paths()

        now = datetime.now()
        entry = {
            "timestamp": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "trigger": trigger,
            "pilot_query": pilot_query,
            "description": description,
            "model": model,
            "response_time": response_time,
        }

        # Archive image if provided
        archived_image_path: Optional[str] = None
        if image_path and Path(image_path).exists():
            try:
                ext = Path(image_path).suffix or ".png"
                safe_time = now.strftime("%H%M%S")
                archive_name = f"bt_vision_{safe_time}{ext}"
                if self._current_image_dir is not None:
                    dest = self._current_image_dir / archive_name
                    shutil.copy2(image_path, dest)
                    archived_image_path = str(dest)
                    entry["image_path"] = archived_image_path
            except Exception:
                pass

        if metadata:
            entry["metadata"] = metadata

        # Write to JSONL log
        try:
            if self._current_log_file is not None:
                with open(self._current_log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

        return {
            "entry": entry,
            "archived_image_path": archived_image_path,
            "log_file": str(self._current_log_file),
        }

    def get_recent_observations(self, count: int = 5) -> list[dict]:
        """
        Retrieve the most recent N observations.

        Returns:
            List of observation dicts, newest first.
        """
        self._update_paths()
        observations = []

        # Gather all log files, newest first
        log_files = sorted(self.log_dir.glob("bt_vision_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)

        for log_file in log_files:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if line:
                        observations.append(json.loads(line))
                        if len(observations) >= count:
                            return observations
            except Exception:
                continue

        return observations

    def get_today_summary(self) -> str:
        """
        Return a human-readable summary of today's observations.

        Returns:
            Formatted summary string.
        """
        self._update_paths()
        observations = self.get_recent_observations(count=50)
        today = datetime.now().strftime("%Y-%m-%d")
        today_obs = [o for o in observations if o.get("date") == today]

        if not today_obs:
            return f"No visual observations recorded for {today}."

        lines = [f"BT-7274 Visual Log — {today}", "=" * 40]
        for obs in reversed(today_obs):  # Oldest first
            time_str = obs.get("time", "??:??:??")
            trigger = obs.get("trigger", "unknown")
            desc = obs.get("description", "No description.")
            lines.append(f"\n[{time_str}] Trigger: {trigger}")
            lines.append(f"  {desc}")

        return "\n".join(lines)

    def get_observation_count_today(self) -> int:
        """Return number of observations logged today."""
        self._update_paths()
        if self._current_log_file is None or not self._current_log_file.exists():
            return 0
        try:
            with open(self._current_log_file, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def _cleanup_old_images(self):
        """Remove vision images older than _max_image_age_days and empty date folders."""
        import time as _time
        images_dir = self.log_dir / "images"
        if not images_dir.exists():
            return
        now = _time.time()
        cutoff = now - (self._max_image_age_days * 86400)
        for date_dir in sorted(images_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            try:
                # Check if directory is old enough to clean
                dir_mtime = date_dir.stat().st_mtime
                if dir_mtime < cutoff:
                    import shutil
                    shutil.rmtree(date_dir)
                else:
                    # Remove empty dirs even if recent
                    if not any(date_dir.iterdir()):
                        date_dir.rmdir()
            except Exception:
                pass
