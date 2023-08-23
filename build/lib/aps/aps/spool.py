import re
import os
from pathlib import Path
import glob
from collections import OrderedDict

from aps.utils import app, to_float, to_int
from aps.utils.files import TEXTfile
from aps.utils.utctime import utc, MJD

# Regex to decode specific line. Valid for POST2005 and PRE2005 format
delay_info = re.compile(r'.*(?:Delay|Delay\(All\))[ ]*(?P<used>[0-9]*)[ ]*(?P<wrms>[0-9\.]*) ps .*').match
rate_info = re.compile(r'.*(?:Rate|Rate\(All\))[ ]*(?P<used>[0-9]*)[ ]*(?P<rate>[0-9\.]*) fs/s[ ]*.*').match
baseline_data = re.compile(r' (?P<fr>.{8})\-(?P<to>.{8})(?P<used>[ 0-9]{4,5})/(?P<recov>[ 0-9]{5}).*').match
baseline_nodata = re.compile(r' (?P<fr>.{8})\-(?P<to>.{8}).*No Data.*').match
source_data = re.compile(r'(?:\s{5}|SRC_STAT:\s{2})(?P<name>.{8})\s[\sA-Z]\s+(?P<used>[0-9]+)[/\s]+(?P<recov>[0-9]+).*').match
station_data = re.compile(r' {5}(?P<name>.{8})     (?P<used>[ 0-9]{5})/(?P<recov>[ 0-9]{5}).*').match
param_clock = re.compile(r'[ 0-9]{5}\. (?P<sta>.{8}) (?P<code>AT|CL|BR) (?P<id>[0-9]) (?P<time>.{14}).*').match
param_coord = re.compile(r'[ 0-9]{5}\. (?P<sta>.{8}).{12}(?P<code>[XYZ]) Comp.*').match
check_db_name = re.compile('^ Data base (?P<name>[$]?\d{2}[A-Z]{3}\d{2}[A-Z]{1,2}|\d{8}-\w{1,12}) .*$').match
baseline_clock = re.compile(r'[ 0-9]{5}\. (?P<fr>.{8})-(?P<to>.{8}) Clock offset.*').match


# Decode header line
def add_header_info(header, line):
    if (key := line[0:18].strip()).endswith(':'):
        key, info = key[:-1], line[18:].strip()
        if key == 'Listing_Options':
            options, values = header.get(key, {}), iter(info.split())
            for val in values:
                options[val] = next(values)
            header[key] = options
        else:
            header[key] = info
        return True
    return False


