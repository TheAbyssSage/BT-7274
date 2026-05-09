# tests/test_log_encryption.py
import json
import os
import pytest
from pathlib import Path
from bt7274.bt7274_workstation.log_encryption import LogEncryptor, generate_key, load_key


class TestLogEncryptor:
    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def encryptor(self, temp_dir):
        key = generate_key()
        key_path = temp_dir / "bt7274.key"
        with open(key_path, "wb") as f:
            f.write(key)
        return LogEncryptor(key_path=str(key_path))

    def test_encrypt_decrypt_roundtrip(self, encryptor):
        original = "Pilot said: mission is a go at 0500 hours."
        encrypted = encryptor.encrypt(original)
        assert encrypted != original
        assert isinstance(encrypted, str)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_json_roundtrip(self, encryptor):
        original = {"pilot_message": "hello", "bt_response": "copy that", "timestamp": "2026-05-07T12:00:00"}
        encrypted = encryptor.encrypt_json(original)
        assert isinstance(encrypted, str)
        decrypted = encryptor.decrypt_json(encrypted)
        assert decrypted == original

    def test_different_keys_produce_different_ciphertext(self, temp_dir):
        key1 = generate_key()
        key2 = generate_key()
        assert key1 != key2

        encryptor1 = LogEncryptor(key_data=key1)
        encryptor2 = LogEncryptor(key_data=key2)

        text = "sensitive data"
        assert encryptor1.encrypt(text) != encryptor2.encrypt(text)

    def test_decrypt_with_wrong_key_fails(self, temp_dir):
        key1 = generate_key()
        key2 = generate_key()
        encryptor1 = LogEncryptor(key_data=key1)
        encryptor2 = LogEncryptor(key_data=key2)

        encrypted = encryptor1.encrypt("secret")
        with pytest.raises(Exception):
            encryptor2.decrypt(encrypted)

    def test_generate_key_creates_valid_key(self):
        key = generate_key()
        assert isinstance(key, bytes)
        assert len(key) == 44  # Base64-encoded 32-byte Fernet key

    def test_load_key_from_file(self, temp_dir):
        key = generate_key()
        key_path = temp_dir / "test.key"
        with open(key_path, "wb") as f:
            f.write(key)

        loaded = load_key(str(key_path))
        assert loaded == key

    def test_encryptor_raises_on_missing_key_file(self, temp_dir):
        with pytest.raises(FileNotFoundError):
            LogEncryptor(key_path=str(temp_dir / "nonexistent.key"))

    def test_encrypted_file_is_not_plaintext(self, encryptor, temp_dir):
        sensitive = "Pilot location: 50.9311, 5.3378"
        encrypted = encryptor.encrypt(sensitive)

        file_path = temp_dir / "test.enc"
        with open(file_path, "w") as f:
            f.write(encrypted)

        with open(file_path, "r") as f:
            content = f.read()
        assert "50.9311" not in content
        assert "Pilot" not in content
