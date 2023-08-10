import os
import sys
import shutil
import traceback
from importlib import import_module
from datetime import datetime
from pathlib import Path
from shutil import which
from psutil import process_iter
import logging
import logging.handlers
import select
import importlib.metadata

from aps.utils import app
from aps.utils.files import chmod
from aps.utils.mail import send_message, build_message
from aps.aps import solve
from aps.aps.spool import read_spool
from aps.aps.report import STDreport, INTreport
from aps.aps.processing import Processing
from aps.aps.submit import submit_files
from aps.vgosdb import VGOSdb
from aps.vgosdb.nusolve import get_nuSolve_info
from aps.vgosdb.correlator import CorrelatorReport
from aps.schedule import get_schedule


logger = logging.getLogger()


class APS:

    max_length = 75

    def __init__(self, param):
        super().__init__()
        # List to store error messages
        self._errors, self.critical = [], False
        self.session = self.db_name = self.spool = None

        # Read agency code from vgosDb control file using information in VGOSDB control file
        self.agency = app.agency.upper()
        # Check input parameters to find session and vgosDB
        if param:
            if not self.check_initials(param) and not self.get_session(param):
                self.add_error(f'{param} not a valid session or db_name')
                return
        # Extract session from working directory
        elif not self.get_session(Path().cwd().name):
            self.add_error('Could not find session or db_name')
            self.add_error('')
            self.add_error('1 - Move to session or vgosdb folder or')
            self.add_error('2 - Input session name, db_name or initials as parameter')
            return
        self.init_logger()

        # Extract some information for session
        self.ac_code = app.analysis_center.upper()
        self.is_intensive = self.session.type == 'intensive'
        self.analysis_center = self.session.analysis_center.upper()
        self.ses_id = self.session.code.lower()
        self.db_name = self.session.db_name
        # Get OPA config file from arguments or used default.
        if app.args.opa_config and Path(getattr(app.args, 'opa_config')).exists():
            print('from input', app.args.opa_config, Path(getattr(app.args, 'opa_config')))
            self.opa_lcl = app.args.opa_config
        else:  # Use default control file for session type
            self.opa_lcl = app.opa_int if self.session.type == 'intensive' else app.opa_std
        # Read vgosDB file
        self.vgosdb = VGOSdb(self.session.db_folder)
        if not self.vgosdb.is_valid():
            self.add_error(f'Cannot access {self.db_name} at {self.vgosdb.folder}')
            return
        # Set active wrapper to last wrapper created by this agency
        self.vgosdb.set_wrapper(self.vgosdb.get_last_wrapper(self.agency))
        self.nuSolve = get_nuSolve_info(self.vgosdb.wrapper)
        self.processing = Processing(self.vgosdb, self.session, self.ac_code)

        if not self.spool:
            self.spool = read_spool(db_name=self.db_name, read_unused=True)

    # Add error in list of errors
    def add_error(self, err, critical=False):
        self._errors.append(err)
        self.critical = critical if critical else self.critical
        logger.error(err)
        return None

    # Test if there are some errors
    @property
    def has_errors(self):
        return len(self._errors) > 0

    # Clear errors
    def clear_errors(self):
        self._errors = []

    # Test if valid
    @property
    def is_valid(self):
        return self.session and len(self._errors) == 0

    # Return list of errors (1 per line)
    @property
    def errors(self):
        return '\n'.join(self._errors)

    # Use database to find session or db_name
    def get_session(self, name):
        # Get database url from control file
        dbase = app.get_dbase()
        db_name = name
        # Retrieve session by db_name
        if not (ses_id := dbase.get_db_session_code(db_name)):
            ses_id, db_name = name, None
        # Retrieve session by name
        self.session = dbase.get_session(ses_id)
        if self.session:
            self.session.db_name = db_name
        return bool(self.session)

    # Check if input param is valid initial
    def check_initials(self, initials):
        if not (spool_file := read_spool(initials=initials.upper(), read_unused=True)):
            return False
        # Extract db_name from spool file
        self.spool = spool_file
        try:
            self.db_name = self.spool.runs[0].DB_NAME
        except:
            self.add_error(f'Could not extract DB_NAME from spool SPLF{initials}')
            return False
        if not self.get_session(self.db_name):
            self.add_error(f'{self.db_name} extracted from SPLF{initials} is invalid db_name')
            return False
        return True

    # Extract notes from correlator report and insert in problems
    def extract_corr_notes(self):
        # Recursively split lines longer than max_length
        def split_line(text):
            if len(text) < APS.max_length + 10 or ((index := text[:APS.max_length].rfind(' ')) == -1):
                return [text]
            lines = [text[:index]]
            lines.extend(split_line(text[index+1:]))
            return lines

        # Check if something in the problem information
        if not self.processing.Comments.get('CorrNotes', False):
            logger.info('extract comments from correlator notes')
            problems = self.processing.Comments['Problems']
            # Read correlator notes
            self.processing.Comments['CorrNotes'] = True
            # Insert lines in problems
            for name, comment in CorrelatorReport(self.session.file_path('corr')).get_notes().items():
                prefix = name
                for line in split_line(comment):
                    problems.append(f'{prefix} {line}')
                    prefix = ' ' * len(prefix)
            if problems:
                self.processing.Comments['Problems'] = problems
            self.processing.save()  # Save processing history

    # Check if AC should be doing IVS solution
    def _submit_(self):
        return self.analysis_center.upper() == self.ac_code

    # Check if solution is not to old to submit
    def _not_too_old_(self):
        return (datetime.utcnow() - self.session.start).days < 90

    # Make path of master notes for this session
    def master_notes(self):
        session_type = {'intensive': '-intnotes', 'vgos': '-vgosnotes'}.get(self.session.type, '-notes')
        for year in [self.session.year, self.session.year[2:]]:
            if (path := Path(app.folder('MASTER_DIR'), f'master{year}{session_type}.txt')).exists():
                return path
        return None

    # Use generic function to submit special files
    def submit_results(self, name):
        try:
            # The process file has the same name than the option
            aps_module = import_module('aps.aps.submit')
            # Find class for this process
            code = name.split('-')[-1]
            cls = getattr(aps_module, code)
            # Get instance of class and submit file
            prc = cls(self.opa_lcl)
            if not prc.has_errors:
                return prc.submit(session=self.session, vgosdb=self.vgosdb)
            # Save error and return failed
            self.add_error(prc.errors)
            return None
        except Exception as err:
            self.add_error(f'Unexpected error! Contact Mario\n{str(err)}\n{traceback.format_exc()}')
            return None

    # Make name of analysis and spool file and them to cddis
    def submit_report(self, is_IVS):
        if not os.path.exists(self.spool.path):
            return False, f'{os.path.basename(self.spool.path)} does not exist!'
        ac = 'IVS' if is_IVS else self.ac_code
        ses_id = self.session.code.lower()
        now, tmp = datetime.utcnow().strftime('%Y%m%d-%H%M'), self.processing.TempReport

        analysis_report = os.path.join(self.session.folder, f'{ses_id}-{ac}-analysis-report-{now}.txt')
        spool_file = os.path.join(self.session.folder, f'{ses_id}-{ac}-analysis-spoolfile-{now}.txt')
        shutil.copy(tmp, analysis_report)
        chmod(analysis_report)
        shutil.copy(self.spool.path, spool_file)
        chmod(spool_file)

        # Remove tmp file
        os.remove(tmp)
        self.processing.Reports.append(os.path.basename(analysis_report))
        self.processing.SpoolFiles.append(os.path.basename(spool_file))
        self.processing.save()  # Save Processing history

        # Submit files to cddis
        return submit_files([analysis_report, spool_file])

    # Extract comments from report
    @staticmethod
    def get_comments(text, reset=False):
        if reset:
            return [], [], [], {}

        # Extract in line comments from intensive report lines
        def get_inline_comments(_lines):
            _title = _lines[0].split(':')[0].split()[-1]
            _comments = []
            for _line in _lines[1:]:
                if not _line.strip():
                    continue
                if _line.strip().startswith(('Number of observations ', 'Other comments:', 'observation')):
                    return _title, _comments
                _comments.append(line)

        def get_standard_comments(title, lines):
            offset = len(title) + 1
            comments = [lines[0][offset:]]
            for line in lines[1:]:
                if not line.strip():
                    return comments
                comment = line.strip() if line[:offset].strip() else line[:offset]
                comments.append(comment)
            return comments

        groups, in_line = {'Problems:': [], 'Parameterization comments:': [], 'Other comments:': []}, {}
        lines = text.splitlines() if text else []
        for index, line in enumerate(lines):
            for title, lst in groups.items():
                if line.startswith(title):
                    groups[title] = get_standard_comments(title, lines[index:])
                    break
            else:
                if line.startswith('Number of observations '):
                    name, comments = get_inline_comments(lines[index:])
                    in_line[name] = comments

        return groups['Problems:'], groups['Parameterization comments:'], groups['Other comments:'], in_line

    # Make analysis report
    def make_analysis_report(self, is_ivs_report, problems, parameterization, other, in_line=None, auto=None):

        cls_report = STDreport if self.session.type == 'standard' else INTreport

        schedule = get_schedule(self.session)
        if schedule.session_code.lower() != self.session.code:
            if not schedule.path:
                problems.append(f'{self.session.code} has not schedule file')
            else:
                problems.append('{} has invalid record $EXPER {}'.format(os.path.basename(schedule.path), schedule.session_code))
            problems.append('Therefore the source breakdown at the end of the summary has been deleted.')
            problems.append('The reported information is based on the nuSolve spoolfile, which is based')
            problems.append('on the correlated data.')
            schedule = None
        else:
            schedule.stations['removed'] = self.session.removed

        self.vgosdb.statistics()

        logger.info('create analysis report')
        with cls_report() as analysis_report:
            analysis_report.write_header(self.ac_code, self.ses_id, self.db_name, is_ivs_report)
            analysis_report.write_analysts_info(self.nuSolve, auto=auto)
            analysis_report.write_warnings(schedule, self.spool)
            analysis_report.write_comments('Problems:', problems, in_line, schedule, self.vgosdb, self.spool)
            analysis_report.write_comments('Parameterization comments:', parameterization)
            analysis_report.write_comments('Other comments:', other)
            try:
                analysis_report.write_stats(schedule, self.vgosdb, self.spool)
            except Exception as err:
                logger.error(f'failed creating analysis. {str(err)}')
                [logger.error(line) for line in traceback.format_exc().splitlines() if line]
                return False, f'Could not create analysis report {str(err)}. See log.'
            analysis_report.write_station_performance(schedule, self.vgosdb, self.spool)
            analysis_report.write_source_performance(schedule, self.vgosdb, self.spool)
            analysis_report.write_baseline_performance(schedule, self.vgosdb, self.spool)

        return True, analysis_report.get_text()

    # Send email to IVS analysis group
    def send_analyst_email(self, name='last'):

        if name == 'last' and not self.processing.Reports:
            return 'No report to send'

        name = self.processing.Reports[-1] if name == 'last' else name
        if (path := os.path.join(self.session.folder, name)) and not os.path.exists(path):
            return f'{name} does not exist!'
        if not os.stat(path).st_size:
            return f'{name} is empty!'

        if not app.mail_server:
            return 'SMTP mail server not defined'
        logger.info('email analysis report')
        ac = 'IVS' if self.processing.check_agency() else self.ac_code
        name = self.vgosdb.name
        name = name.lower() if name[:4].isdigit() else name.upper()
        title = f'{self.session.code.upper()} ({name}) {ac} Analysis Report'

        recipients = app.recipients.split(',')
        is_smtp = not app.mail_server.startswith('gmail')

        msg = build_message(app.sender, recipients, title, text=open(path, 'r').read(), is_smtp=is_smtp)
        return send_message(app.mail_server, msg)

    # Use generic function to execute a specific process using its name
    def run_process(self, name, initials='--', auto=False):
        try:
            self.clear_errors()
            # The process file has the same name than the option
            aps_module = import_module(f'aps.aps.{name.lower()}')
            # Find class for this process
            cls = getattr(aps_module, name.upper())
            # Execute process
            prc = cls(self.opa_lcl, initials)
            if not prc.has_errors and prc.execute(self.session, self.vgosdb):
                logger.info(f'{name} done successfully{" - auto" if auto else ""}')
                return True
            # Save error and return failed
            self.add_error(prc.errors)
            return False
        except Exception as err:
            self.add_error('Unexpected error! Contact Mario\n{}\n{}'.format(str(err), traceback.format_exc()))
            return False

    # Validate initials using letok file in SAVE_DIR
    @staticmethod
    def validate_initials(initials):
        if len(initials) == 2:
            initials = initials.upper()
            with open(os.path.join(os.getenv('SAVE_DIR'), 'letok')) as file:
                for line in file.readlines():
                    if line.startswith(initials):
                        return initials
        return None

    def logit(self, msg):
        logger.info(msg)

    # Initialize logger recording most of the user actions.
    def init_logger(self):
        # Custom filter use to format records
        class RecordFilter(logging.Filter):
            def filter(self, record):
                setattr(record, 'now', datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
                return True

        path = self.session.file_path('aps.log')
        logging.basicConfig(
            level=logging.INFO,
            format="%(now)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(str(path))
            ]
        )
        logger.addFilter(RecordFilter())
        logger.info('APS started')


