#!/usr/bin/env python3
"""
Enhanced TTS Training Dataset Generator for BT-7274
Adds phoneme-level transcriptions, prosody annotations, and character emotion tagging
"""

import csv
import json
import re
from pathlib import Path
from collections import defaultdict
import numpy as np

# Try to import optional libraries
try:
    from phonemizer import phonemize
    from phonemizer.backend import EspeakBackend
    PHONEMIZER_AVAILABLE = True
except ImportError:
    PHONEMIZER_AVAILABLE = False
    print("⚠ phonemizer not available. Install with: pip install phonemizer")

try:
    import librosa
    import soundfile as sf
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    print("⚠ librosa not available. Install with: pip install librosa soundfile")


def normalize_phrase(phrase: str) -> str:
    """Normalize a phrase for dictionary lookup."""
    phrase = phrase.lower().strip()
    phrase = re.sub(r'[^\w\s]', '', phrase)
    phrase = re.sub(r'\s+', ' ', phrase)
    return phrase


def get_phoneme_transcription(text: str) -> str:
    """Get phoneme-level transcription using phonemizer or fallback."""
    if PHONEMIZER_AVAILABLE:
        try:
            # Use espeak backend for English phonemes
            phonemes = phonemize(
                text,
                language='en-us',
                backend='espeak',
                strip=True,
                preserve_punctuation=True,
                with_stress=True
            )
            return phonemes.strip()
        except Exception as e:
            print(f"    ⚠ Phonemization failed: {e}")
            return _fallback_phonemize(text)
    else:
        return _fallback_phonemize(text)


def _fallback_phonemize(text: str) -> str:
    """Simple fallback phonemizer using basic English phoneme mapping."""
    # Basic phoneme mapping for common English sounds
    phoneme_map = {
        'th': 'θ', 'sh': 'ʃ', 'ch': 'tʃ', 'zh': 'ʒ',
        'ph': 'f', 'gh': 'g', 'ck': 'k', 'ng': 'ŋ',
        'wh': 'w', 'wr': 'r', 'kn': 'n', 'gn': 'n',
        'ps': 's', 'pn': 'n', 'rh': 'r', 'mn': 'n',
        'a': 'æ', 'e': 'ɛ', 'i': 'ɪ', 'o': 'ɒ', 'u': 'ʌ',
        'ay': 'eɪ', 'ee': 'iː', 'ie': 'iː', 'oa': 'oʊ',
        'oo': 'uː', 'ou': 'aʊ', 'oi': 'ɔɪ', 'oy': 'ɔɪ',
        'aw': 'ɔː', 'au': 'ɔː', 'ow': 'oʊ', 'ew': 'juː',
        'ar': 'ɑːr', 'er': 'ɜːr', 'ir': 'ɪr', 'or': 'ɔːr', 'ur': 'ɜːr',
        'ai': 'eɪ', 'ea': 'iː', 'ei': 'eɪ', 'ey': 'eɪ',
        'igh': 'aɪ', 'ign': 'aɪn', 'ind': 'aɪnd',
        'ough': 'oʊ', 'ought': 'ɔːt', 'aught': 'ɔːt',
    }
    
    text = text.lower()
    phonemes = []
    i = 0
    
    while i < len(text):
        # Try to match longest pattern first
        matched = False
        for length in [4, 3, 2, 1]:
            if i + length <= len(text):
                substr = text[i:i+length]
                if substr in phoneme_map:
                    phonemes.append(phoneme_map[substr])
                    i += length
                    matched = True
                    break
        
        if not matched:
            # Keep character as-is if it's a space or punctuation
            char = text[i]
            if char.isalpha():
                phonemes.append(char)
            elif char in ' .,!?;':
                phonemes.append(char)
            i += 1
    
    return ' '.join(phonemes)


