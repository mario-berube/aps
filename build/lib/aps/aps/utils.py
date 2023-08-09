import sys
import select
from pathlib import Path
import importlib.metadata

from aps.aps import APS


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

    codes = [code for code in arguments.submit if code in ("SINEX", "DB", "EOPS", "EOPI", "EOPXY", "ALL")]
    sessions = [code for code in arguments.submit if code not in ("SINEX", "DB", "EOPS", "EOPI", "EOPXY", "ALL")]
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


