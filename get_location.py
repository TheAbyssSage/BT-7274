#!/usr/bin/env python3
"""
Simple location getter for macOS
"""

import subprocess
import json
import sys

def get_location_via_corelocation():
    """Try to get location via macOS CoreLocation using osascript"""
    try:
        # This requires the user to grant location permissions to Terminal.app or the running app
        script = '''
        use framework "CoreLocation"
        use scripting additions
        
        set locationManager to current application's CLLocationManager's alloc()'s init()
        set loc to locationManager's location()
        
        if loc is not missing value then
            set coord to loc's coordinate()
            set lat to coord's latitude()
            set lng to coord's longitude()
            return {lat, lng}
        else
            return "Location not available"
        end if
        '''
        
        result = subprocess.run([
            'osascript', '-l', 'JavaScript', '-e', script
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            return f"Error: {result.stderr}"
    except Exception as e:
        return f"Exception: {e}"

def get_location_via_ip():
    """Get approximate location via IP address"""
    try:
        import requests
        response = requests.get('http://ip-api.com/json/', timeout=5)
        data = response.json()
        if data.get('status') == 'success':
            return {
                'lat': data.get('lat'),
                'lon': data.get('lon'),
                'city': data.get('city'),
                'region': data.get('regionName'),
                'country': data.get('country')
            }
        else:
            return "IP location failed"
    except Exception as e:
        return f"IP location error: {e}"

def main():
    print("Getting your location...")
    
    # Try IP location first (works without special permissions)
    print("\\n1. Trying IP-based location...")
    ip_location = get_location_via_ip()
    print(f"   IP Location: {ip_location}")
    
    # Try CoreLocation (requires permissions)
    print("\\n2. Trying CoreLocation (may require permissions)...")
    core_location = get_location_via_corelocation()
    print(f"   CoreLocation: {core_location}")
    
    print("\\nTo use precise location in BT-7274:")
    print("1. Uncomment the 'manual' section in config.yaml")
    print("2. Fill in your latitude and longitude")
    print("3. You can get your coordinates from:")
    print("   - Google Maps (right-click on your location → What's here?)")
    print("   - iPhone Settings → Privacy → Location Services → System Services → Significant Locations")

if __name__ == "__main__":
    main()