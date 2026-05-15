#!/usr/bin/env python3
"""
Auto-select the best BT-7274 voice clips for XTTS v2 multi-reference conditioning.

Criteria for selection:
1. Clean, isolated voice (no music, no combat sounds)
2. Clear pronunciation
3. Duration 2-6 seconds (XTTS sweet spot)
4. Iconic BT lines that represent his voice well
5. Variety of emotional tones (neutral, urgent, calm)

Usage:
    python bt7274_assistant/scripts/select_bt_references.py

This creates:
    bt7274_assistant/dataset/bt_references.json  (list of selected clip paths)
    bt7274_assistant/dataset/bt_references/      (symlinks or copies of selected clips)
"""

import json
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

sf = None
HAS_SOUNDFILE = False
try:
    import soundfile as _sf
    sf = _sf
    HAS_SOUNDFILE = True
except ImportError:
    pass


# Hand-curated list of the best BT-7274 voice clips for voice cloning.
# These are iconic, clean, and representative of BT's voice.
# Selected based on:
#   - Clear, isolated voice
#   - No background music or combat sounds
#   - Duration 2-6 seconds
#   - Variety of tones (calm, urgent, formal)
#   - Iconic lines that pilots recognize
CURATED_BT_REFERENCES = [
    # Core identity lines (calm, formal)
    "i_am_bt7274.wav",
    "protocol_1_link_to_pilot.wav",
    "protocol_2_uphold_the_mission.wav",
    "protocol_3_protect_the_pilot.wav",
    "you_may_call_me_bt.wav",
    "neural_link_established.wav",
    
    # Status/operational (confident, calm)
    "systems_operational.wav",
    "all_systems_nominal.wav",
    "standing_by_pilot.wav",
    "ready_to_proceed.wav",
    "embark_when_ready.wav",
    
    # Mission/combat (urgent, determined)
    "our_orders_are_to_resume_special_operation_217.wav",
    "rendezvous_with_major_anderson_of_the_srs.wav",
    "engaging_enemy_titans.wav",
    "weapon_systems_online.wav",
    
    # Pilot care (concerned, loyal)
    "be_careful_pilot.wav",
    "are_you_alright_pilot.wav",
    "i_will_not_lose_another_pilot.wav",
    
    # Acknowledgment (neutral, military)
    "understood.wav",
    "acknowledged.wav",
    "copy_that.wav",
    "affirmative.wav",
    
    # Personality/dry humor
    "trust_me.wav",
    "i_am_a_vanguard_class_titan.wav",
    "my_systems_are_rebooting.wav",
]


def find_bt_clips_dir() -> Path:
    """Find the BT clips directory."""
    # Try relative to project root
    project_root = Path(__file__).parent.parent.parent
    clips_dir = project_root / "BT-7274.Voicepack" / "bt_clips"
    if clips_dir.exists():
        return clips_dir
    
    # Try relative to this script (one level up from scripts/)
    clips_dir = Path(__file__).parent.parent.parent / "BT-7274.Voicepack" / "bt_clips"
    if clips_dir.exists():
        return clips_dir
    
    raise FileNotFoundError("BT clips directory not found. Expected: bt7274/BT-7274.Voicepack/bt_clips")


def normalize_filename(filename: str) -> str:
    """Normalize a filename for matching."""
    name = filename.lower().replace('.wav', '')
    name = name.replace('_', ' ').replace('-', ' ')
    # Remove leading numbers like "001_"
    parts = name.split('_', 1)
    if parts[0].isdigit() and len(parts) > 1:
        name = parts[1]
    return name.strip()


