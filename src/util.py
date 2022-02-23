def error_payload(msg, code):
    return {'status': 'failed', 'reason': msg}, code
