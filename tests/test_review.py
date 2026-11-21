import sqlite3
from contextlib import closing
from fractions import Fraction

from blindplate.issue.release import issue
from blindplate.plate.protocol import build_protocol
from blindplate.reading.correction import correct
from blindplate.reading.freeze import freeze
from blindplate.reading.observation import InstrumentSource
from blindplate.receipt.admit import admit
from blindplate.receipt.ledger import get_received_issue
from blindplate.review.pairing import Disagreements
from blindplate.review.readback import read
from blindplate.review.report import ReportEvidence, ReportReceipt
from blindplate.review.signing import sign
from tests.fixtures import (
    DatabaseCase, LEGACY, initialize_center, make_original, open_center, open_station, prepare,
    report_counts, restore_legacy,
)


class TestReview(DatabaseCase):
    def assert_four_slot_report(self, report, plate, west, east, west_original, east_original):
        self.assertEqual(plate, report.plate_id)
        self.assertEqual(Disagreements(('1', '2', '3'), ('4',)), report.disagreements)
        self.assertEqual(Fraction(5, 16), report.probability)
        self.assertEqual(ReportEvidence(west.receipt_id, west_original.issue_id, west_original.freeze_id), report.a)
        self.assertEqual(ReportEvidence(east.receipt_id, east_original.issue_id, east_original.freeze_id), report.b)
        self.assertEqual(ReportReceipt(report.report_id, f'signed:{report.report_id}'), report.receipt)

    def test_exact_tail_and_readback(self):
        originals = {
            'west': make_original(self.directory / 'west.sqlite', 'P-6', 'west', (1, 1, 1, 0)),
            'east': make_original(self.directory / 'east.sqlite', 'P-6', 'east', (0, 0, 0, 1)),
        }
        for arrival in (('west', 'east'), ('east', 'west')):
            with self.subTest(arrival=arrival):
                center_path = self.directory / f'arrives-{arrival[0]}-first.sqlite'
                with closing(open_center(center_path)) as db:
                    receipts = {station: admit(db, originals[station].payload) for station in arrival}
                    west, east = receipts['west'], receipts['east']
                    self.assertLess(receipts[arrival[0]].receipt_id, receipts[arrival[1]].receipt_id)
                    reports = [sign(db, west.receipt_id, east.receipt_id), sign(db, east.receipt_id, west.receipt_id)]
                    self.assertEqual((2, 2), report_counts(db))
                with closing(open_center(center_path)) as reopened:
                    for report in reports:
                        self.assert_four_slot_report(report, 'P-6', west, east, originals['west'], originals['east'])
                        self.assertEqual(report, read(reopened, report.report_id))
                    with self.assertRaises(KeyError):
                        read(reopened, 9000)

    def test_tail_boundaries(self):
        with closing(open_center(self.directory / 'center.sqlite')) as center:
            for plate, west, east, expected, disagreements in (
                ('A-ONLY', (1, 1, 1, 0), (0, 1, 0, 0), Fraction(1, 4), Disagreements(('3', '1'), ())),
                ('B-ONLY', (0, 1, 0, 0), (1, 1, 1, 0), Fraction(1), Disagreements((), ('3', '1'))),
            ):
                slots = ('3', '2', '1', '4')
                a = make_original(self.directory / f'{plate}-west.sqlite', plate, 'west', west, slots=slots)
                b = make_original(self.directory / f'{plate}-east.sqlite', plate, 'east', east, slots=slots)
                west_receipt = admit(center, a.payload)
                east_receipt = admit(center, b.payload)
                report = sign(center, east_receipt.receipt_id, west_receipt.receipt_id)
                self.assertEqual(expected, report.probability)
                self.assertEqual(disagreements, report.disagreements)
                self.assertEqual(report, read(center, report.report_id))

    def test_pinned_history(self):
        path = self.directory / 'center.sqlite'
        east_path = self.directory / 'east.sqlite'
        west_original = make_original(self.directory / 'west.sqlite', 'PIN', 'west', (1, 1, 1, 0))
        with closing(open_station(east_path)) as east_source:
            previous = prepare(east_source, 'PIN', 'east', (0, 0, 0, 1))
            east_original = issue(east_source, freeze(east_source, 'PIN', 'east'))
        with closing(open_center(path)) as center:
            east = admit(center, east_original.payload)
            west = admit(center, west_original.payload)
            original = sign(center, east.receipt_id, west.receipt_id)
            self.assert_four_slot_report(original, 'PIN', west, east, west_original, east_original)
        with closing(open_station(east_path)) as east_source:
            correct(east_source, previous['1'], 1, InstrumentSource('east-check', 'confirmed-1'))
            updated_original = issue(east_source, freeze(east_source, 'PIN', 'east'))
        with closing(open_center(path)) as center:
            updated_east = admit(center, updated_original.payload)
        with closing(open_center(path)) as reopened:
            self.assertEqual(original, read(reopened, original.report_id))
            repeated = sign(reopened, west.receipt_id, east.receipt_id)
            self.assert_four_slot_report(repeated, 'PIN', west, east, west_original, east_original)
            updated = sign(reopened, west.receipt_id, updated_east.receipt_id)
            self.assertEqual(Fraction(1, 2), updated.probability)
            self.assertEqual(ReportEvidence(updated_east.receipt_id, updated_original.issue_id,
                                            updated_original.freeze_id), updated.b)
            self.assertEqual(original, read(reopened, original.report_id))

    def test_legacy_readback(self):
        path = self.directory / 'old-center.sqlite'
        restore_legacy(path, 'center.sql')
        with closing(open_center(path)) as center:
            initialize_center(center)
            original = read(center, 17)
            self.assertEqual('LEG-04', original.plate_id)
            self.assertEqual(Fraction(5, 16), original.probability)
            self.assertEqual(Disagreements(('1', '2', '3'), ('4',)), original.disagreements)
            self.assertEqual(ReportEvidence(12, 'v1:LEG-04:west:7', 7), original.a)
            self.assertEqual(ReportEvidence(11, 'v1:LEG-04:east:9', 9), original.b)
            self.assertEqual(ReportReceipt(17, 'signed:17'), original.receipt)
            for receipt_id, station in ((12, 'west'), (11, 'east')):
                wire = (LEGACY / f'{station}-v1.json').read_bytes()
                received = get_received_issue(center, receipt_id)
                self.assertEqual(wire, received.payload)
                self.assertEqual(received.first_receipt, admit(center, wire))
            new = sign(center, 11, 12)
            self.assertGreater(new.report_id, original.report_id)
            self.assertEqual((original.probability, original.a, original.b, original.disagreements),
                             (new.probability, new.a, new.b, new.disagreements))
        with closing(open_center(path)) as reopened:
            self.assertEqual(original, read(reopened, 17))
            self.assertEqual(new, read(reopened, new.report_id))

    def test_reject_cross_board(self):
        with closing(open_station(self.directory / 'west.sqlite')) as station:
            ids = prepare(station, 'P-7', 'west', (1, 1, 1, 0))
            west = issue(station, freeze(station, 'P-7', 'west'))
            correct(station, ids['1'], 0, InstrumentSource('local-check', 'enter-correction'))
            same_station = issue(station, freeze(station, 'P-7', 'west'))
        other_plate = make_original(self.directory / 'other.sqlite', 'OTHER', 'east', (0, 0, 0, 1))
        changed_roster = make_original(
            self.directory / 'changed.sqlite', 'P-7', 'east', (0, 0, 0, 1),
            protocol=build_protocol('west', 'spray-A', 'east', 'different-scheme'),
        )
        with closing(open_center(self.directory / 'center.sqlite')) as center:
            real_west = admit(center, west.payload)
            for unpaired in (other_plate, same_station, changed_roster):
                foreign = admit(center, unpaired.payload)
                with self.subTest(issue=unpaired.issue_id):
                    with self.assertRaises(ValueError):
                        sign(center, real_west.receipt_id, foreign.receipt_id)
                    self.assertEqual((0, 0), report_counts(center))
            with self.assertRaises(KeyError):
                sign(center, real_west.receipt_id, 9000)
            self.assertEqual((0, 0), report_counts(center))

    def test_atomic_retry_and_zero_disagreement(self):
        for plate, west_values, east_values in (
            ('ZERO', (1, 0, 1, 0), (1, 0, 1, 0)),
            ('FOUR', (1, 1, 1, 0), (0, 0, 0, 1)),
        ):
            with self.subTest(plate=plate):
                self._assert_receipt_failure_and_retry(plate, west_values, east_values)

    def _assert_receipt_failure_and_retry(self, plate, west_values, east_values):
        a = make_original(self.directory / f'{plate}-west.sqlite', plate, 'west', west_values)
        b = make_original(self.directory / f'{plate}-east.sqlite', plate, 'east', east_values)
        center_path = self.directory / f'{plate}-center.sqlite'
        with closing(open_center(center_path)) as center:
            east = admit(center, b.payload)
            west = admit(center, a.payload)
            if plate == 'FOUR':
                foreign_original = make_original(self.directory / 'foreign.sqlite', 'FOREIGN', 'east', east_values)
                foreign = admit(center, foreign_original.payload)
                with self.assertRaises(ValueError):
                    sign(center, foreign.receipt_id, west.receipt_id)
                self.assertEqual((0, 0), report_counts(center))
            center.execute('''
                CREATE TRIGGER fail_report_receipt BEFORE INSERT ON report_receipts
                WHEN EXISTS (SELECT 1 FROM reports WHERE report_id = NEW.report_id)
                BEGIN SELECT RAISE(ABORT, 'receipt write blocked'); END
            ''')
            center.commit()
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt write blocked'):
                sign(center, east.receipt_id, west.receipt_id)
            with closing(sqlite3.connect(center_path)) as observer:
                self.assertEqual((0, 0), report_counts(observer))
            center.execute('DROP TRIGGER fail_report_receipt')
            center.commit()
        with closing(open_center(center_path)) as retry:
            result = sign(retry, east.receipt_id, west.receipt_id)
            self.assertEqual((1, 1), report_counts(retry))
            if plate == 'ZERO':
                self.assertEqual(Fraction(1), result.probability)
                self.assertEqual(Disagreements((), ()), result.disagreements)
                self.assertEqual(ReportEvidence(west.receipt_id, a.issue_id, a.freeze_id), result.a)
                self.assertEqual(ReportEvidence(east.receipt_id, b.issue_id, b.freeze_id), result.b)
            else:
                self.assert_four_slot_report(result, plate, west, east, a, b)
        with closing(open_center(center_path)) as reopened:
            self.assertEqual(result, read(reopened, result.report_id))
            self.assertEqual((1, 1), report_counts(reopened))
