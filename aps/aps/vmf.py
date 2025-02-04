from pathlib import Path

from aps.aps.process import APSprocess


# Class use to update VMF
class VMF(APSprocess):
    # Initialize class with path
    def __init__(self, opa_config, initials='--'):
        super().__init__(opa_config, initials)

        self.vmf_exec = self.get_app_path('VMF_PROGRAM')
        # Get INPUT_VMF_DIR
        self.vmf_dir = self.get_opa_directory('VMF_DATA_DIR')

    # Execute VMF application for apriori type (TOTAL or DRY)
    def create_vmf_file(self, apriori, out_dir, vgosdb):
        if not out_dir:
            return
        folder = Path(out_dir.split()[0].strip())
        folder.mkdir(exist_ok=True)
        cmd = [self.vmf_exec, vgosdb.wrapper.name]
        if self.vmf_exec == 'vmf_2_trp':
            cmd.extend([f'VMF_DIR_OUT={str(folder)}', f'VMF_APRIORI={apriori}'])
        else:
            folder = Path(folder, vgosdb.year) if 'YEAR' in out_dir else folder
            folder.mkdir(exist_ok=True)
            out_file = Path(folder, f"{vgosdb.name}.trp")
            cmd.extend([str(out_file),  self.vmf_dir, apriori])

        # Exec command for vmf application
        ans = self.execute_command(' '.join(cmd), vgosdb.name)
        if not ans or not ans[-1].strip().startswith('Made') or not Path(ans[-1].split()[-1]).exists():
            path = self.save_bad_solution('vmf_', ans)
            self.add_error(f'TRP file not created! Check error report at {path}')

    def execute(self, session, vgosdb):

        # Create VMF file for TOTAL and DRY
        self.create_vmf_file('TOTAL', self.get_opa_directory('VMF_TOTAL_OUTPUT_DIR'), vgosdb)
        self.create_vmf_file('DRY', self.get_opa_directory('VMF_DRY_OUTPUT_DIR'), vgosdb)

        return not self.has_errors
