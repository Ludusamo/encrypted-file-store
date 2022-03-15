from Crypto.Cipher import AES
from hashlib import sha256
import os, random, struct, json, base64
import logging
import time

from .error import InvalidPassword

class FileEncrypter:
    def __init__(self, password):
        self.password = password.encode('utf-8')

    def encrypt_file(self, path, outpath, chunksize=64*1024*1024):
        start = time.time()
        key = sha256(self.password).digest()
        iv = os.urandom(16)
        encryptor = AES.new(key, AES.MODE_CBC, iv)
        filesize = os.path.getsize(path)
        with open(path, 'rb') as in_file, open(outpath, 'wb') as out_file:
            out_file.write(struct.pack('<Q', filesize))
            out_file.write(iv)
            while True:
                chunk = in_file.read(chunksize)
                if len(chunk) == 0:
                    break
                elif len(chunk) % 16 != 0:
                    chunk += b' ' * (16 - len(chunk) % 16)
                out_file.write(encryptor.encrypt(chunk))
        logging.info('Encrypting took {} seconds'.format(time.time() - start))

    def decrypt_file(self, path, outpath, filetype, chunksize=64*1024*1024):
        start = time.time()
        with open(path, 'rb') as in_file, open('{}.{}'.format(outpath, filetype), 'wb') as out_file:
            key = sha256(self.password).digest()
            origsize = struct.unpack('<Q', in_file.read(struct.calcsize('Q')))[0]
            iv = in_file.read(16)
            decryptor = AES.new(key, AES.MODE_CBC, iv)
            while True:
                chunk = in_file.read(chunksize)
                if len(chunk) == 0:
                    break
                out_file.write(decryptor.decrypt(chunk))
            out_file.truncate(origsize)
        logging.info('Decrypting took {} seconds'.format(time.time() - start))

    def decrypt_json(self, path, chunksize=64*1024*1024):
        with open(path, 'rb') as in_file:
            key = sha256(self.password).digest()
            origsize = struct.unpack('<Q', in_file.read(struct.calcsize('Q')))[0]
            iv = in_file.read(16)
            decryptor = AES.new(key, AES.MODE_CBC, iv)
            chunks = []
            while True:
                chunk = in_file.read(chunksize)
                if len(chunk) == 0:
                    break
                chunks.append(decryptor.decrypt(chunk).decode('utf-8'))
            json_str = ''.join(chunks)
            json_str.strip()

            metadata = None
            try:
                metadata = json.loads(json_str)
            except Exception as e:
                print(e)
                raise InvalidPassword()
            return metadata
