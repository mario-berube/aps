from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import orm, exists
from sqlalchemy import Column, BigInteger, Float, Integer, String, DateTime, TIMESTAMP, Boolean, BLOB, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from aps.utils import app, to_float

Base = declarative_base()

T0 = datetime(1970, 1, 1)
VLBAStations = "VaBrFdHnKpLaMkNlPtOvSc"


class Correlator(Base):
    """ Class to manage correlator information """

    __tablename__ = 'correlators'

    code = Column('code', String(4), primary_key=True, unique=True)
    name = Column('name', String(100), nullable=False, server_default='')
    description = Column('description', String(200), nullable=False, server_default='')
    notes = Column('notes', BLOB)

    def __init__(self, code, name=None):
        self.code = code
        self.name = name if name else code

    def __str__(self):
        return self.name if self.name else self.code.upper()

    def __repr__(self):
        return "Correlator('%s, '%s')" % (self.code, self.name)


class OperationsCenter(Base):
    """ Class to manage Operations Center information """

    __tablename__ = 'operations_centers'

    code = Column('code', String(4), primary_key=True, unique=True)
    name = Column('name', String(100), nullable=False, server_default='')
    description = Column('description', String(200), nullable=False, server_default='')
    notes = Column('notes', BLOB)

    def __init__(self, code, name=None):
        self.code = code
        self.name = name if name else code

    def __str__(self):
        return self.name if self.name else self.code.upper()

    def __repr__(self):
        return "OperationsCenter('%s, '%s')" % (self.code, self.name)


class AnalysisCenter(Base):
    """ Class to manage Analysis center information """

    __tablename__ = 'analysis_centers'

    code = Column('code', String(4), primary_key=True, unique=True)
    name = Column('name', String(100), nullable=False, server_default='')
    description = Column('description', String(200), nullable=False, server_default='')
    notes = Column('notes', BLOB)

    def __init__(self, code, name=None):
        self.code = code
        self.name = name if name else code

    def __str__(self):
        return self.name if self.name else self.code.upper()

    def __repr__(self):
        return "Analyst('%s, '%s')" % (self.code, self.name)


class Station(Base):
    """ IVS Station information (from IVS catalog) """

    __tablename__ = 'stations'

    code = Column('code', String(2), primary_key=True, unique=True)
    name = Column('name', String(50), nullable=False)
    operational = Column('operational', Boolean, default=True)
    domes = Column('domes', String(10), nullable=False, server_default='')
    cdp = Column('cdp', String(4), nullable=False, server_default='')
    description = Column('description', String(200), nullable=False, server_default='')
    notes = Column('notes', BLOB)

    def __init__(self, code, name=None):
        self.code = code
        self.name = name if name else code

    def __str__(self):
        return self.name if self.name else self.code.upper()

    def __repr__(self):
        return "Station('%s, '%s')" % (self.code, self.name)

    @staticmethod
    def exists(dbase, code):
        (ret,), = dbase.orm_ses.query(exists().where(Station.code == code))
        return ret

    @staticmethod
    def get(dbase, code):
        return dbase.orm_ses.query(Station).filter(Station.code == code).one() if Station.exists(dbase, code) else None

    @staticmethod
    def delete(dbase, code):
        if Station.exists(dbase, code):
            return dbase.orm_ses.query(Station).filter(Station.code == code).delete()


