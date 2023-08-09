
if __name__ == '__main__':

    import argparse

    from aps.ivsdb import IVSdata, loaders
    from aps.utils import app

    parser = argparse.ArgumentParser( description='Database loader' )

    parser.add_argument('-c', '--config', help='configuration file', required=True)
    parser.add_argument('-d', '--db', help='database name', default='ivscc', required=False)
    parser.add_argument('-master', help='master file', default='', required=False)
    parser.add_argument('-ns', help='ns-codes.txt file', default='', required=False)
    parser.add_argument('-mf', help='master-format.txt file', default='', required=False)
    parser.add_argument('-build', help='build database', action='store_true', required=False)

    args = app.init(parser.parse_args())
    db_url, db_tunnel = app.get_dbase_info()
    if args.build:
        IVSdata.build(db_url)
    else:
        with IVSdata(db_url, db_tunnel) as dbase:
            if args.ns:
                loaders.load_ns_codes(dbase, args.ns)
            elif args.mf:
                loaders.load_master_format(dbase, args.mf)
            elif args.master:
                loaders.load_master(dbase, args.master)


