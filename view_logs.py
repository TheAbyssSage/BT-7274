#!/usr/bin/env python3
"""
View BT-7274 interaction logs.

Usage:
    python view_logs.py              # Show today's interactions
    python view_logs.py --all        # Show all log files
    python view_logs.py --summary    # Show summary statistics
    python view_logs.py --date 2026-04-24  # Show specific date
"""

import argparse
import json
from pathlib import Path
from datetime import datetime

from bt7274_assistant.interaction_logger import InteractionLogger


def format_entry(entry: dict) -> str:
    """Format a single log entry for display."""
    timestamp = entry.get("time", "??:??:??")
    pilot = entry.get("pilot_message", "")
    bt = entry.get("bt_response", "")
    ai_mode = entry.get("ai_mode", "local")
    perf_mode = entry.get("performance_mode", "standard")
    tts = entry.get("tts_metrics", {})
    tts_line = ""
    if tts:
        if tts.get("cached"):
            tts_line = "│ TTS: ♻️ cached"
        elif tts.get("mode") == "streaming":
            synth = tts.get("sentences_synthesized", 0)
            played = tts.get("sentences_played", 0)
            proc = tts.get("processing_time", 0)
            tts_line = f"│ TTS: ⚡ streaming | {synth}synth {played}played | {proc:.2f}s"
        else:
            proc = tts.get("processing_time", 0)
            rtf = tts.get("real_time_factor", 0)
            tts_line = f"│ TTS: ⏱ {proc:.2f}s | RTF {rtf:.2f}x"
    return f"""
┌─────────────────────────────────────────
│ {timestamp}  —  {entry.get('interaction_type', 'voice').upper()}
│ AI: {ai_mode.upper():<8}  │  TTS: {perf_mode.upper()}
{tts_line}
├─────────────────────────────────────────
│ Pilot:    {pilot}
│
│ BT-7274:  {bt}
└─────────────────────────────────────────"""


def show_today(logger: InteractionLogger):
    """Display today's interactions."""
    interactions = logger.get_today_log()
    if not interactions:
        print("No interactions logged today.")
        return

    print(f"\n📋 BT-7274 Interaction Log — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"   {len(interactions)} interaction(s) recorded\n")
    for entry in interactions:
        print(format_entry(entry))


def show_all(logger: InteractionLogger):
    """Display all interactions from all log files."""
    files = logger.get_log_files()
    if not files:
        print("No log files found.")
        return

    total = 0
    for log_file in files:
        date_str = log_file.stem.replace("bt7274_interactions_", "")
        print(f"\n{'='*50}")
        print(f"📅 {date_str}")
        print(f"{'='*50}")

        with open(log_file, "r", encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
            total += len(entries)
            for entry in entries:
                print(format_entry(entry))

    print(f"\n📊 Total interactions across all logs: {total}")


def show_summary(logger: InteractionLogger):
    """Display summary statistics."""
    summary = logger.get_log_summary(days=30)
    print("\n📊 BT-7274 Interaction Log Summary")
    print(f"   Log directory: {summary['log_directory']}")
    print(f"   Total log files: {summary['total_log_files']}")
    print(f"   Total interactions: {summary['total_interactions']}")


def show_date(logger: InteractionLogger, date_str: str):
    """Display interactions for a specific date."""
    log_file = logger.log_dir / f"bt7274_interactions_{date_str}.jsonl"
    if not log_file.exists():
        print(f"No log file found for {date_str}.")
        return

    with open(log_file, "r", encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    print(f"\n📋 BT-7274 Interaction Log — {date_str}")
    print(f"   {len(entries)} interaction(s) recorded\n")
    for entry in entries:
        print(format_entry(entry))


def main():
    parser = argparse.ArgumentParser(description="View BT-7274 interaction logs")
    parser.add_argument("--all", action="store_true", help="Show all log files")
    parser.add_argument("--summary", action="store_true", help="Show summary statistics")
    parser.add_argument("--date", type=str, help="Show logs for a specific date (YYYY-MM-DD)")
    args = parser.parse_args()

    logger = InteractionLogger()

    if args.summary:
        show_summary(logger)
    elif args.all:
        show_all(logger)
    elif args.date:
        show_date(logger, args.date)
    else:
        show_today(logger)


if __name__ == "__main__":
    main()
