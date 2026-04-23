#!/usr/bin/env python3
"""
Test script for Cloud AI implementation
"""

import sys
from pathlib import Path

# Add the assistant module to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "bt7274_assistant"))

from llm import CloudLLMClient
import yaml

def test_cloud_ai():
    # Load config
    config_path = Path(__file__).parent.parent / "bt7274_assistant" / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize cloud AI client
    try:
        cloud_llm = CloudLLMClient(config["llm"]["cloud"])
        print("Cloud AI client initialized successfully!")
        
        # Test a simple query
        response = cloud_llm.chat("Hello, this is a test. Who are you?")
        print(f"Response: {response}")
        
    except Exception as e:
        print(f"Error initializing cloud AI client: {e}")
        print("Make sure you have set the required environment variables.")
        return False
    
    return True

if __name__ == "__main__":
    test_cloud_ai()