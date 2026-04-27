#!/usr/bin/env python3
"""
Test script to verify BT-7274 original clips loading
"""

import sys
import csv
import re
from pathlib import Path

def normalize_phrase(phrase: str) -> str:
    """Normalize a phrase for dictionary lookup."""
    phrase = phrase.lower().strip()
    phrase = re.sub(r'[^\w\s]', '', phrase)  # remove punctuation
    phrase = re.sub(r'\s+', ' ', phrase)     # collapse spaces
    return phrase

def load_bt_original_clips():
    """Load BT-7274's original voice clips from the game for instant responses."""
    voicepack_dir = Path(__file__).parent / "BT-7274.Voicepack"
    bt_clips_dir = voicepack_dir / "bt_clips"
    csv_file = voicepack_dir / "bt_clips_index.csv"
    
    bt_clips = {}
    
    if not csv_file.exists():
        print("⚠ BT-7274 original clips CSV not found. Skipping.")
        return bt_clips
        
    if not bt_clips_dir.exists():
        print("⚠ BT-7274 original clips directory not found. Skipping.")
        return bt_clips

    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            loaded = 0
            for row in reader:
                filename = row['filename']
                text = row['text']
                wav_path = bt_clips_dir / filename
                
                if wav_path.exists():
                    # Normalize the text for matching
                    normalized_text = normalize_phrase(text)
                    bt_clips[normalized_text] = str(wav_path)
                    loaded += 1
                    
        print(f"✓ Loaded {loaded} BT-7274 original voice clips.")
        return bt_clips
    except Exception as e:
        print(f"✗ Error loading BT-7274 original clips: {e}")
        return bt_clips

def test_bt_clips():
    """Test that BT clips are loaded correctly"""
    print("Loading BT-7274 original clips...")
    bt_clips = load_bt_original_clips()
    
    print(f"Loaded {len(bt_clips)} BT-7274 original voice clips")
    
    # Show some examples
    print("\nSample BT clips loaded:")
    count = 0
    for phrase, path in bt_clips.items():
        print(f"  '{phrase}' -> {Path(path).name}")
        count += 1
        if count >= 10:  # Show first 10
            print("  ...")
            break
            
    # Test matching
    test_phrases = [
        "standing by pilot climb onto my hand",
        "you're welcome pilot",
        "copy that",
        "understood pilot"
    ]
    
    print("\nTesting phrase matching:")
    for phrase in test_phrases:
        normalized = normalize_phrase(phrase)
        if normalized in bt_clips:
            print(f"  ✓ Found match for '{phrase}'")
        else:
            print(f"  ✗ No match for '{phrase}'")

if __name__ == "__main__":
    test_bt_clips()