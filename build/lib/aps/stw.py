from aps.weight import Weight


# Class use to update SIT_WEIGHT_FILE
class STW(Weight):

    # Initialize class with path
    def __init__(self, opa_config, initials):
        super().__init__(opa_config, initials)

        # Check if files available
        self.check_required_files(['SIT_WEIGHT_CNT'])
        self.check_required_files(['SIT_WEIGHT_FILE'], chk_write=True)
        self.comment = '*'

    def execute(self, session, vgosdb):
        template = self.get_opa_path('SIT_WEIGHT_CNT')
        global_file = self.get_opa_path('SIT_WEIGHT_FILE')

        return self.update_weight_file(template, global_file, session, vgosdb)
