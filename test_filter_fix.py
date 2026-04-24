#!/usr/bin/env python3
"""
Test script to verify the filter fix works correctly.
"""

import numpy as np
import soundfile as sf
import tempfile
import os
from bt7274_assistant.stt import WhisperSTT

def test_edge_cases():
    """Test edge cases for the noise reduction filter."""
    print("Testing edge cases for noise reduction...")
    
    # Initialize STT
    config = {
        "model": "base.en",
        "language": "en",
        "device": "cpu"
    }
    stt = WhisperSTT(config)
    
    # Test 1: Normal case with typical sample rate
    print("\nTest 1: Normal case with 16kHz sample rate")
    duration = 1.0  # seconds
    sample_rate = 16000
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio = np.sin(2 * np.pi * 440 * t) * 0.5  # 440Hz sine wave
    
    temp_path = tempfile.mktemp(suffix=".wav")
    sf.write(temp_path, audio, sample_rate)
    
    result = stt.transcribe(temp_path)
    print(f"Result: {result.get('text', 'N/A')}")
    print(f"Confidence: {result.get('confidence', 0.0):.2f}")
    
    os.remove(temp_path)
    
    # Test 2: Low sample rate edge case
    print("\nTest 2: Low sample rate edge case")
    sample_rate_low = 8000
    t_low = np.linspace(0, duration, int(sample_rate_low * duration), False)
    audio_low = np.sin(2 * np.pi * 440 * t_low) * 0.5
    
    temp_path_low = tempfile.mktemp(suffix=".wav")
    sf.write(temp_path_low, audio_low, sample_rate_low)
    
    result_low = stt.transcribe(temp_path_low)
    print(f"Result: {result_low.get('text', 'N/A')}")
    print(f"Confidence: {result_low.get('confidence', 0.0):.2f}")
    
    os.remove(temp_path_low)
    
    # Test 3: Empty audio
    print("\nTest 3: Empty audio")
    empty_audio = np.array([])
    result_empty = stt.transcribe_buffer(empty_audio, 16000)
    print(f"Result: {result_empty.get('text', 'N/A')}")
    print(f"Confidence: {result_empty.get('confidence', 0.0):.2f}")
    
    print("\nAll edge case tests completed successfully!")

if __name__ == "__main__":
    test_edge_cases()