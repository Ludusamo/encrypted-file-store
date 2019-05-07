import sys
import EncryptedFile
import json
import os
from functools import reduce
from fuzzywuzzy import process
from getpass import getpass
from termcolor import colored
import tarfile

def printUsage():
    print('Usage: {} [filestore]', sys.argv[0])

def helpMsg(*args):
    return 'To Do: Print Help message'

def entryToString(entry):
    return colored('{:4}'.format(entry['id']), 'red') + '|' + \
        colored('{:48}'.format(entry['name']), 'white') + '|' + \
        colored('{:4}'.format(entry['filetype']), 'yellow') + '|' + \
        colored('{}'.format(entry['tags']), 'blue')

def search(fileEncryptor, metadata, *args):
    if len(args) < 2: return helpMsg()
    searchType = args[0]

    if searchType == 'tag':
        query = args[1]
        tags = list(
                reduce(lambda t1, t2: t1 + t2,
                map(lambda entry: entry['tags'],
                    metadata)))
        try:
            return process.extract(query, tags)
        except:
            return []
    elif searchType == 'file':
        subtype = args[1]
        if subtype == 'tag':
            def incexc(inclusion, exclusion, l):
                for t in inclusion:
                    if t not in l: return False
                for t in exclusion:
                    if t in l: return False
                return True

            incl = args[2:]
            excl = []
            if 'NOT' in incl:
                split = incl.index('NOT')
                incl, excl = incl[:split], incl[split + 1:]
            return reduce(lambda x, y: x + entryToString(y) + '\n',
                    filter(lambda e: incexc(incl, excl, e['tags']), metadata),
                    '')
        elif subtype == 'name':
            query = set(args[2])
            names = list(map(lambda entry: entry['name'], metadata))
            try:
                matches = process.extract(query, names)
                return reduce(lambda x, y: x + entryToString(y) + '\n',
                        map(lambda match: \
                                next(e for e in metadata \
                                    if e['name'] == match[0]),
                            matches),
                        '')
            except:
                return []
    else:
        return '{} is not a valid search type'.format(searchType)

def tag(fileEncryptor, metadata, *args):
    if len(args) < 2: return helpMsg()
    entry = int(args[0])
    tag = args[1]
    if tag not in metadata[entry]['tags']:
        metadata[entry]['tags'].append(tag)
        return 'successfully tagged {} with tag {}'.format(entry, tag)
    else:
        return 'entry {} already has tag {}'.format(entry, tag)

def untag(fileEncryptor, metadata, *args):
    if len(args) < 2: return helpMsg()
    entry = int(args[0])
    tag = args[1]
    if tag not in metadata[entry]['tags']:
        return 'entry {} does not have tag {}'.format(entry, tag)
    else:
        metadata[entry]['tags'].remove(tag)
        return 'successfully removed {} tag from {}'.format(tag, entry)

def ls(fileEncryptor, metadata, *args):
    return reduce(lambda x, y: x + entryToString(y) + '\n', metadata, '')

def quit(password, metadata, *args):
    return None

def add(fileEncryptor, metadata, *args):
    def addFile(path, name, filetype, tags):
        nextId = metadata[-1]['id'] + 1 if len(metadata) > 0 else 0
        newEntry = \
            { 'id': nextId
            , 'name': name
            , 'filetype': filetype
            , 'tags': list(tags)
            }
        metadata.append(newEntry)
        fileEncryptor.encrypt(path, fileEncryptor.filestore + '/' + str(nextId))
        return newEntry

    if len(args) < 3: return helpMsg()
    path = args[0]
    name = args[1]
    filetype = args[2]
    tags = args[3:]
    print(path)
    if filetype == 'dir':
        with tarfile.open('dir.tar.gz', 'w:gz') as dirEntry:
            dirEntry.add(path, arcname=os.path.basename(path))
        entry = addFile('dir.tar.gz', name, filetype, tags)
        os.remove('dir.tar.gz')
        return entryToString(entry)
    else:
        return entryToString(addFile(path, name, filetype, tags))
    return None # Should never occur

