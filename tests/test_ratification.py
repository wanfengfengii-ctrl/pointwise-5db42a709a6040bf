import json
import sqlite3
from contextlib import closing
from fractions import Fraction

from blindplate.issue.pack import PACK_KIND, PACK_VERSION
from blindplate.issue.pickup import pickup_correction, pickup_issue
from blindplate.issue.release import issue, issue_correction
from blindplate.reading.freeze import freeze
from blindplate.reading.observation import InstrumentSource
from blindplate.receipt.admit import admit, admit_correction
from blindplate.receipt.ledger import get_received_pack
from blindplate.review.readback import read, read_ratification
from blindplate.review.signing import ratify, sign
from tests.fixtures import (
    DatabaseCase,
    initialize_center,
    initialize_station,
    open_center,
    open_station,
    prepare,
)


PLATE = 'R-3'
SLOTS = ('1', '2')


def source(tag, slot):
    return InstrumentSource('camera', f'{tag}-slot-{slot}')


class WorkOrder:
    def __init__(self, west_values=(0, 0), east_values=(0, 0)):
        self.west_db = sqlite3.connect(':memory:')
        initialize_station(self.west_db)
        prepare(self.west_db, PLATE, 'west', west_values, slots=SLOTS)
        self.west_base = issue(self.west_db, freeze(self.west_db, PLATE, 'west'))
        self.east_db = sqlite3.connect(':memory:')
        initialize_station(self.east_db)
        prepare(self.east_db, PLATE, 'east', east_values, slots=SLOTS)
        self.east_base = issue(self.east_db, freeze(self.east_db, PLATE, 'east'))

    def close(self):
        self.west_db.close()
        self.east_db.close()


