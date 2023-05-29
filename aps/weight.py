import os
from datetime import datetime

from aps.process import APSprocess
from aps import solve


# Base class use to update WEIGHT files
class Weight(APSprocess):

    # Initialize class with path
    def __init__(self, opa_config, initials):
        super().__init__(opa_config, initials)

        self.comment = ''

        # Check that solve is in PATH
        self.is_executable('solve')

    # Get the key for record in global files
    @staticmethod
    def get_key(line):
        db_name, version = line.split()[0:2]
        try:  # Try format YYMMMDD where MMM month name
            date, name = datetime.strptime(db_name[:7], '%y%b%d'), db_name[7:]
        except ValueError:
            try:  # Try format with numeric month
                date, name = datetime.strptime(db_name[:8], '%Y%m%d'), db_name[9:].upper()
            except ValueError:
                return ''
        return f'{date.strftime("%Y%j")}{name}{int(version):03d}'

    def read_new_records(self, path):
        with open(path) as f:
            records = [line for line in f.readlines() if not line.startswith('*')]
        return self.get_key(records[0]), {'comments': [], 'records': records}

    @staticmethod
    def insert_records(grp, file):
        for comment in grp['comments']:
            print(comment, end='', file=file)
        for record in grp['records']:
            vgosdb, version, data = record.split(maxsplit=2)
            print(f'{vgosdb:<23s} {version:>3s} {data}', end='', file=file)
        print('*', file=file)

    def update_weight_file(self, template, gpath, session, vgosdb):

        # Make control file
        cnt = self.get_control_filename()
        weight_file = os.path.splitext(cnt)[0] + '.wgt'
        words = {'@weight_file@': weight_file, '@arc_line@': self.format_arc_line(vgosdb.wrapper.name, session.code)}

        if not self.make_control_file(template, cnt, words):
            return False

        # Call solve script
        solve.check_lock(self.initials)
        ans = self.execute_command(f'solve {self.initials} {cnt} silent', vgosdb.name)
        solve.remove_lock(self.initials)
        if not ans or 'Solve run was not successful' in ans[-1] or not solve.check_status(self.initials) \
                or not os.path.exists(weight_file):
            path = self.save_bad_solution('solve_', ans)
            self.add_error(f'Error running solve! Check control file {cnt} or output {path}')
            self.add_error(f'Weight file {weight_file}')
            return None

        # Return None if errors in solve
        if self.has_errors:
            self.add_error(cnt)
            self.add_error(weight_file)
            return None  # Do not remove cnt, weight_file to look at them

        # Update a temporary copy of the global file
        groups = {}
        with open(gpath) as glo:
            found, comments = False, []
            for line in glo:
                if line.strip() in [None, '',  '*']:
                    continue
                elif line.startswith('*'):  # Comment added after '*'. Must be for next lines
                    comments.append(line)
                elif (key := self.get_key(line)) not in groups:
                    groups[key] = {'comments': comments, 'records': [line]}
                    comments = []
                else:
                    groups[key]['records'].append(line)

        # Insert new weight records, sort and save in temporary file
        key, grp = self.read_new_records(weight_file)
        groups[key] = grp
        prefix, suffix = os.path.splitext(gpath)
        tpath = self.get_tmp_file(prefix=prefix + '_', suffix=suffix)
        with open(tpath, 'w') as tmp:
            for key in sorted(list(groups.keys())):
                self.insert_records(groups[key], tmp)

        # Remove cnt and weight file
        self.remove_files(cnt, weight_file)
        # Update the global file
        return self.update_global_file(tpath, gpath)
