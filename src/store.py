import json
import time
import os
import tempfile
import logging

from uuid import uuid4

from flask import Blueprint, request, send_file, jsonify

from .util import *
from .session import get_session, check_file_locked, get_encrypt_job, add_encrypt_job, \
                     add_decrypt_job, get_decrypt_job
from .error import MissingSessionName, NoJSONMetadata, FileStoreDNE, \
                   FileStoreExists, FailedToWriteMetadata, InvalidFileID, NoFile, \
                   InvalidTag, FileUploadError, FileIsBeingDecrypted

BASE_METADATA = {'files': {}, 'tags': []}

bp = Blueprint('store', __name__, url_prefix='/api/store')

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

    file_encrypter.encrypt_file(path + '.unencrypted', path)
    os.remove(path + '.unencrypted')

def setup_session_and_meta(session_name):
    if not session_name:
        raise MissingSessionName()
    session = get_session(session_name)
    filepath = get_metadata_path(session)
    if not os.path.exists(filepath):
        raise FileStoreDNE()
    metadata = session['file_encrypter'].decrypt_json(filepath)

    return session, metadata

@bp.route('', methods=['POST'])
def store_endpoint():
    if request.method == 'POST':
        request_data = request.get_json()
        if 'session_name' not in request_data:
            raise MissingSessionName()
        session = get_session(request_data['session_name'])
        filepath = get_metadata_path(session)

        if os.path.exists(filepath):
            raise FileStoreExists()

        os.mkdir('{}/{}'.format(get_data_filepath(), session['name']))
        os.mkdir('{}/{}/decrypted'.format(get_data_filepath(), session['name']))
        unencrypted_filepath = '{}.unencrypted'.format(filepath)
        with open(unencrypted_filepath, 'w') as unencrypted_file:
            try:
                json.dump(BASE_METADATA, unencrypted_file)
            except Exception as e:
                print(e)
                raise FailedToWriteMetadata()
        session['file_encrypter'].encrypt_file(unencrypted_filepath, filepath)
        os.remove(unencrypted_filepath)
        return {'status': 'success'}, 200


@bp.route('/metadata/file', methods=['GET', 'POST'])
def store_file_metadata_endpoint():
    if request.method == 'GET':
        _, metadata = setup_session_and_meta(request.args.get('session_name', None))
        return jsonify(metadata['files']), 200
    elif request.method == 'POST':
        request_data = request.get_json()
        if 'session_name' not in request_data:
            raise MissingSessionName()
        session, metadata = setup_session_and_meta(request_data.get('session_name', None))

        new_id = uuid4()
        while new_id in metadata['files']:
            new_id = uuid4()
        new_id = str(new_id)

        metadata['tags'] = list(set(metadata['tags']) | set(request_data['tags']))
        metadata['files'][new_id] = _create_file(
            new_id,
            request_data['name'],
            request_data['tags'],
            request_data['filetype'])
        encrypt_metadata(get_metadata_path(session), metadata, session['file_encrypter'])

        return new_id

@bp.route('/metadata/file/<file_id>', methods=['GET', 'PATCH'])
def get_file_metadata_endpoint(file_id):
    if request.method == 'GET':
        _, metadata = setup_session_and_meta(request.args.get('session_name', None))
        if file_id not in metadata['files']:
            raise InvalidFileID(file_id)
        return metadata['files'][file_id], 200
    elif request.method == 'PATCH':
        request_data = request.get_json()
        session, metadata = setup_session_and_meta(request_data.get('session_name', None))
        if file_id not in metadata['files']:
            raise InvalidFileID(file_id)
        metadata['tags'] = list(set(metadata['tags']) | set(request_data.get('tags', [])))
        f_meta = metadata['files'][file_id]
        for key in ['tags', 'name', 'filetype']:
            f_meta[key] = request_data.get(key, f_meta[key])

        encrypt_metadata(get_metadata_path(session), metadata, session['file_encrypter'])
        return f_meta, 200