class TestStationPacks(DatabaseCase):
    def test_issue_and_pickup_packs(self):
        with closing(open_station(self.directory / 'west.sqlite')) as west:
            prepare(west, PLATE, 'west', (0, 0), slots=SLOTS)
            base = issue(west, freeze(west, PLATE, 'west'))
            p_id, p_payload = issue_correction(west, base.issue_id, {
                '1': (None, 1, source('P', '1')),
                '2': (None, 1, source('P', '2')),
            })
            self.assertEqual('pack:R-3:west:1:1', p_id)
            self.assertIsInstance(p_payload, bytes)
            self.assertEqual(p_payload, pickup_correction(west, p_id).payload)
            # 同值仍发行独立新包，且原包字节永不改变。
            p2_id, p2_payload = issue_correction(west, base.issue_id, {
                '1': (None, 1, source('P2', '1')),
            })
            self.assertNotEqual(p_id, p2_id)
            self.assertEqual('pack:R-3:west:1:2', p2_id)
            q_id, q_payload = issue_correction(west, base.issue_id, {
                '1': (p_id, 0, source('Q', '1')),
            })
            r_id, r_payload = issue_correction(west, base.issue_id, {
                '1': (p_id, 0, source('R', '1')),
            })
            self.assertNotEqual(q_id, r_id)
            self.assertEqual(q_payload, pickup_correction(west, q_id).payload)
            values = json.loads(p_payload)
            self.assertEqual(PACK_VERSION, values['version'])
            self.assertEqual(PACK_KIND, values['kind'])
            self.assertEqual(p_id, values['pack_id'])
            self.assertEqual(base.issue_id, values['base_issue']['issue_id'])
            self.assertEqual([['1', None, 1], ['2', None, 1]], values['changes'])
            # 仪器出处与私有判读号留在站库，不出现在交付字节里。
            self.assertNotIn(b'camera', p_payload)
            self.assertNotIn(b'observation_id', p_payload)
            self.assertNotIn(b'instrument', p_payload)
            stored = west.execute(
                'SELECT instrument, source_ref FROM correction_pack_slots WHERE slot = ?', ('1',),
            ).fetchone()
            self.assertEqual(('camera', 'P-slot-1'), stored)
        with closing(open_station(self.directory / 'west.sqlite')) as reopened:
            self.assertEqual(p_payload, pickup_correction(reopened, p_id).payload)
            self.assertEqual(q_payload, pickup_correction(reopened, q_id).payload)
            self.assertEqual(base.payload, pickup_issue(reopened, base.issue_id).payload)

    def test_predecessor_must_have_written_slot(self):
        with closing(open_station(self.directory / 'west.sqlite')) as west:
            prepare(west, PLATE, 'west', (0, 0), slots=SLOTS)
            base = issue(west, freeze(west, PLATE, 'west'))
            p_id, _ = issue_correction(west, base.issue_id, {'1': (None, 1, source('P', '1'))})
            self.assertEqual(1, west.execute('SELECT COUNT(*) FROM correction_packs').fetchone()[0])
            with self.assertRaises(ValueError):
                issue_correction(west, base.issue_id, {'2': (p_id, 0, source('Q', '2'))})
            with self.assertRaises(KeyError):
                issue_correction(west, base.issue_id, {'1': ('pack:R-3:west:1:99', 0, source('Q', '1'))})
            with self.assertRaises(KeyError):
                issue_correction(west, 'v1:R-3:west:99', {'1': (None, 1, source('Q', '1'))})
            with self.assertRaises(KeyError):
                pickup_correction(west, 'pack:R-3:west:1:99')
            # 失败的发行不留下任何新包。
            self.assertEqual(1, west.execute('SELECT COUNT(*) FROM correction_packs').fetchone()[0])

    def test_predecessor_pack_must_share_the_baseline(self):
        with closing(open_station(self.directory / 'west.sqlite')) as west:
            prepare(west, PLATE, 'west', (0, 0), slots=SLOTS)
            first_base = issue(west, freeze(west, PLATE, 'west'))
            old_pack, _ = issue_correction(west, first_base.issue_id, {'1': (None, 1, source('P', '1'))})
            # 重新冻结发行第二份 V1 原件（同槽图、不同冻结号）。
            second_base = issue(west, freeze(west, PLATE, 'west'))
            self.assertNotEqual(first_base.issue_id, second_base.issue_id)
            with self.assertRaises(ValueError):
                issue_correction(west, second_base.issue_id, {'1': (old_pack, 0, source('Q', '1'))})
            self.assertEqual(1, west.execute('SELECT COUNT(*) FROM correction_packs').fetchone()[0])

    def test_invalid_change_inputs(self):
        with closing(open_station(self.directory / 'west.sqlite')) as west:
            prepare(west, PLATE, 'west', (0, 0), slots=SLOTS)
            base = issue(west, freeze(west, PLATE, 'west'))
            invalid = [
                {},
                {'1': (None, 1, 'not-a-source')},
                {'1': (None, 2, source('P', '1'))},
                {'1': (None, True, source('P', '1'))},
                {'1': (None, 1.0, source('P', '1'))},
                {'9': (None, 1, source('P', '9'))},
                {'1': 'x'},
                {'1': (None, 1)},
                {'': (None, 1, source('P', ''))},
            ]
            for changes in invalid:
                with self.subTest(changes=changes):
                    with self.assertRaises(ValueError):
                        issue_correction(west, base.issue_id, changes)
            self.assertEqual((0,), west.execute('SELECT COUNT(*) FROM correction_packs').fetchone())