def analyze_prosody(audio_path: str) -> dict:
    """Analyze prosodic features of an audio file."""
    if not LIBROSA_AVAILABLE:
        return {}
    
    try:
        # Load audio
        y, sr = librosa.load(audio_path, sr=None)
        
        # Extract pitch (fundamental frequency)
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
        
        # Get mean pitch (excluding zeros)
        pitch_values = pitches[magnitudes > np.max(magnitudes) * 0.5]
        if len(pitch_values) > 0:
            mean_pitch = np.mean(pitch_values)
            pitch_range = np.max(pitch_values) - np.min(pitch_values)
        else:
            mean_pitch = 0
            pitch_range = 0
        
        # Extract energy (RMS)
        rms = librosa.feature.rms(y=y)[0]
        mean_energy = np.mean(rms)
        energy_range = np.max(rms) - np.min(rms)
        
        # Extract tempo (if applicable)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)[0]
        
        # Extract spectral features
        spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
        spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
        
        # Calculate speaking rate (approximate)
        duration = len(y) / sr
        
        return {
            "mean_pitch_hz": round(float(mean_pitch), 2),
            "pitch_range_hz": round(float(pitch_range), 2),
            "mean_energy": round(float(mean_energy), 4),
            "energy_range": round(float(energy_range), 4),
            "tempo_bpm": round(float(tempo), 2),
            "spectral_centroid": round(float(spectral_centroid), 2),
            "spectral_rolloff": round(float(spectral_rolloff), 2),
            "duration_seconds": round(float(duration), 2)
        }
    except Exception as e:
        print(f"    ⚠ Prosody analysis failed: {e}")
        return {}


def detect_emotion_from_text(text: str) -> dict:
    """Detect character emotion from text content."""
    text_lower = text.lower()
    
    # Define emotion indicators with weights
    emotion_indicators = {
        "urgent": {
            "keywords": ["danger", "warning", "alert", "emergency", "critical", "hurry", "quick", "immediately"],
            "weight": 1.0
        },
        "cautious": {
            "keywords": ["careful", "caution", "beware", "watch out", "attention", "safe"],
            "weight": 0.8
        },
        "positive": {
            "keywords": ["good", "great", "excellent", "perfect", "wonderful", "congratulations", "well done"],
            "weight": 0.9
        },
        "concerned": {
            "keywords": ["worry", "concern", "afraid", "careful", "protect", "safe"],
            "weight": 0.7
        },
        "determined": {
            "keywords": ["must", "will", "shall", "determined", "committed", "resolve", "protocol", "mission"],
            "weight": 0.8
        },
        "neutral": {
            "keywords": ["understood", "acknowledged", "copy that", "roger", "affirmative", "standing by"],
            "weight": 0.5
        },
        "questioning": {
            "keywords": ["?", "what", "why", "how", "when", "where", "who"],
            "weight": 0.6
        },
        "commanding": {
            "keywords": ["order", "command", "execute", "proceed", "move", "advance", "retreat"],
            "weight": 0.9
        }
    }
    
    # Calculate emotion scores
    emotion_scores = {}
    for emotion, data in emotion_indicators.items():
        score = sum(1 for keyword in data["keywords"] if keyword in text_lower)
        if score > 0:
            emotion_scores[emotion] = score * data["weight"]
    
    # Get primary and secondary emotions
    if emotion_scores:
        sorted_emotions = sorted(emotion_scores.items(), key=lambda x: x[1], reverse=True)
        primary_emotion = sorted_emotions[0][0]
        primary_score = sorted_emotions[0][1]
        
        # Calculate confidence (normalize score)
        max_possible = max(len(data["keywords"]) * data["weight"] for data in emotion_indicators.values())
        confidence = min(1.0, primary_score / max_possible)
        
        secondary_emotion = sorted_emotions[1][0] if len(sorted_emotions) > 1 else None
        
        return {
            "primary_emotion": primary_emotion,
            "primary_score": round(float(primary_score), 2),
            "confidence": round(float(confidence), 2),
            "secondary_emotion": secondary_emotion,
            "all_scores": {k: round(float(v), 2) for k, v in sorted_emotions[:3]}
        }
    
    return {
        "primary_emotion": "neutral",
        "primary_score": 0.0,
        "confidence": 0.0,
        "secondary_emotion": None,
        "all_scores": {}
    }


