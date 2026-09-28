"""Symmetric encryption for secrets stored in the database (SMTP passwords).

Uses Fernet (AES-128-CBC + HMAC-SHA256). The key comes from ENCRYPTION_KEY.
If ENCRYPTION_KEY is not set, a key is derived from SECRET_KEY so local
development works out of the box; production should set a dedicated key
(ideally from a secrets manager / KMS).
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class DecryptionError(Exception):
    """Raised when stored ciphertext cannot be decrypted (e.g. the key changed)."""


@lru_cache
def _fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY.get_secret_value().strip()
    if not key:
        digest = hashlib.sha256(
            b"email-agent-smtp-credentials:" + settings.SECRET_KEY.get_secret_value().encode()
        ).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        raise DecryptionError("Stored credential could not be decrypted") from None
