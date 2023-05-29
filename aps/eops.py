import traceback

from utils import app
from aps.spool import read_spool
from aps.eop import EOP
from aps.eob import eob_to_eops
from aps import solve


class EOPS(EOP):
    # Initialize class with path
    def __init__(self, opa_config, initials, run_simul=False):
        super().__init__(opa_config, initials)

        self.run_simul = run_simul

        self.check_required_files(['EOPS_CGM'])
        self.check_required_files(['EOPB_FILE', 'EOPK_FILE', 'EOPS_CGM'], chk_write=True)

    def execute(self, session, vgosdb):

        arc_line = session.code
        name2code = app.get_dbase().get_station_name_dict()

        for option, erp in [(' NO_EOP_MOD', 'GEN_INPERP'), ('', 'EOPK_FILE')]:
            # Make control file
            cnt = self.get_control_filename()
            words = {'@cgm_file@': self.get_opa_path('EOPS_CGM'),
                     '@erp_file@': f'{self.get_opa_path(erp)} ' + '  SPL  UT1S ',
                     '@arc_line@': f'{vgosdb.wrapper.name:100s} {option} ! {arc_line}'
                     }
            template = self.get_opa_path('EOPS_CNT')
            if not self.make_control_file(template, cnt, words, header=True):
                return False  # Failed building control file

            # Call solve script
            solve.check_lock(self.initials)
            ans = self.execute_command(f'solve {self.initials} {cnt} silent', vgosdb.name)
            solve.remove_lock(self.initials)
            if not ans or not solve.check_status(self.initials):
                path = self.save_bad_solution('solve_',
                                              ans if ans else f'solve {self.initials} {cnt} returned empty answer')
                self.add_error(f'Error running solve! Check control file {cnt} or output {path}')
                return False

            # Read spool file
            if not (spool := read_spool(self.initials)):
                self.add_error(f'Error reading spool file SPLF{self.initials}')
                return False
            # Update EOPB_XY_FILE and EOPB_FILE
            for index, (bcode, wantXY) in enumerate([('EOPB_XY_FILE', True), ('EOPB_FILE', False)]):
                if eopb := self.get_opa_path(bcode):
                    try:
                        records = [run.make_eob_record(name2code, arc_line, wantXY) for run in spool.runs]
                        tmp_eopb = self.get_tmp_file(prefix=bcode.replace('FILE', '').lower())
                        self.update_eop_file(tmp_eopb, eopb, records)
                        self.update_global_file(tmp_eopb, eopb)

                        scode = bcode.replace('EOPB', 'EOPS')
                        tmp_eops = self.get_tmp_file(prefix=scode.replace('FILE', '').lower())
                        eob_to_eops(eopb, tmp_eops)
                        eops = self.get_opa_path(scode)
                        self.update_global_file(tmp_eops, eops)
                    except Exception as exc:
                        print('EOPS', str(exc), traceback.format_exc())
                        return False

            # Call eopk Not required
            # tpath = self.eopkal(self.get_opa_path('EOPB_FILE'), vgosdb)
            # return self.update_global_file(tpath, self.get_opa_path('EOPK_FILE')) if tpath else False
        return True
