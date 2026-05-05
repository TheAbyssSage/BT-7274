#!/usr/bin/env python3
"""
Demo script showcasing BT-7274 original clips integration
"""

import sys
from pathlib import Path

# Add the assistant directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Simple demo without importing heavy dependencies
import csv
import re
from pathlib import Path

def normalize_phrase(phrase: str) -> str:
    """Normalize a phrase for dictionary lookup."""
    phrase = phrase.lower().strip()
    phrase = re.sub(r'[^\w\s]', '', phrase)  # remove punctuation
    phrase = re.sub(r'\s+', ' ', phrase)     # collapse spaces
    return phrase

def load_bt_clips():
    """Load BT-7274's original voice clips."""
    voicepack_dir = Path(__file__).parent.parent / "BT-7274.Voicepack"
    csv_file = voicepack_dir / "bt_clips_index.csv"
    bt_clips_dir = voicepack_dir / "bt_clips"
    
    bt_clips = {}
    
    if not csv_file.exists():
        print("❌ BT-7274 clips CSV not found")
        return bt_clips

    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                filename = row['filename']
                text = row['text']
                wav_path = bt_clips_dir / filename
                
                if wav_path.exists():
                    normalized_text = normalize_phrase(text)
                    bt_clips[normalized_text] = str(wav_path)
                    
        print(f"✅ Loaded {len(bt_clips)} BT-7274 voice clips")
        return bt_clips
    except Exception as e:
        print(f"❌ Error loading BT-7274 clips: {e}")
        return bt_clips

def demo_matching(bt_clips):
    """Demonstrate phrase matching capabilities."""
    print("\n🎯 Demo: Phrase Matching")
    
    test_phrases = [
        "standing by pilot climb onto my hand",
        "you're welcome pilot",
        "copy that pilot",
        "be careful pilot",
        "understood pilot",
        "imc salvage teams are not far away"
    ]
    
    for phrase in test_phrases:
        normalized = normalize_phrase(phrase)
        if normalized in bt_clips:
            print(f"  ✅ '{phrase}' -> FOUND")
        else:
            print(f"  ❌ '{phrase}' -> NOT FOUND")

def demo_random_samples(bt_clips, count=5):
    """Show random samples from the clips."""
    print(f"\n🎲 Demo: Random BT-7274 Clips ({count} samples)")
    
    import random
    samples = random.sample(list(bt_clips.items()), min(count, len(bt_clips)))
    
    for i, (phrase, path) in enumerate(samples, 1):
        # Extract just the filename for cleaner display
        filename = Path(path).name
        print(f"  {i}. \"{phrase}\" -> {filename}")

def demo_statistics(bt_clips):
    """Show statistics about the clips."""
    print("\n📊 Demo: BT-7274 Clips Statistics")
    print(f"  Total clips: {len(bt_clips)}")
    
    # Calculate average phrase length
    if bt_clips:
        avg_length = sum(len(phrase.split()) for phrase in bt_clips.keys()) / len(bt_clips)
        print(f"  Average words per clip: {avg_length:.1f}")
        
        # Find longest and shortest phrases
        sorted_phrases = sorted(bt_clips.keys(), key=len)
        shortest = sorted_phrases[0]
        longest = sorted_phrases[-1]
        print(f"  Shortest phrase: \"{shortest}\" ({len(shortest)} chars)")
        print(f"  Longest phrase: \"{longest}\" ({len(longest)} chars)")

def main():
    """Main demo function."""
    print("🚀 BT-7274 Original Clips Integration Demo")
    print("=" * 50)
    
    # Load clips
    bt_clips = load_bt_clips()
    
    if not bt_clips:
        print("❌ Failed to load BT-7274 clips. Exiting.")
        return
    
    # Run demos
    demo_statistics(bt_clips)
    demo_random_samples(bt_clips)
    demo_matching(bt_clips)
    
    print("\n✨ Demo complete!")
    print("For full integration, restart the BT-7274 assistant to use these clips.")

if __name__ == "__main__":
    main()