import json
import time
import os
import tempfile
from uuid import uuid4

from flask import Blueprint, request, send_file

from .session import get_session
from .util import error_payload

MAX_SESSION_TIME = 10 * 60 # 10 Minutes
BASE_METADATA = {'files': {}, 'tags': []}

bp = Blueprint('store', __name__, url_prefix='/api/store')

def _get_session(session_hash):
    session = get_session(session_hash)
    if not session:
        return None, error_payload('invalid session', 400)
    return session, None

def _get_filepath(name):
    data_filepath = os.environ.get('DATA_FILEPATH', 'data')
    return '{}/{}'.format(data_filepath, name)

def _get_metadata_path(session):
    data_filepath = os.environ.get('DATA_FILEPATH', 'data')
    return '{}/{}.metadata'.format(data_filepath, session['name'])

def _create_file(file_id, name, tags, filetype):
    return {
        'id': file_id,
        'name': name,
        'tags': list(set(tags)), # remove duplicates
        'filetype': filetype
    }

def encrypt_metadata(path, metadata, file_encrypter):
    with open(path + '.unencrypted', 'w') as f:
        json.dump(metadata, f)

    file_encrypter.encrypt(path + '.unencrypted', path)
    os.remove(path + '.unencrypted')

@bp.route('', methods=['POST'])
def store_endpoint():
    if request.method == 'POST':
        request_data = json.loads(request.data)
        if 'session_hash' not in request_data:
            return error_payload('missing session_hash in request data', 400)
        session, failure_payload = _get_session(request_data['session_hash'])
        if not session: return failure_payload
        filepath = _get_metadata_path(session)

        if os.path.exists(filepath):
            return error_payload('file store already exists', 409)

        unencrypted_filepath = '{}.unencrypted'.format(filepath)
        with open(unencrypted_filepath, 'w') as unencrypted_file:
            try:
                json.dump(BASE_METADATA, unencrypted_file)
            except Exception as e:
                print(e)
                return error_payload('failed to write base metadata file', 500)
        session['file_encrypter'].encrypt(unencrypted_filepath, filepath)
        os.remove(unencrypted_filepath)
        return {'status': 'success'}, 200


@bp.route('/metadata/file', methods=['GET'])
def store_file_metadata_endpoint():
    if request.method == 'GET':
        if 'session_hash' not in request.args:
            return error_payload('missing session_hash in url parameters', 400)
        session, failure_payload = _get_session(request.args['session_hash'])
        if not session: return failure_payload
        filepath = _get_metadata_path(session)

        if not os.path.exists(filepath):
            return json.dumps([]), 200

        metadata = session['file_encrypter'].decrypt_json(filepath)
        if not metadata:
            return error_payload('invalid password on session', 400)

        return json.dumps(metadata['files']), 200

@bp.route('/metadata/file/<file_id>', methods=['GET'])
def get_file_metadata_endpoint(file_id):
    print('hi')
    if request.method == 'GET':
        if 'session_hash' not in request.args:
            return error_payload('missing session_hash in url parameters', 400)
        session, failure_payload = _get_session(request.args['session_hash'])
        if not session: return failure_payload
        filepath = _get_metadata_path(session)

        if not os.path.exists(filepath):
            return json.dumps([]), 200

        metadata = session['file_encrypter'].decrypt_json(filepath)
        if not metadata:
            return error_payload('invalid password on session', 400)

        if file_id not in metadata['files']:
            return error_payload('invalid file id: {}'.format(file_id), 400)
        return metadata['files'][file_id], 200

@bp.route('/file', methods=['POST'])
def store_file_endpoint():
    if request.method == 'POST':
        if 'metadata' not in request.form:
            return error_payload('no json metadata attached', 400)
        request_data = json.loads(request.form['metadata'])
        if 'session_hash' not in request_data:
            return error_payload('missing session_hash in request data', 400)
        session, failure_payload = _get_session(request_data['session_hash'])
        if not session: return failure_payload
        meta_filepath = _get_metadata_path(session)

        if not os.path.exists(meta_filepath):
            return error_payload('file store does not exist', 404)

        if 'file' not in request.files:
            return error_payload('no file attached', 400)

        metadata = session['file_encrypter'].decrypt_json(meta_filepath)
        if not metadata:
            return error_payload('invalid password on session', 400)

        new_id = uuid4()
        while new_id in metadata['files']:
            new_id = uuid4()
        new_id = str(new_id)

        filepath = _get_filepath(new_id)
        uploaded_file = request.files['file']
        uploaded_file.save(filepath + '.unencrypted')
        session['file_encrypter'].encrypt(filepath + '.unencrypted', filepath)
        os.remove(filepath + '.unencrypted')

        metadata['tags'] = list(set(metadata['tags']) | set(request_data['tags']))
        metadata['files'][new_id] = _create_file(
            new_id,
            request_data['name'],
            request_data['tags'],
            request_data['filetype'])
        encrypt_metadata(meta_filepath, metadata, session['file_encrypter'])
        return {'status': 'success', 'id': new_id}, 200

@bp.route('/file/<file_id>', methods=['GET'])
def get_file_endpoint(file_id):
    if request.method == 'GET':
        if 'session_hash' not in request.args:
            return error_payload('missing session_hash in url parameters', 400)
        session, failure_payload = _get_session(request.args['session_hash'])
        if not session: return failure_payload
        meta_filepath = _get_metadata_path(session)
        if not os.path.exists(meta_filepath):
            return error_payload('file store does not exist', 404)

        metadata = session['file_encrypter'].decrypt_json(meta_filepath)
        if not metadata:
            return error_payload('invalid password on session', 400)

        if file_id not in metadata['files']:
            return error_payload('invalid file id: {}'.format(file_id), 400)
        file_metadata = metadata['files'][file_id]

        filepath = _get_filepath(file_id)
        disp_name = '{}.{}'.format(file_metadata['name'], file_metadata['filetype'])
        session['file_encrypter'].decrypt(filepath, filepath, file_metadata['filetype'])

        unencrypted_path = filepath + '.' + file_metadata['filetype']
        ret = send_file(unencrypted_path, download_name=disp_name)

        os.remove(unencrypted_path)
        return ret
