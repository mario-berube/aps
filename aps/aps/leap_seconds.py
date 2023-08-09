import os
from pathlib import Path
from aps.utils import app, to_float


# Setup so it read only once
def read_ut1ls():
    globals()['UT1LS'] = info = {'first': None, 'last': None, 'data': [], 'errors': []}
    path = Path(app.folder('CALC_APRIORI_DIR'), 'ut1ls.dat')
    if not os.path.exists(path):
        info['errors'].append(f'{path} does not exist!')
        return info

    try:
        with open(path) as ls:
            for line in ls:
                JD, TAImUTC = to_float(line[17:26]), to_float(line[36:48])
                if not info['first']:
                    info['first'] = JD
                info['last'] = JD
                info['data'].append((JD, TAImUTC))

    except Exception as err:
        info['errors'].append(str(err))
    return info


def get_error():
    info = globals()['UT1LS'] if 'UT1LS' in globals() else read_ut1ls()
    return '\n'.join(info['errors'])


# Get UT1 - TAI for specific julian date
def get_UTC_minus_TAI(julian_date):
    info = globals()['UT1LS'] if 'UT1LS' in globals() else read_ut1ls()
    if info['errors']:
        return None
    # Test out of limit
    if julian_date < info['first'] or julian_date > info['last']:
        info['errors'].append(f'{julian_date} not between {info["first"]} and {info["last"]}')
        return None

    for JD, TAImUTC in info['data']:
        if JD > julian_date:
            break
        UTCmTAI = -TAImUTC

    return UTCmTAI  # It is exactly the last value
