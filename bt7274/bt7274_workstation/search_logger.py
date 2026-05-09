"""
Search Logger for BT-7274 Voice Assistant.

Logs all internet searches performed by BT-7274 with timestamps,
storing them in daily JSONL files under the logs/bt_memory/ directory.
"""

import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from bt7274.bt7274_workstation.log_manager import get_bt_memory_dir, daily_jsonl_path, append_jsonl


class SearchLogger:
    """Logger for internet searches performed by BT-7274."""

    def __init__(self, log_dir: str | None = None):
        if log_dir is None:
            log_dir = str(get_bt_memory_dir())
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_file = None
        self._update_current_file()
        # Deduplication: keep hashes of last 50 queries to prevent duplicates
        self._recent_hashes: set[str] = set()
        self._max_recent_hashes = 50

    def _get_query_hash(self, query: str) -> str:
        """Generate a hash for deduplication based on query content."""
        content = query.strip().lower()
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]

    def _is_duplicate(self, query_hash: str) -> bool:
        """Check if this query was recently logged (prevents duplicates)."""
        if query_hash in self._recent_hashes:
            return True
        self._recent_hashes.add(query_hash)
        if len(self._recent_hashes) > self._max_recent_hashes:
            self._recent_hashes = set(list(self._recent_hashes)[-self._max_recent_hashes:])
        return False

    def _update_current_file(self):
        """Update the current log file based on today's date."""
        self.current_file = daily_jsonl_path(self.log_dir, "bt_logs")

    def log_search(
        self,
        query: str,
        results: str,
        success: bool = True,
        error_message: Optional[str] = None,
        response_time: Optional[float] = None,
    ):
        """Log a single search performed by BT-7274."""
        self._update_current_file()

        # Deduplication check
        query_hash = self._get_query_hash(query)
        if self._is_duplicate(query_hash):
            return  # Skip duplicate search

        now = datetime.now()
        entry = {
            "timestamp": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "query": query,
            "results": results,
            "success": success,
        }

        if error_message:
            entry["error_message"] = error_message
        if response_time is not None:
            entry["response_time"] = round(response_time, 3)

        if self.current_file is None:
            return
        append_jsonl(self.current_file, entry)

    def get_today_log(self) -> list:
        """Get all searches from today."""
        self._update_current_file()
        if self.current_file is None or not self.current_file.exists():
            return []

        searches = []
        with open(self.current_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    searches.append(json.loads(line))
        return searches

    def get_log_files(self) -> list:
        """Get all search log files sorted by date (oldest first)."""
        return sorted(self.log_dir.glob("bt_logs_*.jsonl"))