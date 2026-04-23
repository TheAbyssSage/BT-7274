#!/usr/bin/env python3
"""
Generate BT-7274 voice responses for common phrases.
"""

import sys
import os
from pathlib import Path

# Add the project directory to the path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir / "bt7274_assistant"))

# Try to import the TTS client
try:
    from tts import XTTSClient
    TTS_AVAILABLE = True
except ImportError as e:
    print(f"TTS not available: {e}")
    TTS_AVAILABLE = False

def generate_bt_responses():
    """Generate BT-style responses for common phrases."""
    if not TTS_AVAILABLE:
        print("TTS not available, using placeholder")
        return
        
    # Configuration for XTTS
    config = {
        "model": "tts_models/multilingual/multi-dataset/xtts_v2",
        "reference_wav": "dataset/reference_speaker.wav",
        "language": "en",
        "speed": 1.0,
        "output_dir": "standby",
    }
    
    # Initialize TTS client
    tts = XTTSClient(config)
    output_dir = Path("standby")
    output_dir.mkdir(exist_ok=True)
    
    # Phrases to generate
    phrases = [
        "You're welcome, Pilot.",
        "My pleasure, Pilot.",
        "Glad to assist, Pilot.",
        "Happy to help, Pilot.",
        "Anytime, Pilot.",
        "Acknowledged, Pilot.",
        "Copy that, Pilot.",
        "Understood, Pilot.",
        "Affirmative, Pilot.",
        "Roger that, Pilot."
    ]
    
    print("Generating BT-style responses...")
    generated = 0
    failed = 0
    
    for phrase in phrases:
        # Create safe filename
        safe_name = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in phrase.lower())
        safe_name = safe_name.replace(" ", "_").replace("-", "_")
        output_path = output_dir / f"{safe_name}.wav"
        
        if output_path.exists():
            print(f"  ⏭ Skipping: {phrase}")
            continue
            
        print(f"  → Generating: {phrase}")
        try:
            wav_path = tts.speak(phrase)
            if wav_path:
                import shutil
                shutil.move(wav_path, str(output_path))
                print(f"    ✓ Saved: {output_path.name}")
                generated += 1
            else:
                print(f"    ✗ Failed: {phrase}")
                failed += 1
        except Exception as e:
            print(f"    ✗ Error generating '{phrase}': {e}")
            failed += 1
    
    print(f"\nDone! Generated: {generated}, Failed: {failed}")

if __name__ == "__main__":
    generate_bt_responses()