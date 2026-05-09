#!/usr/bin/env python3
"""
Test script to verify enhanced logging features
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bt7274.bt7274_workstation.interaction_logger import InteractionLogger

def test_enhanced_logging():
    """Test that enhanced logging fields are properly captured."""
    print("Testing Enhanced Logging Features")
    print("=" * 60)
    
    # Create a test logger
    test_log_dir = Path(__file__).parent.parent.parent / "logs" / "test"
    logger = InteractionLogger(log_dir=str(test_log_dir))
    
    # Simulate an interaction with enhanced metadata
    test_metadata = {
        "handled_types": ["weather"],
        "match_type": "semantic",
        "match_score": 0.85,
        "personality_weights": {
            "loyalty": 0.9,
            "formality": 0.8,
            "tactical": 0.85,
            "humor": 0.3,
            "urgency": 0.5
        },
        "dialogue_state": "mission_brief",
        "emotion_detected": "determined",
        "context_topic": "weather",
        "user_emotion": "neutral",
        "conversation_history_length": 5,
        "semantic_similarity_available": True,
    }
    
    # Log the interaction
    logger.log_interaction(
        pilot_message="What's the weather like today?",
        bt_response="Current conditions are clear, Pilot.",
        interaction_type="voice",
        ai_mode="local",
        performance_mode="standard",
        cache_hit="standby_clip",
        session_id="test123",
        protocol_reference="Protocol 2: Uphold the Mission",
        pilot_trust_level=3,
        actions_executed=["weather"],
        metadata=test_metadata,
    )
    
    # Read back the log
    interactions = logger.get_today_log()
    
    if not interactions:
        print("✗ No interactions logged")
        return False
    
    last_interaction = interactions[-1]
    
    print("\nLogged Interaction:")
    print(json.dumps(last_interaction, indent=2))
    
    # Verify enhanced fields
    checks = [
        ("match_type", "semantic"),
        ("match_score", 0.85),
        ("dialogue_state", "mission_brief"),
        ("emotion_detected", "determined"),
        ("context_topic", "weather"),
        ("user_emotion", "neutral"),
    ]
    
    print("\nVerification:")
    all_passed = True
    for field, expected in checks:
        actual = last_interaction.get(field)
        if actual == expected:
            print(f"  ✓ {field}: {actual}")
        else:
            print(f"  ✗ {field}: expected {expected}, got {actual}")
            all_passed = False
    
    # Check personality weights
    if "personality_weights" in last_interaction:
        weights = last_interaction["personality_weights"]
        print(f"  ✓ personality_weights: {weights}")
    else:
        print("  ✗ personality_weights not found")
        all_passed = False
    
    # Cleanup
    import shutil
    if test_log_dir.exists():
        shutil.rmtree(test_log_dir)
    
    if all_passed:
        print("\n✓ All enhanced logging fields verified!")
        return True
    else:
        print("\n✗ Some checks failed")
        return False

if __name__ == "__main__":
    success = test_enhanced_logging()
    sys.exit(0 if success else 1)