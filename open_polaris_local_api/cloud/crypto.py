"""AES scheme used by the Tecnosystemi app (docs/app/http-flows/01-http-transport-auth.md)."""

import base64
import hashlib

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

SALT = "ns91wr48"
_IV = bytes(16)  # the app uses an all-zero IV


class PolarisCipher:
    """AES-256-CBC, key = SHA-256(device_id[:8] + SALT), zero IV."""

    def __init__(self, device_id: str):
        self._key = hashlib.sha256((device_id[:8] + SALT).encode()).digest()

    def _cipher(self) -> Cipher:
        return Cipher(algorithms.AES(self._key), modes.CBC(_IV))

    def encrypt(self, text: str) -> str:
        """Base64 like Android `Base64.encode(.., 0)`: 76-char lines, trailing newline."""
        padder = padding.PKCS7(128).padder()
        enc = self._cipher().encryptor()
        raw = enc.update(padder.update(text.encode()) + padder.finalize()) + enc.finalize()
        b64 = base64.b64encode(raw).decode()
        return "".join(b64[i:i + 76] + "\n" for i in range(0, len(b64), 76))

    def decrypt(self, b64: str) -> str:
        dec = self._cipher().decryptor()
        unpadder = padding.PKCS7(128).unpadder()
        data = dec.update(base64.b64decode(b64)) + dec.finalize()
        return (unpadder.update(data) + unpadder.finalize()).decode()

    def next_token(self, token: str) -> str:
        """`Functions.calcNewToken`: decrypt `<text>_<counter>`, counter+1, re-encrypt, strip newlines."""
        text, _, counter = self.decrypt(token).rpartition("_")
        return self.encrypt(f"{text}_{int(counter) + 1}").replace("\r", "").replace("\n", "")
