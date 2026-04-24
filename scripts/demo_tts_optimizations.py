#!/usr/bin/env python3
"""
Demo script showing TTS optimizations in action.
"""

import sys
import os
from pathlib import Path
import time

# Add the assistant directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "bt7274_assistant"))

from tts import XTTSClient


def demo_caching():
    """Demonstrate TTS caching optimization."""
    print("=== TTS Caching Demo ===")
    
    # Configure TTS
    config = {
        "model": "tts_models/multilingual/multi-dataset/xtts_v2",
        "reference_wav": "dataset/reference_speaker.wav",
        "language": "en",
        "speed": 1.0,
        "output_dir": "outputs",
    }
    
    tts = XTTSClient(config)
    
    # Test phrase
    phrase = "This is a demonstration of TTS caching."
    
    print(f"Testing phrase: {phrase}")
    
    # Time the first generation
    print("First generation (no cache)...")
    start_time = time.time()
    wav_path1 = tts.speak(phrase)
    time1 = time.time() - start_time
    
    if wav_path1:
        print(f"  Time: {time1:.2f} seconds")
        print(f"  File: {wav_path1}")
        
        # Time the second generation (should use cache)
        print("Second generation (with cache)...")
        start_time = time.time()
        wav_path2 = tts.speak(phrase)
        time2 = time.time() - start_time
        
        if wav_path2 == wav_path1:
            print(f"  Time: {time2:.2f} seconds (using cached file)")
            print(f"  Improvement: {(time1-time2)/time1*100:.1f}% faster")
        else:
            print(f"  Time: {time2:.2f} seconds")
            
        # Show cache size
        cache_size = len(tts._response_cache)
        print(f"  Cache size: {cache_size} items")
    else:
        print("  Failed to generate audio")


def demo_text_processing():
    """Demonstrate improved text processing."""
    print("\n=== Text Processing Demo ===")
    
    # Configure TTS
    config = {
        "model": "tts_models/multilingual/multi-dataset/xtts_v2",
        "reference_wav": "dataset/reference_speaker.wav",
        "language": "en",
        "speed": 1.0,
        "output_dir": "outputs",
    }
    
    tts = XTTSClient(config)
    
    # Test long text with sentence boundaries
    long_text = ("This is a very long response that demonstrates the improved text processing. "
                "It shows how the system preserves sentence boundaries when truncating text. "
                "Notice how it cuts at natural sentence breaks rather than arbitrarily. "
                "This makes the spoken output more natural and easier to understand. "
                "The system is designed to optimize for listening experience.") * 2
    
    print(f"Original text length: {len(long_text)} characters")
    
    # Test the preprocessing
    processed = tts._preprocess_text(long_text)
    print(f"Processed text length: {len(processed)} characters")
    
    # Show truncation behavior
    max_chars = 600
    if len(processed) > max_chars:
        truncated = processed[:max_chars]
        last_sentence_end = truncated.rfind('.')
        if last_sentence_end > max_chars * 0.7:
            final_text = truncated[:last_sentence_end + 1]
        else:
            final_text = truncated.rsplit('.', 1)[0] + '...'
        print(f"Truncated text length: {len(final_text)} characters")
        print(f"Truncated text: {final_text}")


def main():
    """Run all demos."""
    print("BT-7274 TTS Optimization Demo")
    print("=" * 40)
    
    demo_caching()
    demo_text_processing()
    
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()