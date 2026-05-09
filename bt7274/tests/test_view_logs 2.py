#!/usr/bin/env python3
"""
Test script for the enhanced view_logs.py functionality.
"""

import subprocess
import sys
from pathlib import Path

def test_view_logs():
    """Test the enhanced view_logs.py script."""
    print("Testing enhanced view_logs.py functionality...")
    
    # Test the new --logs option
    print("\n1. Testing --logs option:")
    result = subprocess.run([
        sys.executable, 
        "view_logs.py", 
        "--logs"
    ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
    
    if result.returncode == 0:
        print("✓ --logs option works correctly")
        # Show first 500 characters of output
        print("Sample output:")
        print(result.stdout[:500] + ("..." if len(result.stdout) > 500 else ""))
    else:
        print("✗ --logs option failed")
        print("Error:", result.stderr)
    
    # Test the --all option to compare
    print("\n2. Testing --all option:")
    result_all = subprocess.run([
        sys.executable, 
        "view_logs.py", 
        "--all"
    ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
    
    if result_all.returncode == 0:
        print("✓ --all option works correctly")
    else:
        print("✗ --all option failed")
        print("Error:", result_all.stderr)

if __name__ == "__main__":
    test_view_logs()