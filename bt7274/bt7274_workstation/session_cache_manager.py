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

When a session ends, data is archived to logs/archive/sessions.jsonl
with timestamped entries, and the session_cache is cleared for the next session.
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
from bt7274.bt7274_workstation.log_manager import get_archive_dir
ARCHIVE_DIR = get_archive_dir()


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
    """Persist the last known location (encrypted)."""
    from bt7274.bt7274_workstation.log_encryption import LogEncryptor
    from bt7274.bt7274_workstation.log_manager import get_encryption_key_path, ensure_encryption_key
    ensure_encryption_key()
    encryptor = LogEncryptor(key_path=str(get_encryption_key_path()))
    data = {
        "lat": lat,
        "lon": lon,
        "city": city,
        "region": region,
        "country": country,
        "timestamp": datetime.now().isoformat(),
    }
    encrypted = encryptor.encrypt_json(data)
    path = get_location_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(encrypted)
        return True
    except Exception:
        return False


def load_location_cache() -> Optional[dict]:
    """Load the last known location (decrypted)."""
    from bt7274.bt7274_workstation.log_encryption import LogEncryptor
    from bt7274.bt7274_workstation.log_manager import get_encryption_key_path, ensure_encryption_key
    path = get_location_cache_path()
    if not path.exists():
        return None
    try:
        ensure_encryption_key()
        encryptor = LogEncryptor(key_path=str(get_encryption_key_path()))
        with open(path, "r") as f:
            encrypted = f.read()
        return encryptor.decrypt_json(encrypted)
    except Exception:
        return None


# ─── Session state ────────────────────────────────────────────────

def save_session_state(state: dict[str, Any]) -> bool:
    """Persist current session metadata (encrypted)."""
    from bt7274.bt7274_workstation.log_encryption import LogEncryptor
    from bt7274.bt7274_workstation.log_manager import get_encryption_key_path, ensure_encryption_key
    ensure_encryption_key()
    encryptor = LogEncryptor(key_path=str(get_encryption_key_path()))
    encrypted = encryptor.encrypt_json(state)
    path = get_session_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(encrypted)
        return True
    except Exception:
        return False


def load_session_state() -> Optional[dict]:
    """Load the last session state (decrypted)."""
    from bt7274.bt7274_workstation.log_encryption import LogEncryptor
    from bt7274.bt7274_workstation.log_manager import get_encryption_key_path, ensure_encryption_key
    path = get_session_state_path()
    if not path.exists():
        return None
    try:
        ensure_encryption_key()
        encryptor = LogEncryptor(key_path=str(get_encryption_key_path()))
        with open(path, "r") as f:
            encrypted = f.read()
        return encryptor.decrypt_json(encrypted)
    except Exception:
        return None


# ─── Speaker latents (PyTorch) ────────────────────────────────────

def _hash_references(reference_paths: list[str]) -> str:
    """Create a stable hash of the reference file list for cache invalidation."""
    import hashlib
    # Sort for stability, hash the combined paths + sizes + mtimes
    hasher = hashlib.md5()
    for p in sorted(reference_paths):
        path = Path(p)
        if path.exists():
            stat = path.stat()
            hasher.update(f"{path.name}:{stat.st_size}:{stat.st_mtime}".encode())
    return hasher.hexdigest()[:12]


def save_speaker_latents(
    gpt_cond_latent: Any,
    speaker_embedding: Any,
    reference_paths: list[str] | None = None,
) -> bool:
    """Persist XTTS speaker conditioning latents."""
    try:
        import torch
        path = get_speaker_latents_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "gpt_cond_latent": gpt_cond_latent,
            "speaker_embedding": speaker_embedding,
            "timestamp": datetime.now().isoformat(),
        }
        if reference_paths:
            payload["reference_hash"] = _hash_references(reference_paths)
            payload["reference_count"] = len(reference_paths)
        torch.save(payload, path)
        return True
    except Exception:
        return False


def load_speaker_latents(
    reference_paths: list[str] | None = None,
) -> tuple[Any, Any]:
    """Load XTTS speaker conditioning latents.

    If reference_paths is provided, the cached latents are only returned
    if they were computed from the same set of reference files.
    """
    try:
        import torch
        path = get_speaker_latents_path()
        if path.exists():
            data = torch.load(path, weights_only=False)
            # Validate reference hash if provided
            if reference_paths and "reference_hash" in data:
                expected = _hash_references(reference_paths)
                if data["reference_hash"] != expected:
                    return None, None  # References changed, invalidate cache
            return data.get("gpt_cond_latent"), data.get("speaker_embedding")
    except Exception:
        pass
    return None, None


# ─── End-of-session archive & clear ───────────────────────────────

def archive_and_clear_session() -> Optional[Path]:
    """
    Archive the current session cache to logs/archive/sessions.jsonl
    with timestamped entries, and clear the session_cache directory for the next session.

    Returns the archive file path, or None if nothing to archive.
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

    # Create centralized archive directory if needed
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Use a single sessions.jsonl file for all archives
    archive_file = ARCHIVE_DIR / "sessions.jsonl"

    # Collect all session cache files into a temporary directory structure
    session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_state = load_session_state()
    
    file_counts = {}
    file_data = {}

    # Collect metadata about files
    for subdir in SESSION_CACHE_DIR.iterdir():
        if subdir.is_dir():
            file_count = sum(1 for _ in subdir.rglob("*") if _.is_file())
            file_counts[subdir.name] = file_count
        elif subdir.is_file():
            file_counts[subdir.name] = 1

    # Create archive entry (JSONL format with timestamped metadata)
    archive_entry = {
        "timestamp": datetime.now().isoformat(),
        "session_timestamp": session_timestamp,
        "session_state": session_state,
        "file_counts": file_counts,
        "cache_location": str(SESSION_CACHE_DIR),
    }

    # Encrypt the archive entry before writing
    try:
        from bt7274.bt7274_workstation.log_encryption import LogEncryptor
        from bt7274.bt7274_workstation.log_manager import get_encryption_key_path, ensure_encryption_key
        ensure_encryption_key()
        encryptor = LogEncryptor(key_path=str(get_encryption_key_path()))
        encrypted_entry = encryptor.encrypt_json(archive_entry)
    except Exception:
        encrypted_entry = json.dumps(archive_entry, ensure_ascii=False)

    # Append to centralized archive file
    try:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        with open(archive_file, "a", encoding="utf-8") as f:
            f.write(encrypted_entry + "\n")
    except Exception as e:
        # Best-effort: log but don't fail
        pass

    # Prune old archive entries (keep last 100 sessions)
    _prune_archive(archive_file, max_entries=100)

    # Clear session cache
    for item in SESSION_CACHE_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        elif item.is_file():
            item.unlink()

    return archive_file


def _prune_archive(archive_file: Path, max_entries: int = 100):
    """Keep only the most recent N entries in the archive file."""
    if not archive_file.exists():
        return
    try:
        with open(archive_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= max_entries:
            return
        # Keep only the last max_entries lines
        with open(archive_file, "w", encoding="utf-8") as f:
            f.writelines(lines[-max_entries:])
    except Exception:
        pass


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