class Session(Base):
    """ Session information built from master files"""

    __tablename__ = 'sessions'

    code = Column('code', String(15), primary_key=True, unique=True)
    name = Column('name', String(15), nullable=False)
    start = Column('start', DateTime, nullable=False)
    duration = Column('duration', BigInteger, nullable=False)
    type = Column('type', String(10), default='standard')
    correlator = Column('correlator', String(4), ForeignKey(Correlator.code), nullable=False, index=True)
    operations_center = Column('operations_center', String(4), ForeignKey(OperationsCenter.code), nullable=False,
                               index=True)
    analysis_center = Column('analysis_center', String(4), ForeignKey(AnalysisCenter.code), nullable=False, index=True)
    corr_status = Column('corr_status', String(100), default='unknown')
    corr_pf = Column('corr_pf', Float, nullable=True)
    corr_released_date = Column('corr_released_date', DateTime, nullable=True)
    corr_db_code = Column('corr_db_code', String(2))
    corr_mk4_num = Column('corr_mk4_num', String(10))
    analyzed = Column('analyzed', Boolean, default=False)
    correlated = Column('correlated', Boolean, default=False)
    scheduled = Column('scheduled', Boolean, default=False)

    participating = relationship('SessionStation', cascade='save-update, merge, delete, delete-orphan')

    def __init__(self, code=None):
        if code:
            self.code, self.correlator, self.operations_center, self.analysis_center = code, 'WASH', 'NASA', 'NASA'
        self.stations, self.included, self.removed = [], [], []
        self._has_vlba, self.skd = False, None
        self._db_name = self._folder = None

    def __str__(self):
        if not self.start:
            return f'{self.code:10} - empty'
        removed = f' [{",".join([sta.capitalize() for sta in self.removed])}]' if self.removed else ""
        sta_list = f'{",".join([sta.capitalize() for sta in self.included])}{removed}'
        return f'{self.code:8} {self.db_name} {self.name:10} {self.start.strftime("%Y-%m-%d %H:%M")} {sta_list} ' \
               f'{self.operations_center.upper()} {self.correlator.upper()} {self.analysis_center.upper()}'

    @orm.reconstructor
    def __reinit__(self):

        self.__init__()
        for ses_sta in self.participating:
            self.stations.append(ses_sta.station)
            if ses_sta.status == 'included':
                self.included.append(ses_sta.station)
                if ses_sta.station.capitalize() in VLBAStations:
                    self._has_vlba = True
            else:
                self.removed.append(ses_sta.station)

        self.stations.sort()
        self.included.sort()
        self.removed.sort()

    @staticmethod
    def build_path(*args, **kwargs):
        path = args[0][0] if isinstance(args[0], list) else args[0]
        for key, value in kwargs.items():
            if (key_word := f'{{key}}') in path:
                path = path.replace(key_word, value)
        return Path(path)

    @property
    def has_vlba(self):
        return self._has_vlba

    @property
    def folder(self):
        self._folder = self._folder if self._folder else Path(app.folder('SESSION_DIR'), self.year, self.code)
        return self._folder

    @property
    def year(self):
        return self.start.strftime('%Y')

    @property
    def is_intensive(self):
        return self.type == 'intensive'

    @property
    def end(self):
        return self.start + timedelta(seconds=self.duration)

    def make_folder(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        return self.folder

    def file_name(self, code, sta=''):
        return '{ses}{sta}.{code}'.format(ses=self.code, sta=sta.lower(), code=code)

    def file_path(self, code, sta=''):
        name = self.file_name(code, sta)
        return Path(self.folder, name)

    def log_path(self, sta):
        name = self.file_name('log', sta.lower())
        return Path(self.folder, name)

    def get_listing(self):
        return [x for x in self.folder if x.is_file()]

    def master(self):
        stype = {'intensive': '-int', 'vgos': '-vgos'}.get(self.type, '')
        return f'master{self.start.strftime("%Y")}{stype}.txt'

    # Return vgos db_name
    @property
    def db_name(self):
        if not self._db_name:
            self._db_name = f'{self.start.strftime("%Y%m%d")}-{self.code.lower()}' if int(self.year) > 2022 \
                else f'{self.start.strftime("%y%b%d")}{self.corr_db_code}'.upper()
        return self._db_name

    # Set vgos db_name
    @db_name.setter
    def db_name(self, name):
        self._db_name = name

    # Return vgosdb folder
    @property
    def db_folder(self):
        return Path(app.folder('VGOSDB_DIR'), self.year, self.db_name)


class SessionStation(Base):
    """ Relation between session and station (built from master) """

    __tablename__ = 'session_stations'

    session = Column('session', String(15), ForeignKey(Session.code, ondelete='CASCADE'), primary_key=True)
    station = Column('station', String(2), ForeignKey(Station.code, ondelete='CASCADE'), primary_key=True)
    status = Column('status', String(100), default='included')

    def __repr__(self):
        return "SesSta('%s, '%s', '%s')" % (self.session, self.station, self.status)

    def __init__(self, session, station):
        self.session = session
        self.station = station


class MailCode(Base):
    """ Class to access email_codes table in database"""

    __tablename__ = 'email_codes'

    code = Column('code', String(4), primary_key=True, unique=True)
    words = Column('words', String(100), nullable=False, server_default='')
    oper = Column('oper', String(1), nullable=False, server_default='N')
    title = Column('title', String(100), nullable=False, server_default='')
    description = Column('description', String(200), nullable=False, server_default='')

    def __str__(self):
        return '{} {}'.format(self.code, self.text);

    def __repr__(self):
        return "%s(%r)" % (self.__class__, self.__dict__)


class UploadedFile(Base):
    """ Class to store/access information on files uploaded to cddis """

    __tablename__ = 'uploaded_files'

    id = Column(Integer, autoincrement=True, primary_key=True)
    name = Column('name', String(100))
    user = Column('user', String(25))
    application = Column('application', String(25))
    status = Column('status', String(10))
    updated = Column('updated', TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))

    def __init__(self, name='N/A', user='N/A', application='N/A', status='N/A', updated=None):
        self.name, self.user, self.application, self.status = name, user, application, status
        self.updated = updated if updated else datetime.now()

    def __str__(self):
        return f'{self.name} {self.user} {self.application} {self.updated}';

    def __repr__(self):
        return f'{self.__class__} {self.__dict__}'


class AnalyzedSession(Base):
    __tablename__ = 'analyzed_sessions'

    id = Column('id', Integer, primary_key=True, autoincrement=True)
    session = Column('session', String(15), ForeignKey(Session.code, ondelete='CASCADE'))
    updated = Column('analyzed', TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    analyst = Column('analyst', String(25), nullable=False)

    def __init__(self, session, user):
        self.session, self.analyst = session, user


class MasterFile(Base):
    __tablename__ = 'master_files'

    code = Column('code', String(100), primary_key=True, unique=True)
    updated = Column('updated', DateTime, nullable=True)
