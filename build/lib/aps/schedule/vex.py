from collections import OrderedDict, defaultdict

from utils.utctime import utc
from schedule.skd import SKD


def decode_vex_value(param, row=0, col=0):
    return param[row][col]


class VEX(SKD):

    def __init__(self, path):
        super().__init__(path)

    def read(self, VieSched_sort=False):

        blocks = defaultdict(dict)
        block, literal = '', False

        if not self.has_next() or not self.line.strip().startswith('VEX_rev'):
            print(f'{self.path} not a VEX file! Check first line.')
            return

        while self.has_next():
            for part in self.line.strip().split(';'):
                if not (part := part.strip()) or part.startswith('*'):
                    continue
                if part.startswith('end_literal'):
                    literal = False
                elif literal:
                    continue
                elif part.startswith('start_literal'):
                    literal = True
                elif part.startswith('$'):
                    block = part[1:]
                elif part.startswith('enddef') or part.startswith('endscan'):
                    blocks[block][record['code']] = record
                elif part.startswith('def ') or part.startswith('scan '):
                    record = {'code': part.split()[1], 'ref': defaultdict(list)}
                elif part.startswith('ref '):
                    key = (info := part[3:].split('='))[0].strip()[1:]
                    if block == 'GLOBAL':
                        blocks[block][key] = info[1].strip()
                    else:
                        record['ref'][key].append(info[1].strip())
                elif '=' in part:
                    if (key := (info := part.split('='))[0].strip()) not in record:
                        record[key] = []
                    record[key].append(info[1].strip().split(':'))

        # Keep EXPER information
        for code, record in blocks['EXPER'].items():
            if 'exper_name' in record:
                self.session_code = decode_vex_value(record['exper_name']).lower()
            if 'target_correlator' in record:
                self.correlator = decode_vex_value(record['target_correlator']).lower()
        # Keep station information
        stations, sites = blocks['STATION'], blocks['SITE']
        for _key, record in stations.items():
            code, name = record['code'], record['ref']['SITE'][0]
            if name in sites:
                site = sites[name]
                code, name = decode_vex_value(site['site_ID']), decode_vex_value(site.get('site_name', name))
            sta = SKD.init_sta(code, name)
            self.stations['codes'][code] = self.stations['names'][name] = sta

        # Keep source information
        for record in blocks['SOURCE'].values():
            name, code = decode_vex_value(record['source_name']), record['code']
            self.sources[name] = SKD.init_src(code, name)
        # Keep scans self.data
        for record in blocks['SCHED'].values():
            code = decode_vex_value(record['source'])
            source = decode_vex_value(blocks['SOURCE'][code]['source_name'])
            start = utc(vex=decode_vex_value(record['start']))
            self.start = self.start if self.start else start

            name = record['code'].lower()
            scan = {'name': name, 'source': source, 'start': start, 'station_codes': {}}
            self.sources[source]['scans'][name] = self.scans[name] = scan
            nbr_obs = len(record['station']) - 1
            self.scheduled_obs += int((nbr_obs * (nbr_obs + 1)) / 2)
            for info in record['station']:
                code = info[0].strip().capitalize()
                start_rec, stop_rec = int(info[1].split()[0].strip()), int(info[2].split()[0].strip())
                scan['station_codes'][code] = {'duration': stop_rec - start_rec}
                sta = self.stations['codes'][code]
                sta['scans'][name] = scan
                sta['scheduled_obs'] += nbr_obs

            scan['station_codes'] = dict(sorted(scan['station_codes'].items()))
            src = self.sources[source]

            for fr in scan['station_codes']:
                if fr not in src:
                    src[fr] = {}
                for to in scan['station_codes']:
                    if fr != to:
                        if to not in src[fr]:
                            src[fr][to] = []
                        src[fr][to].append(scan)

            if source not in self.observations:
                self.observations[source] = {}
            src = self.observations[source]
            for fr in scan['station_codes']:
                if fr not in src:
                    src[fr] = {}
                for to in scan['station_codes']:
                    if fr < to:
                        if to not in src[fr]:
                            src[fr][to] = []
                        obs = SKD.init_obs(scan, fr, to)
                        src[fr][to].append(obs)
                        self.obs_list.append(obs)

        self.end = self.end if self.end else start
        self.set_first_sources()
        self.count_observations()

        return


