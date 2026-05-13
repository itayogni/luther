from luther.crypto import encrypt, decrypt


def test_encrypt_decrypt_roundtrip():
    key = "a" * 32
    plaintext = "my-secret-token-12345"
    encrypted = encrypt(plaintext, key)
    assert encrypted != plaintext
    decrypted = decrypt(encrypted, key)
    assert decrypted == plaintext


def test_encrypt_produces_different_output_each_time():
    key = "a" * 32
    plaintext = "same-input"
    enc1 = encrypt(plaintext, key)
    enc2 = encrypt(plaintext, key)
    assert enc1 != enc2


def test_decrypt_with_wrong_key_fails():
    import pytest

    key1 = "a" * 32
    key2 = "b" * 32
    encrypted = encrypt("secret", key1)
    with pytest.raises(Exception):
        decrypt(encrypted, key2)
