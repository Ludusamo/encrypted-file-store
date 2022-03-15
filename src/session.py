import os
import json
import time
import logging
from threading import Lock, Timer
from uuid import uuid4
from multiprocessing import Process, Event

from flask import Blueprint, request

from .error import SessionNotInitialized, FileIsBeingEncrypted
from .encrypter import FileEncrypter

MAX_SESSION_TIME = 60 * 30 # 10 Minutes
SESSION_CHECK_INTERVAL = 60 * 5 # 5 Minutes

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
        return session['encrypt_jobs'].get(file_id, None)

def add_decrypt_job(session, file_id, done_event, encrypt_proc):
    with session['lock']:
        encrypt_job = get_decrypt_job(session, file_id)
        if encrypt_job:
            encrypt_job[1].join()
        session['encrypt_jobs'][file_id] = (done_event, encrypt_proc)

def check_file_locked(session, file_id):
    encrypt_job = get_encrypt_job(session, file_id)
    if encrypt_job and not encrypt_job[0].is_set():
        raise FileIsBeingEncrypted

@bp.route('', methods=['POST'])
def sessions_endpoint():
    if request.method == 'POST':
        request_data = json.loads(request.data)

        session_name = request_data['name']

        session = {
            'file_encrypter': FileEncrypter(request_data['password'])
            , 'name': session_name
            , 'creation_time': time.time()
            , 'encrypt_jobs': {}
            , 'lock': Lock()
        }
        with sessions_lock:
            sessions[str(session_name)] = session
        return {'status': 'success', 'session_name': session_name}, 201

@bp.route('<session_name>/valid', methods=['GET'])
def session_endpoint(session_name):
    if request.method == 'GET':
        session = get_session(session_name)
        if session:
            return {
                'active': False,
                'reason': 'Session hash {} not found'.format(session_name)
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
    session_clear_timer = Timer(SESSION_CHECK_INTERVAL, _clear_invalid_sessions)
    session_clear_timer.name = 'ClearSessionThread'
    session_clear_timer.start()

def _clear_invalid_sessions():
    global sessions
    logging.info('clearing invalid sessions')
    with sessions_lock:
        to_delete = []
        for k, session in sessions.items():
            if time.time() - session['creation_time'] >= MAX_SESSION_TIME:
                to_delete.append(k)
        for k in to_delete:
            del sessions[k]
    logging.info('cleared {} sessions'.format(len(to_delete)))

    create_session_clear_timer()
