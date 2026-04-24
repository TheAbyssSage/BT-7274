#!/usr/bin/env python3
"""
Test script to demonstrate TTS optimizations.
"""

import sys
import os
from pathlib import Path
import time

# Add the assistant directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "bt7274_assistant"))

from tts import XTTSClient


def main():
    """Test the TTS optimizations."""
    print("Testing TTS optimizations...")
    
    # Configure TTS
    config = {
        "model": "tts_models/multilingual/multi-dataset/xtts_v2",
        "reference_wav": "dataset/reference_speaker.wav",
        "language": "en",
        "speed": 1.0,
        "output_dir": "outputs",
    }
    
    tts = XTTSClient(config)
    
    # Test phrases
    test_phrases = [
        "You're welcome, Pilot.",
        "Copy that, Pilot. Stand by.",
        "Processing complete, Pilot.",
        "Acknowledged. Retrieving data.",
        "This is a longer response that should demonstrate the text truncation optimization. " * 3,
        "BT seven two seven four, reporting for duty.",
    ]
    
    print("\nTesting TTS with caching...")
    
    for i, phrase in enumerate(test_phrases, 1):
        print(f"\nTest {i}: {phrase}")
        
        # Time the first generation
        start_time = time.time()
        wav_path1 = tts.speak(phrase)
        time1 = time.time() - start_time
        
        if wav_path1:
            print(f"  First generation: {time1:.2f}s")
            
            # Time the second generation (should use cache)
            start_time = time.time()
            wav_path2 = tts.speak(phrase)
            time2 = time.time() - start_time
            
            if wav_path2 == wav_path1:
                print(f"  Cached generation: {time2:.2f}s (using cached file)")
            else:
                print(f"  Cached generation: {time2:.2f}s")
                
            # Show cache effectiveness
            if time2 < time1:
                print(f"  Cache improvement: {(time1-time2)/time1*100:.1f}% faster")
        else:
            print("  Failed to generate audio")
    
    print("\n✅ TTS optimization test complete!")


if __name__ == "__main__":
    main()