import sqlite3
import os
import sys
import re
from datetime import datetime

from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import create_engine, event, exists, and_
from sqlalchemy.engine import Engine

from aps.ivsdb import models
from aps.utils import app

is_vgosDBnameOld = re.compile(r'(?P<date>\d{2}[a-zA-Z]{3}\d{2})(?P<db_code>\w{1,2})').match
is_vgosDBnameNew = re.compile(r'(?P<date>\d{8})-(?P<ses_id>\w{4,12})').match


# Needed to cascade on delete in sqlite
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(conn, record):
    if isinstance(conn, sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


# Class to handle sqlite database using sqlalchemy
# scoped_sessions is used for multithreading
class IVSdata:
    def __init__(self, url):
        self.engine, self.orm_ses = None, None
        self.url = url

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

    # Build tables using definitions in model.py file
    @staticmethod
    def build(url):
        models.Base.metadata.create_all(create_engine(url))

    # Connect to database
    def open(self):
        self.engine = create_engine(self.url)
        self.orm_ses = scoped_session(sessionmaker(bind=self.engine))

    # Close connection
    def close(self):
        try:
            self.orm_ses.close()
            self.engine.dispose()
        except (KeyError, AttributeError):
            pass

    # Turn verbose mode on
    @staticmethod
    def verbose():
        sys.stderr = sys.stdout

    # Set quiet mode
    @staticmethod
    def quiet():
        sys.stderr = open(os.devnull, 'w')

    # Flush database
    def flush(self):
        self.orm_ses.flush()

    # Refresh a record
    def refresh(self, record):
        self.orm_ses.refresh(record)

    # Commit changes
    def commit(self):
        self.orm_ses.commit()

    # Add record to database
    def add(self, record):
        self.orm_ses.add(record)

    # Delete a record
    def delete(self, record):
        if record:
            self.orm_ses.delete(record)

    # Roll back any change
    def rollback(self):
        self.orm_ses.rollback()

    # Get a record from database and create a new one if missing
    def get_or_create(self, cls, **kwargs):
        if not (obj := self.orm_ses.query(cls).filter_by(**kwargs).first()):
            obj = cls(**kwargs)
            self.orm_ses.add(obj)
        return obj
        # return self.orm_ses.query(cls).filter(**kwargs**kwargs).one()

    # Get record from database. None if not available
    def get(self, cls, **kwargs):
        return self.orm_ses.query(cls).filter_by(**kwargs).first()

    # Get record from database. None if not available
    def get_all(self, cls, **kwargs):
        return self.orm_ses.query(cls).filter_by(**kwargs).all()

    # Get a VLBI session using the session code
    def get_session(self, code, create=False):
        if create:
            return self.get_or_create(models.Session, code=code)
        return self.get(models.Session, code=code)

    # Get session code using the db_name
    def get_db_session_code(self, db_name):
        if found := is_vgosDBnameNew(db_name):
            if session := self.get_session(found['ses_id']):
                return session.code if db_name[:8] == session.start.strftime('%Y%m%d') else None
            return None
        if found := is_vgosDBnameOld(db_name):
            date = datetime.strptime(found['date'], '%y%b%d').strftime('%Y-%m-%d%%')
            return ans[0] if (ans := self.orm_ses.query(models.Session.code).filter(
                and_(models.Session.start.like(date), models.Session.corr_db_code == found['db_code'])
            ).first()) else None
        else:
            return None

    # Get list of session's codes for a specific period
    def get_sessions(self, start, end, masters):
        return [rec[0] for rec in self.orm_ses.query(models.Session.code).filter(
            and_(models.Session.start.between(start, end), models.Session.type.in_(masters))).order_by(
            models.Session.start.asc()).all()]

    # Request all sessions using a list of names
    def get_sessions_from_names(self, lst):
        return [rec[0] for rec in self.orm_ses.query(models.Session.code).filter(models.Session.name.in_(lst)).all()]

    # Request sessions using a list of code
    def get_sessions_from_ids(self, lst):
        return [rec[0] for rec in self.orm_ses.query(models.Session.code).filter(models.Session.code.in_(lst)).all()]

    # Request sessions using some numbers
    def get_sessions_from_digits(self, test):
        return [rec[0] for rec in self.orm_ses.query(models.Session.code).filter(models.Session.code.like(test)).all()]

    # Request all session for specific year
    def get_sessions_from_year(self, year, masters=['standard', 'intensive', 'vgos']):
        return self.orm_ses.query(models.Session.code, models.Session.start).filter(
            and_(models.Session.start.like(year + '%'), models.Session.type.in_(masters))).all()

    # Check if file is newer than what we have in database.
    def is_new_file(self, name, timestamp, tableId=0):
        try:
            timestamp = int(timestamp)
            cls = models.CorrFile if tableId == 1 else models.RecentFile
            return not (record := self.get(cls, code=name)) or timestamp > record.timestamp
        except Exception as err:
            print('is_new_file error', str(err))
        return True, 'Problem'  # Not sure so declare it as new

    # Update recent_file
    def update_recent_file(self, name, timestamp, tableId=0, commit=True):
        try:
            timestamp = int(float(timestamp))
            cls = models.CorrFile if tableId == 1 else models.RecentFile
            if not (record := self.get(cls, code=name)):
                record = cls(code=name)
                record.timestamp = timestamp
                self.add(record)
            elif timestamp < record.timestamp:
                return
            else:
                record.timestamp = timestamp
            if commit:
                self.commit()
        except:
            self.rollback()

    # Get recent files using regex filter and dates
    def get_recent_files(self, regex, date, tableId=0):
        cls = models.RecentFile if tableId == 0 else models.CorrFile
        return self.orm_ses.query(cls).filter(and_(cls.code.op('regexp')(regex)),(cls.timestamp >= date))\
            .order_by(cls.timestamp.desc()).all()

    # Get directory for this session
    def wd(self, param):
        try:
            if session := self.get_session(param[0]):
                sys.stdout(str(session.folder))
                return
        except:
            pass
        sys.stdout.write(param[0])

    # Get station information using its code
    def get_station(self, code):
        return self.get(models.Station, code=code)

    # Get all station codes
    def get_stations(self):
        return [info[0] for info in self.orm_ses.query(models.Station.code).all()]

    # Get station names
    def get_station_names(self):
        return [info[0] for info in self.orm_ses.query(models.Station.name).all()]

    # Get dictionary with station name as key
    def get_station_name_dict(self):
        return {rec[0]: rec[1].capitalize() for rec in self.orm_ses.query(models.Station.name, models.Station.code).all()}

    # Get SEFDs for specific period
    def get_sefds(self, start=None, end=None):
        start = start if start else '1970-01-01'
        end = end if end else datetime.utcnow().strftime('%Y-%m-%d')
        for info in self.orm_ses.query(models.SEFD.id).filter(models.SEFD.observed.between(start, end))\
                .order_by(models.SEFD.observed.asc()).all():
            yield info[0]

