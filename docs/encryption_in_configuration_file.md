# Encryption and Decryption with secret

The authentication key is protected by standard AES algorithm, and the ciphertext is created using following code:

```python
from rabibridge import encrypt_pwd

secret = 'my secret'
password = '123456'
print(encrypt_pwd(password, secret))
# >>> /PVbueoeqoyjzZipLBXIow==
```