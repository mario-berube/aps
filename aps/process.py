import os
import pwd
from datetime import datetime
from tempfile import NamedTemporaryFile, gettempdir
import shutil
from subprocess import Popen, PIPE
import logging

from utils.files import chmod
from utils import readDICT

logger = logging.getLogger()


class APSprocess:
    prefix = 'aps'

    def __init__(self, opa_config, initials='--'):
        self._errors = []
        self.action = type(self).__name__.lower()
        self.initials = initials

        # Read opa files file for specific session type
        self.read_opa_config(opa_config)

        # Set user and pid
        self.real_user = os.environ['SUDO_USER'] if 'SUDO_USER' in os.environ else os.environ['USER']
        self.user_name = pwd.getpwuid(os.getuid()).pw_name
        self.pid = f'{os.getpid():010d}'

    # Add error in list of errors
    def add_error(self, err):
        self._errors.append(err)
        return None

    # Log in special file
    def logit(self, path, text_format, info):
        if path:
            info['now'] = datetime.now().strftime('%Y.%m.%d-%H:%M:%S')
            info['user'] = self.real_user
            with open(path, 'a') as log:
                print(text_format.format(**info), file=log)

    # Test if process has errors
    @property
    def has_errors(self):
        return len(self._errors) > 0

    # Return list of errors (1 per line)
    @property
    def errors(self):
        return '\n'.join(self._errors)

    def test(self):
        print(f'You are executing {self.action}')

    # Check if opa codes are valid files
    def check_required_files(self, codes, chk_write=False):
        for code in codes:
            path = self.get_opa_path(code)
            if not path:
                self.add_error(f'No file for {code} in {self.OPA_CONFIG}')
            else:
                self.check_permissions(path, chk_write)

    # Write output to a temporary file and return path
    @staticmethod
    def save_bad_solution(prefix, output):
        path = NamedTemporaryFile(prefix=prefix, suffix='_err.txt', delete=False).name
        output = '\n'.join(output) if isinstance(output, list) else output
        with open(path, 'w') as f:
            f.write(output if output else 'output was empty.')
        return path

    # Create a temporary file and return name
    @staticmethod
    def get_tmp_file(prefix='', suffix=''):
        return NamedTemporaryFile(prefix=prefix, suffix=suffix,delete=False).name

    # Set arc_line information
    @staticmethod
    def format_arc_line(wrapper, arc_line):
        return f'{wrapper:100s} ! {arc_line}'

    # Set OPA code information
    def get_opa_code(self, code, default=None):
        return getattr(self, code, default)

    # Get path for a specific application
    def get_app_path(self, code):
        name = self.get_opa_code(code, code)
        # Check if application is there
        if (name.startswith('/') and not os.path.exists(name)) or not self.is_executable(name):
            self.add_error(f'Executable file {name} for {code} was not found!')
            return None
        return name

    # Get the key for record in global files
    def get_key(self, line):
        db_name, version = line.split()[0:2]
        try:  # Try format YYMMMDD where MMM month name
            date, name = datetime.strptime(db_name[:7], '%y%b%d'), db_name[7:]
        except ValueError:
            try:  # Try format with numeric month
                date, name = datetime.strptime(db_name[:8], '%Y%m%d'), db_name[9:]
            except ValueError:
                print(f'Invalid db_name [{db_name} version [{int(version):03d}]')
                return ''
        return f'{date.strftime("%Y%j")}{name}{int(version):03d}'

    # Check file permission
    def check_permissions(self, path, chk_write=False):
        # Check if file exists
        if not os.path.exists(path):
            return self.add_error(f'{path} does not exists!')
        # Check if user has all privileges to modify solve file
        if not os.access(path, os.R_OK):
            return self.add_error(f'{path} read permission denied for {self.user_name}!')
            # Check if user has all privileges to modify solve file
        if chk_write and not os.access(path, os.W_OK):
            return self.add_error(f'{path} write permission denied for {self.user_name}!')
        return True

    # Get path of file using OPA code
    def get_opa_path(self, code):
        path = self.get_opa_code(code)
        return None if not path or '/dev/null' in path or not os.path.exists(path) else path

    # Check existence of directory
    def get_opa_directory(self, code):
        if (info := self.get_opa_code(code)) and info.upper() != 'NO':
            return info if os.path.isdir(info.split()[0]) else None
        return None

    # Make header for new control file
    @staticmethod
    def add_header(template):
        now = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
        return f'*  This file was generated automatically by program APS on {now}\n' \
               f'*  using a template file {template}\n'

    # Create temporary control file name
    def get_control_filename(self):
        return self.get_tmp_file(prefix=f'{APSprocess.prefix}_{self.action}_', suffix='.cnt')

    # Make control file in /tmp folder
    def make_control_file(self, template, path, keys, header=False):
        # Check if keys are empty
        for key, val in keys.items():
            if not val:
                self.add_error(f'Signature {key} not defined')
        if self.has_errors:
            return False

        # Open control file and write new lines in it.
        with open(path, "w") as f_out, open(template, 'r') as file:
            # Write header
            if header:
                f_out.write(self.add_header(template))
            # Read and write each line. Replace keywords
            for line in file.readlines():
                line = line.rstrip()
                if not line.startswith('*') and line.count('@') == 2:
                    if (key := f'@{line.split("@")[1]}@') in keys:
                        text = keys[key]
                        line = text if text.startswith('*') else line.replace(key, keys[key]).replace('ARCFILE ', '')
                        keys.pop(key, '')
                    else:
                        self.add_error(f'Signature {key} not replaced by any value')
                f_out.write(line)
                f_out.write('\n')

        # Check that all keys have been found
        for key in keys.keys():
            self.add_error(f'Signature {key} was not found in a template control file {template}')

        return not self.has_errors

    # Make backup file for global file
    def make_backup(self, gpath):
        backup = f'{gpath}.bck_{self.pid}'
        try:
            shutil.copyfile(gpath, backup)
            chmod(backup)
            return backup
        except Exception as err:
            self.add_error(f'Could not make backup of {os.path.basename(gpath)} [{str(err)}]')
            return None

    # Check if temporary file exists and remove it
    def remove_files(self, *args):
        for path in args:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    self.add_error(f'Could not delete {path}')

    # Control the update of global file
    def update_global_file(self, tmp_path, glb_path):
        # Make backup
        bck_path = f'{glb_path}.bck_{self.pid}'
        glb_name, bck_name = [os.path.basename(path) for path in [glb_path, bck_path]]
        try:
            shutil.copyfile(glb_path, bck_path)
            chmod(bck_path)
        except Exception as err:
            self.add_error(f'Could not make backup of {glb_name} [{str(err)}]')
            return False
        # Rename global file
        try:
            shutil.move(tmp_path, glb_path, copy_function=shutil.copyfile)
            chmod(glb_path)
            self.remove_files(bck_path)
            logger.info(f'{glb_path} updated')
            return True
        except Exception as err:
            self.add_error('Serious error in attempt to move the new file to the old place.')
            self.add_error(f'The old file {glb_name} is probably spoiled!!! Check the backup copy {bck_name}')
            self.add_error(f'Error [{str(err)}]')
            self.remove_files(tmp_path)
            return False

    # Read OPA configuration file
    def read_opa_config(self, path):
        # Store the path of the files file
        setattr(self, 'OPA_CONFIG', path)
        # Store data into class attribute
        for key, val in readDICT(path).items():
            setattr(self, key, val)

    def save_output(self, db_name, txt, ext):
        path = os.path.join(gettempdir(), f'{db_name}_{self.action}.{ext}')
        with open(path, 'w') as out:
            out.write(txt)

    # Use popen to execute a command
    def execute_command(self, cmd, db_name=None):
        try:
            st_out, st_err = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE).communicate()
            st_out, st_err = st_out.decode('utf-8'), st_err.decode('utf-8')
            if db_name:
                self.save_output(db_name, st_out, 'txt')
                self.save_output(db_name, st_err, 'err')
            if st_err:
                self.add_error(st_err)
                return st_out.splitlines() if st_out else f"ERROR: {st_err}"
            return st_out.splitlines()
        except Exception as err:
            self.add_error(str(err))
            return st_out.splitlines() if st_out else f"ERROR: {str(err)}"

    def is_executable(self, app_name):
        # Check if app_name is a full path
        if app_name.startswith('/'):
            if os.path.exists(app_name) and os.path.isfile(app_name) and os.access(app_name, os.X_OK):
                logger.info(f'executable {app_name}')
                return True
            self.add_error(f'{app_name} is not executable')
            return False
        # Check if app_name in user's path
        if full_path := shutil.which(app_name):
            logger.info(f'executable {app_name} {full_path}')
            return True
        # Add error message
        self.add_error(f'{app_name} is not in PATH')
        return False
