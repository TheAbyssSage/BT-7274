#!/usr/bin/env python3
"""
Test script to compare Standard vs Performance TTS modes.
"""

import sys
import os
import time
from pathlib import Path

# Add the assistant directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "bt7274_assistant"))

from tts import XTTSClient
from tts_fast import StreamingXTTSClient


def test_standard_mode():
    """Test standard (non-streaming) TTS mode."""
    print("=" * 60)
    print("TESTING STANDARD MODE")
    print("=" * 60)
    
    config = {
        "model": "tts_models/multilingual/multi-dataset/xtts_v2",
        "reference_wav": "dataset/reference_speaker.wav",
        "language": "en",
        "speed": 1.0,
        "output_dir": "outputs",
    }
    
    tts = XTTSClient(config)
    
    test_text = (
        "Pilot, I have analyzed the tactical situation. "
        "The enemy forces are advancing from the north. "
        "I recommend we take defensive positions immediately. "
        "My systems are at optimal performance. "
        "Standing by for further orders."
    )
    
    print(f"Test text: {test_text}")
    print(f"Text length: {len(test_text)} characters")
    print("")
    
    start_time = time.time()
    wav_path = tts.speak(test_text)
    total_time = time.time() - start_time
    
    if wav_path:
        print(f"✓ Standard mode complete in {total_time:.2f}s")
        print(f"  Output: {wav_path}")
    else:
        print("✗ Standard mode failed")
    
    return total_time if wav_path else None


def test_performance_mode():
    """Test performance (streaming) TTS mode."""
    print("")
    print("=" * 60)
    print("TESTING PERFORMANCE MODE (STREAMING)")
    print("=" * 60)
    
    config = {
        "model": "tts_models/multilingual/multi-dataset/xtts_v2",
        "reference_wav": "dataset/reference_speaker.wav",
        "language": "en",
        "speed": 1.0,
        "output_dir": "outputs",
    }
    
    tts = StreamingXTTSClient(config)
    
    test_text = (
        "Pilot, I have analyzed the tactical situation. "
        "The enemy forces are advancing from the north. "
        "I recommend we take defensive positions immediately. "
        "My systems are at optimal performance. "
        "Standing by for further orders."
    )
    
    print(f"Test text: {test_text}")
    print(f"Text length: {len(test_text)} characters")
    print("")
    
    start_time = time.time()
    success = tts.speak_streaming(test_text)
    total_time = time.time() - start_time
    
    if success:
        print(f"✓ Performance mode complete in {total_time:.2f}s")
        metrics = tts.get_metrics()
        print(f"  Sentences synthesized: {metrics['sentences_synthesized']}")
        print(f"  Sentences played: {metrics['sentences_played']}")
        if 'avg_synthesis_time' in metrics:
            print(f"  Avg synthesis time: {metrics['avg_synthesis_time']:.2f}s")
    else:
        print("✗ Performance mode failed")
    
    return total_time if success else None


def compare_modes():
    """Compare both modes side by side."""
    print("")
    print("=" * 60)
    print("COMPARISON RESULTS")
    print("=" * 60)
    
    standard_time = test_standard_mode()
    performance_time = test_performance_mode()
    
    print("")
    print("-" * 60)
    print("RESULTS SUMMARY")
    print("-" * 60)
    
    if standard_time and performance_time:
        print(f"Standard mode:   {standard_time:.2f}s")
        print(f"Performance mode:  {performance_time:.2f}s")
        
        if performance_time < standard_time:
            improvement = ((standard_time - performance_time) / standard_time) * 100
            print(f"Improvement:     {improvement:.1f}% faster")
        else:
            print("Note: Performance mode may be slower for very short responses")
            print("      Benefits increase with longer responses")
    else:
        print("Could not complete comparison - one or both tests failed")
    
    print("")
    print("Key differences:")
    print("  Standard mode:")
    print("    - Full response synthesized before playback")
    print("    - Simpler, more predictable")
    print("    - Best for short responses")
    print("")
    print("  Performance mode:")
    print("    - Sentence-level streaming with parallel synthesis")
    print("    - Audio starts playing while still synthesizing")
    print("    - Best for long responses")
    print("    - Maintains BT-7274's voice quality")


def main():
    """Run the comparison test."""
    print("BT-7274 TTS Performance Comparison")
    print("This test compares Standard vs Performance (Streaming) TTS modes")
    print("")
    
    try:
        compare_modes()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\nError during test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
