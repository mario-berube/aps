
from pathlib import Path

from aps.utils import app, toggle_options
from aps.aps import APS, version, print_status, email_report, print_report, batch_proc, batch_submit
from aps.aps.main import QAPS
from aps.ivsdb import IVSdata, loaders
from aps.make_config import Config


def update_db():
    dbase = app.get_dbase()

    # Add default values for master-format.txt and ns-codes.txt
    if loaders.load_master_format(dbase, app.get_hidden_file('master-format.txt')) and \
            loaders.load_ns_codes(dbase, app.get_hidden_file('ns-codes.txt')):
        loaders.load_master_format(dbase, Path(app.folder('MASTER_DIR'), 'master-format.txt'), notify=True)
        loaders.load_ns_codes(dbase, Path(app.folder('MASTER_DIR'), 'ns-codes.txt'), notify=True)
        loaders.load_masters(dbase, app.folder('MASTER_DIR'))


def make_config(args):
    config = Config(args.ac_code, args.path)
    config.exec()


def test_init(arguments):
    args = app.init(arguments)
    if missing := app.test_environment():
        print('These environment variables must be defined!')
        print('\n'.join([f'{code}: {desc}' for code, desc in missing.items()]))
        sys.exit(0)
    return args


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Access APS functionalities')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-V', '--version', help='display version', action='store_true', required=False)
    group.add_argument('-m', '--make_config', help='make config file', action='store_true', required=False)
    group.add_argument('-u', '--update_db', help='update database', action='store_true', required=False)

    args, _ = parser.parse_known_args()
    if args.version:
        print(f'APS {version()}')
    elif args.make_config:
        parser = argparse.ArgumentParser(description='Update APS database')
        parser.add_argument('-m', '--make_config', action='store_true')
        parser.add_argument('ac_code', help='code of your analysis center', type=str.upper)
        parser.add_argument('path', help='path to configuration file', default='', nargs='?')
        make_config(parser.parse_args())
    elif args.update_db:
        parser = argparse.ArgumentParser(description='Update APS database')
        parser.add_argument('-u', '--update_db', action='store_true', required=True)
        parser.add_argument('-c', '--config', help='config file', required=False)
        test_init(parser.parse_args())
        update_db()
    else:
        parser = argparse.ArgumentParser(description='APS application')
        parser.add_argument('-c', '--config', help='config file', required=False)
        parser.add_argument('-opa', '--opa_config', help='opa lcl file ', default=None, required=False)
        parser.add_argument('-s', '--status', help='', action='store_true', required=False)
        parser.add_argument('-r', '--report', help='', action='store_true', required=False)
        parser.add_argument('-e', '--email_report', help='', required=False)
        parser.add_argument('-b', '--batch', help='procedure to execute in batch mode', nargs='+', required=False)
        parser.add_argument('-S', '--submit', help='procedure to execute in batch mode', nargs='+', required=False)
        parser.add_argument('-editor', help='toggle editor view', action='store_true', required=False)
        parser.add_argument('-notes', help='toggle correlator note usage', action='store_true', required=False)
        parser.add_argument('param', help='initials or session or db_name', default='', nargs='?')

        args = test_init(parser.parse_args())
        update_db()

        if not toggle_options(APS, ['editor', 'notes'], args):
            if args.status:
                print_status(args)
            elif args.email_report:
                email_report(args)
            elif args.report:
                print_report(args)
            elif args.batch:
                batch_proc(args)
            elif args.submit:
                batch_submit(args)
            else:
                qaps = QAPS(args.param)
                qaps.exec()


if __name__ == '__main__':

    import sys
    sys.exit(main())
