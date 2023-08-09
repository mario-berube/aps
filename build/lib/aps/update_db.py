import sys
import re
import os
try:
    from importlib.resources import files
except:
    from importlib_resources import files
from datetime import datetime
from pathlib import Path

from aps.ivsdb import IVSdata, loaders, models
from aps.utils import app

is_master = re.compile('master(?P<year>\d{4}|\d{2})(?P<type>|-int|-vgos)\.txt').match


def year(name):
    info = is_master(name)
    y = int(info['year'])
    y = y + 2000 if y < 50 else y + 1900 if y < 1900 else y
    return f'{y}{info["type"]}-{len(info["year"])}'


def load_masters(dbase, folder):
    lst = sorted([path for path in Path(folder).glob('master*.txt') if is_master(path.name)],
                 key=lambda x: year(x.name))
    for path in lst:
        if path.exists() and path.stat().st_size > 0 and not loaders.load_master(dbase, path):
            break


def main():
    import argparse

    parser = argparse.ArgumentParser(description='APS Database')
    parser.add_argument('-c', '--config', help='configuration file', required=False)

    parser.add_argument('path', help='path to configuration file', default='', nargs='?')
    app.init(parser.parse_args())

    if missing := app.test_environment():
        print('These environment variables must be defined!')
        print('\n'.join([f'{code}: {desc}' for code, desc in missing.items()]))
        sys.exit(0)

    url = app.db_url()
    if not Path(app.database).exists():
        IVSdata.build(url)

    with IVSdata(url) as dbase:
        # Add default values for master-format.txt and ns-codes.txt
        if loaders.load_master_format(dbase, Path(files('aps').joinpath('files/master-format'))) and \
                loaders.load_ns_codes(dbase, Path(files('aps').joinpath('files/ns-codes'))):
            loaders.load_master_format(dbase, Path(app.master_dir, 'master-format.txt.txt'), notify=True)
            loaders.load_ns_codes(dbase, Path(app.control_dir, 'ns-codes.txt.txt'), notify=True)
            load_masters(dbase, app.control_dir)


if __name__ == '__main__':

    sys.exit(main())