class Section:
    # Define needed records and their categories (EOP, NUT)
    need = {'. X Wobble  0': ('XEOP', 'EOP'),
            '. X Wobble  1': ('XREOP', 'EOP'),
            '. Y Wobble  0': ('YEOP', 'EOP'),
            '. Y Wobble  1': ('YREOP', 'EOP'),
            '. UT1-TAI   0': ('UEOP', 'EOP'),
            '. UT1-TAI   1': ('REOP', 'EOP'),
            '. UT1-TAI   2': ('QEOP', 'EOP'),
            '  Nutation DPSI': ('PEOP', 'NUT'),
            '  Nutation DEPS': ('EEOP', 'NUT'),
            'Nutation Dx   wrt   apriori model': ('XNUT', 'NUT'),
            'Nutation Dy   wrt   apriori model': ('YNUT', 'NUT')
            }
    # Define MJD for each category
    mjds = {'EOP': 'MJD_EOP', 'NUT': 'MJD_NUT'}
    # Define format for value and sigma for each variables (length, fraction, scale)
    eob = OrderedDict([('XEOP', [(8, 6, 1.0e-3), (8, 6, 1.0e-6)]),
                       ('YEOP', [(8, 6, 1.0e-3), (8, 6, 1.0e-6)]),
                       ('UEOP', [(11, 7, 1.0e-3), (9, 7, 1.0e-6)]),
                       ('XNUT', [(8, 3, 1.0), (7, 3, 1.0e-3)]),
                       ('YNUT', [(8, 3, 1.0), (7, 3, 1.0e-3)]),
                       ('PEOP', [(8, 3, 1.0), (7, 3, 1.0e-3)]),
                       ('EEOP', [(8, 3, 1.0), (7, 3, 1.0e-3)]),
                       ('XREOP', [(9, 6, 1.0e-3), (9, 6, 1.0e-6)]),
                       ('YREOP', [(9, 6, 1.0e-3), (9, 6, 1.0e-6)]),
                       ('REOP', [(7, 4, 1.0), (7, 4, 1.0e-3)])
                       ])

    def __init__(self, spl):
        self.DB_NAME = self.MJD_NUT = None
        self.USED, self.WRMS, self.RATE = 0, 0.0, 0.0
        self.spl = spl
        self.run_id = self.spl.line.strip().split()[1]
        self.POST2005 = False
        self.CORRELATION = [0] * 28
        self.Duration = 0
        self.stats = {'session': {}, 'baselines': {}, 'stations': {}, 'sources': {}}
        self.parameters = []
        self.header = {}
        self.read_all()
        self.MJD_NUT = self.MJD_NUT if self.MJD_NUT else getattr(self, 'MJD_EOP', 0.0)

    # Read header
    def read_header(self):
        while self.spl.has_next():
            line = self.spl.line
            if line.startswith('  Flyby'):
                #
                # Check if post2005 format and change decoding functions
                if self.header.get('Listing_Options', {}).get('SEG_STYLE', '') == 'POST2005':
                    self.POST2005 = True
                    self.decode_eops = self.decode_eops_post2005
                    self.decode_nutation = self.decode_nutation_post2005
                return True
            if has_db_name := check_db_name(line):
                self.DB_NAME = has_db_name['name'].replace('$', '')
            else:
                add_header_info(self.header, line)
        return False

    # Decode eops records
    def decode_eops(self, line):
        return to_float(line[38:49]), to_float(line[77:87]), to_float(line[99:108]), MJD(spool=line[21:35])

    # Decode eops records in POST2005 format
    def decode_eops_post2005(self, line):
        return to_float(line[45:57]), to_float(line[85:95]), to_float(line[105:116]), MJD(spl=line[21:44])

    # Decode nutation records
    def decode_nutation(self, line):
        return to_float(line[51:62]), to_float(line[67:77]), to_float(line[67:77]),MJD(spool=line[21:35])

    # Decode nutation records in POST2005 format
    def decode_nutation_post2005(self, line):
        return to_float(line[65:74]), to_float(line[79:89]), to_float(line[100:110]), MJD(spl=line[41:64])

    def read_eop_correlation(self):
        self.CORRELATION = []
        for row in range(8):
            if self.spl.has_next():
                # Extract all values in row except the last 1.000
                self.CORRELATION.extend([to_float(val) for val in re.findall('.{1,8}', self.spl.line[12:])[:-1]])

    @property
    def has_eop(self):
        return hasattr(self, 'EOP')

    @staticmethod
    def get_delay(line):
        return (to_int(info['used']), to_float(info['wrms'])) if (info := delay_info(line)) else (0, 0.0)

    @staticmethod
    def get_rate(line):
        return to_float(info['rate']) if (info := rate_info(line)) else 0.0

    def get_data(self, line):
        if (param := param_clock(line)) or (param := param_coord(line)) or (param := baseline_clock(line)):
            self.parameters.append(param)
        else:
            for string in Section.need.keys():
                if string in line:
                    key, code = Section.need[string]
                    val, a_sigma, m_sigma, mjd = self.decode_eops(line) if code == 'EOP' else self.decode_nutation(line)
                    setattr(self, key, [val, a_sigma, m_sigma])
                    if not hasattr(self, Section.mjds[code]):
                        setattr(self, Section.mjds[code], mjd)
                    return

    def decode_stats(self, Id, decoder):
        stats = self.stats[Id]
        while self.spl.has_next():
            data = decoder(self.spl.line)
            if data:
                stats[data['name'].strip()] = {'used': to_int(data['used']), 'recov': to_int(data['recov']) }
            elif stats:  # Stats not empty so it should be over
                return

    def decode_baseline_stats(self):
        stats = self.stats['baselines']
        while self.spl.has_next():
            no_data, data = baseline_nodata(self.spl.line), baseline_data(self.spl.line)
            if not no_data and not data and stats:  # Stats not empty so it should be over
                return
            if no_data:  # Database has no data
                key = f'{no_data["fr"].strip()}|{no_data["to"].strip()}'
                stats[key] = {'used': 0, 'recov': 0}
            elif data:  # Process data
                key = f'{data["fr"].strip()}|{data["to"].strip()}'
                stats[key] = {'used': to_int(data['used']), 'recov': to_int(data['recov']) }

    # Read all records in section
    def read_all(self):
        # Read the header
        if not self.read_header():
            return
        # Read each line
        while self.spl.has_next():
            line = self.spl.line
            if line.startswith('1Run'):
                return
            if line.startswith((' Nominal duration:', ' Actual duration:')):
                self.Duration = to_float(line.split(':')[1].split()[0])
            elif line.startswith('   Delay'):
                self.USED, self.WRMS = self.get_delay(line)
            elif line.startswith('   Rate'):
                self.RATE = self.get_rate(line)
            elif line.startswith(' Baseline Statistics'):
                self.decode_baseline_stats()
            elif line.startswith(' Source Statistics'):
                self.decode_stats('sources', source_data)
            elif line.startswith(' Station Statistics'):
                self.decode_stats('stations', station_data)
            elif line.startswith(' EOP Correlations:'):
                self.read_eop_correlation()
            elif line.startswith(' Number of potentially recoverable observations'):
                self.stats['session']['recov'] = to_int(line[55:60])
            elif line.startswith(' Number of potentially good observations'):
                self.stats['session']['good'] = to_int(line[55:60])
            elif line.startswith(' Number of used observations'):
                self.stats['session']['used'] = to_int(line[55:60])
            else:
                self.get_data(line)

    def fmt_val(self, val, err, width, precision):
        if err < 1.0E-20:
            return '{val:{width}s}'.format(width=width, val='-0')
        string = '{val:{width}.{precision}f}'.format(width=width, precision=precision, val=val)
        if width - precision == 2 and string.startswith('-0.'):
            return '-' + string[2:]
        return string

    def make_eob_record(self, stations, ses_id='??--??', wantXY=True):
        # Check if section has EOP data
        if not (mjd_eop := getattr(self, 'MJD_EOP', None)):
           return ''

        # Write EOP epoch, db_name and session name
        name = self.header.get('Experiment code', ses_id).lower()
        vals = [f'  {mjd_eop:12.6f} {self.DB_NAME:<24} {name:<12s}']
        # Build dictionary to write parameter values and errors
        pars = OrderedDict()
        removed = ['PEOP', 'EEOP'] if wantXY else ['XNUT', 'YNUT']
        for key, item in Section.eob.items():
            if key not in removed:
                pars[key] = item
        # Print values and then errors
        for _id in range(2):
            for key in pars.keys():
                data = getattr(self, key, [0, 0])
                width, precision, scale = pars[key][_id]
                vals.append(self.fmt_val(data[_id] * scale, data[1], width, precision))
        # Write correlation
        for index in [1, 6, 8, 27, 14, 10, 12]:
            val = self.CORRELATION[index] if hasattr(self, 'CORRELATION') else 0.0
            vals.append(f'{val:6.4f}'.replace('-0.', '-.'))

        # Define network
        if self.stats['stations']:
            network = [stations[name] for name in self.stats['stations'] if name in stations]
        else:
            network = [stations[name] for bl in self.stats['baselines'] for name in bl.split('|') if name in stations]
        network = sorted(list(set(network)))  # Sorted, oo duplicate

        # Write duration, WRMS,  number of used observation, nutation epoch and network
        vals.append(f'{self.Duration/3600:5.2f} {self.WRMS:7.2f} {self.USED:6d} {self.MJD_NUT:12.6f} '
                    f'{"".join(network)}')
        return ' '.join(vals)


