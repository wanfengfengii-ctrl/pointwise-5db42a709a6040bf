import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from blindplate.issue.archive import initialize_issue_archive
from blindplate.issue.release import issue
from blindplate.plate.protocol import build_protocol
from blindplate.plate.register import initialize_rosters, register
from blindplate.reading.admission import record
from blindplate.reading.freeze import freeze
from blindplate.reading.observation import InstrumentSource
from blindplate.reading.revisions import initialize_readings
from blindplate.receipt.ledger import initialize_receipts
from blindplate.review.signing import initialize_reports


SLOTS = ('1', '2', '3', '4')
PROTOCOL = build_protocol('west', 'spray-A', 'east', 'spray-B')
LEGACY = Path(__file__).resolve().parents[1] / 'examples' / 'legacy'


def initialize_station(db):
    initialize_rosters(db)
    initialize_readings(db)
    initialize_issue_archive(db)


def initialize_center(db):
    initialize_receipts(db)
    initialize_reports(db)


def open_station(path):
    connection = sqlite3.connect(path)
    try:
        initialize_station(connection)
    except BaseException:
        connection.close()
        raise
    return connection


def open_center(path):
    connection = sqlite3.connect(path)
    try:
        initialize_center(connection)
    except BaseException:
        connection.close()
        raise
    return connection


def source(station, slot):
    return InstrumentSource(f'local-instrument-{station}', f'private-trace-{station}-{slot}')


def prepare(db, plate, station, values, *, slots=SLOTS, protocol=PROTOCOL):
    register(db, plate, slots, protocol)
    return {
        slot: record(db, plate, station, slot, detected, source(station, slot))
        for slot, detected in reversed(list(zip(slots, values, strict=True)))
    }


def make_original(path, plate, station, values, *, slots=SLOTS, protocol=PROTOCOL):
    with closing(open_station(path)) as db:
        prepare(db, plate, station, values, slots=slots, protocol=protocol)
        return issue(db, freeze(db, plate, station))


def restore_legacy(path, file_name):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript((LEGACY / file_name).read_text(encoding='utf-8'))


def report_counts(db):
    return db.execute('''
        SELECT (SELECT COUNT(*) FROM reports), (SELECT COUNT(*) FROM report_receipts)
    ''').fetchone()


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='blindplate-test-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
