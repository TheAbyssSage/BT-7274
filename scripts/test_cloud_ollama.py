#!/usr/bin/env python3
"""
Test script for Ollama model selection
"""

import sys
from pathlib import Path

# Add the assistant module to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "bt7274_assistant"))

from llm import OllamaClient
import yaml

def test_model(model_config, model_name):
    """Test a specific model configuration"""
    try:
        llm = OllamaClient(model_config)
        print(f"{model_name} client initialized successfully!")
        
        # Test a simple query
        response = llm.chat("Hello, this is a test. Who are you?")
        print(f"Response: {response}")
        
        return True
    except Exception as e:
        print(f"Error testing {model_name}: {e}")
        return False

def test_both_models():
    """Test both local and cloud models"""
    # Load config
    config_path = Path(__file__).parent.parent / "bt7274_assistant" / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    print("Testing Local Model:")
    local_success = test_model(config["llm"]["local"], "Local")
    
    print("\nTesting Cloud Model:")
    cloud_success = test_model(config["llm"]["cloud"], "Cloud")
    
    if local_success and cloud_success:
        print("\nBoth models are working correctly!")
        return True
    else:
        print("\nOne or more models failed to initialize.")
        return False

if __name__ == "__main__":
    test_both_models()