@bp.route('/metadata/tag', methods=['GET'])
def store_tag_metadata_endpoint():
    if request.method == 'GET':
        _, metadata = setup_session_and_meta(request.args.get('session_name', None))
        return jsonify(metadata['tags']), 200

@bp.route('/metadata/tag/<tag_name>', methods=['PUT', 'DELETE'])
def store_change_tag_metadata_endpoint(tag_name):
    request_data = request.get_json()
    if request.method == 'PUT':
        session, metadata = setup_session_and_meta(request_data.get('session_name', None))
        new_tag = request_data['new_tag']
        try:
            metadata['tags'].remove(tag_name)
        except ValueError:
            raise InvalidTag(tag_name)
        if new_tag not in metadata['tags']:
            metadata['tags'].append(new_tag)
        for file_id, f_meta in metadata['files'].items():
            try:
                f_meta['tags'].remove(tag_name)
            except ValueError:
                continue
            if new_tag not in f_meta['tags']:
                f_meta['tags'].append(request_data['new_tag'])
        encrypt_metadata(get_metadata_path(session), metadata, session['file_encrypter'])
        return 'successfully updated tag {} to {}'.format(tag_name, request_data['new_tag']), 200
    if request.method == 'DELETE':
        session, metadata = setup_session_and_meta(request_data.get('session_name', None))
        try:
            metadata['tags'].remove(tag_name)
        except ValueError:
            raise InvalidTag(tag_name)
        for file_id, f_meta in metadata['files'].items():
            try:
                f_meta['tags'].remove(tag_name)
            except ValueError:
                continue
        encrypt_metadata(get_metadata_path(session), metadata, session['file_encrypter'])
        return 'successfully deleted tag {}'.format(tag_name), 200

@bp.route('/file', methods=['POST'])
def store_file_endpoint():
    if request.method == 'POST':
        if 'metadata' not in request.form:
            raise NoJSONMetadata()
        request_data = json.loads(request.form['metadata'])
        session, metadata = setup_session_and_meta(request_data.get('session_name', None))

        chunk = int(request_data['chunk'])
        chunk_offset = int(request_data['chunk_offset'])
        total_chunks = int(request_data['total_chunks'])
        file_size = int(request_data.get('file_size', -1))
        file_id = request_data['file_id']

        if 'file' not in request.files:
            raise NoFile()

        path = get_filepath(session['name'], file_id)
        part_path = path + '.part'
        logging.info('Path: {}'.format(path))
        logging.info('Partial Path: {}'.format(part_path))
        with open(part_path, 'ab') as f:
            f.seek(chunk_offset)
            uploaded_file = request.files['file']
            f.write(uploaded_file.read())
        logging.info('File Size: {}, {}'.format(os.path.getsize(part_path), file_size))
        if chunk + 1 == total_chunks:
            check_file_locked(session, file_id)
            if file_size != -1 and os.path.getsize(part_path) != file_size:
                os.remove(part_path)
                raise FileUploadError(file_id, 'file size mismatch')
            else:
                logging.info('Encrypting file')
                add_encrypt_job(session, file_id, part_path, path)

        return {'status': 'success'}, 200

@bp.route('/file/<file_id>', methods=['GET'])
def get_file_endpoint(file_id):
    if request.method == 'GET':
        if 'session_name' not in request.args:
            raise MissingSessionName()
        session, metadata = setup_session_and_meta(request.args.get('session_name', None))

        if file_id not in metadata['files']:
            raise InvalidFileID(file_id)
        check_file_locked(session, file_id)
        file_metadata = metadata['files'][file_id]

        filepath = get_filepath(session['name'], file_id)
        outpath = '{}.{}'.format(get_decrypted_filepath(session['name'], file_id), file_metadata['filetype'])
        if outpath in session['decrypted']:
            return send_file(outpath, download_name='{}.{}'.format(file_metadata['name'], file_metadata['filetype']))
        add_decrypt_job(session, file_id, filepath, outpath)
        raise FileIsBeingDecrypted
