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
    """Display comprehensive summary statistics with enhanced formatting."""
    summary = logger.get_log_summary(days=30)
    
    # Collect all entries for detailed analysis
    all_entries = []
    files = logger.get_log_files()
    for log_file in files:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    all_entries.append(json.loads(line))
    
    print("\n" + "=" * 60)
    print("BT-7274 INTERACTION LOG SUMMARY")
    print("=" * 60)
    
    # ── Basic Stats ──
    print("\n📊 BASIC STATISTICS")
    print("-" * 40)
    print(f"  Log Directory:      {summary['log_directory']}")
    print(f"  Total Log Files:    {summary['total_log_files']}")
    print(f"  Total Interactions: {summary['total_interactions']}")
    
    if summary['total_log_files'] > 0:
        avg_per_day = summary['total_interactions'] / summary['total_log_files']
        print(f"  Avg. Per Day:       {avg_per_day:.1f}")
    
    # Activity level
    if summary['total_interactions'] > 100:
        activity_level = "🔥 VERY HIGH"
    elif summary['total_interactions'] > 50:
        activity_level = "⚡ HIGH"
    elif summary['total_interactions'] > 20:
        activity_level = "📈 MODERATE"
    else:
        activity_level = "💤 LOW"
    print(f"  Activity Level:     {activity_level}")
    
    if not all_entries:
        print("\n  No interactions recorded yet.")
        print("=" * 60)
        return
    
    # ── AI Mode Distribution ──
    ai_modes = {}
    for entry in all_entries:
        mode = entry.get("ai_mode", "unknown")
        ai_modes[mode] = ai_modes.get(mode, 0) + 1
    
    if ai_modes:
        print("\n🤖 AI MODE DISTRIBUTION")
        print("-" * 40)
        for mode, count in sorted(ai_modes.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            print(f"  {mode.title():12} {count:4} ({pct:5.1f}%) {bar}")
    
    # ── Performance Mode Distribution ──
    perf_modes = {}
    for entry in all_entries:
        mode = entry.get("performance_mode", "unknown")
        perf_modes[mode] = perf_modes.get(mode, 0) + 1
    
    if perf_modes:
        print("\n⚡ PERFORMANCE MODE DISTRIBUTION")
        print("-" * 40)
        for mode, count in sorted(perf_modes.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            print(f"  {mode.title():12} {count:4} ({pct:5.1f}%) {bar}")
    
    # ── Cache Hit Statistics ──
    cache_hits = {}
    for entry in all_entries:
        cache = entry.get("cache_hit")
        if cache:
            cache_hits[cache] = cache_hits.get(cache, 0) + 1
    
    if cache_hits:
        print("\n💾 CACHE USAGE")
        print("-" * 40)
        for cache_type, count in sorted(cache_hits.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            display = cache_type.replace("_", " ").title()
            print(f"  {display:20} {count:4} ({pct:5.1f}%) {bar}")
    
    # ── Clip Source Distribution ──
    clip_sources = {}
    for entry in all_entries:
        source = entry.get("clip_source")
        if source:
            clip_sources[source] = clip_sources.get(source, 0) + 1
    
    if clip_sources:
        print("\n🎙️ CLIP SOURCE DISTRIBUTION")
        print("-" * 40)
        for source, count in sorted(clip_sources.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            display = source.replace("_", " ").title()
            print(f"  {display:20} {count:4} ({pct:5.1f}%) {bar}")
    
    # ── TTS Trigger Rate ──
    tts_triggered = sum(1 for e in all_entries if e.get("tts_triggered") is True)
    tts_not_triggered = sum(1 for e in all_entries if e.get("tts_triggered") is False)
    tts_unknown = len(all_entries) - tts_triggered - tts_not_triggered
    
    print("\n🔊 TTS TRIGGER RATE")
    print("-" * 40)
    if tts_triggered + tts_not_triggered > 0:
        rate = tts_triggered / (tts_triggered + tts_not_triggered) * 100
        print(f"  Triggered:    {tts_triggered:4} ({rate:5.1f}%)")
        print(f"  Not Triggered: {tts_not_triggered:4}")
    if tts_unknown > 0:
        print(f"  Unknown:      {tts_unknown:4}")
    
    # ── BT Running State ──
    bt_running = sum(1 for e in all_entries if e.get("bt_running") is True)
    bt_not_running = sum(1 for e in all_entries if e.get("bt_running") is False)
    
    print("\n🤖 BT RUNNING STATE")
    print("-" * 40)
    if bt_running + bt_not_running > 0:
        running_pct = bt_running / (bt_running + bt_not_running) * 100
        print(f"  Running:     {bt_running:4} ({running_pct:5.1f}%)")
        print(f"  Not Running: {bt_not_running:4}")
    
    # ── Protocol Distribution ──
    protocols = {}
    for entry in all_entries:
        protocol = entry.get("protocol_reference")
        if protocol:
            protocols[protocol] = protocols.get(protocol, 0) + 1
    
    if protocols:
        print("\n📜 PROTOCOL DISTRIBUTION")
        print("-" * 40)
        for protocol, count in sorted(protocols.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            print(f"  {count:4} ({pct:5.1f}%) {bar}  {protocol}")
    
    # ── Trust Level Stats ──
    trust_levels = [e.get("pilot_trust_level", 1) for e in all_entries if e.get("pilot_trust_level")]
    if trust_levels:
        avg_trust = sum(trust_levels) / len(trust_levels)
        max_trust = max(trust_levels)
        min_trust = min(trust_levels)
        print("\n🤝 PILOT TRUST LEVEL")
        print("-" * 40)
        print(f"  Average: {avg_trust:.1f}/5")
        print(f"  Range:   {min_trust} - {max_trust}")
        trust_bar = "█" * int(avg_trust) + "░" * (5 - int(avg_trust))
        print(f"  Visual:  [{trust_bar}]")
    
    # ── Action Type Distribution ──
    action_counts = {}
    for entry in all_entries:
        actions = entry.get("actions_executed", [])
        if actions:
            for action in actions:
                action_counts[action] = action_counts.get(action, 0) + 1
    
    if action_counts:
        print("\n⚙️ ACTIONS EXECUTED")
        print("-" * 40)
        for action, count in sorted(action_counts.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            print(f"  {action.title():20} {count:4} ({pct:5.1f}%) {bar}")
    
    # ── Match Type Distribution ──
    match_types = {}
    for entry in all_entries:
        match = entry.get("match_type")
        if match:
            match_types[match] = match_types.get(match, 0) + 1
    
    if match_types:
        print("\n🎯 MATCH TYPE DISTRIBUTION")
        print("-" * 40)
        for match, count in sorted(match_types.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            print(f"  {match.title():20} {count:4} ({pct:5.1f}%) {bar}")
    
    # ── Match Score Stats ──
    match_scores = [e.get("match_score", 0) for e in all_entries if e.get("match_score") is not None]
    if match_scores:
        avg_score = sum(match_scores) / len(match_scores)
        max_score = max(match_scores)
        min_score = min(match_scores)
        print("\n📊 MATCH SCORE STATISTICS")
        print("-" * 40)
        print(f"  Average: {avg_score:.3f}")
        print(f"  Best:    {max_score:.3f}")
        print(f"  Worst:   {min_score:.3f}")
    
    # ── Emotion Distribution ──
    emotions = {}
    for entry in all_entries:
        emotion = entry.get("emotion_detected")
        if emotion:
            emotions[emotion] = emotions.get(emotion, 0) + 1
    
    if emotions:
        print("\n😊 EMOTION DETECTED (BT)")
        print("-" * 40)
        for emotion, count in sorted(emotions.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            print(f"  {emotion.title():20} {count:4} ({pct:5.1f}%) {bar}")
    
    # ── User Emotion Distribution ──
    user_emotions = {}
    for entry in all_entries:
        emotion = entry.get("user_emotion")
        if emotion:
            user_emotions[emotion] = user_emotions.get(emotion, 0) + 1
    
    if user_emotions:
        print("\n👤 USER EMOTION DETECTED")
        print("-" * 40)
        for emotion, count in sorted(user_emotions.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            print(f"  {emotion.title():20} {count:4} ({pct:5.1f}%) {bar}")
    
    # ── Context Topic Distribution ──
    topics = {}
    for entry in all_entries:
        topic = entry.get("context_topic")
        if topic:
            topics[topic] = topics.get(topic, 0) + 1
    
    if topics:
        print("\n📍 CONTEXT TOPIC DISTRIBUTION")
        print("-" * 40)
        for topic, count in sorted(topics.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            print(f"  {topic.title():20} {count:4} ({pct:5.1f}%) {bar}")
    
    # ── Dialogue State Distribution ──
    dialogue_states = {}
    for entry in all_entries:
        state = entry.get("dialogue_state")
        if state:
            dialogue_states[state] = dialogue_states.get(state, 0) + 1
    
    if dialogue_states:
        print("\n🌳 DIALOGUE STATE DISTRIBUTION")
        print("-" * 40)
        for state, count in sorted(dialogue_states.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            print(f"  {state.title():20} {count:4} ({pct:5.1f}%) {bar}")
    
    # ── Wake Word Distribution ──
    wake_words = {}
    for entry in all_entries:
        ww = entry.get("wake_word")
        if ww:
            wake_words[ww] = wake_words.get(ww, 0) + 1
    
    if wake_words:
        print("\n🔔 WAKE WORD USAGE")
        print("-" * 40)
        for ww, count in sorted(wake_words.items(), key=lambda x: -x[1]):
            pct = count / len(all_entries) * 100
            bar = "█" * int(pct / 5)
            print(f"  '{ww}' {count:4} ({pct:5.1f}%) {bar}")
    
    # ── STT Confidence Stats ──
    stt_confs = [e.get("stt_confidence", 0) for e in all_entries if e.get("stt_confidence") is not None]
    if stt_confs:
        avg_conf = sum(stt_confs) / len(stt_confs)
        max_conf = max(stt_confs)
        min_conf = min(stt_confs)
        print("\n🎤 SPEECH RECOGNITION CONFIDENCE")
        print("-" * 40)
        print(f"  Average: {avg_conf:.1%}")
        print(f"  Best:    {max_conf:.1%}")
        print(f"  Worst:   {min_conf:.1%}")
        # Quality distribution
        high = sum(1 for c in stt_confs if c > 0.8)
        med = sum(1 for c in stt_confs if 0.5 < c <= 0.8)
        low = sum(1 for c in stt_confs if c <= 0.5)
        print(f"  High (>80%):  {high:3}")
        print(f"  Med (50-80%): {med:3}")
        print(f"  Low (<50%):   {low:3}")
    
    # ── Response Time Stats ──
    response_times = [e.get("llm_response_time", 0) for e in all_entries if e.get("llm_response_time") is not None]
    if response_times:
        avg_rt = sum(response_times) / len(response_times)
        max_rt = max(response_times)
        min_rt = min(response_times)
        print("\n⏱️ LLM RESPONSE TIME")
        print("-" * 40)
        print(f"  Average: {avg_rt:.2f}s")
        print(f"  Slowest: {max_rt:.2f}s")
        print(f"  Fastest: {min_rt:.2f}s")
        # Speed distribution
        fast = sum(1 for t in response_times if t < 2.0)
        med = sum(1 for t in response_times if 2.0 <= t < 5.0)
        slow = sum(1 for t in response_times if t >= 5.0)
        print(f"  Fast (<2s):  {fast:3}")
        print(f"  Med (2-5s):  {med:3}")
        print(f"  Slow (>5s):  {slow:3}")
    
    # ── Conversation Duration Stats ──
    durations = [e.get("conversation_duration", 0) for e in all_entries if e.get("conversation_duration") is not None]
    if durations:
        avg_dur = sum(durations) / len(durations)
        max_dur = max(durations)
        min_dur = min(durations)
        print("\n⏳ CONVERSATION DURATION")
        print("-" * 40)
        print(f"  Average: {avg_dur:.1f}s")
        print(f"  Longest: {max_dur:.1f}s")
        print(f"  Shortest: {min_dur:.1f}s")
    
    # ── Mission Elapsed Time Stats ──
    met_values = [e.get("mission_elapsed_time", 0) for e in all_entries if e.get("mission_elapsed_time") is not None]
    if met_values:
        avg_met = sum(met_values) / len(met_values)
        max_met = max(met_values)
        print("\n🚀 MISSION ELAPSED TIME")
        print("-" * 40)
        print(f"  Average: {avg_met:.1f}s")
        print(f"  Longest: {max_met:.1f}s")
    
    # ── Error Statistics ──
    error_count = sum(len(e.get("errors", [])) for e in all_entries)
    entries_with_errors = sum(1 for e in all_entries if e.get("errors"))
    
    print("\n⚠️ ERROR STATISTICS")
    print("-" * 40)
    print(f"  Total Errors:       {error_count}")
    print(f"  Entries w/ Errors:  {entries_with_errors}")
    if all_entries:
        error_rate = entries_with_errors / len(all_entries) * 100
        print(f"  Error Rate:         {error_rate:.1f}%")
    
    # Error type breakdown
    error_types = {}
    for entry in all_entries:
        for error in entry.get("errors", []):
            err_type = error.get("error_type", "Unknown")
            error_types[err_type] = error_types.get(err_type, 0) + 1
    
    if error_types:
        print("\n  Error Type Breakdown:")
        for err_type, count in sorted(error_types.items(), key=lambda x: -x[1]):
            print(f"    {err_type}: {count}")
    
    # ── Follow-up Depth Stats ──
    follow_ups = [e.get("follow_up_depth", 0) for e in all_entries if e.get("follow_up_depth", 0) > 0]
    if follow_ups:
        avg_depth = sum(follow_ups) / len(follow_ups)
        max_depth = max(follow_ups)
        print("\n🔄 FOLLOW-UP CONVERSATIONS")
        print("-" * 40)
        print(f"  Follow-up Turns: {len(follow_ups)}")
        print(f"  Average Depth:   {avg_depth:.1f}")
        print(f"  Max Depth:       {max_depth}")
    
    # ── Session Statistics ──
    sessions = {}
    for entry in all_entries:
        sid = entry.get("session_id")
        if sid:
            sessions[sid] = sessions.get(sid, 0) + 1
    
    if sessions:
        print("\n📅 SESSION STATISTICS")
        print("-" * 40)
        print(f"  Total Sessions:    {len(sessions)}")
        avg_per_session = len(all_entries) / len(sessions)
        print(f"  Avg. Per Session:  {avg_per_session:.1f}")
        max_session = max(sessions.values())
        print(f"  Largest Session:   {max_session} interactions")
    
    # ── Location Context ──
    locations = {}
    for entry in all_entries:
        loc = entry.get("location_context")
        if loc:
            locations[loc] = locations.get(loc, 0) + 1
    
    if locations:
        print("\n📍 LOCATIONS RECORDED")
        print("-" * 40)
        for loc, count in sorted(locations.items(), key=lambda x: -x[1])[:5]:
            print(f"  {loc}: {count}x")
    
    # ── Most Recent Activity ──
    if all_entries:
        latest = max(all_entries, key=lambda e: e.get("timestamp", ""))
        latest_time = latest.get("timestamp", "Unknown")
        if "T" in latest_time:
            latest_time = latest_time.split("T")[1].split(".")[0]
        print("\n🕐 MOST RECENT ACTIVITY")
        print("-" * 40)
        print(f"  Time:     {latest_time}")
        print(f"  Pilot:    {latest.get('pilot_message', 'N/A')}")
        print(f"  BT-7274:  {latest.get('bt_response', 'N/A')[:50]}...")
    
    print("\n" + "=" * 60)


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
