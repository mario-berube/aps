from pathlib import Path
import tempfile
import shutil
import signal
import os
import time
import traceback
import subprocess

from utils import app, readDICT
from utils.files import remove
from utils.mail import build_message, send_message
from utils.servers import get_server, get_config_item, CORRELATOR
from vgosdb.compress import VGOStgz
from vgosdb import VGOSdb, vgosdb_folder, get_db_name
from aps import APS, submit, get_aps_process, spool
from ivsdb import IVSdata


# Class to control vgosDB download from correlator
class VGOSDBController:

    # Initialize variables using files file
    def __init__(self, user=None):

        self.user = user
        self.agency = self.notifications = self.nusolveApps = self.auto = self.lastmod = self.origin = None
        self.check_control_file()

        self.save_corr_report = app.args.corr if hasattr(app.args, 'corr') else True

    # Print message. Could be overwritten by Broker class
    def info(self, msg):
        print(type(self).__name__, msg)

    # Print message. Could be overwritten by Broker class
    def warning(self, msg):
        print(type(self).__name__, msg)

    # Sleep for 1 second. Could be overwritten by Broker class to use pika sleep.
    def sleep_1sec(self):
        time.sleep(1)
        print(type(self).__name__, 'end of sleep')

    # Send notification to default watchdog. Could be overwritten by Broker class
    def notify(self, msg):
        self.warning(msg)
        app.notify('VGOS DB', msg)

    def check_control_file(self):
        # Read configuration file every time in case there was some changes.
        self.lastmod, info = app.load_control_file(name=app.ControlFiles.VGOSdb, lastmod=self.lastmod)
        if info:
            self.nusolveApps = info['nuSolve']
            self.auto = info['Auto']
            self.save_corr_report = info['Options'].get('save_correlator_report', True)
            self.notifications = info['Notifications']
            # Read agency code
            conf = readDICT(os.path.expanduser(info['Agency']['file']))
            self.agency = conf[info['Agency']['keys'][0]][info['Agency']['keys'][1]]

    # Send message that vgosDB is ready
    def send_ready_email(self, vgosdb, action, summary, err):
        if app.args.no_mail:
            return  # Do not send email

        vtype = 'problem' if app.args.test else vgosdb.type
        vtype == 'intensive' if vtype == 'intensives' else vtype
        if vtype not in self.notifications or vtype == VGOSdb.Unknown:
            self.notify(f'{vgosdb.name} type was detected as {vgosdb.type}')
            vtype = 'problem'
        if vgosdb.session.lower() != vgosdb.code.lower():
            err.append(f'\n\n*** WARNING: Head.nc has session name ({vgosdb.code} different than master'
                       f' ({vgosdb.session})***\n')
        sender, recipients = self.notifications['sender'], self.notifications[vtype]
        sender = sender.replace('watchdog', self.user) if self.user else sender

        title = f'{vgosdb.name} ({vgosdb.code}) has been {action} and is ready for processing'
        errs = '\n'.join(err)
        message = f'{vgosdb.name} from {self.origin} is available at {vgosdb.folder}\n\n{summary}\n{errs}'
        msg = build_message(sender, recipients, title, text=message)
        send_message(self.notifications['server'], msg)

    # Send message that vgosDB is ready
    def send_auto_processing_email(self, vgosdb, summary, err):
        vtype = 'intensive' if vgosdb.type == 'intensives' else vgosdb.type
        if vtype not in self.notifications or vtype == VGOSdb.Unknown:
            self.notify(f'{vgosdb.name} type was detected as {vgosdb.type}')
            vtype = 'problem'
        if vgosdb.session.lower() != vgosdb.code.lower():
            err.append(f'\n\n*** WARNING: Head.nc has session name ({vgosdb.code} different than master'
                       f' ({vgosdb.session})***\n')
        sender, recipients = self.notifications['sender'], self.notifications[vtype]
        sender = sender.replace('watchdog', self.user) if self.user else sender

        title = f'{vgosdb.name} ({vgosdb.code}) has been automatically processed{" [PROBLEM]" if err else ""}'
        errs = f"PROBLEMS\n--------\n{err}" if err else ''
        message = f'n{vgosdb.name} from {self.origin} has been processed in {vgosdb.folder}\n\n{summary}{errs}'
        msg = build_message(sender, recipients, title, text=message)
        send_message(self.notifications['server'], msg)
    # Download vgosDB file
    def download(self, center, rpath):
        errors = []
        # Do it few times to avoid empty file due to early detection.
        for nbr_tries in range(5):
            # Make unique tmp file for this
            lpath = tempfile.NamedTemporaryFile(delete=False).name
            with get_server(CORRELATOR, center) as server:
                ok, info = server.download(rpath, lpath)
                if not ok or not os.stat(lpath).st_size:
                    err = f'Download failed {ok} - [{info}]'
                    self.warning(err)
                    errors.append(err)
                    remove(lpath)
                    time.sleep(1)
                    continue
                return lpath
        # Error downloading this vgosDb
        err = '\n'.join(errors)
        self.notify(f'{err}\n{str(traceback.format_exc())}')
        return None

    # Test if vgosDB already exists and
    @staticmethod
    def is_new(db_name, lpath, folder):
        tgz = VGOStgz(db_name, lpath)
        create_time, err = tgz.get_create_time()
        if not create_time:
            return False, err
        if not os.path.isdir(folder):
            return True, 'downloaded'  # Folder does not exist
        if not os.access(folder, os.R_OK):
            return False, 'No privileges to read folder'  # Folder is protected
        if create_time > VGOSdb(folder).create_time:
            return True, 'updated'
        return False, 'Created time same or older'

    @staticmethod
    def is_used_by_aps(db_name):
        # Get ses_id from database
        url, tunnel = app.get_dbase_info()
        with IVSdata(url, tunnel) as dbase:
            ses_id = dbase.get_db_session_code(db_name)
            for pid, code in get_aps_process():
                if code == db_name or code == ses_id:
                    break
                # Check if code is initial for spool file
                if (spl := spool.read_spool(code)) and dbase.get_db_session_code(spl.runs[0].DB_NAME) == ses_id:
                    break
            else:
                return False
        os.kill(pid, signal.SIGUSR1)
        return True

    # Move new vgosDb to appropriate folder
    def extract_vgosdb(self, db_name, lpath, folder):
        if os.path.isdir(folder):
            self.rename_folder(folder, 'p')
            if os.path.isdir(folder):  # Not able to move folder
                return False
        try:
            # Extract compress file to folder
            tgz = VGOStgz(db_name, lpath)
            tgz.extract(folder)
            return True
        except:
            return False

    # Get the name without extensions (for tar.gz files)
    def validate_db_name(self, center, name):

        basename = name.replace(''.join(Path(name).suffixes), '')
        db_name = get_db_name(name)['name']
        # Check if what we expect from correlator site
        if file_name := get_config_item(CORRELATOR, center, 'file_name'):
            expected = os.path.basename(file_name.format(year='', db_name=db_name))
            if basename != expected.replace(''.join(Path(expected).suffixes), ''):
                return None

        return db_name

    # Process information regarding new file
    def process(self, center, name, rpath):

        self.origin = center.upper()

        self.check_control_file()

        # Make sure the filename and db_name agree.
        basename = os.path.basename(rpath)
        if not (db_name := self.validate_db_name(center, basename)):
            self.info(f'{basename} from {center} has not been downloaded [Not accepted name]')
            return True

        folder = vgosdb_folder(db_name)
        # Make year folder if it does not exist
        os.makedirs(os.path.dirname(folder), exist_ok=True)
        # Download to temp folder
        if not (lpath := self.download(center, rpath)):
            return False  # Download failed
        ok, msg = self.is_new(db_name, lpath, folder)

        if not ok:
            self.warning(f'{db_name} from {center} not download. [{msg}]')
        elif self.is_used_by_aps(db_name):
            self.warning(f'APS is processing {db_name}')
            remove(lpath)
            return False
        elif self.extract_vgosdb(db_name, lpath, folder):
            try:
                self.processDB(folder, msg)
            except Exception as err:
                self.notify(f'{name} {str(err)}\n{str(traceback.format_exc())}')
        remove(lpath)
        return True

    def process_file(self, db_name, path):

        self.origin = path

        folder = vgosdb_folder(db_name)
        ok, msg = self.is_new(db_name, path, folder)

        if self.extract_vgosdb(db_name, path, folder):
            try:
                self.processDB(folder, msg)
            except Exception as err:
                self.notify(f'{db_name} {str(err)}\n{str(traceback.format_exc())}')
        return True

    @staticmethod
    def has_cal_cable(wrapper):
        for item in wrapper.var_list.values():
            if isinstance(item, dict):
                if 'cal-cable_kpcmt' in item.keys():
                    return True
        return False

    # Process applications required by nuSolve
    def processDB(self, folder, action=None):
        if not folder or (hasattr(app.args, 'no_processing') and app.args.no_processing):
            return  # Nothing to do

        vgosdb = VGOSdb(folder)
        if vgosdb.get_last_wrapper(self.agency):
            self.warning(f'vgosDB already process by {self.agency}')
            return  # This vgosDb has already been process by this agency
        err = []
        wrapper = vgosdb.get_oldest_wrapper()
        wrapper = wrapper if (isVGOS := self.has_cal_cable(wrapper)) else vgosdb.get_v001_wrapper()
        for app_info in self.nusolveApps:
            # Check if this processing is done for VGOS sessions
            if isVGOS and not app_info.get('processVGOS', False):
                continue
            # Execute app
            path = path if (path := shutil.which(app_info['name'])) else app_info['path']
            cmd, ans, errors = self.exec_app(path, app_info.get(vgosdb.type, ''), wrapper)
            # Test if application name in last wrapper
            wrapper = vgosdb.get_last_wrapper(self.agency,reload=True)
            if not wrapper or app_info['name'] not in wrapper.processes:
                err.extend([f'\n{cmd} failed!\n', ans, errors])
                for line in ans.splitlines()+errors.splitlines():
                    self.warning(f'{vgosdb.name} {line}')
                break

        # Save correlator report
        if not app.args.test and self.save_corr_report:
            try:
                if name := vgosdb.save_correlator_report():
                    self.info(f'{name} saved to {vgosdb.code}')
            except Exception as exc:
                self.warning(f'Could not save {name}\n{str(exc)}')
                pass

        if options := self.auto.get(vgosdb.type, None):
            self.auto_analysis(vgosdb, options)
        else:
            self.send_ready_email(vgosdb, action, vgosdb.summary(self.agency), err)

    def execute_nuSolve(self, cmd):
        try:
            ans, _ = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()
            text = ans.decode('utf-8')
            if (total := text.find('Number of total obs')
            keys = set(["WRMS", "DoF", "Chi^2/DoF", "dUT1 value", "dUT1 adjustment", "dUT1 std.dev"])
            summary = [line for line in ans.decode('utf-8').splitlines() if line.split(':')[0].strip() in keys]
            return (True, '\n'.join(summary)) if summary else (False, ans)
        except Exception as err:
            return False, f"ERROR: {str(err)}"

    def auto_analysis(self, vgosdb, options):
        summary = ['', 'nuSolve solution summary', '-'*24, '']
        # Run nuSolve
        ok, ans = self.execute_nuSolve(options['cmd'].format(db_name=vgosdb.name))
        if not ok:
            self.notify(ans)
        elif conf := readDICT(os.path.expanduser(self.auto[vgosdb.type].get('files'))):
            summary.append(ans)
            summary.append('')
            initials = conf['Identities']['userdefaultinitials']
            #app.add_args_attr('opa_config', None)
            aps = APS(initials)
            path = options['copy'].format(db_name=vgosdb.name)
            shutil.copyfile(aps.spool.path, path)
            summary.extend(['', f'Spool file copied to {path}', '', 'APS processing', '--------------'])
            # Run all post nuSolve required processes
            for action, info in aps.processing.Actions.items():
                if info['required']:
                    if not aps.run_process(action, options['initials'], auto=True):
                        break
                    else:
                        summary.append(f'{action} done {aps.processing.done(action)}')
            else: # loop not stopped by break. Submit files
                for submission, info in aps.processing.Submissions.items():
                    if info['required']:
                        if ans := aps.submit_results(submission.replace('SUBMIT-', '')):
                            for name in ans:
                                aps.logit(f'{name} will be uploaded later')
                                summary.append(f'{submission} {aps.processing.done(submission)} - '
                                               f'{name} will be uploaded later')
                        if aps.has_errors:
                            break
                        else:
                            for file in submit.get_last_submission():
                                name = os.path.basename(file)
                                aps.logit(f'{name} submitted')
                                summary.append(f'{submission}: {aps.processing.done(submission)} - {name} submitted')
                else:  # loop not stopped by break. Generate analysis report
                    is_ivs = aps.processing.check_agency()
                    ok, txt = aps.make_analysis_report(is_ivs, [], [], [], auto=options['analyst'])
                    if ok:
                        aps.processing.TempReport = tempfile.NamedTemporaryFile(prefix='{}_report_'.format(aps.session.code),
                                                                  suffix='.txt', delete=False).name
                        with open(aps.processing.TempReport, 'w') as out:
                            out.write(txt)
                        aps.logit('submit analysis report and spoolfile')
                        ans = aps.submit_report(is_ivs)
                        if not aps.has_errors:
                            summary.append(f'{aps.processing.Reports[-1]} submitted')
                            summary.append(f'{aps.processing.SpoolFiles[-1]} submitted')
                            for name in ans:
                                aps.logit(f'{name} will be uploaded later')
                            # Send email to IVS
                            if msg := aps.send_analyst_email('last'):
                                aps.errors(f'Failed sending report {msg}')
                            else:
                                summary.append('Analysis report sent to IVS mail')
            self.send_auto_processing_email(vgosdb, "\n".join(summary), aps.errors)

    # Execute pre-nuSolve applications
    def exec_app(self, path, option, wrapper):
        # Clean option and make command
        if option.startswith('-'):
            option = ' ' + option
        cmd = f'{path}{option} {wrapper.path}'
        # Execute command
        ans, err = app.exec_and_wait(cmd)
        return cmd, ans, err

    # Rename folder in case it already exist
    @staticmethod
    def rename_folder(folder, prefix):
        if os.path.exists(folder):
            for index in range(1, 10):
                new_folder = f'{folder}.{prefix}{index}'
                if not os.path.isdir(new_folder):
                    os.renames(folder, new_folder)
                    return new_folder
        return None

    # Send warning when it fails
    def failed(self, msg):
        self.warning(msg)
        return False
