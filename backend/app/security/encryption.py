"""
Encryption Service
==================

Protocol for at-rest and in-transit encryption operations.
All encryption uses on-prem key management — no cloud KMS.

At rest: AES-256-GCM for all index files, graph stores, and logs.
In transit: TLS 1.3 / mTLS for all in-cluster communication.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class EncryptionConfig(BaseModel):
    """Encryption configuration per data classification level."""

    algorithm: str = Field(
        default="AES-256-GCM",
        description="Encryption algorithm for data at rest",
    )
    key_scope: str = Field(
        default="per-domain",
        description='Key scope: "per-tenant", "per-domain", or "global"',
    )
    key_id: str = Field(
        default="",
        description="Key identifier in on-prem key store",
    )

    model_config = {"extra": "forbid"}


@runtime_checkable
class EncryptionService(Protocol):
    """
    Protocol for data encryption operations.

    Implementations must:
    - Use only on-prem key storage (no cloud KMS)
    - Support AES-256-GCM for at-rest encryption
    - Never expose raw key material in logs or exceptions
    - Fail-closed on any encryption/decryption error
    """

    def encrypt(self, plaintext: bytes, key_id: str) -> bytes:
        """
        Encrypt plaintext data using the specified key.

        Args:
            plaintext: Data to encrypt
            key_id: Key identifier in on-prem key store

        Returns:
            Ciphertext (including nonce/IV as prefix)

        Raises:
            EncryptionError on failure
        """
        ...

    def decrypt(self, ciphertext: bytes, key_id: str) -> bytes:
        """
        Decrypt ciphertext data using the specified key.

        Args:
            ciphertext: Data to decrypt (nonce/IV prefixed)
            key_id: Key identifier in on-prem key store

        Returns:
            Plaintext data

        Raises:
            EncryptionError on failure
        """
        ...

    def get_key_for_classification(self, classification: str) -> str:
        """
        Resolve the encryption key ID for a given data classification level.

        Args:
            classification: Sensitivity level (PUBLIC, INTERNAL, CONFIDENTIAL, SECRET)

        Returns:
            Key ID from the on-prem key store
        """
        ...

    def rotate_key(self, old_key_id: str, new_key_id: str) -> bool:
        """
        Initiate key rotation — mark old key for re-encryption.

        This is an administrative operation that should be audit-logged.

        Returns:
            True if rotation was initiated successfully
        """
        ...
