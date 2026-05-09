#!/usr/bin/env python3
"""
Test script to verify error display in logs.
"""

import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bt7274.bt7274_workstation.interaction_logger import InteractionLogger

def test_error_display():
    """Test that errors are properly displayed in logs."""
    logger = InteractionLogger()
    
    # Simulate an error entry
    test_errors = [
        {
            "timestamp": "2026-04-25T10:30:45.123456",
            "component": "tts",
            "function": "speak",
            "error_type": "RuntimeError",
            "error_message": "Failed to initialize audio device",
            "traceback": "Traceback (most recent call last):\n  File \"test.py\", line 10, in <module>\n    raise RuntimeError('Failed to initialize audio device')\nRuntimeError: Failed to initialize audio device"
        },
        {
            "timestamp": "2026-04-25T10:31:22.654321",
            "component": "stt",
            "function": "transcribe",
            "error_type": "ValueError",
            "error_message": "Audio file is corrupted",
            "traceback": "Traceback (most recent call last):\n  File \"test.py\", line 15, in <module>\n    raise ValueError('Audio file is corrupted')\nValueError: Audio file is corrupted"
        }
    ]
    
    # Log a test interaction with errors
    logger.log_interaction(
        pilot_message="Test error display",
        bt_response="Testing error logging",
        interaction_type="test",
        ai_mode="local",
        performance_mode="standard",
        errors=test_errors
    )
    
    print("Test error entry added to logs.")
    print("Run 'python view_logs.py' to see the error display.")

if __name__ == "__main__":
    test_error_display()