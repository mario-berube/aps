from aps.schedule.skd import SKD
from aps.schedule.vex import VEX
from collections import OrderedDict


def sched_reader(session, vex_first=False):
    cls = OrderedDict([('skd', SKD), ('vex', VEX)])
    codes = list(cls.keys())
    if vex_first:
        codes.reverse()
    for code in codes:
        if (path := session.file_path(code)).exists():
            return cls[code](path)
    return SKD('')


def get_schedule(session, vex_first=False, VieSched_sort=False):
    with sched_reader(session, vex_first) as sched:
        if sched.valid:
            sched.read(VieSched_sort)
            for sta in session.removed:
                if (sta := sta.capitalize()) in sched.stations['codes']:
                    sched.missed.append(sched.stations['codes'][sta]['name'])

    return sched
