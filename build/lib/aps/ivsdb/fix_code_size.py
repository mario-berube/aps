from utils import app
from sqlalchemy import create_engine


def fix_code_size():

    db_url, _ = app.get_dbase_info()
    connection = create_engine(db_url).connect()
    query = "SELECT table_name, column_name FROM information_schema.key_column_usage " \
            "WHERE referenced_table_name IS NOT NULL AND referenced_table_name = 'sessions' " \
            "AND referenced_column_name = 'code' AND table_schema = 'ivscc';"

    print('set foreign key off')
    connection.execute('SET FOREIGN_KEY_CHECKS = 0')  # turn off foreign key checks
    for (table_name, column_name) in [('sessions', 'code')] + list(connection.execute(query)):
        print(f'alter {table_name} {column_name}')
        connection.execute(f'ALTER TABLE {table_name} MODIFY {column_name} varchar(15);')
    print('set foreign key on')
    connection.execute('SET FOREIGN_KEY_CHECKS = 1')  # turn on foreign key checks
    print('done')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser( description='VGOSDB preprocessor.' )

    parser.add_argument('-c', '--config', help='config file', required=True)
    parser.add_argument('-d', '--db', help='database name', default='ivscc', required=False)

    app.init(parser.parse_args())

    fix_code_size()
