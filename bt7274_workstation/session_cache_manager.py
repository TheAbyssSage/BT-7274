"""
Session Cache Manager for BT-7274.

Provides centralized utilities for session-scoped temporary data:
- TTS output files
- STT temporary audio
- TTS response cache index
- Semantic matching vectors
- Location cache
- Model warmup artifacts (speaker latents)
- Session state

When a session ends, data is archived to logs/session_archive/<timestamp>/
and the session_cache is cleared for the next session.
"""

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np

# Base session cache directory (relative to project root)
SESSION_CACHE_DIR = Path(__file__).parent.parent / "bt7274_workstation" / "session_cache"

# Archive directory for ended sessions
ARCHIVE_DIR = Path(__file__).parent.parent / "logs" / "session_archive"


def _ensure_dirs():
    """Ensure all session cache subdirectories exist."""
    for subdir in (
        "tts_outputs",
        "stt_temp",
        "semantic",
    ):
        (SESSION_CACHE_DIR / subdir).mkdir(parents=True, exist_ok=True)


def get_session_cache(subdir: str = "") -> Path:
    """Return a session cache path, creating subdirectories as needed."""
    path = SESSION_CACHE_DIR / subdir if subdir else SESSION_CACHE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_tts_output_dir() -> Path:
    """Directory for generated TTS WAV files."""
    return get_session_cache("tts_outputs")


def get_stt_temp_dir() -> Path:
    """Directory for temporary STT processed audio."""
    return get_session_cache("stt_temp")


def get_semantic_dir() -> Path:
    """Directory for cached semantic matching vectors."""
    return get_session_cache("semantic")


def get_location_cache_path() -> Path:
    """Path to the location cache JSON file."""
    return SESSION_CACHE_DIR / "location_cache.json"


def get_tts_cache_index_path() -> Path:
    """Path to the TTS response cache index JSON file."""
    return SESSION_CACHE_DIR / "tts_cache_index.json"


def get_speaker_latents_path() -> Path:
    """Path to cached speaker conditioning latents."""
    return SESSION_CACHE_DIR / "speaker_latents.pt"


def get_session_state_path() -> Path:
    """Path to the current session state JSON file."""
    return SESSION_CACHE_DIR / "session_state.json"


# ─── Persistence helpers ──────────────────────────────────────────

def save_json(path: Path, data: dict) -> bool:
    """Atomically save a dict to a JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
        return True
    except Exception as e:
        # Best-effort: don't crash the pipeline
        return False


def load_json(path: Path, default: Optional[dict] = None) -> Optional[dict]:
    """Load a dict from a JSON file, returning default on failure."""
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_numpy(path: Path, arr: np.ndarray) -> bool:
    """Save a numpy array to disk."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, arr)
        return True
    except Exception:
        return False


def load_numpy(path: Path) -> Optional[np.ndarray]:
    """Load a numpy array from disk."""
    try:
        if path.exists():
            return np.load(path)
    except Exception:
        pass
    return None


# ─── TTS cache index ──────────────────────────────────────────────

def save_tts_cache_index(cache: dict[str, str]) -> bool:
    """Persist the TTS response cache index to disk."""
    return save_json(get_tts_cache_index_path(), cache)


def load_tts_cache_index() -> dict[str, str]:
    """Load the TTS response cache index from disk."""
    data = load_json(get_tts_cache_index_path(), {})
    return data if isinstance(data, dict) else {}


# ─── Semantic vectors ─────────────────────────────────────────────

def save_semantic_vectors(
    vectorizer_state: dict,
    clip_matrix: np.ndarray,
    phrases: list[str],
) -> bool:
    """Persist semantic matching artifacts."""
    sem_dir = get_semantic_dir()
    ok = True
    ok &= save_json(sem_dir / "phrases.json", {"phrases": phrases})
    ok &= save_numpy(sem_dir / "clip_matrix.npy", clip_matrix)
    # vectorizer is pickled via joblib or json-serialized params
    ok &= save_json(sem_dir / "vectorizer_state.json", vectorizer_state)
    return ok


