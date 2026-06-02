"""Fernet-basierte Token-Verschlüsselung.

Genutzt um OAuth-Tokens client-side zu verschlüsseln bevor sie in Supabase
landen. Damit ist Supabase blind gegenüber den Klartext-Werten — selbst
Admin-Access zur DB enthüllt sie nicht ohne den Master-Key.

Master-Key wird aus `EVE_MASTER_KEY` (env) gelesen, muss ein gültiger
Fernet-Key sein (32-byte url-safe base64-encoded).

Beispiel:
    >>> from eve.utils.crypto import TokenCipher
    >>> cipher = TokenCipher(master_key="<32-byte-base64-key>")
    >>> encrypted = cipher.encrypt("my-access-token")
    >>> assert cipher.decrypt(encrypted) == "my-access-token"
"""

from __future__ import annotations

from cryptography.fernet import Fernet


class TokenCipher:
    """Symmetrische Verschlüsselung für OAuth-Tokens.

    Thin wrapper um cryptography.Fernet — separates Modul damit Tests +
    Helper das ohne Settings-Aufbau benutzen können.
    """

    def __init__(self, master_key: str) -> None:
        try:
            self._fernet = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)
        except Exception as e:
            raise ValueError(
                "EVE_MASTER_KEY ist kein valider Fernet-Key. "
                "Generiere einen neuen mit:\n"
                "  uv run python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            ) from e

    def encrypt(self, plaintext: str) -> bytes:
        """Verschlüsselt Klartext zu Cipher-Bytes (für BYTEA-Spalte in Postgres)."""
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        """Entschlüsselt Cipher-Bytes zurück zum Klartext-String."""
        return self._fernet.decrypt(ciphertext).decode("utf-8")


def generate_master_key() -> str:
    """Generiert einen frischen Fernet-Master-Key (32-byte url-safe base64)."""
    return Fernet.generate_key().decode("utf-8")
