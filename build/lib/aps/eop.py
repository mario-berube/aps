from datetime import datetime

from aps.process import APSprocess


# Class use to update EOP solutions
class EOP(APSprocess):
    # Initialize class with path
    def __init__(self, opa_config, initials):
        super().__init__(opa_config, initials)

        self.check_required_files(['GEN_INPERP', 'EOPS_CNT'])

    def update_eop_file(self, tpath, global_file, records):

        def make_key(string):
            mjd, _, ses_id, *_ = string[1:].split()
            return f'{mjd}-{ses_id}'

        def insert_record(lines, file):
            for record in lines:
                mjd, vgosdb, session, data = record[1:].split(maxsplit=3)
                print(f'{record[0]} {mjd} {vgosdb.replace("$", ""):<22s} {session:<12s} {data}', file=file)

        # Insert new records into file
        db_key = make_key(records[0])
        inserted = False
        with open(tpath, 'w') as tmp, open(global_file, errors='ignore') as glb:
            for line in glb:
                line = line.rstrip()
                if line.startswith('#'):
                    print(line, file=tmp)
                    if line.startswith('# Analysis'):
                        now = datetime.now().strftime('%Y.%m.%d-%H:%M:%S')
                        print(f'# Updated by APS at      {now}  by user {self.real_user}', file=tmp)
                elif line.strip():  # Not empty
                    key = make_key(line)
                    if key < db_key:
                        insert_record([line], tmp)
                    elif key == db_key:
                        if not inserted:
                            insert_record(records, tmp)
                            inserted = True
                    elif key > db_key:
                        if not inserted:
                            insert_record(records, tmp)
                        insert_record([line], tmp)
                        inserted = True
            # Insert at end of file
            if not inserted:
                insert_record(records, tmp)

    def eopkal(self, eopb, vgosdb):
        # Make temp files
        new = self.get_tmp_file(prefix='eopk_', suffix='.erp')
        sts = self.get_tmp_file(prefix='eopk_', suffix='.sts')
        prg = self.get_tmp_file(prefix='eopk_', suffix='.prg')

        # Execute eopkal
        self.execute_command(f'eopkal -i {eopb} -o {new} -s {sts} > {prg}', vgosdb.name)
        if self.has_errors:
            return None
        # Read status file
        with open(sts) as f:
            if not f.readline().startswith('EOPKAL: finished'):
                self.add_error('Program eopkal terminated abnormally.')
                self.add_error(f'Please investigate file {prg}')
                return None
        # Remove temporary files
        self.remove_files(prg, sts)
        return new
