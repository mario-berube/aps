import os
import tempfile
import tarfile
import zipfile
from pytz import UTC
from datetime import datetime

from netCDF4 import Dataset

from utils.utctime import utc


# Compress and uncompress vgosdb file
class VGOStgz:

    def __init__(self, db_name, path):
        self.db_name, self.path = db_name, path
        self._problems = []

    # Add text to problem list
    def problem(self, txt):
        self._problems.append(txt)

    # Return problems as string
    def problems(self):
        return '\n'.join(self._problems)

    # Get CORRTIME from GSI correlator file
    def get_gsi_corr_time(self, lines):
        for line in lines:
            text = line.decode('utf-8').strip()
            if text.startswith('CORRTIME'):
                return UTC.localize(datetime.strptime(text.split()[-1], '%Y/%m/%d'))
            elif text.startswith('START'):
                try:
                    return UTC.localize(datetime.strptime(text.split()[-1], '%Y-%m-%d-%H%M'))
                except ValueError:
                    return UTC.localize(datetime.strptime(text.split()[-1], '%Y-%j-%H%M'))
        return None

    def find_gsi_corr_report(self, file):
        in_proc = False
        for line in file:
            if (line := line.decode('utf-8').strip()).startswith('Begin Process Calc/Solve Processing'):
                in_proc = True
            elif in_proc and line.startswith('History'):
                return line.split()[1]
        return None

    # Get create_time from tgz file
    def get_create_time(self):
        def get_basedir(tgz):
            for info in tgz.getmembers():
                name = info.name
                if os.path.basename(name) == 'Head.nc':
                    return os.path.dirname(name)
            return ''
        with tarfile.open(self.path, 'r:gz') as tgz:
            # Extract information from Head.nc file
            if not (folder := get_basedir(tgz)) or not (head := tgz.getmember(os.path.join(folder, 'Head.nc'))):
                return False, "FATAL: Missing Header Record File"
            file = tgz.extractfile(head.name)
            with Dataset('dummy', mode='r', memory=file.read()) as nc:
                create_time = utc(vgosdb=nc.variables['CreateTime'][:].tobytes().decode('utf-8').replace(' UTC', ''))
                program = nc.variables['Program'][:].tobytes().decode('utf-8')
                correlator = nc.variables['Correlator'][:].tobytes().decode('utf-8').strip()
                if program.startswith('db2vgosDB') and correlator == 'GSI':
                    wrapper = sorted([name for name in tgz.getnames() if name.endswith('.wrp')])[0]
                    if not(corr := self.find_gsi_corr_report(tgz.extractfile(wrapper))):
                        return None, 'No GSI correlator report'
                    if not (corr_time := self.get_gsi_corr_time(tgz.extractfile(os.path.join(folder, 'History', corr)))):
                        return None, 'No GSI correlator report'
                    if (create_time - corr_time).days > 90:
                        return None, f'GSI correlator report too old ({corr_time.strftime("%Y-%m-%d")}'
                    return create_time, ''  # Good GSI

            if not program.startswith('vgosDbMake'):
                return None, 'Not created by vgosDbMake'

            return create_time, ''

    # Extract vgosDB to specified folder
    def extract_tar(self, folder):
        def get_basedir(tar):
            for info in tar.getmembers():
                name = info.name
                if os.path.basename(name) == 'Head.nc':
                    return os.path.dirname(name)
            return ''

        def get_members(tar, basedir):
            for info in tar.getmembers():
                info.name = os.path.relpath(info.name, basedir)
                yield info

        try:
            with tarfile.open(self.path) as tar:
                basedir = get_basedir(tar)
                for member in get_members(tar, basedir):
                    tar.extract(member, folder)
            return True
        except Exception as err:
            if not self.path:
                self.problem(f'Problem extracting {self.db_name} - TMP file is None')
            else:
                exists = os.path.exists(self.path)
                self.problem(f'Problem extracting {self.db_name} - Exists {exists}\n{str(err)}')
            return False

    def extract_zip(self, folder):
        def get_basedir(zip):
            for file in zip.namelist():
                if os.path.basename(file) == 'Head.nc':
                    return os.path.dirname(file)
            return ''

        def make_dir_path(folder):
            parent = os.path.dirname(folder)
            if not os.path.isdir(parent):
                make_dir_path(parent)
            if not os.path.isdir(folder):
                os.mkdir(folder)

        try:
            zip = zipfile.ZipFile(self.path)
            # Find basedir using Head.nc file
            basedir = get_basedir(zip)
            # Rename all files with new folder and download
            for file in zip.namelist():
                info = zip.getinfo(file)
                path = os.path.join(folder, os.path.relpath(file, basedir))
                if info.is_dir():
                    make_dir_path(path)
                else: # extract a specific file from zip
                    with open(path, 'wb') as f:
                        zf = zip.open(file)
                        f.write(zf.read())
            return folder
        except Exception as err:
            self.problem(f'Problem extracting {self.db_name} - {str(err)}')
            return None

    def extract(self, folder):
        success = False
        if tarfile.is_tarfile(self.path):
            success = self.extract_tar(folder)
        elif zipfile.is_zipfile(self.path):
            success = self.extract_zip(folder)
        if not success:
            if not self.path:
                self.problem(f'{self.db_name} not a compress file - TMP file is None')
            else:
                self.problem(f'{self.db_name} is not a compress file')
        return success

    # Compress
    def compress(self, folder):
        basedir = os.path.dirname(folder)
        path = os.path.join(tempfile.gettempdir(), self.db_name+'.tgz')
        with tarfile.open(path, "w:gz") as tar:
            for root, dirs, files in os.walk(folder):
                for file in files:
                    dir = os.path.relpath(root, basedir)
                    tar.add(os.path.join(root, file), arcname=os.path.join(dir, file))

        return path