def get_speaking_style(text: str, emotion: dict) -> dict:
    """Determine speaking style based on text and emotion."""
    text_lower = text.lower()
    
    # Determine pace
    if emotion["primary_emotion"] in ["urgent", "commanding"]:
        pace = "fast"
    elif emotion["primary_emotion"] in ["cautious", "concerned"]:
        pace = "slow"
    else:
        pace = "normal"
    
    # Determine volume
    if emotion["primary_emotion"] in ["urgent", "commanding", "positive"]:
        volume = "loud"
    elif emotion["primary_emotion"] in ["cautious", "concerned"]:
        volume = "soft"
    else:
        volume = "normal"
    
    # Determine pitch variation
    if emotion["primary_emotion"] in ["questioning", "concerned"]:
        pitch_variation = "high"
    elif emotion["primary_emotion"] in ["neutral", "determined"]:
        pitch_variation = "low"
    else:
        pitch_variation = "normal"
    
    # Check for specific BT-7274 speech patterns
    is_question = "?" in text
    has_pilot_address = "pilot" in text_lower
    is_protocol = text_lower.startswith("protocol")
    is_acknowledgment = any(word in text_lower for word in ["understood", "acknowledged", "copy that", "roger"])
    
    return {
        "pace": pace,
        "volume": volume,
        "pitch_variation": pitch_variation,
        "is_question": is_question,
        "has_pilot_address": has_pilot_address,
        "is_protocol": is_protocol,
        "is_acknowledgment": is_acknowledgment
    }


