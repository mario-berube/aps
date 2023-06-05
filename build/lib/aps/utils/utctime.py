from datetime import datetime, timedelta
import os
import re
import pytz
import math

UTC = pytz.utc

FORMATS = {'spl': '%Y.%m.%d-%H:%M:%S.%f', 'sumry': '%y/%m/%d %H:%M:%S.%f', 'sked': '%Y%j%H%M%S',
           'short': '%Y.%j.%H:%M:%S', 'pcfs': '%Y.%j.%H:%M:%S.%f', 'skd': '%y%j%H%M%S', 'vex': '%Yy%jd%Hh%Mm%Ss',
           'xlist': '%y%j-%H%M%S', 'date': '%Y-%m-%d', 'utc': '%Y-%m-%d %H:%M:%S', 'ftp': '%b %d %H:%M %Y',
           'ftpold': '%b %d %Y', 'file': '', 'mk5': '%Yy%jd%Hh%Mm%S.%fs', 'spool': '%y/%m/%d %H:%M',
           'long': '%Y-%m-%d %H:%M:%S.%f', 'unix': '', 'vgsum': '%Y  %m  %d  %H  %M  %S.%f',
           'english': '%a %b %d %H:%M:%S %Z %Y', 'web': '%Y-%m-%d %H:%M UTC', 'vgosdb': '%Y/%m/%d %H:%M:%S',
           'earthdata': '%Y:%m:%d %H:%M:%S'}


def utc(*args, **kwargs):
    tz = kwargs.get('tzinfo', UTC)
    for key, value in kwargs.items():
        if key in FORMATS:
            return decode(key, value, tz)
    if len(args) < 2:
        return decode('pcfs', args[0], tz)

    return tz.localize(datetime.strptime(args[0], args[1]))


def utcnow():
    return UTC.localize(datetime.utcnow())


def utcstr(value):
    return UTC.normalize(value).strftime(FORMATS['utc'])


def JAN01(year):
    year = int(year) if isinstance(year, str) else year
    return UTC.localize(datetime(year=int(year), month=1, day=1))


def DEC31(year):
    year = int(year) if isinstance(year, str) else year
    return UTC.localize(datetime(year=int(year), month=12, day=31, hour=23, minute=59, second=59, microsecond=999999))


# ftputil needs time difference between local and remote servers to determine year in time format
# sometime it things the time is in future so it is removing 1 year from date with format Month, day, hour, minute
# Since recent files are usually very recent, this function correct old dates to new.
def validate_recent_timestamp(timestamp):
    t = datetime.fromtimestamp(timestamp)
    try:
        new_t = UTC.localize(datetime(datetime.utcnow().year, t.month, t.day, t.hour, t.minute, t.second)).timestamp()
        if new_t - timestamp > 5184000 and abs(utcnow().timestamp() - new_t) < 43200:
            if t.hour > 0 or t.minute > 0 or t.second > 0 or t.microsecond > 0:
                return new_t
    except:
        pass
    return timestamp


def decode(fmt, value, tz=UTC, cformat=''):
    if fmt == 'pcfs':
        value = value[0:20]
    elif fmt == 'vex' and '24h' in value:
        t = datetime.strptime(value[:9], '%Yy%jd')
        t += timedelta(days=1)
        value = t.strftime(FORMATS['vex'])
    elif fmt == 'skd' and value[-6:] == '240000':
        t = datetime.strptime(value[:5], '%y%j')
        t += timedelta(days=1)
        value = t.strftime(FORMATS['skd'])
    elif fmt == 'ftp':
        if ':' in value:
            value += datetime.now().strftime(' %Y')
        else:
            fmt = 'ftpold'
    elif fmt == 'vgsum':
        year, month, day, hour, minute, second, microsecond = re.split('[. ]+', value)
        return tz.localize(datetime(int(year) + 2000, int(month), int(day), int(hour), int(minute),
                                           int(second), int(microsecond)))
    elif fmt == 'file':
        return UTC.localize(datetime.utcfromtimestamp(os.path.getmtime(value)))
    elif fmt == 'unix':
        return UTC.localize(datetime.utcfromtimestamp(value))

    return tz.localize(datetime.strptime(value, FORMATS[fmt]))

# Information to transform utc timedate to Modified Julian Day.
MJD0 = -678957 # MJD at 01-JAN of the 0-th year"
days_in_4years = 1461 # Number of days in 4 years
months = [[0,  31,  60,  91, 121, 152, 182, 213, 244, 274, 305, 335],
          [366, 397, 425, 456, 486, 517, 547, 578, 609, 639, 670, 700],
          [731, 762, 790, 821, 851, 882, 912, 943, 974,1004,1035,1065],
          [1096,1127,1155,1186,1216,1247,1277,1308,1339,1369,1400,1430]
          ]
# Transform string time to Modified Julian Day
def MJD(*args, **kwargs):
    t = utc(*args, **kwargs)
    sec = t.hour * 3600 + t.minute * 60 + t.second
    year = t.year - 4 * int(t.year/4)
    return MJD0 + days_in_4years * int(t.year/4) + months[year][t.month-1] + t.day + sec / 86400

# Special function to decode TIMETAG to avoid 60 second problem
def vgosdbTimeTag(text):
    # Sometime the datetime.strptime failed because of seconds = 60 or hours = 24.
    utc = text.replace('TIMETAG', '').replace('UTC', '').strip()
    hour, minute, second = list(map(int, utc[-8:].split(':')))
    seconds = second + minute * 60 + hour * 3600
    return UTC.localize(datetime.strptime(utc[:10], '%Y/%m/%d') + timedelta(seconds=seconds))


# Combine vgosdb time variable into a datetime
def vgosdbTime(YMDHM, second):
    year, month, day, hour, minute = (YMDHM)
    year = 2000 + year if year < 100 else year
    return UTC.localize(datetime(year, month, day, hour, minute, int(second)))


def toDateTime(ymdhm, sec):
    year = ymdhm[0]
    ymdhm[0] = year if year > 1000 else year + 1900 if year > 50 else year + 2000
    dec, second = math.modf(sec)
    return UTC.localize(datetime(*ymdhm, int(second), int(dec * 1.0e6)))