class TestCenterAdmission(DatabaseCase):
    def _packs(self):
        order = WorkOrder()
        self.addCleanup(order.close)
        p = issue_correction(order.west_db, order.west_base.issue_id, {
            '1': (None, 1, source('P', '1')), '2': (None, 1, source('P', '2')),
        })
        q = issue_correction(order.west_db, order.west_base.issue_id, {
            '1': (p[0], 0, source('Q', '1')),
        })
        r = issue_correction(order.west_db, order.west_base.issue_id, {
            '1': (p[0], 0, source('R', '1')),
        })
        return order, p, q, r

    def test_offline_out_of_order_admission_and_replay(self):
        order, p, q, r = self._packs()
        with closing(open_center(self.directory / 'center.sqlite')) as center:
            # 关站后按 Q、R、P 的乱序接纳，基线 V1 尚未到齐也允许。
            q_receipt = admit_correction(center, q[1])
            r_receipt = admit_correction(center, r[1])
            p_receipt = admit_correction(center, p[1])
            self.assertEqual(f'received:{q[0]}', q_receipt.acknowledgement)
            self.assertLess(q_receipt.receipt_id, r_receipt.receipt_id)
            self.assertLess(r_receipt.receipt_id, p_receipt.receipt_id)
            # 等价重投（不同键序与空白）返首执，首件字节保留。
            reformatted = json.dumps(json.loads(q[1]), indent=2).encode('utf-8')
            self.assertNotEqual(q[1], reformatted)
            self.assertEqual(q_receipt, admit_correction(center, reformatted))
            self.assertEqual(q[1], get_received_pack(center, q_receipt.receipt_id).payload)
            self.assertEqual((3,), center.execute('SELECT COUNT(*) FROM received_correction_packs').fetchone())
            # 同号异文拒收，首次记录保留。
            conflict = json.loads(p[1])
            conflict['changes'][0][2] = 0
            with self.assertRaises(ValueError):
                admit_correction(center, json.dumps(conflict).encode())
            self.assertEqual(p[1], get_received_pack(center, p_receipt.receipt_id).payload)
            self.assertEqual((3,), center.execute('SELECT COUNT(*) FROM received_correction_packs').fetchone())
        with closing(open_center(self.directory / 'center.sqlite')) as reopened:
            self.assertEqual(q_receipt, admit_correction(reopened, q[1]))

    def test_malformed_packs_rejected(self):
        _order, p, _q, _r = self._packs()
        good = json.loads(p[1])
        malformed = {
            'not bytes': 'x',
            'bad json': b'{',
            'duplicate field': p[1].replace(b'"version":1', b'"version":1,"version":1'),
            'wrong version': json.dumps({**good, 'version': 2}).encode(),
            'wrong kind': json.dumps({**good, 'kind': 'other'}).encode(),
            'missing field': json.dumps({k: v for k, v in good.items() if k != 'kind'}).encode(),
            'empty changes': json.dumps({**good, 'changes': []}).encode(),
            'bool detected': json.dumps({**good, 'changes': [['1', None, True]]}).encode(),
            'slot outside roster': json.dumps({**good, 'changes': [['9', None, 1]]}).encode(),
            'duplicate slot': json.dumps(
                {**good, 'changes': [['1', None, 0], ['1', None, 1]]}).encode(),
            'id plate mismatch': json.dumps({**good, 'pack_id': 'pack:OTHER:west:1:1'}).encode(),
            'id station mismatch': json.dumps({**good, 'pack_id': 'pack:R-3:east:1:1'}).encode(),
            'id freeze mismatch': json.dumps({**good, 'pack_id': 'pack:R-3:west:2:1'}).encode(),
            'malformed id': json.dumps({**good, 'pack_id': 'pack:R-3'}).encode(),
            'broken base': json.dumps(
                {**good, 'base_issue': {**good['base_issue'], 'station_id': 'east'}}).encode(),
        }
        with closing(open_center(self.directory / 'center.sqlite')) as center:
            for name, payload in malformed.items():
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        admit_correction(center, payload)
            self.assertEqual((0,), center.execute('SELECT COUNT(*) FROM received_correction_packs').fetchone())


