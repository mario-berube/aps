import tempfile
import os

from utils import app
from utils.servers import load_servers, get_server, DATACENTER
from vgosdb.compress import VGOStgz


def fetch(center, tmp_dir, db_name):
    # Get database
    dbase = app.get_dbase()
    if not (ses_id := dbase.get_db_session_code(db_name)):
        print(f'{db_name} is invalid vgosDB name')
        return
    session = dbase.get_session(ses_id)

    if center not in load_servers(DATACENTER):
        print(f'{center} is not a valid IVS Data Center')
        return

    folder = os.path.join(tmp_dir, db_name)
    if os.path.exists(folder):
        print(f'{folder} exists and cannot be overwritten')
        return

    with tempfile.NamedTemporaryFile(delete=True) as file, get_server(DATACENTER, center) as server:
        rpath = os.path.join(server.root, f'ivsdata/vgosdb/{session.year}/{db_name}.tgz')
        ok, info = server.download(rpath, file.name)
        if not ok:
            print(f'Could not download {db_name} from {center} - {info}')
            return
        tgz = VGOStgz(db_name, file.name)
        tgz.extract(folder)
        print(f'{db_name} downloaded in {folder}')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser( description='vgosdb ' )

    parser.add_argument('-c', '--files', help='adap control file', required=True)
    parser.add_argument('-d', '--db', help='database name', default='ivscc', required=False)
    parser.add_argument('-C', '--center', help='IVS Data Center', default = 'cddis', required=False)
    parser.add_argument('-t', '--tmp', help='tmp directory', required=True)
    parser.add_argument('db_name', help='vgosDB name')

    args = app.init(parser.parse_args())

    fetch(args.center, args.tmp, args.db_name)
