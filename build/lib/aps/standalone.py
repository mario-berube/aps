import os
from pathlib import Path

from aps.process import APSprocess
from aps import solve


# Class use to update GLO_ARC_FILE
class STANDALONE(APSprocess):
    # Initialize class with path
    def __init__(self, opa_config, initials):
        super().__init__(opa_config, initials)

        self.check_required_files(['STANDALONE_CNT', 'GEN_INPERP'])

    def execute(self, session, vgosdb):

        cnt = self.get_control_filename()

        session_dir = self.get_opa_code('SESSION_DIR')
        session_dir = session_dir if session_dir.endswith('/') else session_dir + '/'
        # Defined words changed from template
        erp = self.get_opa_code('GEN_INPERP')
        words = {'@session_dir@': session_dir,
                 '@erp_file@':  f'{erp}  SPL  UT1S',
                 '@arc_line@': self.format_arc_line(vgosdb.wrapper.name, session.code)
                 }

        template = self.get_opa_path('STANDALONE_CNT')
        if not self.make_control_file(template, cnt, words, header=True):
            return False

        solve.check_lock(self.initials)
        ans = self.execute_command(f'solve {self.initials} {cnt} silent', vgosdb.name)
        solve.remove_lock(self.initials)
        if not ans or 'Solve run was not successful' in ans[-1] or not solve.check_status(self.initials):
            err_file = self.save_bad_solution('solve_', ans)
            self.add_error(f'Error running solve! Check control file {cnt} or output {err_file}')
            return False
        # Extract important part from spool file and make sinex link
        return self.store_spool_data(session) and self.make_sinex_link(session)

    def make_sinex_link(self, session):
        # Check if sinex file exist.
        ext = 'sni' if session.type == 'intensive' else 'snx'
        if not (path := session.file_path(ext)).exists():
            self.add_error(f'Sinex file {path.name} does not exist')
            return False
        name = f'{session.start.strftime("%Y%m%d")}-{session.code.lower()}_{self.get_opa_code("STANDALONE_ID")}.{ext}'
        if (link := Path(session.folder, name)).exists():
            try:
                link.unlink()  # Remove symlink
            except Exception as err:
                self.add_error(f'Could not remove existing link {link.name} [{str(err)}]')
                return False
        link.symlink_to(path)
        return True

    # Extract information from spool file and store to new file
    def store_spool_data(self, session):
        if not (spool := Path(os.environ['SPOOL_DIR'], f'SPLF{self.initials}')).exists():
            self.add_error(f'{spool.name} does not exist')
            return False
        try:
            path = session.file_path('spl')
            with open(path, 'w') as f_out, open(spool) as sp:
                for line in sp:
                    if line.startswith('PROGRAM VERSIONS:'):
                        return True  # End of interesting information
                    print(line, end='', file=f_out)
            return True
        except Exception as err:  # Problem
            self.add_error(f'Error creating {path.name} file [{str(err)}]')
            return False

