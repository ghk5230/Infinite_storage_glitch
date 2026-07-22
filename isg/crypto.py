"""Optional AES-256-GCM encryption of the payload before encoding.

The key is derived from the password with scrypt (memory-hard, resists GPU
brute force). GCM authenticates as well as encrypts, so a wrong password is
detected reliably instead of producing garbage output.
"""

import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_MAGIC = b"ISGE"
_SALT_LEN = 16
_NONCE_LEN = 12


def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


def encrypt(data: bytes, password: str) -> bytes:
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(_derive_key(password, salt)).encrypt(nonce, data, None)
    return _MAGIC + salt + nonce + ciphertext


def decrypt(blob: bytes, password: str) -> bytes:
    if blob[: len(_MAGIC)] != _MAGIC:
        raise ValueError("payload is not ISG-encrypted data")
    salt = blob[len(_MAGIC): len(_MAGIC) + _SALT_LEN]
    nonce = blob[len(_MAGIC) + _SALT_LEN: len(_MAGIC) + _SALT_LEN + _NONCE_LEN]
    ciphertext = blob[len(_MAGIC) + _SALT_LEN + _NONCE_LEN:]
    try:
        return AESGCM(_derive_key(password, salt)).decrypt(nonce, ciphertext, None)
    except InvalidTag:
        raise ValueError("wrong password") from None
