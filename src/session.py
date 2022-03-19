import os
import json
import time
import logging
from threading import Lock, Timer
from uuid import uuid4
from multiprocessing import Process, Event

from flask import Blueprint, request

from .error import SessionNotInitialized, FileIsBeingEncrypted, FileIsBeingDecrypted, SessionExists
from .encrypter import FileEncrypter
from .util import *

MAX_SESSION_TIME = 60 * 60 # 1 hour
CHECK_INTERVAL = 60 * 10 # 10 minutes

bp = Blueprint('session', __name__, url_prefix='/api/session')

sessions = {}
sessions_lock = Lock()

def get_session(session_name):
    with sessions_lock:
        session = sessions.get(session_name, None)
        if not session:
            raise SessionNotInitialized
        return session

def get_encrypt_job(session, file_id):
    with session['lock']:
        return session['encrypt_jobs'].get(file_id, None)

def add_encrypt_job(session, file_id, input_path, output_path):
    encrypt_job = get_encrypt_job(session, file_id)
    with session['lock']:
        if encrypt_job:
            encrypt_job[1].join()
        event = Event()
        def encrypt_file_wrapper():
            try:
                session['file_encrypter'].encrypt_file(input_path, output_path)
            except Exception as e:
                logging.error('failed to encrypt')
                logging.error(e)
            finally:
                event.set()
                os.remove(input_path)
        encrypt_proc = Process(target=encrypt_file_wrapper)
        encrypt_proc.start()
        session['encrypt_jobs'][file_id] = (event, encrypt_proc)

def get_decrypt_job(session, file_id):
    with session['lock']:
        return session['decrypt_jobs'].get(file_id, None)

def add_decrypt_job(session, file_id, input_path, output_path):
    decrypt_job = get_decrypt_job(session, file_id)
    with session['lock']:
        if decrypt_job:
            decrypt_job[1].join()
        event = Event()
        def decrypt_file_wrapper():
            try:
                session['file_encrypter'].decrypt_file(input_path, output_path)
            except Exception as e:
                logging.error('failed to decrypt')
                logging.error(e)
            finally:
                event.set()
        decrypt_proc = Process(target=decrypt_file_wrapper)
        decrypt_proc.start()
        session['decrypted'].add(output_path)
        session['decrypt_jobs'][file_id] = (event, decrypt_proc)

def check_file_locked(session, file_id):
    encrypt_job = get_encrypt_job(session, file_id)
    if encrypt_job and not encrypt_job[0].is_set():
        raise FileIsBeingEncrypted
    decrypt_job = get_decrypt_job(session, file_id)
    if decrypt_job and not decrypt_job[0].is_set():
        raise FileIsBeingDecrypted

@bp.route('', methods=['POST'])
def sessions_endpoint():
    if request.method == 'POST':
        request_data = json.loads(request.data)

        session_name = str(request_data['name'])

        session = None
        try:
            session = get_session(session_name)
        except:
            pass
        if session and session['password'] == request_data['password']:
            raise SessionExists
        session = {
            'file_encrypter': FileEncrypter(request_data['password'])
            , 'name': session_name
            , 'creation_time': time.time()
            , 'encrypt_jobs': {}
            , 'decrypt_jobs': {}
            , 'decrypted': set()
            , 'lock': Lock()
            , 'password': request_data['password']
        }
        with sessions_lock:
            sessions[session_name] = session
        return {'status': 'success', 'session_name': session_name}, 201

@bp.route('<session_name>/refresh', methods=['PUT'])
def session_refresh_endpoint(session_name):
    if request.method == 'PUT':
        session = get_session(session_name)
        session['creation_time'] = time.time()
        logging.info('Session Refreshed, Time Left: {}'.format((MAX_SESSION_TIME / 60) - (time.time() - session['creation_time'])))
        return { 'status': 'success' }, 200

@bp.route('<session_name>/valid', methods=['GET'])
def session_endpoint(session_name):
    if request.method == 'GET':
        session = get_session(session_name)
        if not session:
            return {
                'active': False,
                'reason': 'Session name {} not found'.format(session_name)
            }, 404
        if time.time() - session['creation_time'] < MAX_SESSION_TIME:
            return {
                'active': True,
            }, 200
        else:
            return {
                'active': False,
                'reason': 'Session timed out'.format(session_name)
            }, 404

def create_session_clear_timer():
    session_clear_timer = Timer(CHECK_INTERVAL, _clear_invalid_sessions)
    session_clear_timer.name = 'ClearSessionThread'
    session_clear_timer.start()

def _clear_decrypted(session):
    dir_path = get_decrypted_folder(session['name'])
    for f in os.listdir(dir_path):
        os.remove(os.path.join(dir_path, f))

def _clear_invalid_sessions():
    global sessions
    logging.info('clearing invalid sessions')
    with sessions_lock:
        to_delete = []
        for k, session in sessions.items():
            if time.time() - session['creation_time'] >= MAX_SESSION_TIME:
                to_delete.append(k)
        for k in to_delete:
            _clear_decrypted(sessions[k])
            del sessions[k]
    logging.info('cleared {} sessions'.format(len(to_delete)))

    create_session_clear_timer()
