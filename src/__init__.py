import os
import json
import logging
import sys

from flask import Flask
from werkzeug.exceptions import HTTPException


def create_app(test_config=None):
    logging.basicConfig(format='[%(asctime)s][%(levelname)s] - %(message)s',
                        stream=sys.stdout,
                        level=logging.DEBUG)
    app = Flask(__name__, instance_relative_config=True)
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 * 1024
    logging.info('MAX_CONTENT_LENGTH: {}'.format(app.config['MAX_CONTENT_LENGTH']))

    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import session
    app.register_blueprint(session.bp)
    session.create_session_clear_timer()

    from . import store
    app.register_blueprint(store.bp)

    @app.errorhandler(HTTPException)
    def handle_exception(e):
        response = e.get_response()
        response.data = json.dumps({
            "code": e.code,
            "name": e.name,
            "description": e.description,
        })
        response.content_type = "application/json"
        return response

    @app.route('/heartbeat')
    def heartbeat():
        return 'heartbeat'

    return app
