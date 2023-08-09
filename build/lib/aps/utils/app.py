import os
import sys
import atexit
from subprocess import Popen, PIPE
from pathlib import Path
import toml
from datetime import datetime
try:
    from importlib.resources import files
except:
    from importlib_resources import files


args = None

env_vars = {'VGOSDB_DIR': 'vgosDB files Folder', 'SESSION_DIR': 'Session files Folder',
            'MASTER_DIR': 'Master files Folder', 'CALC_APRIORI_DIR': 'Folder containing Leap Seconds file ut1ls.dat',
            'MODEL_DIR': 'Folder containing glo.sit file', 'WORK_DIR': 'Folder containing Solve output',
            'SPOOL_DIR': 'Folder containing spool files',
            'CALC_APRIORI_DIR': 'Folder containing lead seconds file (ut1ls.dat)'}

_dbase = None


# Get application input options and parameters
def init(arg_list):
    global args
    global _dbase

    # Register function that will be executed at exit.
    atexit.register(_app_exit)

    # Initialize global variables
    args = arg_list
    # Set global attributes
    this_module = sys.modules[__name__]
    for path in [Path(args.config if args.config else 'aps.conf'), Path(Path.home(), 'aps.conf')]:
        if path.expanduser().exists():
            try:
                for key, info in toml.load(path).items():
                    if isinstance(info, dict):
                        setattr(this_module, key, type('', (), info))
                    else:
                        setattr(this_module, key, info)

            except toml.TomlDecodeError as err:
                print(f'Problem reading {str(path)}\n{err}')

    _dbase = _db_generator(f'sqlite:///{getattr(this_module, "database")}')

    return args


def add_args_attr(key, info):
    global args
    if isinstance(info, dict):
        setattr(args, key, type('', (), info))
    else:
        setattr(args, key, info)


# Change dictionary into attributes of a class
def make_object(info):
    return type('', (), info)


# Call every time application exit
def _app_exit():
    pass


# Exec command and wait for answer
def exec_and_wait(command, action=None):
    with Popen(command, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, universal_newlines=True) as prc:
        return prc.communicate(action if action else None)


# Notify watchdogs
def notify(title, message, extra=""):
    for line in f'{message}\n{extra}'.splitlines():
        print(f'{title} - {line}')


# Get database instance
def _db_generator(url):
    from aps.ivsdb import IVSdata

    IVSdata.build(url)
    dbase = IVSdata(url)
    dbase.open()
    try:
        while True:
            yield dbase
    finally:
        dbase.close()


def get_dbase():
    global _dbase
    db = next(_dbase)
    return db


# Test if specific environment variables have been set.
def test_environment():
    return {code: desc for code, desc in env_vars.items() if not os.environ.get(code)}


def get_hidden_file(name):
    print(Path(files('aps').joinpath(f'files/{name}')))
    return Path(files('aps').joinpath(f'files/{name}'))


def folder(dir_name):
    return os.environ.get(dir_name, '')




