import os

from aps.aps.process import APSprocess


# Class use to create SNRANAL report
class SNR(APSprocess):
    # Initialize class with path
    def __init__(self, opa_config, initials='--'):
        super().__init__(opa_config, initials)

        # Test if snranal in path
        self.is_executable('snranal')

    def execute(self, session, vgosdb):
        # Define some folders or files
        session_dir, master_dir = self.get_opa_directory('SESSION_DIR'), self.get_opa_directory('MASTER_DIR')
        vgosdb_dir = self.get_opa_directory('VGOSDB_DIR')
        out_dir = str(session.folder)  # os.path.join(session_dir, session.year, session.code)
        status = self.get_tmp_file(prefix='snr_', suffix='.sts')
        listing = self.get_tmp_file(prefix='snr_', suffix='.prg')
        app_err = os.path.join(out_dir, f'{session.code}.err')
        for ext in ('skd', 'vex'):
            if (skd := session.file_path(ext)).exists():
                break
        else:
            self.add_error(f'Program snranal terminated abnormally. No schedule file for {session.code}')
            return False

        # Build command
        cmd = f'snranal -session_dir {session_dir} -master_dir {master_dir} -vgosdb_dir {vgosdb_dir} ' \
              f'-schedule {skd.name} -status {status} -outdir {out_dir} > {listing}'

        # Execute and check result and check success
        self.execute_command(cmd, vgosdb.name)
        if not open(status).read().startswith('# SNRANAL successful completion'):
            self.add_error('Program snranal terminated abnormally. Please investigate SNRANAL output files ')
            self.add_error(f' 1) Status: {status}\n 2) Listing: {listing}\n 3) Error: {app_err}')
            return False

        # Remove temporary files
        self.remove_files(status, listing, app_err)
        return True

