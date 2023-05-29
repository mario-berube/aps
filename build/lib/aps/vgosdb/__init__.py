from datetime import datetime, timedelta
from operator import attrgetter
from pytz import UTC
import os
import re
from collections import defaultdict

import numpy as np
from netCDF4 import Dataset

from utils import app, bstr
from utils.files import TEXTfile
from utils.utctime import utc, vgosdbTime
from ivsdb import IVSdata
from vgosdb.wrapper import Wrapper
from vgosdb.correlator import CorrelatorReport


get_db_name = re.compile('(?P<name>\d{2}[A-Z]{3}\d{2}[A-Z]{1,2}|\d{8}-[a-z0-9]{1,12}).*$').match


# Extract year from db_name and join with vgosDB folder and db_name
def vgosdb_folder(db_name):
    year = db_name[:4] if db_name[:8].isdigit() else datetime.strptime(db_name[0:2], '%y').strftime('%Y')
    return os.path.join(app.VLBIfolders.vgosdb, year, db_name)


# Class to process vgosDB files
class VGOSdb:
    Standard = 'standard'
    Intensive = 'intensive'
    VGOS = 'vgos'
    Unknown = 'unknown'

    def __init__(self, folder):
        self._valid = False
        self.errors = []
        self.wrappers = []
        self.wrapper = self.create_time = None
        self.program = self.session = self.exp_name = self.exp_desc = self.correlator = self.correlatorType = ''
        self.correlated = 0
        self.station_list, self.stations, self.sources = [], {}, []

        # Variables for statistics
        self.stats = {}
        self.recoverable = self.good = self.used = 0
        self.deselected_bl, self.deselected_st = [], []
        self.clk_ref_station, self.clk_stations, self.atm_station_list = '', [], []

        folder = str(folder)
        self.folder = folder[:-1] if folder and folder.endswith('/') else folder
        if not os.path.exists(self.folder):
            print(self.folder, 'doest not exist')
            return
        try:
            self.name = get_db_name(os.path.basename(self.folder))['name']
        except:
            print('Invalid db_name')
            return

        self._valid = True

        # Find the oldest wrapper and retrieve processes and var_list
        self.wrapper = oldest = self.get_oldest_wrapper(reload=True)
        # Read master to find if standard, intensive or vgos
        self.code, self.type, self.year = self.get_session_info()
        # Read Head.nc file
        self.read_head(oldest)

        self.corr, self.corr_path = None, None

    # Set the wrapper that will be used by default
    def set_wrapper(self, wrapper):
        self.wrapper = wrapper

    def is_valid(self):
        return self._valid

    @staticmethod
    def get_optional(src, name):
        try:
            return src.variables[name][:].tostring().decode('utf-8').upper()
        except:
            return ''

    # Read Head.nc file
    def read_head(self, wrapper):
        if not (head := wrapper.get_head()):
            return
        path = os.path.join(self.folder, head)
        with Dataset(path, 'r') as src:
            # Get create time and program
            created = src.variables['CreateTime'][:].tostring().decode('utf-8').replace(' UTC', '')
            self.create_time = utc(vgosdb=created)
            self.program = src.variables['Program'][:].tostring().decode('utf-8')
            # Get session info
            self.session = self.get_optional(src, 'Session')
            self.exp_name = self.get_optional(src, 'ExpName')
            self.exp_desc = self.get_optional(src, 'ExpDescription')

            try:
                # Get correlator and type
                self.correlator = self.S1_string(src.variables['Correlator'][:])
                self.correlatorType = self.S1_string(src.variables['CorrelatorType'][:])
                # Get number of observations in database
                self.correlated = int(src.variables['NumObs'][0])
            except:
                pass

            if self.correlated:
                # Get station list
                self.station_list = [sta for val in src.variables['StationList'][:] if (sta := self.S1_string(val))]
                self.stations = {name: {'code': '', 'vlba': False, 'met': False} for name in self.station_list}
                # Get source list
                self.sources = [src for val in src.variables['SourceList'][:] if (src := self.S1_string(val))]
            else:
                self.correlated = self.get_numobs()

    # Get list of wrappers in vgosdb directory
    def get_wrappers(self):
        self.wrappers = []
        for filename in os.listdir(self.folder):
            if filename.endswith('.wrp'):
                path = os.path.join(self.folder, filename)
                with Wrapper(path) as wrp:
                    if wrp.version:
                        wrp.read()
                        self.wrappers.append(wrp)

    def get_numobs(self):
        if (path := os.path.join(self.folder, 'Observables', 'TimeUTC.nc')) and os.path.exists(path):
            try:
                with Dataset(path, 'r') as nc:
                    return nc.dimensions['NumObs'].size
            except:
                pass
        return 0

    # Get oldest wrapper:
    def get_oldest_wrapper(self, reload=False):
        if reload:
            self.get_wrappers()
        return sorted(self.wrappers, key=attrgetter('version', 'time_tag'))[-1]

    # Get last wrapper for this agency (GSFC):
    def get_last_wrapper(self, agency, reload=False):
        if reload:
            self.get_wrappers()
        lst = sorted(filter(lambda x: x.agency == agency and x.subset == 'all', self.wrappers),
                     key=attrgetter('version'))
        return lst[-1] if lst else None

    # Get first wrapper for this agency (GSFC):
    def get_first_wrapper(self, agency, reload=False):
        if reload:
            self.get_wrappers()
        lst = sorted(filter(lambda x: x.agency == agency, self.wrappers), key=attrgetter('version'))
        return lst[0] if lst else None

    # Get V001 wrapper:
    def get_v001_wrapper(self, reload=False):
        if reload:
            self.get_wrappers()
        lst = sorted(filter(lambda x: x.version == 'V001', self.wrappers), key=attrgetter('time_tag'))
        return lst[0] if lst else None

    # Read data base to extract session name and type
    def get_session_info(self):
        url, tunnel = app.get_dbase_info()
        with IVSdata(url, tunnel) as dbase:
            if ses_id := dbase.get_db_session_code(self.name):
                session = dbase.get_session(ses_id)
                return ses_id, session.type, session.start.strftime('%Y')
        return None, VGOSdb.Unknown, None

    # List variables
    @staticmethod
    def list_variables(path):
        vars = {}
        skip = ['Stub', 'CreateTime', 'CreatedBy', 'Program', 'Subroutine', 'vgosDB_Version', 'DataOrigin', 'Session', 'TimeTag', 'TimeTagFile']
        with Dataset(path, 'r') as src:
            for var in src.variables:  # list of nc variables
                if var not in skip:
                    print(os.path.basename(path), var)
                    vars[var] = path
        return vars

    # Extract correlator report
    def get_corr_report(self):
        for proc in self.get_v001_wrapper().processes.values():
            if filename := proc.get('history', '').strip():
                self.corr_path = os.path.join(self.folder, 'History', filename)
                with CorrelatorReport(self.corr_path) as corr:
                    if corr.read():
                        self.corr = corr
                        return True
        return False

    # Get correlator report
    def correlator_report(self):
        return self.corr.text if self.corr or self.get_corr_report() else ''

    # Save correlator report in session folder
    def save_correlator_report(self):
        if self.year and (self.corr or self.get_corr_report()):
            report_errors = []
            if self.name.lower() != self.corr.db_name.lower():
                report_errors.append(f'Correlator report has wrong db_name {self.corr.db_name}')
            if self.corr.ses_id not in [self.code.upper(), self.session, self.exp_name, self.exp_desc]:
                report_errors.append(f'Correlator report has wrong session name {self.corr.ses_id}')
            if self.corr.is_template:
                report_errors.append('Correlator report seems to be a template')
            if report_errors:
                self.errors.extend(report_errors)
                self.errors.extend(['', 'Correlator report not saved'])
                return ''
            name = f'{self.code}.corr'
            self.errors.append('')
            self.corr.save(os.path.join(app.VLBIfolders.session, self.year, self.code, name))
            self.errors.append(f'Correlator report saved in {self.code.upper()}')
            return name
        return ''

    def get_dbmake_warnings(self):
        app_name = 'vgosDbMake'
        wrapper = self.get_v001_wrapper()
        if app_name in wrapper.processes:
            file_name = wrapper.processes[app_name]['history']
            path = os.path.join(self.folder, 'History', file_name)
            with TEXTfile(path) as file:
                while file.has_next():
                    if file.line.startswith('w ') or file.line.strip().startswith('Warning:'):
                        return f'WARNINGS in {app_name}! Check {file_name}\n'
        return ''

    # Print summary of vgosDB
    def summary(self, agency):
        lines = []
        timefmt = lambda t: t.strftime('%Y/%m/%d %H:%M:%S UTC')
        try:
            lines.extend([f'{self.name} {self.code.upper()} {timefmt(self.create_time)}', self.folder, ''])
            self.get_wrappers()  # read all wrappers
            for wrapper in sorted(self.wrappers, key=attrgetter('version', 'time_tag')):
                lines.append(wrapper.name)
            lines.append('')

            if wrapper := self.get_last_wrapper(agency):
                for name, prc in wrapper.processes.items():
                    lines.append(f'{name:25s} {timefmt(prc["runtimetag"])} {prc["history"]}')
                lines.append('')
            else:
                lines.append(f'No {agency} wrappers')
            if warnings := self.get_dbmake_warnings():
                lines.extend([warnings, ''])
            lines.extend(self.errors)

            return('\n'.join(lines))

        except Exception as err:
            return f'Problem creating summary!\n{str(err)}'

    # Change S1 variable to string
    def S1_string(self, data):
        return data.tostring().decode('utf-8').strip('\x00').strip()

    # Change S1 variable or multi dimension S1 array in string
    def cleanS1var(self, data, ndim):
        return self.S1_string(data) if ndim < 1 else [self.cleanS1var(value, ndim - 1) for value in data]

    # Get variable data
    def get_variable(self, path, name, is_str=False):
        with Dataset(path, 'r') as nc:
            if name not in nc.variables:
                print(f'{name} not found')
                return np.ma.core.MaskedArray([])
            var = nc.variables[name]
            data = var[:][0] if var.dimensions[0] == 'DimUnity' else var[:]
            ndim = len(var.dimensions)
            if 'REPEAT' in var.ncattrs():
                data = [data] * var.getncattr('REPEAT')
                ndim += 1
            # Transform S1 arrays in STRING array
            if is_str and var.dtype == 'S1':
                data = self.cleanS1var(data, ndim - 1)
            return np.ma.core.MaskedArray(data) if isinstance(data, list) else data

    # Extract UTC time and combine YMDHM and Second in datetime variables
    def get_utctime(self, path):
        utc = []
        with Dataset(path, 'r') as nc:
            for ymdhm, second in zip(nc.variables['YMDHM'], nc.variables['Second']):
                t_str = '{:02d}-{:02d}-{:02d} {:02d}:{:02d}:{:09.6f}'.format(*ymdhm, second)
                try:
                    t = UTC.localize(datetime.strptime(t_str, '%y-%m-%d %H:%M:%S.%f'))
                except:
                    t = UTC.localize(datetime.strptime(t_str, '%Y-%m-%d %H:%M:%S.%f'))
                utc.append(t)
        return np.ma.core.MaskedArray(utc)

    # Dump details of variable
    @staticmethod
    def dump_var(name, var):
        fmt = '      {:<12s}: {}'.format
        print('Name:', name)
        print(fmt('dimensions', var.dimensions))
        print(fmt('size', var.size))
        print(fmt('type', repr(var.dtype)))
        for attr in var.ncattrs():
            print(fmt(attr, var.getncattr(attr)))

    # Show all variable in a file
    @staticmethod
    def show_variables(path):
        ignore = ['Stub', 'CreateTime', 'CreatedBy', 'Program', 'Subroutine', 'DataOrigin', 'Session',
                  'vgosDB_Version', 'Station', 'TimeTag', 'TimeTagFile', 'CalcVer', 'Kind', 'Band']

        with Dataset(path, 'r') as nc:
            for name in nc.variables:
                if name not in ignore:
                    VGOSdb.dump_var(name, nc.variables[name])

    # Get variable using var_list information
    def get_data(self, group, key, var_name, is_str=False):
        if rel_path := self.wrapper.var_list[group.lower()].get(key.lower(), ''):
            path = os.path.join(self.folder, rel_path)
            return self.get_utctime(path) if var_name == 'YMDHMS' else self.get_variable(path, var_name, is_str)
        return np.ma.MaskedArray([])

    # Compile statistics for this sessions
    def statistics(self):
        # Get AtmRateStationList
        self.atm_station_list = self.get_data('Session', 'AtmSetup', 'AtmRateStationList', is_str=True)
        # Get clock information
        self.clk_ref_station = self.get_data('Session', 'ClockSetup', 'ReferenceClock', is_str=True)
        self.clk_stations = self.get_data('Session', 'ClockSetup', 'ClockRateConstraintStationList', is_str=True)

        # Get selected baseline information
        selected_bl = self.get_data('Session', 'SelectionStatus', 'BaselineSelectionFlag')

        # Initialize statistics for stations, baselines and sources
        for name in [*self.station_list, *self.sources]:
            self.stats[name] = {'used': 0, 'recov': 0, 'good': 0, 'corr': 0}
        if not self.stats:
            return
        for i, fr in enumerate(self.station_list):
            for j, to in enumerate(self.station_list[i+1:]):
                key1 = '{}-{}'.format(fr, to)
                key2 = '{}-{}'.format(to, fr)
                l = i + j + 1
                # Both keys are using same data set
                self.stats[key1] = self.stats[key2] = {'used': 0, 'recov': 0, 'good': 0, 'corr': 0}
                if selected_bl.size and (selected_bl[i, l] == 0 or selected_bl[l, i] == 0): # add baseline keys into list of deselected baselines
                    self.deselected_bl.extend([key1, key2])
                else: # Remove stations from list of deselected stations
                    if fr in self.deselected_st:
                        self.deselected_st.remove(fr)
                    if to in self.deselected_st:
                        self.deselected_st.remove(to)
        # Compile stats
        good_qc = b'56789'

        for index, bl, src, utc, qc_x, qc_s, fc_x, fc_s, flg in self.get_all_obs():
            recoverable = 0 if flg > 1 else 1
            good = usable = 0
            if qc_s in good_qc and qc_x in good_qc:
                good = 1
                usable = 1 if flg == 0 else 0

            self.recoverable += recoverable
            self.used += usable
            # Update statistics for stations, source and baseline
            for key in [bl[0], bl[1], src, '{}-{}'.format(bl[0], bl[1])]:
                stats = self.stats[key]
                stats['good'] += good
                stats['recov'] += recoverable
                stats['used'] += usable
                stats['corr'] += 1

    # Get list of all observations
    def get_scans(self):
        # Compile list of not usable observations
        Names = self.get_data('Scan', 'ScanName', 'ScanName', is_str=True)
        FullNames = self.get_data('Scan', 'ScanName', 'ScanNameFull', is_str=True)
        UTC = self.get_data('Scan', 'TimeUTC', 'YMDHMS')
        return zip(Names, FullNames, UTC)

    # Get list of all observations
    def get_all_obs(self):
        # Compile list of not usable observations
        Baselines = self.get_data('Observation', 'Baseline', 'Baseline', is_str=True)
        Sources = self.get_data('Observation', 'Source', 'Source', is_str=True)
        UTC = self.get_data('Observation', 'TimeUTC', 'YMDHMS')
        QCx = self.get_data('Observation', 'QualityCode_bX', 'QualityCode')
        QCs = self.get_data('Observation', 'QualityCode_bS', 'QualityCode')
        if QCs.size == 0: # Probably VGOS session
            QCs = QCx
        FCx = self.get_data('Observation', 'CorrInfo_bX', 'FRNGERR')
        if FCx.size == 0: # Probably VGOS session or K5 correlator
            FCx = np.ma.core.MaskedArray([b' '] * self.correlated)
        FCs = self.get_data('Observation', 'CorrInfo_bS', 'FRNGERR')
        if FCs.size == 0: # Probably VGOS session or K5 correlator
            FCs = FCx

        Flags = self.get_data('Observation', 'Edit', 'DelayFlag')
        if Flags.size == 0:
            Flags = np.ma.core.MaskedArray([0] * self.correlated)
        indexes = np.arange(1, self.correlated + 1) # Index (base 1) of each observation

        return zip(indexes, Baselines, Sources, UTC, QCx, QCs, FCx, FCs, Flags)
    # Get list of correlated sources with usage
    def get_source_statistics(self):
        sources = defaultdict(int)
        for src in self.get_data('Observation', 'Source', 'Source', is_str=True):
            # Store number of correlated scans for each source
            sources[src] += 1
        return sources

    def get_uncorrelated_observations(self, schedule):
        corr, not_corr = defaultdict(list), []
        for index, bl, src, utc, qc_x, qc_s, fc_x, fc_s, flg in self.get_all_obs():
            key = f'{bl[0]}:{bl[1]}:{src}'
            # Store time of each scan
            corr[key].append(utc)
        # Get list of removed stations
        removed = set(schedule.missed) | set(self.deselected_st)
        # Extract list of uncorrelated scans.
        for index, obs in enumerate(schedule.obs_list):
            fr = obs['fr']
            fr_name = schedule.stations['codes'][fr]['name']
            if fr_name not in self.station_list or fr_name in removed:
                continue
            to = obs['to']
            to_name = schedule.stations['codes'][to]['name']
            if to_name not in self.station_list or to_name in removed:
                continue

            scan = obs['scan']
            duration = min(scan['station_codes'][fr]['duration'], scan['station_codes'][to]['duration'])
            start = scan['start']
            stop = start + timedelta(seconds=duration)
            key = f'{fr_name}:{to_name}:{obs["scan"]["source"]}'
            if key not in corr:
                key = '{}:{}:{}'.format(to_name, fr_name, obs['scan']['source'])
            if key not in corr or not any([start <= t <= stop for t in corr[key]]):
                not_corr.append(f"    observation of {obs['scan']['source']:8s} at {start.strftime('%H:%M:%S')}")
        return not_corr

    # Get list of not usable observations
    def get_rejected_obs(self, unusable, excluded):

        self.unusable, self.excluded = [], []
        # Format for rejected and not rejected observations
        fmt_not = '{:4d}, {:8s}:{:8s}, {:8s}, {:8s}, quality code X: {} S: {}, fringe code X: \'{}\' S: \'{}\''.format
        fmt_rej = '{:4d}, {:8s}:{:8s}, {:8s}, {:8s}, which fits at {:10.1f} +/- {:9.1f} ps'.format

        all_obs = self.get_all_obs()
        for index in unusable:
            id, bl, src, utc, qc_x, qc_s, fc_x, fc_s, flg = all_obs[index]
            line = fmt_not(index, bl[0], bl[1], src, utc.strftime('%H:%M:%S'),
                           bstr(qc_x), bstr(qc_s), bstr(fc_x), bstr(fc_s))
            self.unusable.append(line)

        for index in sorted(list(excluded.keys())):
            bl, src, utc, qc_x, qc_s, fc_x, fc_s, flg = all_obs[index]
            values = excluded[index]
            line = fmt_rej(index, bl[0], bl[1], src, utc.strftime('%H:%M:%S'), values[0], values[1])
            self.excluded.append(line)

    # Print all observations
    def dump_observables(self):
        if name := self.var_list['OBSERVATION']['FILES'].get('TIMEUTC', ''):
            path = os.path.join(self.folder, name)
            for id, timeUTC in enumerate(read_vgosdb_time(path)):
                print(f'{id:5d} {str(timeUTC)}')


# Read vgosDB time from
def read_vgosdb_time(path):
    timeUTC = []
    with Dataset(path,"r") as time_file:
        # match each Timestamp with the corresponding second
        for YMDHM, sec in zip(time_file.variables['YMDHM'], time_file.variables['Second']):
            timeUTC.append(vgosdbTime(YMDHM, sec))
    return timeUTC


def vgosDb_dump(db_name):

    folder = vgosdb_folder(db_name)

    print(folder)

    vgosdb = VGOSdb(folder)

    print(vgosdb.name)
    print(vgosdb.code)
    print(vgosdb.session)
    print(vgosdb.type)
    print(vgosdb.get_v001_wrapper().path)



if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser(description='Update web pages')
    parser.add_argument('-c', '--files', help='adap control file', default='~/.files/adap/vlbi.toml', required=False)
    parser.add_argument('-d', '--db', help='database name', default='ivscc', required=False)
    parser.add_argument('db_name', help='vgosDb name')

    args = app.init(parser.parse_args())

    print(args.db_name, args.config)
    vgosDb_dump(args.db_name)