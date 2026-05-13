import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt(plaintext: str, key: str) -> str:
    key_bytes = key.encode("utf-8")[:32].ljust(32, b"\0")
    nonce = os.urandom(12)
    aesgcm = AESGCM(key_bytes)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt(ciphertext_b64: str, key: str) -> str:
    key_bytes = key.encode("utf-8")[:32].ljust(32, b"\0")
    raw = base64.b64decode(ciphertext_b64)
    nonce = raw[:12]
    ciphertext = raw[12:]
    aesgcm = AESGCM(key_bytes)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