class TestRatification(DatabaseCase):
    def _prepare_center(self, west_values=(0, 0), east_values=(0, 0)):
        order = WorkOrder(west_values, east_values)
        self.addCleanup(order.close)
        p = issue_correction(order.west_db, order.west_base.issue_id, {
            '1': (None, 1, source('P', '1')), '2': (None, 1, source('P', '2')),
        })
        q = issue_correction(order.west_db, order.west_base.issue_id, {
            '1': (p[0], 0, source('Q', '1')),
        })
        r = issue_correction(order.west_db, order.west_base.issue_id, {
            '1': (p[0], 0, source('R', '1')),
        })
        center = sqlite3.connect(':memory:')
        self.addCleanup(center.close)
        initialize_center(center)
        west_receipt = admit(center, order.west_base.payload)
        east_receipt = admit(center, order.east_base.payload)
        report = sign(center, west_receipt.receipt_id, east_receipt.receipt_id)
        # 关站后乱序接纳 Q、R、P。
        q_receipt = admit_correction(center, q[1])
        r_receipt = admit_correction(center, r[1])
        p_receipt = admit_correction(center, p[1])
        return order, center, report, p, q, r, p_receipt, q_receipt, r_receipt

    def test_two_slot_work_order(self):
        _order, center, report, _p, _q, _r, p_receipt, q_receipt, r_receipt = self._prepare_center()
        self.assertEqual(Fraction(1), report.probability)
        # 只选 Q 拒签，即使 P 已经实收。
        with self.assertRaises(ValueError):
            ratify(center, report.report_id, [q_receipt.receipt_id])
        # 只选 P：(1,1)，仅甲槽 1、2，概率 1/4。
        only_p = ratify(center, report.report_id, [p_receipt.receipt_id])
        self.assertEqual((('1', 1), ('2', 1)), only_p['decisions'])
        self.assertEqual(('1', '2'), only_p['a_only'])
        self.assertEqual((), only_p['b_only'])
        self.assertEqual(Fraction(1, 4), only_p['probability'])
        self.assertEqual((p_receipt.receipt_id,), only_p['pack_receipt_ids'])
        self.assertEqual(report.report_id, only_p['original_report_id'])
        self.assertEqual('west', only_p['station_id'])
        self.assertEqual(f'ratified:{only_p["report_id"]}', only_p['acknowledgement'])
        # P+Q 与 P+R 均得 (0,1)，仅甲槽 2，概率 1/2，且各自记录实收号。
        pq = ratify(center, report.report_id, [p_receipt.receipt_id, q_receipt.receipt_id])
        pr = ratify(center, report.report_id, [r_receipt.receipt_id, p_receipt.receipt_id])
        for result, expected_receipts in (
            (pq, (p_receipt.receipt_id, q_receipt.receipt_id)),
            (pr, (p_receipt.receipt_id, r_receipt.receipt_id)),
        ):
            self.assertEqual((('1', 0), ('2', 1)), result['decisions'])
            self.assertEqual(('2',), result['a_only'])
            self.assertEqual((), result['b_only'])
            self.assertEqual(Fraction(1, 2), result['probability'])
            self.assertEqual(tuple(sorted(expected_receipts)), result['pack_receipt_ids'])
        # 列表顺序不影响结果。
        reversed_pq = ratify(center, report.report_id, [q_receipt.receipt_id, p_receipt.receipt_id])
        self.assertEqual(pq['decisions'], reversed_pq['decisions'])
        self.assertEqual(pq['pack_receipt_ids'], reversed_pq['pack_receipt_ids'])
        # 三包同选拒签，报告与回执均无新增。
        before = self._ratification_counts(center)
        with self.assertRaises(ValueError):
            ratify(center, report.report_id,
                   [p_receipt.receipt_id, q_receipt.receipt_id, r_receipt.receipt_id])
        self.assertEqual(before, self._ratification_counts(center))
        # 原报告保持不变。
        self.assertEqual(report, read(center, report.report_id))

    def test_same_value_does_not_clear_predecessor_conflict(self):
        _order, center, report, _p, _q, _r, p_receipt, q_receipt, r_receipt = self._prepare_center()
        # Q、R 同值但共同消耗 P 在槽 1 的同一前身。
        with self.assertRaises(ValueError):
            ratify(center, report.report_id,
                   [p_receipt.receipt_id, q_receipt.receipt_id, r_receipt.receipt_id])
        self.assertEqual((0, 0), self._ratification_counts(center))

    def test_unselected_received_pack_has_no_authority(self):
        _order, center, report, _p, _q, _r, p_receipt, q_receipt, _r_receipt = self._prepare_center()
        # P 已实收但未选，Q 的前置缺失 -> 拒签。
        with self.assertRaises(ValueError):
            ratify(center, report.report_id, [q_receipt.receipt_id])
        # 已选集合互不相同。
        with self.assertRaises(ValueError):
            ratify(center, report.report_id, [p_receipt.receipt_id, p_receipt.receipt_id])
        for bad in ([], (), 'x', 7):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    ratify(center, report.report_id, bad)

    def test_unknown_identifiers_raise_key_error(self):
        _order, center, report, _p, _q, _r, p_receipt, _q_receipt, _r_receipt = self._prepare_center()
        with self.assertRaises(KeyError):
            ratify(center, report.report_id, [9999])
        with self.assertRaises(KeyError):
            ratify(center, 9999, [p_receipt.receipt_id])
        with self.assertRaises(KeyError):
            read_ratification(center, 9999)

    def test_pack_bound_to_other_original_rejected(self):
        order = WorkOrder()
        self.addCleanup(order.close)
        # 另冻发一份甲站 (0,0)，新原件号不同。
        second_freeze = freeze(order.west_db, PLATE, 'west')
        second_original = issue(order.west_db, second_freeze)
        self.assertNotEqual(order.west_base.issue_id, second_original.issue_id)
        pack = issue_correction(order.west_db, order.west_base.issue_id, {
            '1': (None, 1, source('P', '1')),
        })
        center = sqlite3.connect(':memory:')
        self.addCleanup(center.close)
        initialize_center(center)
        west_receipt = admit(center, order.west_base.payload)
        second_receipt = admit(center, second_original.payload)
        east_receipt = admit(center, order.east_base.payload)
        old_report = sign(center, west_receipt.receipt_id, east_receipt.receipt_id)
        new_report = sign(center, second_receipt.receipt_id, east_receipt.receipt_id)
        pack_receipt = admit_correction(center, pack[1])
        # 绑定旧原件的包不能在使用新原件的报告上追认。
        with self.assertRaises(ValueError):
            ratify(center, new_report.report_id, [pack_receipt.receipt_id])
        # 同一包在旧报告上合法。
        result = ratify(center, old_report.report_id, [pack_receipt.receipt_id])
        self.assertEqual((('1', 1), ('2', 0)), result['decisions'])

    def test_role_b_station_ratification_keeps_protocol_direction(self):
        # 乙站基线 (1,0)，把槽 1 勘误为 0；甲站保持 (1,0)，分歧朝向甲。
        order = WorkOrder(west_values=(1, 0), east_values=(1, 0))
        self.addCleanup(order.close)
        pack = issue_correction(order.east_db, order.east_base.issue_id, {
            '1': (None, 0, source('P', '1')),
        })
        center = sqlite3.connect(':memory:')
        self.addCleanup(center.close)
        initialize_center(center)
        west_receipt = admit(center, order.west_base.payload)
        east_receipt = admit(center, order.east_base.payload)
        report = sign(center, west_receipt.receipt_id, east_receipt.receipt_id)
        pack_receipt = admit_correction(center, pack[1])
        result = ratify(center, report.report_id, [pack_receipt.receipt_id])
        self.assertEqual('east', result['station_id'])
        self.assertEqual((('1', 0), ('2', 0)), result['decisions'])
        self.assertEqual(('1',), result['a_only'])
        self.assertEqual((), result['b_only'])
        self.assertEqual(Fraction(1, 2), result['probability'])

    def test_cross_station_packs_rejected(self):
        order = WorkOrder()
        self.addCleanup(order.close)
        west_pack = issue_correction(order.west_db, order.west_base.issue_id, {
            '1': (None, 1, source('P', '1')),
        })
        east_pack = issue_correction(order.east_db, order.east_base.issue_id, {
            '2': (None, 1, source('P', '2')),
        })
        center = sqlite3.connect(':memory:')
        self.addCleanup(center.close)
        initialize_center(center)
        west_receipt = admit(center, order.west_base.payload)
        east_receipt = admit(center, order.east_base.payload)
        report = sign(center, west_receipt.receipt_id, east_receipt.receipt_id)
        west_pack_receipt = admit_correction(center, west_pack[1])
        east_pack_receipt = admit_correction(center, east_pack[1])
        with self.assertRaises(ValueError):
            ratify(center, report.report_id,
                   [west_pack_receipt.receipt_id, east_pack_receipt.receipt_id])
        self.assertEqual((0, 0), self._ratification_counts(center))

    def test_readback_and_reopen(self):
        center_path = self.directory / 'center.sqlite'
        order = WorkOrder()
        self.addCleanup(order.close)
        pack = issue_correction(order.west_db, order.west_base.issue_id, {
            '1': (None, 1, source('P', '1')), '2': (None, 1, source('P', '2')),
        })
        follow = issue_correction(order.west_db, order.west_base.issue_id, {
            '1': (pack[0], 0, source('Q', '1')),
        })
        with closing(open_center(center_path)) as center:
            west_receipt = admit(center, order.west_base.payload)
            east_receipt = admit(center, order.east_base.payload)
            signed = sign(center, west_receipt.receipt_id, east_receipt.receipt_id)
            p_receipt = admit_correction(center, pack[1])
            q_receipt = admit_correction(center, follow[1])
            saved = ratify(center, signed.report_id, [p_receipt.receipt_id, q_receipt.receipt_id])
        with closing(open_center(center_path)) as reopened:
            self.assertEqual(saved, read_ratification(reopened, saved['report_id']))
            self.assertEqual(signed, read(reopened, signed.report_id))
            # 后续追认不影响先前结果。
            again = ratify(reopened, signed.report_id, [p_receipt.receipt_id])
            self.assertEqual(saved, read_ratification(reopened, saved['report_id']))
            self.assertNotEqual(saved['report_id'], again['report_id'])

    def test_atomic_failure_keeps_old_records_and_allows_retry(self):
        center_path = self.directory / 'center.sqlite'
        order = WorkOrder()
        self.addCleanup(order.close)
        pack = issue_correction(order.west_db, order.west_base.issue_id, {
            '2': (None, 1, source('P', '2')),
        })
        with closing(open_center(center_path)) as center:
            west_receipt = admit(center, order.west_base.payload)
            east_receipt = admit(center, order.east_base.payload)
            signed = sign(center, west_receipt.receipt_id, east_receipt.receipt_id)
            pack_receipt = admit_correction(center, pack[1])
            center.execute('''
                CREATE TRIGGER block_ratification BEFORE INSERT ON ratification_receipts
                WHEN EXISTS (SELECT 1 FROM ratification_reports WHERE report_id = NEW.report_id)
                BEGIN SELECT RAISE(ABORT, 'ratification receipt blocked'); END
            ''')
            center.commit()
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'ratification receipt blocked'):
                ratify(center, signed.report_id, [pack_receipt.receipt_id])
            center.execute('DROP TRIGGER block_ratification')
            center.commit()
        with closing(sqlite3.connect(center_path)) as observer:
            self.assertEqual((0, 0), (
                observer.execute('SELECT COUNT(*) FROM ratification_reports').fetchone()[0],
                observer.execute('SELECT COUNT(*) FROM ratification_receipts').fetchone()[0],
            ))
        with closing(open_center(center_path)) as retry:
            result = ratify(retry, signed.report_id, [pack_receipt.receipt_id])
            self.assertEqual((('1', 0), ('2', 1)), result['decisions'])
            self.assertEqual(Fraction(1, 2), result['probability'])
        with closing(open_center(center_path)) as reopened:
            self.assertEqual(result, read_ratification(reopened, result['report_id']))

    @staticmethod
    def _ratification_counts(db):
        return (
            db.execute('SELECT COUNT(*) FROM ratification_reports').fetchone()[0],
            db.execute('SELECT COUNT(*) FROM ratification_receipts').fetchone()[0],
        )
