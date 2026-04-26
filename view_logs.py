#!/usr/bin/env python3
"""
View BT-7274 interaction logs.

Usage:
    python view_logs.py              # Show today's interactions
    python view_logs.py --all        # Show all log files
    python view_logs.py --summary    # Show summary statistics
    python view_logs.py --date 2026-04-24  # Show specific date
    python view_logs.py --logs       # Show all logs content
"""

import argparse
import json
from pathlib import Path
from datetime import datetime

from bt7274_assistant.interaction_logger import InteractionLogger


def format_entry(entry: dict) -> str:
    """Format a single log entry for display with enhanced styling."""
    timestamp = entry.get("timestamp", "??:??:??")
    # Extract time portion from ISO timestamp
    if "T" in timestamp:
        time_part = timestamp.split("T")[1].split(".")[0]  # HH:MM:SS format
    else:
        time_part = timestamp
    
    pilot = entry.get("pilot_message", "")
    bt = entry.get("bt_response", "")
    ai_mode = entry.get("ai_mode", "local")
    perf_mode = entry.get("performance_mode", "standard")
    
    # ── Header with enhanced styling ──
    lines = [
        "",
        "+" + "-" * 60 + "+",
        f"| Time: {time_part}  |  Type: {entry.get('interaction_type', 'voice').upper()}",
        f"| AI Mode: {ai_mode.title()}  |  TTS Mode: {perf_mode.title()}",
    ]
    
    # ── TTS Metrics ──
    tts = entry.get("tts_metrics", {})
    audio_file_path = entry.get("audio_file_path")
    if tts or audio_file_path:
        lines.append("+" + "-" * 60 + "+")
        if audio_file_path == "streaming":
            lines.append("| TTS: Streaming playback")
        elif audio_file_path and audio_file_path != "streaming":
            lines.append(f"| TTS: Played audio file ({Path(audio_file_path).name})")
        elif tts.get("cached"):
            lines.append("| TTS: Cached response")
        elif tts.get("mode") == "streaming":
            synth = tts.get("sentences_synthesized", 0)
            played = tts.get("sentences_played", 0)
            proc = tts.get("processing_time", 0)
            lines.append(f"| TTS: Streaming ({synth} synthesized, {played} played in {proc:.2f}s)")
        elif tts:
            proc = tts.get("processing_time", 0)
            rtf = tts.get("real_time_factor", 0)
            lines.append(f"| TTS: Standard mode ({proc:.2f}s, RTF: {rtf:.2f}x)")
        else:
            lines.append("| TTS: No audio output")
    
    # ── Conversation with better formatting ──
    lines.extend([
        "+" + "-" * 60 + "+",
        f"| Pilot:    {pilot}",
        "|",
        f"| BT-7274:  {bt}",
    ])
    
    # ── Technical Details ──
    details = []
    
    # LLM response time
    llm_time = entry.get("llm_response_time")
    if llm_time is not None:
        # Indicator based on response time
        if llm_time < 2.0:
            time_indicator = "[FAST]"  
        elif llm_time < 5.0:
            time_indicator = "[MED]"  
        else:
            time_indicator = "[SLOW]"
        details.append(f"| Response Time: {llm_time:.2f}s {time_indicator}")
    
    # STT confidence
    stt_conf = entry.get("stt_confidence")
    if stt_conf is not None:
        # Indicator based on confidence
        if stt_conf > 0.8:
            conf_indicator = "[HIGH]"
        elif stt_conf > 0.5:
            conf_indicator = "[MED]"
        else:
            conf_indicator = "[LOW]"
        details.append(f"| Speech Confidence: {stt_conf:.1%} {conf_indicator}")
    
    # Cache hit
    cache = entry.get("cache_hit")
    if cache:
        cache_display = cache.replace("_", " ").title()
        details.append(f"| Cache Used: {cache_display}")
    
    # Audio file
    audio = entry.get("audio_file_path")
    if audio and audio != "streaming":
        details.append(f"| Audio File: {Path(audio).name}")
    elif audio == "streaming":
        details.append("| Audio: Streaming playback")
    
    # Session Info
    session = entry.get("session_id")
    if session:
        details.append(f"| Session ID: {session}")
    
    # Follow-up depth
    depth = entry.get("follow_up_depth", 0)
    if depth > 0:
        details.append(f"| Follow-up Turn: {depth}")
    
    # Protocol
    protocol = entry.get("protocol_reference")
    if protocol:
        details.append(f"| {protocol}")
    
    # Trust level
    trust = entry.get("pilot_trust_level")
    if trust:
        # Visual representation of trust level
        trust_bars = "#" * trust + "." * (5 - trust)
        details.append(f"| Pilot Trust Level: {trust_bars} ({trust}/5)")
    
    # Mission elapsed time
    met = entry.get("mission_elapsed_time")
    if met is not None:
        hours = int(met // 3600)
        mins = int((met % 3600) // 60)
        secs = int(met % 60)
        parts = []
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if mins > 0:
            parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
        if secs > 0 or not parts:
            parts.append(f"{secs} second{'s' if secs != 1 else ''}")
        details.append(f"| Mission Time: {', '.join(parts)}")
    
    # Actions executed
    actions = entry.get("actions_executed")
    if actions:
        action_names = [a.title() for a in actions]
        details.append(f"| Actions Executed: {', '.join(action_names)}")
    
    # Location context
    loc = entry.get("location_context")
    if loc:
        details.append(f"| Location: {loc}")
    
    # Weather context
    weather = entry.get("weather_context")
    if weather:
        # Truncate long weather strings
        weather_str = str(weather)
        if len(weather_str) > 60:
            weather_str = weather_str[:57] + "..."
        details.append(f"| Weather Data: {weather_str}")
    
    # Errors
    errors = entry.get("errors")
    if errors:
        details.append(f"| Session Errors: {len(errors)}")
        # Show error details - show all errors but limit message length
        for i, error in enumerate(errors, 1):
            error_type = error.get("error_type", "Unknown")
            error_msg = error.get("error_message", "No message")
            component = error.get("component", "Unknown")
            function = error.get("function", "Unknown")
            timestamp = error.get("timestamp", "")[-8:] if error.get("timestamp") else ""
            details.append(f"|   Error {i}: [{timestamp}] {error_type} in {component}.{function}")
            # Truncate long error messages
            if len(error_msg) > 80:
                error_msg = error_msg[:77] + "..."
            details.append(f"|     Message: {error_msg}")
            # Show context if available
            context = error.get("context")
            if context:
                context_str = str(context)
                if len(context_str) > 80:
                    context_str = context_str[:77] + "..."
                details.append(f"|     Context: {context_str}")
    
    # Add details section if any exist
    if details:
        lines.append("+" + "-" * 60 + "+")
        lines.extend(details)
    
    lines.append("+" + "-" * 60 + "+")
    
    return "\n".join(lines)


def show_today(logger: InteractionLogger):
    """Display today's interactions with enhanced formatting."""
    interactions = logger.get_today_log()
    if not interactions:
        print("No interactions logged today.")
        return

    today_str = datetime.now().strftime('%Y-%m-%d')
    print(f"\n" + "=" * 60)
    print(f"BT-7274 Interaction Log — {today_str}")
    print("=" * 60)
    print(f"{len(interactions)} interaction(s) recorded today\n")
    
    for i, entry in enumerate(interactions, 1):
        print(f"Entry #{i}")
        print(format_entry(entry))
        if i < len(interactions):  # Add spacing between entries
            print()


def show_all(logger: InteractionLogger):
    """Display all interactions from all log files with enhanced formatting."""
    files = logger.get_log_files()
    if not files:
        print("No log files found.")
        return

    total = 0
    print(f"\n" + "=" * 60)
    print("ALL INTERACTION LOGS")
    print("=" * 60)
    
    for log_file in files:
        date_str = log_file.stem.replace("bt7274_interactions_", "")
        with open(log_file, "r", encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
            
        print(f"\nDate: {date_str}")
        print(f"Entries: {len(entries)}")
        print("-" * 40)
        
        if entries:
            total += len(entries)
            for i, entry in enumerate(entries, 1):
                print(f"Entry #{i}")
                print(format_entry(entry))
                if i < len(entries):  # Add spacing between entries
                    print()
        else:
            print("No interactions recorded this day.")

    print(f"\n" + "=" * 60)
    print(f"Total interactions across all logs: {total}")
    print("=" * 60)


def show_summary(logger: InteractionLogger):
    """Display summary statistics with enhanced formatting."""
    summary = logger.get_log_summary(days=30)
    
    print("\n" + "=" * 60)
    print("BT-7274 Interaction Log Summary")
    print("=" * 60)
    
    # Header
    print(f"Log Directory:     {summary['log_directory']}")
    print(f"Total Log Files:   {summary['total_log_files']}")
    print(f"Total Interactions: {summary['total_interactions']}")
    
    # Daily average
    if summary['total_log_files'] > 0:
        avg_per_day = summary['total_interactions'] / summary['total_log_files']
        print(f"Avg. Per Day:      {avg_per_day:.1f}")
    
    # Recent activity indicator
    if summary['total_interactions'] > 100:
        activity_level = "[VERY HIGH]"
    elif summary['total_interactions'] > 50:
        activity_level = "[HIGH]"
    elif summary['total_interactions'] > 20:
        activity_level = "[MODERATE]"
    else:
        activity_level = "[LOW]"
    
    print(f"Activity Level:    {activity_level}")
    
    print("=" * 60)


def show_date(logger: InteractionLogger, date_str: str):
    """Display interactions for a specific date with enhanced formatting."""
    log_file = logger.log_dir / f"bt7274_interactions_{date_str}.jsonl"
    if not log_file.exists():
        print(f"No log file found for {date_str}.")
        return

    with open(log_file, "r", encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    print(f"\n" + "=" * 60)
    print(f"BT-7274 Interaction Log — {date_str}")
    print("=" * 60)
    print(f"{len(entries)} interaction(s) recorded\n")
    
    for i, entry in enumerate(entries, 1):
        print(f"Entry #{i}")
        print(format_entry(entry))
        if i < len(entries):  # Add spacing between entries
            print()


def show_logs_content(logger: InteractionLogger):
    """Display content of all log files with enhanced formatting."""
    files = logger.get_log_files()
    if not files:
        print("No log files found.")
        return

    total = 0
    print(f"\n" + "=" * 60)
    print("COMPLETE LOG CONTENT")
    print("=" * 60)
    
    # Sort files by date (newest first)
    sorted_files = sorted(files, reverse=True)
    
    for log_file in sorted_files:
        date_str = log_file.stem.replace("bt7274_interactions_", "")
        with open(log_file, "r", encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
            
        if entries:  # Only show dates with content
            print(f"\n--- {date_str} ---")
            total += len(entries)
            for i, entry in enumerate(entries, 1):
                # Simplified format for log content view
                timestamp = entry.get("timestamp", "??:??:??")
                if "T" in timestamp:
                    time_part = timestamp.split("T")[1].split(".")[0]
                else:
                    time_part = timestamp
                
                pilot = entry.get("pilot_message", "")
                bt = entry.get("bt_response", "")
                
                print(f"[{time_part}] Pilot: {pilot}")
                print(f"          BT-7274: {bt}")
                print()
    
    print(f"Total interactions across all logs: {total}")


def main():
    parser = argparse.ArgumentParser(description="View BT-7274 interaction logs")
    parser.add_argument("--all", action="store_true", help="Show all log files")
    parser.add_argument("--summary", action="store_true", help="Show summary statistics")
    parser.add_argument("--date", type=str, help="Show logs for a specific date (YYYY-MM-DD)")
    parser.add_argument("--logs", action="store_true", help="Show all logs content")
    args = parser.parse_args()

    logger = InteractionLogger()

    if args.summary:
        show_summary(logger)
    elif args.all:
        show_all(logger)
    elif args.logs:
        show_logs_content(logger)
    elif args.date:
        show_date(logger, args.date)
    else:
        show_today(logger)


if __name__ == "__main__":
    main()
