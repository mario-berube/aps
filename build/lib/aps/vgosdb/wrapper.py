import os
import re
import sys
from datetime import datetime, timedelta
from pytz import UTC

from aps.utils.files import TEXTfile

# Regex to extract information in wrapper
get_name_version = re.compile(r'(?P<name>.*)_v\d{3}\.nc').match
get_name = re.compile(r'(?P<name>.*)\.nc').match
# Regex to extract information from wrapper filename
get_wrapper_info = re.compile(r'[a-zA-Z0-9-]*_(?P<version>V\d{3})_(?P<agency>\w{3,5})_(?P<subset>.*)\.wrp').match


# Class holding information taken from wrapper files.
class Wrapper(TEXTfile):

    def __init__(self, path):
        super().__init__(path)

        self.name, self.folder = os.path.basename(path), os.path.dirname(path)
        self.version, self.agency, self.subset = '', '', ''

        if info := get_wrapper_info(self.name):
            self.version, agency, subset = info['version'], info['agency'], info['subset']
            self.agency = agency[1:] if agency.startswith('i') else agency
            self.subset = subset[1:] if subset.startswith('k') else subset

        self.time_tag = UTC.localize(datetime(1900, 1, 1))
        self.processes, self.var_list = {}, {}

    # Return name of wrapper for print
    def __str__(self):
        return self.name

    # Get head file name. Sometimes the V00x is attached to head name
    def get_head(self):
        for key in list(self.var_list['session'].keys()):
            if key.startswith('head'):
                return self.var_list['session'][key]
        return ''

    # Special function to decode time with possible problem with 60 seconds
    def decode_timetag(self, data):
        # Sometime the datetime.strptime failed because of seconds = 60 or hours = 24.
        data = data.replace('UTC', '').strip()
        hour, minute, second = list(map(int, data[-8:].split(':')))
        seconds = second + minute * 60 + hour * 3600
        return UTC.localize(datetime.strptime(data[:10], '%Y/%m/%d') + timedelta(seconds=seconds))

    # Read var_list from wrapper
    def read(self):
        while self.has_next():
            line = self.line.lower()
            if line.startswith('begin'):
                tokens = line.split()[1:]
                if tokens[0] == 'history':
                    self.get_history()
                elif tokens[0] == 'station':
                    self.get_var_info(tokens[1])
                elif tokens[0] == 'program':
                    self.get_program_info()
                elif len(tokens) == 1:
                    self.get_var_info(tokens[0])

    def get_program_info(self):
        end = self.line.lower().replace('begin', 'end') # Use last line to form end tag
        directory = ''
        while self.has_next():
            line = self.line.lower()
            if line.startswith(end):
                return
            elif line.startswith('default_dir'):
                directory = self.line.split()[1]
            elif line.startswith('begin'):
                tokens = line.split()[1:]
                if len(tokens) == 1:
                    self.get_var_info(tokens[0], directory)

    def get_process_info(self):
        info = {}
        end = self.line.lower().replace('begin', 'end') # Use last line to form end tag
        while self.has_next():
            if self.line.lower().startswith(end):
                return info
            elif not self.line.startswith('!'):
                key, data = self.line.split(' ', 1)
                if key.lower() == 'runtimetag':
                    data = self.decode_timetag(data)
                    self.time_tag = max(self.time_tag, data)
                info[key.lower()] = data

    def get_history(self):
        end = self.line.lower().replace('begin', 'end') # Use last line to form end tag
        while self.has_next():
            line = self.line.lower()
            if line.startswith(end):
                return
            elif line.startswith('begin process'):
                key = os.path.basename(self.line.split()[2])
                self.processes[key] = self.get_process_info()

    def get_var_info(self, key, directory=''):
        if key not in self.var_list:
            self.var_list[key] = {}
        info = self.var_list[key]

        end = self.line.lower().replace('begin', 'end') # Use last line to form end tag
        while self.has_next():
            line = self.line.lower()
            if line.startswith(end):
                return
            elif line.startswith('default_dir'):
                directory = self.line.split()[1]
            elif not line.startswith('!'):
                key = line.split()[0]
                if key.endswith('.nc'):
                    match = get_name_version(key)
                    name = match['name'] if match else get_name(key)['name']
                    if name.startswith('corrinfo'):
                        name = 'corrinfo_{}'.format(name.split('_')[-1])
                    path = os.path.join(directory, self.line)
                    if name in info:
                        print('CONFLICT in wrapper variables', key, info[name], name, path)
                        self.show_var_list()
                        sys.exit(0)
                    info[name] = path
                elif len(line.split()) > 1:
                    _, info[key] = self.line.split(' ', 1)

    def has_cal_cable(self):
        for item in self.var_list.values():
            if isinstance(item, dict):
                if 'cal-cable_kpcmt' in item.keys():
                    return True
        return False

    def show_processes(self):
        for name, process in self.processes.items():
            print(name, process)

    def show_var_list(self):
        for name, info in self.var_list.items():
            for key, value in info.items():
                print(name, key, value)

