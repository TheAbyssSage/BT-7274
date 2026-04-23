#!/usr/bin/env python3
"""
Test script to check location context injection
"""

import sys
from pathlib import Path
import json

# Add the project directory to the path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir / "bt7274_assistant"))

from bt7274_assistant.pipeline import BT7274Assistant

def test_location_context():
    """Test location context injection"""
    print("Testing location context injection...")
    
    # Initialize BT assistant
    assistant = BT7274Assistant()
    assistant.initialize()
    
    # Simulate a travel query
    test_query = "BT, how do I get to Antwerp?"
    print(f"\nSimulating query: {test_query}")
    
    # Mock the location data to see what gets injected
    location_data = {
        "formatted": "Hasselt, Flanders, Belgium",
        "coordinates": {
            "latitude": 50.935,
            "longitude": 5.3372
        },
        "city": "Hasselt",
        "region": "Flanders",
        "country": "Belgium"
    }
    
    location_context = f"PILOT LOCATION DATA (USE THIS EXACT INFORMATION): {location_data.get('formatted', 'Unknown')}. Coordinates: {location_data.get('coordinates', {}).get('latitude', 'N/A')}, {location_data.get('coordinates', {}).get('longitude', 'N/A')}. City: {location_data.get('city', 'Unknown')}."
    enriched_text = f"{test_query} {location_context}"
    
    print(f"Enriched text sent to LLM: {enriched_text}")
    
    # Process the command (skip wake word check for testing)
    result = assistant.process_command(
        audio_path=None, 
        skip_wake_word=True, 
        pre_transcribed_text=test_query
    )
    
    print(f"Processing result: {result}")

if __name__ == "__main__":
    test_location_context()