# Get APS path from environment. If missing, extract from scripts
def get_aps_path():
    if path := os.environ.get('__APS_PATH__', ''):
        return path
    if path := which('aps'):
        with open(path, errors='ignore') as script:
            for line in script:
                if 'python' in line:
                    app_name = line.split('python')[-1].strip().split()[0]
                    app_path = Path(*[os.environ.get(part.replace('$', ''), part) for part in Path(app_name).parts])
                    os.environ['__APS_PATH__'] = str(app_path)
                    return str(app_path)
    return None


# Get all processes running APS
def get_aps_process():
    for prc in process_iter(attrs=['pid', 'name', 'cmdline']):
        if prc.info['name'] == 'python':
            if len(prc.info['cmdline']) > 3 and prc.info['cmdline'][1].endswith('/aps'):
                yield prc.info['pid'], prc.info['cmdline'][-1]


def version(patch=True):
    return '.'.join(importlib.metadata.version('aps').split('.')[:3 if patch else 2])


def print_status(arguments):
    aps = APS(arguments.param)
    if not aps.is_valid:
        print(aps.errors)
        return
    print(aps.processing.make_status_report())


def email_report(arguments):
    report_path = Path(arguments.email_report)
    name = report_path.name
    if name == 'last':
        if not arguments.param:
            print('Need session code as last parameter')
            return
        ses_id, report = arguments.param, 'last'
    elif 'analysis-report' in name:
        if not report_path.exists():
            print(f'{arguments.email_report} does not exist!')
            return
        ses_id, report = name.split('-')[0], arguments.email_report  # get ses_id from report name
    else:
        print(f'Invalid --email_report option {arguments.email_report}')
        return

    aps = APS(ses_id)
    if aps.is_valid:
        if msg := aps.send_analyst_email(report):
            print(f'Failed sending report {msg}')
        else:
            print(f'Email regarding {report} was successfully sent')
    else:
        print(f'{name} is not a valid session or analysis report name')
        print(aps.errors)


