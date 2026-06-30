import binascii
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

_KEY = b'Yg&tc%DEuh6%Zc^8'
_IV  = b'6oyZDr22E3ychjM%'

def encrypt_aes(data: bytes) -> str:
    cipher = AES.new(_KEY, AES.MODE_CBC, _IV)
    encrypted = cipher.encrypt(pad(data, AES.block_size))
    return binascii.hexlify(encrypted).decode()
