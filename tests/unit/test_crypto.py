"""Tests für TokenCipher + generate_master_key."""

from __future__ import annotations

import pytest

from eve.utils.crypto import TokenCipher, generate_master_key


def test_generated_key_works_for_cipher():
    key = generate_master_key()
    cipher = TokenCipher(key)
    encrypted = cipher.encrypt("secret-token-12345")
    assert cipher.decrypt(encrypted) == "secret-token-12345"


def test_encrypt_yields_bytes():
    key = generate_master_key()
    cipher = TokenCipher(key)
    encrypted = cipher.encrypt("hello")
    assert isinstance(encrypted, bytes)
    # Cipher-bytes sollten nicht mit "hello" anfangen (offensichtlich verschlüsselt)
    assert b"hello" not in encrypted


def test_different_keys_cannot_decrypt():
    from cryptography.fernet import InvalidToken

    cipher_a = TokenCipher(generate_master_key())
    cipher_b = TokenCipher(generate_master_key())

    encrypted = cipher_a.encrypt("secret")
    with pytest.raises(InvalidToken):
        cipher_b.decrypt(encrypted)


def test_invalid_key_raises_clear_error():
    with pytest.raises(ValueError, match="EVE_MASTER_KEY"):
        TokenCipher("not-a-valid-fernet-key")


def test_roundtrip_unicode():
    key = generate_master_key()
    cipher = TokenCipher(key)
    plaintext = "Tëst mit Ümläüten 🚀 and emojis"
    encrypted = cipher.encrypt(plaintext)
    assert cipher.decrypt(encrypted) == plaintext