class Spool(TEXTfile):

    def __init__(self, path):
        super().__init__(path)

        self.last_modified = os.path.getmtime(path)

        self.runs, self.header = [], {}
        self.data = {'Apriori model': {}, 'Stations': {}, 'Sources': {}, 'Sections': []}
        self.unused = {}
        self.valid = True
        self._errors = []

    def add_error(self, msg):
        self._errors.append(msg)
        return False

    # Test if has errors
    @property
    def has_errors(self):
        return len(self._errors) > 0

    # Return list of errors (1 per line)
    @property
    def errors(self):
        return '\n'.join(self._errors)

    # Return list of errors (1 per line)
    @property
    def sections(self):
        return self.data['Sections']

    def read_statistics(self):
        pass

    @staticmethod
    def get_position_index(line):
        if line[5:6] == '.':
            try:
                return int(line[0:5].strip())
            except:
                pass
        return -1

    @staticmethod
    def decode_coord(sta, coord, line):
        sta[coord] = (to_float(line[39:53]), to_float(line[83:93]))

    def get_or_create_station(self, name):
        if not (sta := self.data['Stations'].get(name, None)):
            sta = {'X': (None, None), 'Y': (None, None), 'Z': (None, None), 'VX': (None, None),
                   'VY': (None, None), 'VZ': (None, None)}
            self.data['Stations'][name] = sta
        return sta

    def decode_station(self, line):
        name, coord, code = line[7:15].strip(), line[27:28], line[29:35].strip()
        # Decode velocity record
        if code == 'Velo':
            if sta := self.data['Stations'].get(name):
                self.decode_coord(sta, 'V' + coord, line)
            else:
                self.add_error(f'{name} not in station list')
        # Decode station record
        elif code == 'Comp':
            sta = self.get_or_create_station(name)
            self.decode_coord(sta, coord, line)
        else:
            sta = self.get_or_create_station(f'{name}_{code}')
            self.decode_coord(sta, coord, line)

    def decode_ra_dec(self, src, code, line):
        src[code] = (line[34:52].strip().split(), to_float(line[81:93]))

    def get_or_create_source(self, name):
        if not (src := self.data['Sources'].get(name)):
            src = {'RT. ASC.': (None, None), 'DEC.': (None, None), 'CORRELATION': (None, None)}
            self.data['Sources'][name] = src
        return src

    def decode_source(self, line):
        name, code = line[8:16], line[17:28].strip()
        src = self.get_or_create_source(name)
        if code == 'CORRELATION':
            src[code] = to_float(line[32:39])
        else:
            self.decode_ra_dec(src, code, line)

    def read_global_section_old(self):
        sta_coord, src_coord = 'XYZ', ['RT. ASC.', 'DEC.']

        index = 0
        while self.has_next():
            if self.line.startswith('1Run'):
                return
            n = self.get_position_index(self.line)
            if n == index + 1:
                index += 1
                if self.line[27:28] in sta_coord:
                    self.decode_station(self.line)
                elif self.line[17:28].strip() in src_coord:
                    self.decode_source(self.line)
            elif self.line[17:28] == 'CORRELATION':
                self.decode_source(self.line)

    def read_global_section(self):
        while self.has_next():
            if self.line.startswith('1Run'):
                return True
        return False

    def read_sections(self):
        while self.line.startswith('1Run'):
            self.runs.append(Section(self))

    def add_apriori(self, line):
        key, info = line.split(':')
        self.data['Apriori model'][key.strip()] = info.strip()

    def read_apriori(self):
        if self.line.startswith('1  APR'):
            self.add_apriori(self.line[8:])
        while self.has_next():
            if not self.line.startswith('1  APR'):
                return
            self.add_apriori(self.line[8:])

    def get_unused_observations(self):
        if (filepath := Path(self.path)).suffix == '.SFF':
            path = filepath.with_suffix('.NUO')
        elif (filepath := Path(self.path)).name.startswith('SPLF'):
            path = Path(filepath.parent, f'nuSolve_unused_observations_{filepath.name[-2:]}')
        else:
            return
        if not path.exists():
            return

        # Extract
        unused = {'unusable': [], 'excluded': []}

        # Defined some regex and formats
        get_run = re.compile('# Status of observations of the solution of the Run (?P<id>.*)').match
        is_dbase = re.compile('#.* database (?P<name>.*) version.*').match
        # get list of unusable and excluded observations from nuSolve_unused_observations file
        uformat = '{}, quality code X: {} S: {}, fringe code X: \'{}\' S: \'{}\''.format
        eformat = '{}, which fits at {:>10s} +/- {:>9s} ps'.format

        match = re.compile(r'^(?P<code>[ue]) (?P<row>[ 0-9]{5}) (?P<time>[0-9\:]{8})(?P<qc>.{4})(?P<fc>.{4}).{1,20}'
                           r'(?P<nunchan>[ 0-9]{6}) (?P<baseline>.{17}) (?P<source>.{8})(?P<data>.*)$').match
        with open(path, errors='ignore') as file:
            for line in file.readlines():
                code = None
                if (run := get_run(line)) and run['id'].strip() != self.runs[0].run_id:
                    print('Not same run id', run['id'].strip(), self.runs[0].run_id)
                    return
                elif (database := is_dbase(line)) and database['name'] != self.runs[0].DB_NAME:
                    print('Not same database', database['name'].strip(), self.runs[0].DB_NAME)
                    return
                elif matched := match(line):
                    d = matched.groupdict()
                    code = d['code']
                elif line.startswith(('u', 'e')):  # Use the : in baseline to find appropriate format
                    l, data = line, line.split()
                    code, i = data[0], l.rfind(':')
                    d = {'row': data[1], 'baseline': l[i-8:i+9], 'source': l[i+11:i+19], 'time': data[2],
                         'qc': l[16:20], 'fc': l[21:25], 'data': l[i+20:]}
                if code:
                    row = int(d['row'].strip())
                    hdr = f'    observation {row:4d}, {d["baseline"]}, {d["source"]}, {d["time"]}'
                    if code == 'u':
                        unused['unusable'].append(uformat(hdr, d['qc'][3], d['qc'][1], d['fc'][3], d['fc'][1]))
                    elif code == 'e':
                        res, std = d['data'].split()[:2]
                        unused['excluded'].append(eformat(hdr, res, std))
        self.unused = unused


# Get all spool file from backup directories
def get_stored_spool(db_name):
    if not (root := app.folder('STORED_SPOOL')):
        root = str(Path().home())
    files = [Path(file) for file in glob.glob(f'{root}/**/{db_name}.SFF', recursive=True)]
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files[0] if files else None


# Read spool file
def read_spool(path=None, initials='', db_name='', read_unused=False):
    if not path:
        path = Path(app.folder('SPOOL_DIR'), f'SPLF{initials}') if initials \
            else get_stored_spool(db_name) if db_name else None
    if path and path.exists():

        with Spool(path) as spool:
            if spool.read_global_section():
                spool.read_sections()
                if spool.runs:
                    if not db_name or spool.runs[0].DB_NAME == db_name:
                        if read_unused:
                            spool.get_unused_observations()
                        return spool
    return None
