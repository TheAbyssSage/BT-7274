#!/usr/bin/env python3
"""
Test script to check current location detection
"""

import sys
from pathlib import Path

# Add the project directory to the path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir / "bt7274_assistant"))

from bt7274_assistant.location import LocationProvider

def test_location():
    """Test location detection"""
    print("Testing location detection...")
    
    # Initialize location provider
    loc = LocationProvider()
    
    # Update location
    success = loc.update()
    
    if success:
        print(f"Location update successful!")
        print(f"  Latitude: {loc._lat}")
        print(f"  Longitude: {loc._lon}")
        print(f"  City: {loc._city}")
        print(f"  Region: {loc._region}")
        print(f"  Country: {loc._country}")
        print(f"  Formatted: {loc.location_str}")
    else:
        print("Location update failed!")

if __name__ == "__main__":
    test_location()