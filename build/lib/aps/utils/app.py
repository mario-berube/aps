import socket
import os
import sys
import atexit
from datetime import datetime
from subprocess import Popen, PIPE

from utils import readDICT
from utils.mail import send_message, build_message

args = Applications = ControlFiles = Tunnel = None
_dbase = None


# Get application input options and parameters
def init(arg_list):
    global args

    # Register function that will be executed at exit.
    atexit.register(_app_exit)

    # Initialize global variables
    args = arg_list
    # Set global attributes
    this_module = sys.modules[__name__]
    for key, info in readDICT(os.path.expanduser(args.config), exit_on_error=True).items():
        if isinstance(info, dict):
            setattr(this_module, key, type('', (), info))
        else:
            setattr(this_module, key, info)
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


# Check if this server can do a specific action
def check_server_capability(action):
    hostname = socket.gethostname()
    return hostname in Applications.VLBI.get(action, [hostname])


# Return the period for quiet time (Extracted from control file)
def get_quiet_time():
    start, end = Applications.VLBI.get("quiet_time", [None, None])
    if start and end:
        hour, minute = list(map(int, start.split(":")))
        start = datetime.now().replace(hour=hour, minute=minute)
        hour, minute = list(map(int, end.split(":")))
        end = datetime.now().replace(hour=hour, minute=minute)
        return start, end
    return datetime(1970, 1, 1), datetime(1970, 1, 1)


# Call every time application exit
def _app_exit():
    pass


# Exec command and wait for answer
def exec_and_wait(command, action=None):
    with Popen(command, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, universal_newlines=True) as prc:
        return prc.communicate(action if action else None)


# Check if file has changed and read information if needed
def load_control_file(**kwargs):
    if name := kwargs.get('name', None):
        path = os.path.join(os.getenv('CONFIG_DIR'), name)
    else:
        path = kwargs.get('path', '')

    path, data, lastmod = os.path.expanduser(path), None, kwargs.get('lastmod', None)
    if not lastmod or os.path.getmtime(path) > lastmod:
        lastmod, data = os.path.getmtime(path), readDICT(path, exit_on_error=kwargs.get('exit_on_error', False))
    return lastmod, data


def is_nvi_server():
    return socket.gethostname().startswith('nvi-vlbi')


# Notify watchdogs
def notify(title, message, extra=""):
    name = 'nvi-notify.toml' if is_nvi_server() else ControlFiles.Notify
    if info := load_control_file(name=name)[-1]:
        message = f"{message}\n\n{extra}" if extra else message
        details = info['Notifications']
        msg = build_message(details['sender'], details['recipients'], title, text=message)
        send_message(details['server'], msg)


# Create database generator
def _open_dbase():
    global _dbase
    from ivsdb import IVSdata
    # Get database url and tunnel information
    url = load_control_file(name=ControlFiles.Database)[-1]['Credentials'][args.db]
    # Open database
    _dbase = IVSdata(url, tunnel(args.db))
    _dbase.open()
    return _dbase


# Get database instance
def get_dbase():
    return _dbase if _dbase else _open_dbase()

"""
def get_dbase_decorator(f):
    from ivsdb import IVSdata

    def inner():
        return inner.dbase
    # Get database url and tunnel information
    inner.url = load_control_file(name=ControlFiles.Database)[-1]['Credentials'][args.db]
    inner.tunnel = getattr(Tunnel, args.db, None)
    # Open database
    inner.dbase = IVSdata(inner.url, inner.tunnel)
    inner.dbase.open()
    return inner()


@get_dbase_decorator
def get_dbase():
    return get_dbase.dbase
"""


# Get tunnel information from config file
def tunnel(name):
    global Tunnel
    try:
        return getattr(Tunnel, name)
    except:
        return None


# Get database url and tunnel information
def get_dbase_info():
    global ControlFiles

    return load_control_file(name=ControlFiles.Database)[-1]['Credentials'][args.db], tunnel(args.db)
