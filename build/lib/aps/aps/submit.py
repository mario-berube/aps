import os
import shutil
import tarfile
import gzip
from pathlib import Path
from tempfile import mkdtemp

from aps.aps.process import APSprocess
from aps.utils import app, readDICT
from aps.utils.servers import load_servers, get_server, DATACENTER
from aps.ivsdb.models import UploadedFile

last_submission = []


def record_submitted_files(records):

    dbase = app.get_dbase()
    for record in records:
        dbase.add(record)
    dbase.commit()


def get_last_submission():
    global last_submission
    return last_submission


# Move files into special area to be uploaded later
def move_failed_upload(files, user):
    folder = app.failed_dir
    moved, failed = [], []
    for file in files:
        name = os.path.basename(file)
        moved.append(name)
        shutil.copy(file, folder)
        failed.append(UploadedFile(name, user, 'aps', 'try later'))
    record_submitted_files(failed)
    return moved


# Submit files to cddis
def submit_files(files):
    global last_submission
    last_submission = []
    user = os.environ['SUDO_USER'] if 'SUDO_USER' in os.environ else os.environ['USER']

    if (center := app.data_center) not in load_servers(DATACENTER):
        return move_failed_upload(files, user)

    # Upload to primary data center
    server, submitted, failed = get_server(DATACENTER, center), [], []
    #  testing = app.check_server_capability('can_upload')
    uploaded = server.upload(files)
    for file in files:
        if (name := os.path.basename(file)) in uploaded:
            submitted.append(UploadedFile(name, user, 'aps', 'ok'))
        else:
            failed.append(file)

    if submitted:
        last_submission = [os.path.basename(file) for file in files]
        record_submitted_files(submitted)

    return move_failed_upload(failed, user) if failed else []


class SINEX(APSprocess):
    def __init__(self, opa_config):
        super().__init__(opa_config)
        self.cnf_info = readDICT(self.get_opa_path('SNX_CONF'))

    def logit(self, path):
        fmt = '{path} | user {user} | {center} | {now} |'
        data = {'path': str(path), 'center': self.cnf_info['DATA_CENTER']}
        super().logit(self.cnf_info['SUBMIT_LOG'], fmt, data)

    # Submit SINEX file
    def submit(self, **kwargs):
        session, vgosdb = kwargs['session'], kwargs['vgosdb']
        # Get name of link
        ext = '.sni' if session.type == 'intensive' else '.snx'
        name = f'{session.start.strftime("%Y%m%d")}-{session.code.lower()}_{self.get_opa_code("STANDALONE_ID")}{ext}'
        # Temporary folder to store gz file
        folder = mkdtemp()
        tpath = os.path.join(folder, f'{name}.gz')
        # Get sinex link.
        link = Path(session.folder, name)
        # Zip file to tmp folder
        with open(link, 'rb') as glb, gzip.open(tpath, 'wb') as gz:
            gz.writelines(glb)
        # Log it
        self.logit(link)
        # Submit to cddis
        failed = submit_files([tpath])
        # Remove file and temporary folder
        shutil.rmtree(folder)
        return failed


class DB(APSprocess):
    def __init__(self, opa_config):
        super().__init__(opa_config)
        self.cnf_info = readDICT(self.get_opa_path('DBS_CONF'))

    def logit(self, wrapper):
        fmt = '{wrp} | user {user} | {center} | {now} |'
        data = {'wrp': wrapper, 'center': self.cnf_info['DATA_CENTER']}
        super().logit(self.cnf_info['SUBMIT_LOG'], fmt, data)

    def submit(self, **kwargs):
        session, vgosdb = kwargs['session'], kwargs['vgosdb']
        gsf_wrapper = Path(vgosdb.folder, vgosdb.wrapper.name)
        ivs_wrapper = Path(vgosdb.folder, vgosdb.wrapper.name.replace('i'+vgosdb.wrapper.agency, 'iIVS'))
        shutil.copy(gsf_wrapper, ivs_wrapper)

        # TAR gzip database in temporary folder
        folder = mkdtemp()
        tpath = Path(folder, f'{vgosdb.name}.tgz')
        with tarfile.open(tpath, 'w:gz') as tar:
            tar.add(vgosdb.folder, arcname=vgosdb.name)
        # Submit to cddis
        failed = submit_files([tpath])
        # Log it
        self.logit(gsf_wrapper)
        # Remove file and temporary folder
        shutil.rmtree(folder)
        return failed


# Class use to update GLO_ARC_FILE
class EOPsubmit(APSprocess):

    def __init__(self, opa_config, eop_code, eop_conf='EOS_CONF'):
        super().__init__(opa_config)
        self.eop_code = eop_code
        self.cnf_info = readDICT(self.get_opa_path(eop_conf))

    def logit(self, path):
        fmt = '{path} | user {user} | {center} | {now} |'
        data = {'path': path, 'center': self.cnf_info['DATA_CENTER']}
        super().logit(self.cnf_info['SUBMIT_LOG'], fmt, data)

    def submit(self, **kwargs):
        # Get path to global file
        path = self.get_opa_path(self.eop_code)
        # Make folder with new compressed file name
        folder = mkdtemp()
        suffix = self.cnf_info['EOP_SUFFIX']
        name = f'{suffix}.{self.action}.gz'
        tpath = Path(folder, name)
        # Zip file to tmp folder
        with open(path, 'rb') as glb, gzip.open(tpath, 'wb') as gz:
            gz.writelines(glb)
        failed = submit_files([tpath])
        # Log it
        self.logit(path)
        # Remove folder and file
        shutil.rmtree(folder)
        # Set format an information for updating SUBMIT_LOG
        return failed


class EOPS(EOPsubmit):
    def __init__(self, opa_config):
        super().__init__(opa_config, 'EOPS_FILE')


class EOXY(EOPsubmit):
    def __init__(self, opa_config):
        super().__init__(opa_config, 'EOPS_XY_FILE')


class EOPI(EOPsubmit):
    def __init__(self, opa_config):
        super().__init__(opa_config, 'EOPM_FILE', 'EOM_CONF')









