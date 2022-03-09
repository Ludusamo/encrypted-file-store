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

    def encrypt(self, path, outpath, chunksize=64*1024):
        with open(path, 'rb') as in_file, open(outpath, 'wb') as out_file:
            while True:
                chunk = in_file.read(chunksize)
                if len(chunk) == 0:
                    break
                encrypted = self.fernet.encrypt(chunk)
                out_file.write(struct.pack('<I', len(encrypted)))
                out_file.write(encrypted)
                if len(chunk) < chunksize:
                    break

    def decrypt(self, path, outpath, filetype):
        with open(path, 'rb') as in_file, open('{}.{}'.format(outpath, filetype), 'wb') as out_file:
            while True:
                size_data = in_file.read(4)
                if len(size_data) == 0:
                    break
                chunk = in_file.read(struct.unpack('<I', size_data)[0])
                decrypted = self.fernet.decrypt(chunk)
                out_file.write(decrypted)

    def decrypt_json(self, path):
        with open(path, 'rb') as in_file:
            chunks = []
            while True:
                size_data = in_file.read(4)
                if len(size_data) == 0:
                    break
                chunk = in_file.read(struct.unpack('<I', size_data)[0])
                decrypted = self.fernet.decrypt(chunk)
                chunks.append(decrypted.decode('utf-8'))
            json_str = ''.join(chunks)

            metadata = None
            try:
                metadata = json.loads(json_str)
            except Exception as e:
                print(e)
                raise InvalidPassword()
            return metadata