def find_matching_clip(clips_dir: Path, target_name: str) -> Tuple[Optional[Path], float]:
    """Find the best matching clip in the directory."""
    target_normalized = normalize_filename(target_name)
    
    best_match = None
    best_score = -1
    
    for clip_file in clips_dir.glob("*.wav"):
        clip_normalized = normalize_filename(clip_file.name)
        
        # Exact match
        if clip_normalized == target_normalized:
            return clip_file, 1.0
        
        # Partial match score
        score = 0
        target_words = set(target_normalized.split())
        clip_words = set(clip_normalized.split())
        
        # Word overlap
        overlap = len(target_words & clip_words)
        score += overlap / max(len(target_words), 1)
        
        # Check if target is substring of clip or vice versa
        if target_normalized in clip_normalized or clip_normalized in target_normalized:
            score += 0.5
        
        if score > best_score:
            best_score = score
            best_match = clip_file
    
    return best_match, best_score


def get_clip_duration(clip_path: Path) -> float:
    """Get the duration of a WAV file in seconds."""
    if not HAS_SOUNDFILE:
        return 0.0
    assert sf is not None
    try:
        info = sf.info(str(clip_path))
        return info.duration
    except Exception:
        return 0.0


def select_bt_references(
    clips_dir: Path,
    output_dir: Path,
    max_refs: int = 5,
    min_duration: float = 0.5,
    max_duration: float = 8.0,
) -> List[Path]:
    """Select the best BT reference clips for XTTS v2."""
    
    selected = []
    
    for target_name in CURATED_BT_REFERENCES:
        clip_path, score = find_matching_clip(clips_dir, target_name)
        
        if clip_path is None:
            print(f"  [WARN] No match found for: {target_name}")
            continue
        
        if score < 0.3:
            print(f"  [WARN] Poor match ({score:.2f}) for: {target_name} -> {clip_path.name}")
            continue
        
        duration = get_clip_duration(clip_path)
        
        if duration < min_duration:
            print(f"  [SKIP] Too short ({duration:.1f}s): {clip_path.name}")
            continue
        
        if duration > max_duration:
            print(f"  [SKIP] Too long ({duration:.1f}s): {clip_path.name}")
            continue
        
        selected.append(clip_path)
        print(f"  [OK] {clip_path.name} ({duration:.1f}s)")
        
        if len(selected) >= max_refs:
            break
    
    return selected


def create_reference_package(
    selected_clips: List[Path],
    output_dir: Path,
    json_path: Path,
) -> None:
    """Create the reference package: JSON manifest + copied clips."""
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy clips to output dir with clean names
    manifest = []
    for i, clip_path in enumerate(selected_clips, 1):
        clean_name = f"bt_ref_{i:02d}_{normalize_filename(clip_path.name).replace(' ', '_')}.wav"
        dest = output_dir / clean_name
        shutil.copy2(clip_path, dest)
        manifest.append({
            "index": i,
            "original": str(clip_path),
            "reference": str(dest),
            "name": clean_name,
        })
    
    # Write manifest
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            "references": manifest,
            "count": len(manifest),
            "source": "BT-7274 original voice clips",
            "model": "XTTS v2 multi-reference",
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\nCreated {len(manifest)} BT reference clips in: {output_dir}")
    print(f"Manifest written to: {json_path}")


def main():
    print("=" * 60)
    print("BT-7274 Voice Reference Selector")
    print("=" * 60)
    
    clips_dir = find_bt_clips_dir()
    print(f"\nBT clips directory: {clips_dir}")
    print(f"Total clips available: {len(list(clips_dir.glob('*.wav')))}")
    
    output_dir = Path(__file__).parent.parent / "dataset" / "bt_references"
    json_path = Path(__file__).parent.parent / "dataset" / "bt_references.json"
    
    print("\nSelecting best reference clips...")
    selected = select_bt_references(clips_dir, output_dir)
    
    if not selected:
        print("\n[ERROR] No suitable reference clips found!")
        return 1
    
    create_reference_package(selected, output_dir, json_path)
    
    print("\n" + "=" * 60)
    print("Done! Update config.yaml to use:")
    print(f"  reference_wav: {output_dir}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit(main())
