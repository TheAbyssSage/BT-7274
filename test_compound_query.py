#!/usr/bin/env python3
"""
Test script to simulate a compound query (date + weather) without using microphone
"""

# python test_compound_query.py

import sys
from pathlib import Path

# Add the project directory to the path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir / "bt7274_assistant"))

from bt7274_assistant.pipeline import BT7274Assistant

def test_compound_query():
    """Test compound query handling"""
    print("Testing compound query: 'BT, what is the date and the weather?'")
    
    # Initialize BT assistant
    assistant = BT7274Assistant()
    assistant.initialize()
    
    # Simulate the compound query
    test_query = "BT, what is the date and the weather?"
    print(f"\nSimulating query: {test_query}")
    
    # Process the command (skip wake word check for testing)
    result = assistant.process_command(
        audio_path=None, 
        skip_wake_word=True, 
        pre_transcribed_text=test_query
    )
    
    print(f"Processing result: {result}")

if __name__ == "__main__":
    test_compound_query()