def create_enhanced_training_dataset():
    """Create an enhanced dataset with phonemes, prosody, and emotion tagging."""
    voicepack_dir = Path(__file__).parent.parent / "BT-7274.Voicepack"
    csv_file = voicepack_dir / "bt_clips_index.csv"
    bt_clips_dir = voicepack_dir / "bt_clips"
    
    if not csv_file.exists():
        print("⚠ BT-7274 original clips CSV not found.")
        return
    
    # Create training data directory
    training_dir = Path(__file__).parent.parent / "training_data"
    training_dir.mkdir(exist_ok=True)
    
    # Create enhanced dataset structure
    dataset = {
        "name": "BT-7274 Enhanced Voice Training Dataset",
        "description": "Original voice lines from BT-7274 in Titanfall 2 with phoneme transcriptions, prosody annotations, and emotion tagging",
        "version": "2.0",
        "features": [
            "phoneme_transcription",
            "prosody_analysis",
            "emotion_tagging",
            "speaking_style"
        ],
        "samples": []
    }
    
    print("🎙 Creating enhanced training dataset...")
    print(f"   Features: phonemes, prosody, emotion tagging")
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            loaded = 0
            phoneme_count = 0
            prosody_count = 0
            emotion_count = 0
            
            for row in reader:
                filename = row['filename']
                text = row['text']
                wav_path = bt_clips_dir / filename
                
                # Check if file exists
                if not wav_path.exists():
                    continue
                
                print(f"\n  Processing: {filename}")
                print(f"    Text: {text[:60]}...")
                
                # Create base sample
                sample = {
                    "audio_file": str(wav_path.relative_to(training_dir.parent)),
                    "text": text,
                    "normalized_text": normalize_phrase(text),
                    "line_number": int(row.get('line_number', 0))
                }
                
                # 1. Phoneme-level transcription
                if PHONEMIZER_AVAILABLE:
                    print("    📝 Generating phoneme transcription...")
                    phonemes = get_phoneme_transcription(text)
                    if phonemes:
                        sample["phonemes"] = phonemes
                        sample["phoneme_count"] = len(phonemes.split())
                        phoneme_count += 1
                        print(f"      ✓ Phonemes: {phonemes[:50]}...")
                
                # 2. Prosody analysis
                if LIBROSA_AVAILABLE:
                    print("    🎵 Analyzing prosody...")
                    prosody = analyze_prosody(str(wav_path))
                    if prosody:
                        sample["prosody"] = prosody
                        prosody_count += 1
                        print(f"      ✓ Pitch: {prosody['mean_pitch_hz']}Hz, Energy: {prosody['mean_energy']}")
                
                # 3. Emotion tagging
                print("    🎭 Detecting emotion...")
                emotion = detect_emotion_from_text(text)
                sample["emotion"] = emotion
                emotion_count += 1
                print(f"      ✓ Primary: {emotion['primary_emotion']} (confidence: {emotion['confidence']})")
                
                # 4. Speaking style
                style = get_speaking_style(text, emotion)
                sample["speaking_style"] = style
                print(f"      ✓ Style: {style['pace']} pace, {style['volume']} volume")
                
                dataset["samples"].append(sample)
                loaded += 1
                
                # Progress update every 50 samples
                if loaded % 50 == 0:
                    print(f"\n📊 Progress: {loaded} samples processed")
        
        print(f"\n✓ Processed {loaded} BT-7274 clips for enhanced training dataset")
        print(f"  - Phoneme transcriptions: {phoneme_count}")
        print(f"  - Prosody analyses: {prosody_count}")
        print(f"  - Emotion tags: {emotion_count}")
        
        # Save enhanced dataset
        output_file = training_dir / "bt7274_enhanced_dataset.json"
        with open(output_file, "w") as f:
            json.dump(dataset, f, indent=2)
        
        print(f"\n✓ Saved enhanced dataset to {output_file}")
        
        # Save as CSV for easy viewing
        csv_output = training_dir / "bt7274_enhanced_dataset.csv"
        with open(csv_output, "w", newline='') as f:
            if dataset["samples"]:
                # Flatten nested dicts for CSV
                import csv as csv_module
                
                # Get all possible fields
                fieldnames = set()
                for sample in dataset["samples"]:
                    fieldnames.update(sample.keys())
                fieldnames = sorted(fieldnames)
                
                writer = csv_module.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for sample in dataset["samples"]:
                    # Flatten nested dicts
                    flat_sample = {}
                    for key, value in sample.items():
                        if isinstance(value, dict):
                            flat_sample[key] = json.dumps(value)
                        else:
                            flat_sample[key] = value
                    writer.writerow(flat_sample)
        
        print(f"✓ Saved CSV to {csv_output}")
        
        # Print statistics
        print_dataset_statistics(dataset)
        
        # Show sample entries
        print(f"\n📋 Sample Entries:")
        for i, sample in enumerate(dataset["samples"][:3]):
            print(f"\n   Sample {i+1}:")
            print(f"     Text: \"{sample['text']}\"")
            if "phonemes" in sample:
                print(f"     Phonemes: {sample['phonemes'][:60]}...")
            if "prosody" in sample:
                print(f"     Prosody: {sample['prosody']}")
            if "emotion" in sample:
                print(f"     Emotion: {sample['emotion']['primary_emotion']} (confidence: {sample['emotion']['confidence']})")
            if "speaking_style" in sample:
                print(f"     Style: {sample['speaking_style']}")
            
    except Exception as e:
        print(f"✗ Error creating enhanced training dataset: {e}")
        import traceback
        traceback.print_exc()


