import json
import time
import logging
from threading import Lock, Timer
from uuid import uuid4

from flask import Blueprint, request

from .error import InvalidSessionHash
from .encrypter import FileEncrypter

MAX_SESSION_TIME = 60 * 30 # 10 Minutes
SESSION_CHECK_INTERVAL = 60 * 5 # 5 Minutes

bp = Blueprint('session', __name__, url_prefix='/api/session')

sessions = {}
sessions_lock = Lock()

def get_session(session_hash):
    with sessions_lock:
        session = sessions.get(session_hash, None)
        if not session:
            raise InvalidSessionHash()
        return session

@bp.route('', methods=['POST'])
def sessions_endpoint():
    if request.method == 'POST':
        request_data = json.loads(request.data)

        session_hash = uuid4()

        session = {
            'file_encrypter': FileEncrypter(request_data['password'])
            , 'name': request_data['name']
            , 'creation_time': time.time()
        }
        with sessions_lock:
            sessions[str(session_hash)] = session
        return {'status': 'success', 'session_hash': session_hash}, 201

@bp.route('<session_hash>/valid', methods=['GET'])
def session_endpoint(session_hash):
    if request.method == 'GET':
        session = get_session(session_hash)
        if session:
            return {
                'active': False,
                'reason': 'Session hash {} not found'.format(session_hash)
            }, 404
        if time.time() - session['creation_time'] < MAX_SESSION_TIME:
            return {
                'active': True,
            }, 200
        else:
            return {
                'active': False,
                'reason': 'Session timed out'.format(session_hash)
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
