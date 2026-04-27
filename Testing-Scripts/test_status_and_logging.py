#!/usr/bin/env python3
"""Test script for status query handling and enhanced logging fields."""

import sys
import json
from pathlib import Path

# Add the project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bt7274_assistant.pipeline import BT7274Assistant

def test_status_query_detection():
    """Test that status queries are properly detected."""
    print("Testing status query detection...")
    
    # Create a minimal assistant instance for testing
    assistant = BT7274Assistant.__new__(BT7274Assistant)
    
    # Test cases that should be detected as status queries
    status_queries = [
        "what is your status",
        "what's your status",
        "how are you",
        "how are you doing",
        "status report",
        "systems check",
        "systems status",
        "are you operational",
        "are you online",
        "are you functional",
        "how are your systems",
        "are you okay",
        "are you alright",
        "status update",
        "condition report",
    ]
    
    # Test cases that should NOT be detected as status queries
    non_status_queries = [
        "what is the weather",
        "tell me a joke",
        "what time is it",
        "search for something",
        "thank you",
    ]
    
    print("  Status queries (should all be True):")
    for query in status_queries:
        result = assistant._is_status_query(query)
        status = "✓" if result else "✗"
        print(f"    {status} '{query}' -> {result}")
        assert result, f"Failed to detect status query: {query}"
    
    print("  Non-status queries (should all be False):")
    for query in non_status_queries:
        result = assistant._is_status_query(query)
        status = "✓" if not result else "✗"
        print(f"    {status} '{query}' -> {result}")
        assert not result, f"False positive for status query: {query}"
    
    print("  ✓ All status query detection tests passed!")

def test_enhanced_metadata_fields():
    """Test that the enhanced metadata includes new fields."""
    print("\nTesting enhanced metadata fields...")
    
    # Read the pipeline.py file and check for the new fields
    pipeline_file = Path(__file__).parent.parent / "bt7274_assistant" / "pipeline.py"
    with open(pipeline_file, 'r') as f:
        content = f.read()
    
    # Check for new fields in enhanced_metadata
    required_fields = [
        '"clip_source": clip_source',
        '"clip_phrase": clip_phrase',
        '"tts_triggered": tts_success',
        '"bt_running": self.running',
    ]
    
    for field in required_fields:
        if field in content:
            print(f"  ✓ Found: {field}")
        else:
            print(f"  ✗ Missing: {field}")
            assert False, f"Missing field in enhanced_metadata: {field}"
    
    print("  ✓ All enhanced metadata fields present!")

def test_logger_fields():
    """Test that interaction_logger extracts new fields."""
    print("\nTesting interaction_logger fields...")
    
    logger_file = Path(__file__).parent.parent / "bt7274_assistant" / "interaction_logger.py"
    with open(logger_file, 'r') as f:
        content = f.read()
    
    # Check for new fields in logger
    required_fields = [
        '"clip_source"',
        '"clip_phrase"',
        '"tts_triggered"',
        '"bt_running"',
    ]
    
    for field in required_fields:
        if field in content:
            print(f"  ✓ Found: {field}")
        else:
            print(f"  ✗ Missing: {field}")
            assert False, f"Missing field in interaction_logger: {field}"
    
    print("  ✓ All logger fields present!")

def test_status_response_clip():
    """Test that status response clips are available."""
    print("\nTesting status response clip availability...")
    
    # Check if BT clips exist
    bt_clips_dir = Path(__file__).parent.parent / "BT-7274.Voicepack" / "bt_clips"
    
    expected_clips = [
        "044_Ready_to_proceed.wav",
        "070_Embark_when_ready.wav",
        "071_Please_embark_when_ready.wav",
        "101_Get_ready.wav",
        "102_My_systems_are_rebooting.wav",
        "106_Pilot_my_mapping_systems_have_been.wav",
        "319_Still_operational_but_unable_to_escape.wav",
        "086_Reinitializing_critical_systems.wav",
        "001_Standing_by_pilot_Climb_onto_my.wav",
    ]
    
    found = 0
    for clip in expected_clips:
        clip_path = bt_clips_dir / clip
        if clip_path.exists():
            found += 1
            print(f"  ✓ Found: {clip}")
        else:
            print(f"  ⚠ Missing: {clip}")
    
    print(f"  Found {found}/{len(expected_clips)} status clips")
    assert found > 0, "No status clips found!"
    print("  ✓ Status clips available!")

if __name__ == "__main__":
    print("=" * 60)
    print("BT-7274 Status Query & Enhanced Logging Test")
    print("=" * 60)
    
    test_status_query_detection()
    test_enhanced_metadata_fields()
    test_logger_fields()
    test_status_response_clip()
    
    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
    print("\nSummary of changes:")
    print("1. Status queries now trigger BT-7274 original voice clips")
    print("2. Enhanced metadata includes clip_source and clip_phrase")
    print("3. Enhanced metadata includes tts_triggered and bt_running")
    print("4. Interaction logger extracts and logs all new fields")