def load_semantic_vectors() -> tuple[Optional[dict], Optional[np.ndarray], list[str]]:
    """Load semantic matching artifacts."""
    sem_dir = get_semantic_dir()
    phrases_data = load_json(sem_dir / "phrases.json", {})
    phrases = phrases_data.get("phrases", []) if isinstance(phrases_data, dict) else []
    clip_matrix = load_numpy(sem_dir / "clip_matrix.npy")
    vectorizer_state = load_json(sem_dir / "vectorizer_state.json", {})
    return vectorizer_state, clip_matrix, phrases


# ─── Location cache ───────────────────────────────────────────────

def save_location_cache(
    lat: Optional[float],
    lon: Optional[float],
    city: str,
    region: str,
    country: str,
) -> bool:
    """Persist the last known location."""
    data = {
        "lat": lat,
        "lon": lon,
        "city": city,
        "region": region,
        "country": country,
        "timestamp": datetime.now().isoformat(),
    }
    return save_json(get_location_cache_path(), data)


def load_location_cache() -> Optional[dict]:
    """Load the last known location."""
    return load_json(get_location_cache_path(), None)


# ─── Session state ────────────────────────────────────────────────

def save_session_state(state: dict[str, Any]) -> bool:
    """Persist current session metadata."""
    return save_json(get_session_state_path(), state)


def load_session_state() -> Optional[dict]:
    """Load the last session state."""
    return load_json(get_session_state_path(), None)


# ─── Speaker latents (PyTorch) ────────────────────────────────────

def save_speaker_latents(gpt_cond_latent: Any, speaker_embedding: Any) -> bool:
    """Persist XTTS speaker conditioning latents."""
    try:
        import torch
        path = get_speaker_latents_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "gpt_cond_latent": gpt_cond_latent,
                "speaker_embedding": speaker_embedding,
                "timestamp": datetime.now().isoformat(),
            },
            path,
        )
        return True
    except Exception:
        return False


def load_speaker_latents() -> tuple[Any, Any]:
    """Load XTTS speaker conditioning latents."""
    try:
        import torch
        path = get_speaker_latents_path()
        if path.exists():
            data = torch.load(path, weights_only=False)
            return data.get("gpt_cond_latent"), data.get("speaker_embedding")
    except Exception:
        pass
    return None, None


# ─── End-of-session archive & clear ───────────────────────────────

def archive_and_clear_session() -> Optional[Path]:
    """
    Archive the current session cache to logs/session_archive/<timestamp>/
    and clear the session_cache directory for the next session.

    Returns the archive directory path, or None if nothing to archive.
    """
    if not SESSION_CACHE_DIR.exists():
        return None

    # Check if there's anything worth archiving
    has_content = False
    for item in SESSION_CACHE_DIR.rglob("*"):
        if item.is_file():
            has_content = True
            break

    if not has_content:
        return None

    # Create archive directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = ARCHIVE_DIR / timestamp
    archive_path.mkdir(parents=True, exist_ok=True)

    # Write session summary document
    session_state = load_session_state()
    summary = {
        "archived_at": datetime.now().isoformat(),
        "session_state": session_state,
        "file_counts": {},
    }

    # Copy files to archive
    for subdir in SESSION_CACHE_DIR.iterdir():
        if subdir.is_dir():
            dest = archive_path / subdir.name
            shutil.copytree(subdir, dest, dirs_exist_ok=True)
            # Count files
            file_count = sum(1 for _ in subdir.rglob("*") if _.is_file())
            summary["file_counts"][subdir.name] = file_count
        elif subdir.is_file():
            shutil.copy2(subdir, archive_path / subdir.name)
            summary["file_counts"][subdir.name] = 1

    # Write summary document
    save_json(archive_path / "session_summary.json", summary)

    # Clear session cache
    for item in SESSION_CACHE_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        elif item.is_file():
            item.unlink()

    return archive_path


def clear_session_cache():
    """Clear the session cache without archiving."""
    if not SESSION_CACHE_DIR.exists():
        return
    for item in SESSION_CACHE_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        elif item.is_file():
            item.unlink()


# Ensure directories exist on import
_ensure_dirs()
