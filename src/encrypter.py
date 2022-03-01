from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from hashlib import sha256
import os, random, struct, json, base64

from .error import InvalidPassword

class FileEncrypter:
    def __init__(self, password):
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'',
            iterations=390000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8')))
        self.fernet = Fernet(key)

    def encrypt(self, path, outpath=None, chunksize=64*1024):
        if not outpath:
            outpath = path + '/content'

        with open(path, 'rb') as in_file:
            encrypted = self.fernet.encrypt(in_file.read())
            with open(outpath, 'wb') as out_file:
                out_file.write(encrypted)

    def decrypt(self, path, outpath, filetype='txt', chunksize=64*1024):
        with open(path, 'rb') as in_file:
            decrypted = self.fernet.decrypt(in_file.read())
            with open('{}.{}'.format(outpath, filetype), 'wb') as out_file:
                out_file.write(decrypted)

    def decrypt_json(self, path, chunksize=64*1024):
        with open(path, 'rb') as in_file:
            decrypted = self.fernet.decrypt(in_file.read())
            json_str = decrypted.decode('utf-8')

            metadata = None
            try:
                metadata = json.loads(json_str)
            except Exception as e:
                print(e)
                raise InvalidPassword()
            return metadata
