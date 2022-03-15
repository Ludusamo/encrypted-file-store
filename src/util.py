import os

def get_data_filepath():
    return os.path.abspath(os.environ.get('DATA_FILEPATH', 'data'))

def get_filepath(filestore, name):
    data_filepath = get_data_filepath()
    return '{}/{}/{}'.format(data_filepath, filestore, name)

def get_decrypted_folder(filestore):
    data_filepath = get_data_filepath()
    return '{}/{}/decrypted'.format(data_filepath, filestore)

def get_decrypted_filepath(filestore, name):
    data_filepath = get_data_filepath()
    return '{}/{}/decrypted/{}'.format(data_filepath, filestore, name)

def get_metadata_path(session):
    return get_filepath(session['name'], 'metadata')
