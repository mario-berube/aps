from datetime import datetime
from configparser import RawConfigParser
from collections import defaultdict
import os
import json
import toml
import hashlib


# Change dictionary to attribute of a class
def expand_object(data, cls=None, expand=False):
    # Change a iso format string to datetime. Return string if not datetime
    def decode_obj(obj):
        if isinstance(obj, dict):
            return {k: decode_obj(val) for k, val in obj.items()}
        if isinstance(obj, list):
            return [decode_obj(val) for val in obj]
        try:
            return datetime.fromisoformat(obj)
        except (ValueError, TypeError):
            return obj

    # Use empty class if one is not provided
    cls = cls if cls else type('', (), {})

    data = decode_obj(data)
    # Set attribute of the class
    for key, value in data.items():
        if not expand:
            setattr(cls, key, decode_obj(value))
        # Check if data already exists
        if item := getattr(cls, key, None):
            expand_object(value, cls=item) if isinstance(value, dict) else setattr(cls, key, value)
        elif isinstance(value, dict):
            setattr(cls, key, expand_object(value, expand=True))
        else:
            setattr(cls, key, value)
    return cls


# Decode string to float and return NaN if it fails
def to_float(string):
    try:
        return float(string.strip())
    except ValueError:
        return float('nan')


# Decode string to int and return 0 if it fails
def to_int(text):
    text = text.strip()
    return int(text) if text.isdigit() else 0


# Read vgosDb config file
def read_config(path: str) -> defaultdict:
    def expand(last_key: str, last_value: str) -> (str, str):
        if '\\' not in last_key:
            return last_key, last_value
        new_value = last_value
        for new_key in last_key.split('\\')[::-1]:
            new_value = {new_key: new_value}
        return new_key, new_value[new_key]

    def add(sub_section: defaultdict, last_key: str, last_value: str) -> None:
        if last_key not in sub_section:
            sub_section[last_key] = last_value
        else:
            for name, item in last_value.items():
                add(sub_section[last_key], name, item)

    parser = RawConfigParser()
    parser.read(path)
    config = defaultdict(dict)
    for section in parser.sections():
        for key, value in parser.items(section):
            add(config[section], *expand(key, value))
    return config


# Read lcl configuration file
def read_lcl(path):

    with open(path) as file:
        return {key: val for key, val in
                [map(str.strip, line[2:].split(':', 1))
                 for line in file.readlines() if line.startswith('# ') and ':' in line]
                }


# Read json or toml file must have json ot toml extension
def readDICT(path, exit_on_error=False, hook=dict):
    path = str(path)
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1][1:].strip()

    try:
        if ext in ['toml', 'aps']:
            with open(path) as file:
                return toml.load(file, _dict=hook)
        elif ext == 'conf':
            return read_config(path)
        elif ext == 'json':
            with open(path) as file:
                return json.load(file, object_pairs_hook=hook)
        elif ext == 'lcl':
            return read_lcl(path)
        err = f'{ext} not a valid extension'
    except IOError:
        err = ('IO error', f'File {name} does not exist')
    except Exception as error:
        err = (f'{ext.upper()} error', f'Error reading {name} [{str(error)}]')

    if exit_on_error:
        print(err)
        exit(0)
    return {}


# Save json or toml file base on extension
def saveDICT(path, data):
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1][1:].strip()
    try:
        if ext in ['toml', 'aps']:
            with open(path, 'w') as file:
                return toml.dump(data, file)
        else:  # Write as json file
            with open(path, 'w') as f:
                json.dump(data, f, sort_keys=True, indent=4)
        return True
    except:
        return False


# Datetime formats regularly used
DATEfmt = '%Y-%m-%d'
TIMEfmt = '%Y-%m-%d %H:%M:%S'


# Transform '%Y-%m-%d' string date to '%Y-%m-%d %H:%M:%S'
def UTC0(date):
    utc = datetime.strptime(date, DATEfmt).replace(hour=0, minute=0, second=0)
    return utc.strftime(TIMEfmt)


def year_dates(year):
    start = datetime(year=int(year), month=1, day=1).strftime(DATEfmt)
    end = datetime(year=int(year), month=12, day=31).strftime(DATEfmt)
    return UTC0(start), UTC0(end)


def md5_for_file(path, block_size=4096, want_hex=False):
    sums = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(block_size), b''):
            sums.update(chunk)
    return sums.hexdigest() if want_hex else sums.digest()


# Changes bytes to str
def bstr(val):
    return str(val, 'utf-8')


# Read app information
def read_app_info(cls):
    user = os.environ['SUDO_USER'] if 'SUDO_USER' in os.environ else os.environ['USER']
    path = os.path.join(os.path.expanduser('~'), cls.__name__.lower(), f'{user}.toml')
    return readDICT(path)


# Save app information
def save_app_info(cls, app_info):
    user = os.environ['SUDO_USER'] if 'SUDO_USER' in os.environ else os.environ['USER']
    folder = os.path.join(os.path.expanduser('~'), cls.__name__.lower())
    if not os.path.exists(folder):
        os.mkdir(folder)
    path = os.path.join(folder, f'{user}.toml')
    return saveDICT(path, app_info)


# Toggle app option
def toggle_options(cls, options, args):
    info = read_app_info(cls)
    selected = False
    for option in options:
        if hasattr(args, option) and getattr(args, option):
            name = option.capitalize()
            info[name] = not info.get(name, True)
            print(f'Option {option} changed to {info[name]}')
            selected = True
    if selected:
        save_app_info(cls, info)

    return selected


# Check if executable in PATH and had the right permissions
def is_executable(app_name):
    for path in os.environ["PATH"].split(os.pathsep):
        xpath = os.path.join(path, app_name)
        if os.path.exists(xpath) and os.path.isfile(xpath) and os.access(xpath, os.X_OK):
            return True
    return False
