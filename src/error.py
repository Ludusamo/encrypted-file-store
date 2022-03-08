from werkzeug.exceptions import HTTPException

class MissingSessionHash(HTTPException):
    code = 400
    description = "session_hash is missing from request input"

class InvalidSessionHash(HTTPException):
    code = 400
    description = "session_hash is invalid"

class NoJSONMetadata(HTTPException):
    code = 400
    description = "no json metadata attached"

class NoFile(HTTPException):
    code = 400
    description = "no file attached"

class FileStoreDNE(HTTPException):
    code = 404
    description = "file store does not exist"

class FileStoreExists(HTTPException):
    code = 409
    description = "file store already exists"

class FailedToWriteMetadata(HTTPException):
    code = 500
    description = "file store does not exist"

class InvalidPassword(HTTPException):
    code = 400
    description = 'invalid password on session'

class InvalidFileID(HTTPException):
    code = 400

    def __init__(self, file_id):
        self.description = 'invalid file id: {}'.format(file_id)

class InvalidTag(HTTPException):
    code = 400

    def __init__(self, tag):
        self.description = 'tag does not exist: {}'.format(tag)
