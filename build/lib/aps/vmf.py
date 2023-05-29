import os

from aps.process import APSprocess


# Class use to update GLO_ARC_FILE
class VMF(APSprocess):
    # Initialize class with path
    def __init__(self, opa_config, initials='--'):
        super().__init__(opa_config, initials)

        self.vmf_exec = self.get_app_path('VMF_PROGRAM')

        # Get INPUT_VMF_DIR
        self.vmf_dir = self.get_opa_directory('VMF_DATA_DIR')
        if not self.vmf_dir:
            self.add_error('No valid VMF input data file directory was specified in the OPA configuration file.')
        elif not self.vmf_dir.endswith('/'):
            self.vmf_dir += '/'

        # Get output dir for TOTAL and DRY
        self.total_output_dir = self.get_opa_directory('VMF_TOTAL_OUTPUT_DIR')
        self.dry_output_dir = self.get_opa_directory('VMF_DRY_OUTPUT_DIR')
        if not self.total_output_dir and not self.dry_output_dir:
            self.add_error('No valid VMF total or dry output directory were specified in the OPA configuration file.')

    # Execute VMF application for apriori type (TOTAL or DRY)
    def create_vmf_file(self, apriori, out_dir, vgosdb):
        if not out_dir:  # No directory so no computation
            return

        # Extract folder name. Create it if missing
        folder = out_dir.split()[0].strip()
        folder = os.path.join(folder, vgosdb.year) if 'YEAR' in out_dir else folder
        if not os.path.exists(folder):
            os.mkdir(folder)

        # Create command for vmf application
        out_file = os.path.join(folder, vgosdb.name+'.trp')
        cmd = f'{self.vmf_exec} {vgosdb.wrapper.name} {out_file} {self.vmf_dir} {apriori}'
        ans = self.execute_command(cmd, vgosdb.name)
        if not ans or f'Made {out_file}' not in ans[-1] or not os.path.exists(out_file):
            path = self.save_bad_solution('solve_', ans)
            self.add_error(f'{out_file} not created! Check output at {path}')

    def execute(self, session, vgosdb):
        # Create VMF file for TOTAL and DRY
        self.create_vmf_file('TOTAL', self.total_output_dir, vgosdb)
        self.create_vmf_file('DRY', self.dry_output_dir, vgosdb)

        return not self.has_errors
