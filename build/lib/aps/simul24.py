from aps.eops import EOPS


class SIMUL24(EOPS):
    # Initialize class with path
    def __init__(self, opa_config, initials):
        super().__init__(opa_config, initials, run_simul=True)