def print_report(arguments):
    aps = APS(arguments.param)
    if not aps.is_valid:
        print(aps.errors)
        return
    if not aps.spool:
        print(f'No valid spool file for {aps.ses_id} {aps.db_name}')
        return
    is_ivs = aps.processing.check_agency()
    ok, txt = aps.make_analysis_report(is_ivs, [], [], [])
    print(txt if ok else aps.errors)


def batch_submit(arguments):

    accepted = {"SINEX", "DB", "EOPS", "EOPI", "EOXY", "ALL"}
    codes = [code for code in arguments.submit if code in accepted]
    sessions = [code for code in arguments.submit if code not in accepted]
    if select.select([sys.stdin], [], [], 0)[0]:
        sessions = list(filter(None, [name.strip() for name in sys.stdin.readlines()]))

    for ses_id in sessions:
        aps = APS(ses_id)
        if not aps.is_valid:
            print(aps.errors)
        else:
            info = {code.replace('SUBMIT-', ''): item for (code, item) in aps.processing.Submissions.items()}
            submissions = list(info.keys())
            if 'ALL' in codes:
                codes = [code for (code, item) in info.items() if item['required']]
            for code in codes:
                if code in submissions and aps.submit_results(code):
                    if aps.has_errors:
                        print(aps.errors)
                        aps.clear_errors()
                    else:
                        aps.processing.done(f'SUBMIT-{code}')


def batch_proc(arguments):
    codes = [code for code in arguments.batch[::-1] if APS.validate_initials(code)]
    if not codes:
        print(f'No valid initials in --batch option {arguments.batch}')
        return
    initials, index = codes[0], arguments.batch.index(codes[0])
    actions, sessions = arguments.batch[0:index], arguments.batch[index+1:]

    if select.select([sys.stdin], [], [], 0)[0]:
        sessions = list(filter(None, [name.strip() for name in sys.stdin.readlines()]))

    for ses_id in sessions:
        aps = APS(ses_id)
        if not aps.is_valid:
            print(aps.errors)
        else:
            if actions[0] == 'ALL':
                actions = [name for (name, item) in aps.processing.Actions.items() if item['required']]
            for action in aps.processing.Actions.keys():
                if action in actions:
                    if aps.run_process(action, initials):
                        aps.processing.done(action)
                    else:
                        print(aps.errors)
                        break

