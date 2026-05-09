"""Log encryption for BT-7274 sensitive data at rest.

Uses Fernet (AES-128-CBC + HMAC) symmetric encryption.
Key is stored in logs/bt7274.key — protect this file.
"""

import base64
import json
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet


def generate_key() -> bytes:
    """Generate a new Fernet encryption key. Returns base64-encoded bytes."""
    return Fernet.generate_key()


def load_key(key_path: str) -> bytes:
    """Load an encryption key from a file."""
    with open(key_path, "rb") as f:
        return f.read()


class LogEncryptor:
    """Encrypts/decrypts sensitive log data using Fernet symmetric encryption."""

    def __init__(self, key_path: Optional[str] = None, key_data: Optional[bytes] = None):
        if key_data is not None:
            self._fernet = Fernet(key_data)
        elif key_path is not None:
            if not os.path.exists(key_path):
                raise FileNotFoundError(f"Encryption key not found: {key_path}")
            key = load_key(key_path)
            self._fernet = Fernet(key)
        else:
            raise ValueError("Either key_path or key_data must be provided")

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string. Returns base64-encoded ciphertext."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext back to plaintext."""
        return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")

    def encrypt_json(self, data: dict) -> str:
        """Encrypt a dict as JSON. Returns base64-encoded ciphertext."""
        json_str = json.dumps(data, ensure_ascii=False)
        return self.encrypt(json_str)

    def decrypt_json(self, ciphertext: str) -> dict:
        """Decrypt a base64-encoded ciphertext back to a dict."""
        json_str = self.decrypt(ciphertext)
        return json.loads(json_str)