def get(fileEncryptor, metadata, *args):
    if len(args) < 2: return helpMsg()
    dirPath = fileEncryptor.filestore + '/unencrypted'
    def decryptFile(fileId):
        fileData = metadata[fileId]
        if fileData['filetype'] == 'dir':
            folderPath = dirPath + '/' + fileData['name']
            os.makedirs(folderPath)
            fileEncryptor.decrypt(fileEncryptor.filestore + '/' + str(fileId), \
                    dirPath + '/' + fileData['name'], 'tar.gz')
            tarpath = dirPath + '/' + fileData['name'] + '.tar.gz'
            tar = tarfile.open(tarpath, 'r:gz')
            tar.extractall(path=folderPath)
            tar.close()
            os.remove(tarpath)
        else:
            fileEncryptor.decrypt(fileEncryptor.filestore + '/' + str(fileId), \
                    dirPath + '/' + fileData['name'], fileData['filetype'])
    if not os.path.exists(dirPath):
        os.makedirs(dirPath)
    reqType = args[0]
    if reqType == 'file':
        fileId = int(args[1])
        decryptFile(fileId)
    elif reqType == 'tag':
        tag = args[1]
        for f in filter(lambda f: tag in f['tags'], metadata):
            decryptFile(f['id'])
    return 'success'

def remove(fileEncryptor, metadata, *args):
    if len(args) < 1: return helpMsg()
    fileId = int(args[0])
    if fileId >= len(metadata) or fileId < 0:
        return 'id {} does not exist'.format(fileId)
    os.remove(fileEncryptor.filestore + '/' + str(fileId))
    for i in range(fileId + 1, len(metadata)):
        print(i)
        metadata[i]['id'] = i - 1
        metadata[i - 1] = metadata[i]
        os.rename(fileEncryptor.filestore + '/' + str(i), \
                fileEncryptor.filestore + '/' + str(i - 1))
    metadata.pop()
    return 'successfully removed {}'.format(fileId)

def filetype(fileEncryptor, metadata, *args):
    if len(args) < 2: return helpMsg()
    fileId = int(args[0])
    filetype = args[1]
    metadata[fileId]['filetype'] = filetype
    return 'successfully set file {} filetype to {}'.format(fileId, filetype)

dispatch = \
    { 'quit': quit
    , 'search': search
    , 'help': helpMsg
    , 'tag': tag
    , 'untag': untag
    , 'add': add
    , 'ls': ls
    , 'get': get
    , 'remove': remove
    , 'filetype': filetype
    }

def main():
    filestore = 'files'
    if len(sys.argv) >= 2:
        filestore = sys.argv[1]

    password = getpass('Please enter password: ')
    fileEncryptor = EncryptedFile.FileEncryptor(password, filestore)
    #EncryptedFile.FileEncryptor('test', filestore).encrypt('files/ex.json', 'files/metadata')
    print(fileEncryptor)

    # Read in metadata
    metadata = None
    if os.path.exists(filestore + '/metadata'):
        fileEncryptor.decrypt(filestore + '/metadata', \
                filestore + '/metadata', 'json')
        with open(filestore + '/metadata.json', 'rb') as f:
            try:
                metadata = json.load(f)
            except:
                print('incorrect password', file=sys.stderr)
                return
        os.remove(filestore + '/metadata.json')

    if not metadata:
        metadata = []
        print('repository initialized')

    if len(sys.argv) > 2:
        print(dispatch[sys.argv[2]](fileEncryptor, metadata, *sys.argv[3:]))
    else:
        while True:
            cmd = input('>> ').split(' ')
            if cmd[0] not in dispatch:
                print(helpMsg())
                continue
            # Send the rest as arguments
            res = dispatch[cmd[0]](fileEncryptor, metadata, *cmd[1:])
            if not res: break
            print(res)

    with open(filestore + '/metadata.json', 'w') as f:
        try:
            json.dump(metadata, f)
        except:
            pass

    fileEncryptor.encrypt(filestore + '/metadata.json', filestore + '/metadata')
    os.remove(filestore + '/metadata.json')

if __name__ == "__main__":
    main()
