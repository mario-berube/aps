import os

from utils.servers import load_servers, get_server, get_aliases, CORRELATOR
from utils import app, readDICT
from vgosdb import VGOSdb, vgosdb_folder
from vgosdb.controller import VGOSDBController
from ivsdb import IVSdata


def download(center, rpath):
    filename = os.path.basename(rpath)
    with get_server(CORRELATOR, center) as server:
        ok, err = server.download(rpath, filename)
        if ok:
            print(f'{filename} has been downloaded')
        else:
            print(f'Problem downloading {filename} from {server.code} [{err}]')


# Check correltor site to see if database is available
def check_correlator(session, filename):
    correlator, db_name = session.correlator.lower(), session.db_name
    # Check correlator sites
    correlators = [correlator] if correlator in load_servers(CORRELATOR) else []
    correlators.extend(get_aliases(CORRELATOR, correlator))
    correlators.extend([center for center in ['bkg', 'cddis', 'opar'] if center not in correlators])
    for center in correlators:
        with get_server(CORRELATOR, center) as server:
            path = server.file_name.format(year=session.year, session=session.code, db_name=db_name)
            path = os.path.join(os.path.dirname(path), filename) if filename else path
            rpath = os.path.join(server.root, path)
            print(f'Looking for {rpath} at {server.code}.', end='')
            exists, timestamp = server.get_file_info(rpath)
            if exists:
                print(f' Found {os.path.basename(path)}!')
                return center, rpath, timestamp
            print(' Not found!')
    # Did not find it
    return None, None, None


# Check if vgosDB is available on correlator
def get_from_correlator(db_name, reset=False, download_and_stop=False):
    filename = db_name if os.path.splitext(db_name)[-1] else None

    # Get information on this from database
    url, tunnel = app.get_dbase_info()
    with IVSdata(url, tunnel) as db:
        if not (ses_id := db.get_db_session_code(db_name)):
            print(f'{db_name} is not valid vgosDB name')
            return

        session = db.get_session(ses_id)
        session.db_name = db_name
        print(f'Looking for {db_name} ({str(session.code.upper())})')

        # Check if file exists on ftp or https sites
        center, rpath, timestamp = check_correlator(session, filename)
        if not rpath:
            print(f'Did not find {db_name} on any {session.correlator.upper()} servers.')
            return

        if not app.args.test:
            db.update_recent_file(os.path.basename(rpath), timestamp, tableId=1)
        if download_and_stop:
            download(center, rpath)
            db.commit()
            return

        # Process it
        user = os.environ['SUDO_USER'] if 'SUDO_USER' in os.environ else os.environ['USER']
        controller = VGOSDBController(user)

    if reset:  # Rename old database folder if reset option
        print('Reset folder')
        controller.rename_folder(vgosdb_folder(db_name), 'p')

    db.commit() if controller.process(center, db_name, rpath) else db.rollback()


def get_from_file(db_name, path):
    user = os.environ['SUDO_USER'] if 'SUDO_USER' in os.environ else os.environ['USER']
    controller = VGOSDBController(user)
    controller.process_file(db_name, path)


def print_data(keys, info):
    if isinstance(info, dict):
        for key, data in info.items():
            print_data(keys+' '+key, data)
    else:
        print(keys, info)


def vgosDb_dump(db_name):

    vgosdb = VGOSdb(db_name)

    print(vgosdb.correlated)

    for key, data in vgosdb.wrapper.var_list.items():
        print_data(key, data)
    #vgosdb_old.dump_observables()
    vgosdb.statistics()

    used = 0
    corr = 0
    for sta in vgosdb.station_list:
        info = vgosdb.stats[sta]
        corr += info['corr']
        used += info['used']
        print('{:8s} {:5d} {:5d}'.format(sta, info['corr'], info['used']))

    print('{:8s} {:5d} {:5d}'.format('Total', int(corr/2), int(used/2)))


def get_summary(db_name):
    info = app.load_control_file(name=app.ControlFiles.VGOSdb)[-1]
    # Read agency code
    conf = os.path.expanduser(info['Agency']['file'])
    conf = readDICT(conf)
    agency = conf[info['Agency']['keys'][0]][info['Agency']['keys'][1]]

    folder = vgosdb_folder(db_name)
    vgosdb = VGOSdb(folder)
    if not vgosdb.is_valid():
        return
    print(vgosdb.summary(agency))

    vgosdb.statistics()

    if vgosdb.stats:
        [print(f'{sta:8s} {vgosdb.stats[sta]["corr"]:5d} {vgosdb.stats[sta]["used"]:5d}') for sta in vgosdb.station_list]
        corr, used = zip(*[(vgosdb.stats[sta]["corr"], vgosdb.stats[sta]["used"]) for sta in vgosdb.station_list])
        print(f'{"Total":8s} {int(sum(corr)/2):5d} {int(sum(used)/2):5d}')

    wrapper = vgosdb.get_oldest_wrapper()
    for item in wrapper.var_list.values():
        if isinstance(item, dict):
            if 'cal-cable_kpcmt' in item.keys():
                print(item['cal-cable_kpcmt'])


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser( description='vgosdb ' )

    parser.add_argument('-c', '--files', help='control file', required=True)
    parser.add_argument('-d', '--db', help='database name', default='ivscc', required=False)
    parser.add_argument('-C', '--corr', help='do not download correlator report', action='store_false')
    parser.add_argument('-f', '--file', help='process database file')
    parser.add_argument('-g', '--get', help='get database', action='store_true')
    parser.add_argument('-r', '--reset', help='reset database', action='store_true')
    parser.add_argument('-t', '--test', help='test database', action='store_true')
    parser.add_argument('-s', '--summary', help='test database', action='store_true')
    parser.add_argument('-p', '--no_processing', help='no processing', action='store_true')
    parser.add_argument('-m', '--no_mail', help='no email', action='store_true')
    parser.add_argument('-D', '--download', help='just download the file', action='store_true')
    parser.add_argument('db_name', help='vgosDB name')

    args = app.init(parser.parse_args())

    if args.summary:
        get_summary(args.db_name)
    elif args.file:
        get_from_file(args.db_name, args.file)
    elif args.get or args.reset:
        get_from_correlator(args.db_name, args.reset, args.download)