from aps.eop import EOP


# Class use to update EOP solutions
class EOPK(EOP):
    # Initialize class with path
    def __init__(self, opa_config, initials='--'):
        super().__init__(opa_config, initials)

        self.check_required_files(['EOPB_FILE'])
        self.check_required_files(['EOPK_FILE'], chk_write=True)

    def execute(self, session, vgosdb):

        tpath = self.eopkal(self.get_opa_path('EOPB_FILE'), vgosdb)
        return self.update_global_file(tpath, self.get_opa_path('EOPK_FILE')) if tpath else False

