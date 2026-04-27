#!/usr/bin/env python3
"""
Script to create a TTS training dataset from BT-7274 original clips
"""

import csv
import json
from pathlib import Path
from collections import defaultdict

def normalize_phrase(phrase: str) -> str:
    """Normalize a phrase for dictionary lookup."""
    import re
    phrase = phrase.lower().strip()
    phrase = re.sub(r'[^\w\s]', '', phrase)  # remove punctuation
    phrase = re.sub(r'\s+', ' ', phrase)     # collapse spaces
    return phrase

def create_training_dataset():
    """Create a dataset for TTS training from BT clips."""
    voicepack_dir = Path(__file__).parent.parent / "BT-7274.Voicepack"
    csv_file = voicepack_dir / "bt_clips_index.csv"
    bt_clips_dir = voicepack_dir / "bt_clips"
    
    if not csv_file.exists():
        print("⚠ BT-7274 original clips CSV not found.")
        return
    
    # Create training data directory
    training_dir = Path(__file__).parent.parent / "training_data"
    training_dir.mkdir(exist_ok=True)
    
    # Create dataset structure
    dataset = {
        "name": "BT-7274 Voice Training Dataset",
        "description": "Original voice lines from BT-7274 in Titanfall 2",
        "samples": []
    }
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            loaded = 0
            for row in reader:
                filename = row['filename']
                text = row['text']
                wav_path = bt_clips_dir / filename
                
                # Check if file exists
                if not wav_path.exists():
                    continue
                
                # Add to dataset
                sample = {
                    "audio_file": str(wav_path.relative_to(training_dir.parent)),
                    "text": text,
                    "normalized_text": normalize_phrase(text),
                    "duration": float(row.get('end_time', '0').replace(':', '')) - float(row.get('start_time', '0').replace(':', '')) if row.get('end_time') and row.get('start_time') else 0,
                    "line_number": int(row.get('line_number', 0))
                }
                dataset["samples"].append(sample)
                loaded += 1
        
        print(f"✓ Processed {loaded} BT-7274 clips for training dataset")
        
        # Save dataset
        with open(training_dir / "bt7274_dataset.json", "w") as f:
            json.dump(dataset, f, indent=2)
        
        # Save as CSV for easy viewing
        with open(training_dir / "bt7274_dataset.csv", "w") as f:
            if dataset["samples"]:
                # Write header
                sample = dataset["samples"][0]
                fieldnames = list(sample.keys())
                import csv as csv_module
                writer = csv_module.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                # Write rows
                for sample in dataset["samples"]:
                    writer.writerow(sample)
        
        print(f"✓ Saved training dataset to {training_dir}")
        
        # Print some statistics
        total_duration = sum(sample["duration"] for sample in dataset["samples"])
        print(f"📊 Dataset Statistics:")
        print(f"   - Samples: {len(dataset['samples'])}")
        print(f"   - Total Duration: {total_duration:.2f} seconds")
        print(f"   - Average Duration: {total_duration/len(dataset['samples']):.2f} seconds per sample")
        
        # Show sample entries
        print(f"\n📋 Sample Entries:")
        for i, sample in enumerate(dataset["samples"][:5]):
            print(f"   {i+1}. \"{sample['text']}\" ({sample['duration']:.2f}s) -> {sample['audio_file']}")
            
    except Exception as e:
        print(f"✗ Error creating training dataset: {e}")

def create_character_model_card():
    """Create a model card describing BT-7274's character for TTS."""
    model_card = {
        "character_name": "BT-7274",
        "source": "Titanfall 2",
        "characteristics": {
            "voice_type": "Deep, masculine synthetic voice",
            "tone": "Calm, precise, tactical",
            "personality": "Loyal, slightly literal, dry humor",
            "speaking_style": "Concise, efficient, formal with pilot-directed phrases",
            "common_phrases": [
                "Pilot",
                "Copy that",
                "Understood",
                "Acknowledged",
                "Stand by",
                "You're welcome",
                "Roger that",
                "Confirmed"
            ]
        },
        "technical_specs": {
            "sample_rate": "Unknown (game audio)",
            "bit_depth": "Unknown",
            "codec": "WAV"
        },
        "usage_notes": {
            "context": "Military/sci-fi assistant AI",
            "appropriate_for": [
                "Gaming assistants",
                "Sci-fi projects",
                "Military-themed applications"
            ],
            "limitations": [
                "Game-specific terminology",
                "Limited emotional range",
                "Synthetic voice only"
            ]
        }
    }
    
    # Save model card
    training_dir = Path(__file__).parent.parent / "training_data"
    with open(training_dir / "bt7274_model_card.json", "w") as f:
        json.dump(model_card, f, indent=2)
    
    print("✓ Created BT-7274 model card for TTS training")

if __name__ == "__main__":
    create_training_dataset()
    create_character_model_card()