import json
import time
import os
import tempfile
from uuid import uuid4

from flask import Blueprint, request, send_file

from .session import get_session
from .error import MissingSessionHash, NoJSONMetadata, FileStoreDNE, \
                   FileStoreExists, FailedToWriteMetadata, InvalidFileID, NoFile, \
                   InvalidTag

BASE_METADATA = {'files': {}, 'tags': []}

bp = Blueprint('store', __name__, url_prefix='/api/store')

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

def setup_session_and_meta(session_hash):
    if not session_hash:
        raise MissingSessionHash()
    session = get_session(session_hash)
    filepath = _get_metadata_path(session)
    if not os.path.exists(filepath):
        raise FileStoreDNE()
    metadata = session['file_encrypter'].decrypt_json(filepath)

    return session, metadata

@bp.route('', methods=['POST'])
def store_endpoint():
    if request.method == 'POST':
        request_data = json.loads(request.data)
        if 'session_hash' not in request_data:
            raise MissingSessionHash()
        session = get_session(request_data['session_hash'])
        filepath = _get_metadata_path(session)

        if os.path.exists(filepath):
            raise FileStoreExists()

        unencrypted_filepath = '{}.unencrypted'.format(filepath)
        with open(unencrypted_filepath, 'w') as unencrypted_file:
            try:
                json.dump(BASE_METADATA, unencrypted_file)
            except Exception as e:
                print(e)
                raise FailedToWriteMetadata()
        session['file_encrypter'].encrypt(unencrypted_filepath, filepath)
        os.remove(unencrypted_filepath)
        return {'status': 'success'}, 200


@bp.route('/metadata/file', methods=['GET'])
def store_file_metadata_endpoint():
    if request.method == 'GET':
        _, metadata = setup_session_and_meta(request.args.get('session_hash', None))
        return json.dumps(metadata['files']), 200

@bp.route('/metadata/file/<file_id>', methods=['GET'])
def get_file_metadata_endpoint(file_id):
    if request.method == 'GET':
        _, metadata = setup_session_and_meta(request.args.get('session_hash', None))
        if file_id not in metadata['files']:
            raise InvalidFileID(file_id)
        return metadata['files'][file_id], 200

@bp.route('/metadata/tag', methods=['GET'])
def store_tag_metadata_endpoint():
    if request.method == 'GET':
        _, metadata = setup_session_and_meta(request.args.get('session_hash', None))
        return json.dumps(metadata['tags']), 200

@bp.route('/metadata/tag/<tag_name>', methods=['PUT'])
def store_change_tag_metadata_endpoint(tag_name):
    if request.method == 'PUT':
        request_data = json.loads(request.data)
        session, metadata = setup_session_and_meta(request_data.get('session_hash', None))
        try:
            metadata['tags'].remove(tag_name)
        except ValueError:
            raise InvalidTag(tag_name)
        metadata['tags'].append(request_data['new_tag'])
        for file_id, f_meta in metadata['files'].items():
            try:
                f_meta['tags'].remove(tag_name)
            except ValueError:
                continue
            f_meta['tags'].append(request_data['new_tag'])
        encrypt_metadata(_get_metadata_path(session), metadata, session['file_encrypter'])
        return 'successfully updated tag {} to {}'.format(tag_name, request_data['new_tag']), 200

@bp.route('/file', methods=['POST'])
def store_file_endpoint():
    if request.method == 'POST':
        if 'metadata' not in request.form:
            raise NoJSONMetadata()
        request_data = json.loads(request.form['metadata'])
        session, metadata = setup_session_and_meta(request_data.get('session_hash', None))

        if 'file' not in request.files:
            raise NoFile()

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
        encrypt_metadata(_get_metadata_path(session), metadata, session['file_encrypter'])
        return {'status': 'success', 'id': new_id}, 200

@bp.route('/file/<file_id>', methods=['GET'])
def get_file_endpoint(file_id):
    if request.method == 'GET':
        if 'session_hash' not in request.args:
            raise MissingSessionHash()
        session, metadata = setup_session_and_meta(request.args.get('session_hash', None))

        if file_id not in metadata['files']:
            raise InvalidFileID(file_id)
        file_metadata = metadata['files'][file_id]

        filepath = _get_filepath(file_id)
        disp_name = '{}.{}'.format(file_metadata['name'], file_metadata['filetype'])
        session['file_encrypter'].decrypt(filepath, filepath, file_metadata['filetype'])

        unencrypted_path = filepath + '.' + file_metadata['filetype']
        ret = send_file(unencrypted_path, download_name=disp_name)

        os.remove(unencrypted_path)
        return ret
