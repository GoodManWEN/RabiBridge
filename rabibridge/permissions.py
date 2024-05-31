from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from functools import partial 
import hashlib

from .utils import encode_pwd, decode_pwd

def aes_encryption(plaintext: bytes, secret: bytes) -> bytes:
    _h = hashlib.sha512(secret).digest()
    key, iv = _h[:32], _h[32:48]
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    # encrypt
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    return ciphertext

def aes_decryption(ciphertext: bytes, secret: bytes) -> bytes:
    _h = hashlib.sha512(secret).digest()
    key, iv = _h[:32], _h[32:48]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    # decrypt
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    # delete padding
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
    return plaintext

encrypt_pwd = partial(encode_pwd, encrypt_function=aes_encryption)
decrypt_pwd = partial(decode_pwd, decrypt_function=aes_decryption)