def print_dataset_statistics(dataset: dict):
    """Print statistics about the enhanced dataset."""
    samples = dataset["samples"]
    
    print(f"\n📊 Enhanced Dataset Statistics:")
    print(f"   - Total Samples: {len(samples)}")
    
    # Phoneme statistics
    phoneme_samples = [s for s in samples if "phonemes" in s]
    if phoneme_samples:
        avg_phonemes = np.mean([s["phoneme_count"] for s in phoneme_samples])
        print(f"   - Phoneme Coverage: {len(phoneme_samples)} samples ({len(phoneme_samples)/len(samples)*100:.1f}%)")
        print(f"   - Average Phonemes per Sample: {avg_phonemes:.1f}")
    
    # Prosody statistics
    prosody_samples = [s for s in samples if "prosody" in s]
    if prosody_samples:
        avg_pitch = np.mean([s["prosody"]["mean_pitch_hz"] for s in prosody_samples])
        avg_energy = np.mean([s["prosody"]["mean_energy"] for s in prosody_samples])
        avg_duration = np.mean([s["prosody"]["duration_seconds"] for s in prosody_samples])
        print(f"   - Prosody Coverage: {len(prosody_samples)} samples ({len(prosody_samples)/len(samples)*100:.1f}%)")
        print(f"   - Average Pitch: {avg_pitch:.1f} Hz")
        print(f"   - Average Energy: {avg_energy:.4f}")
        print(f"   - Average Duration: {avg_duration:.2f}s")
    
    # Emotion statistics
    emotion_counts = defaultdict(int)
    for sample in samples:
        if "emotion" in sample:
            emotion_counts[sample["emotion"]["primary_emotion"]] += 1
    
    if emotion_counts:
        print(f"   - Emotion Distribution:")
        for emotion, count in sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"     {emotion}: {count} ({count/len(samples)*100:.1f}%)")
    
    # Speaking style statistics
    style_counts = defaultdict(lambda: defaultdict(int))
    for sample in samples:
        if "speaking_style" in sample:
            for key, value in sample["speaking_style"].items():
                if isinstance(value, bool):
                    if value:
                        style_counts[key]["yes"] += 1
                else:
                    style_counts[key][value] += 1
    
    if style_counts:
        print(f"   - Speaking Style Distribution:")
        for style_type, values in style_counts.items():
            print(f"     {style_type}:")
            for value, count in sorted(values.items(), key=lambda x: x[1], reverse=True):
                print(f"       {value}: {count}")


def create_enhanced_model_card():
    """Create an enhanced model card with phoneme and prosody information."""
    model_card = {
        "character_name": "BT-7274",
        "source": "Titanfall 2",
        "version": "2.0",
        "features": [
            "phoneme_transcription",
            "prosody_analysis", 
            "emotion_tagging",
            "speaking_style"
        ],
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
        "phoneme_info": {
            "backend": "espeak",
            "language": "en-us",
            "stress_marks": True,
            "phoneme_set": "IPA"
        },
        "prosody_info": {
            "features": [
                "mean_pitch_hz",
                "pitch_range_hz",
                "mean_energy",
                "energy_range",
                "tempo_bpm",
                "spectral_centroid",
                "spectral_rolloff"
            ],
            "analysis_tool": "librosa"
        },
        "emotion_categories": [
            "urgent",
            "cautious",
            "positive",
            "concerned",
            "determined",
            "neutral",
            "questioning",
            "commanding"
        ],
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
                "Military-themed applications",
                "Voice cloning research"
            ],
            "limitations": [
                "Game-specific terminology",
                "Limited emotional range",
                "Synthetic voice only"
            ],
            "training_recommendations": [
                "Use phoneme transcriptions for pronunciation accuracy",
                "Use prosody features for natural speech patterns",
                "Use emotion tags for expressive synthesis",
                "Combine all features for best results"
            ]
        }
    }
    
    # Save enhanced model card
    training_dir = Path(__file__).parent.parent / "training_data"
    with open(training_dir / "bt7274_enhanced_model_card.json", "w") as f:
        json.dump(model_card, f, indent=2)
    
    print("✓ Created enhanced BT-7274 model card")


if __name__ == "__main__":
    create_enhanced_training_dataset()
    create_enhanced_model_card()
    print("\n🎉 Enhanced dataset generation complete!")