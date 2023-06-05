from datetime import datetime
import unicodedata
import hashlib
import os
import re
import stat

MasterTypes = {'-int': 'intensive', '-vgos': 'vgos', '': 'standard'}

_is_master = re.compile(r'master(?P<year>\d{4}|\d{2})(?P<type>(|-int|-vgos))?.txt$').match


def is_master(name):
    if not (match := _is_master(name)):
        return None
    year = match['year'] if len(match['year']) == 4 else datetime.strptime(match['year'], '%y').strftime('%Y')
    return {'year': year, 'type': MasterTypes[match['type']]}


# Make folder and parent folders with uid and gid
def make_dir(folder, uid, gid):
    parent = os.path.dirname(folder)
    if not os.path.exists(parent):
        make_dir(parent, uid, gid)
    os.mkdir(folder)
    os.chown(folder, uid, gid)


# Class to help reading text file
class TEXTfile:
    encode_list = ['latin-1', 'UTF-8', 'ISO-8859-7', 'us-ascii']
    reg_cr = re.compile('\r$')  # test DOS CR

    def __init__(self, path, encoding='UTF-8'):
        self.path = None
        self.EOL = -1
        self.encoding = ''
        self.file = None
        self.line = None
        self.encoding = encoding
        self.line_nbr = 0
        # Try to read to test encoding
        try:
            with open(path, encoding=self.encoding, errors="surrogateescape") as f:
                line = f.readline()
                if TEXTfile.reg_cr.search(line):
                    self.EOL = -2  # DOS file with CRLF and end of line
                self.path = path
                self.is_valid = True
        except Exception:
            self.is_valid = False

    def __enter__(self):

        if self.is_valid:
            self.file = open(self.path, encoding=self.encoding, errors="surrogateescape")
            self.line_nbr = 0
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()
            self.file = None

    def readline(self):
        return self.file.readline()

    def has_next(self):
        if self.file:
            self.line = self.readline()
            if not self.line:
                return False
            self.line = unicodedata.normalize('NFKC', self.line)
            self.line = self.line[:self.EOL]
            self.line_nbr += 1
            return True
        return False

    def readUntil(self, key_word='', start_word=''):
        while self.has_next():
            if not self.line:
                continue
            if key_word and start_word and key_word in self.line and self.line.startswith(start_word):
                return True
            if key_word and key_word in self.line:
                return True
            if start_word and self.line.startswith(start_word):
                return True
        return False

    def isDOS(self):
        return self.EOL == -2


# Compute md5 hash for a file
def get_md5sum(path, chunk_size=32768):

    md5 = hashlib.md5()
    with open(path, 'rb') as file:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


def remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except:
        pass


def chmod(path):
    try:
        if os.path.exists(path):
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IROTH)
    except:
        pass
