#!/usr/bin/env python3
"""
Utility script to analyze BT-7274 clips and create mappings for better matching
"""

import csv
import re
from pathlib import Path
from collections import defaultdict

def normalize_phrase(phrase: str) -> str:
    """Normalize a phrase for dictionary lookup."""
    phrase = phrase.lower().strip()
    phrase = re.sub(r'[^\w\s]', '', phrase)  # remove punctuation
    phrase = re.sub(r'\s+', ' ', phrase)     # collapse spaces
    return phrase

def load_bt_clips_index():
    """Load BT-7274's original voice clips index."""
    voicepack_dir = Path(__file__).parent.parent / "BT-7274.Voicepack"
    csv_file = voicepack_dir / "bt_clips_index.csv"
    
    clips_data = []
    
    if not csv_file.exists():
        print("⚠ BT-7274 original clips CSV not found.")
        return clips_data

    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                clips_data.append(row)
        print(f"✓ Loaded {len(clips_data)} BT-7274 clip entries from index.")
        return clips_data
    except Exception as e:
        print(f"✗ Error loading BT-7274 clips index: {e}")
        return clips_data

def create_phrase_variants(text):
    """Create common variants of a phrase for better matching."""
    variants = []
    
    # Original normalized
    normalized = normalize_phrase(text)
    variants.append(normalized)
    
    # Common contractions expanded/contracted
    contractions = {
        "you're": "you are",
        "you are": "you're",
        "we're": "we are",
        "we are": "we're",
        "i'm": "i am",
        "i am": "i'm",
        "don't": "do not",
        "do not": "don't",
        "can't": "cannot",
        "cannot": "can't",
        "won't": "will not",
        "will not": "won't"
    }
    
    for contraction, expansion in contractions.items():
        if contraction in normalized:
            variants.append(normalized.replace(contraction, expansion))
        if expansion in normalized:
            variants.append(normalized.replace(expansion, contraction))
    
    # Remove extra spaces
    variants = [re.sub(r'\s+', ' ', v).strip() for v in variants]
    # Remove duplicates while preserving order
    seen = set()
    unique_variants = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique_variants.append(v)
    
    return unique_variants

def analyze_clips():
    """Analyze BT clips and create mappings."""
    clips_data = load_bt_clips_index()
    
    # Create mappings
    phrase_to_file = {}
    file_to_phrase = {}
    phrase_variants = defaultdict(list)
    
    voicepack_dir = Path(__file__).parent.parent / "BT-7274.Voicepack"
    bt_clips_dir = voicepack_dir / "bt_clips"
    
    loaded_count = 0
    missing_files = []
    
    for clip in clips_data:
        filename = clip['filename']
        text = clip['text']
        wav_path = bt_clips_dir / filename
        
        # Check if file exists
        if not wav_path.exists():
            missing_files.append(filename)
            continue
            
        # Store mappings
        file_to_phrase[filename] = text
        normalized = normalize_phrase(text)
        phrase_to_file[normalized] = filename
        
        # Create variants
        variants = create_phrase_variants(text)
        for variant in variants:
            if variant != normalized:
                phrase_variants[variant].append(filename)
        
        loaded_count += 1
    
    print(f"✓ Successfully loaded {loaded_count} BT-7274 clips")
    if missing_files:
        print(f"⚠ {len(missing_files)} audio files missing from clips directory")
    
    # Save mappings to files
    output_dir = Path(__file__).parent / "mappings"
    output_dir.mkdir(exist_ok=True)
    
    # Save phrase to file mapping
    with open(output_dir / "bt_phrases_to_files.json", "w") as f:
        import json
        json.dump(phrase_to_file, f, indent=2)
    
    # Save file to phrase mapping
    with open(output_dir / "bt_files_to_phrases.json", "w") as f:
        import json
        json.dump(file_to_phrase, f, indent=2)
    
    # Save variants
    with open(output_dir / "bt_phrase_variants.json", "w") as f:
        import json
        json.dump(dict(phrase_variants), f, indent=2)
    
    print(f"✓ Saved mappings to {output_dir}")
    
    # Show some examples
    print("\nSample mappings:")
    count = 0
    for phrase, filename in list(phrase_to_file.items())[:10]:
        print(f"  '{phrase}' -> {filename}")
        count += 1
        if count >= 10:
            print("  ...")
            break
    
    # Show variants example
    print("\nSample variants:")
    count = 0
    for phrase, variants in list(phrase_variants.items())[:5]:
        print(f"  '{phrase}' -> {variants}")
        count += 1
        if count >= 5:
            break

if __name__ == "__main__":
    analyze_clips()