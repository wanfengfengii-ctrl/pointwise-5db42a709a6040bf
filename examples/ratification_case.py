"""关站后的勘误整包追认演示（R-3 两槽工单）。

站端发行 V1 基线站件与 P/Q/R 三个勘误整包后关闭站库；中心离线、乱序收包，
按工单尝试不同选包组合，展示拒签、(1,1) 与 (0,1) 复算、同号异文拒收以及
重开后按报告号复领。任一核验失败以非零码退出。
"""
import json
import sqlite3
from contextlib import closing
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from blindplate.issue.pickup import pickup_correction
from blindplate.issue.release import issue, issue_correction
from blindplate.plate.protocol import build_protocol
from blindplate.plate.register import initialize_rosters, register
from blindplate.reading.admission import record
from blindplate.reading.freeze import freeze
from blindplate.reading.observation import InstrumentSource
from blindplate.reading.revisions import initialize_readings
from blindplate.issue.archive import initialize_issue_archive
from blindplate.receipt.admit import admit, admit_correction
from blindplate.receipt.ledger import initialize_receipts
from blindplate.review.readback import read, read_ratification
from blindplate.review.signing import initialize_reports, ratify, sign


PLATE = 'R-3'
SLOTS = ('1', '2')
PROTOCOL = build_protocol('west', 'spray-A', 'east', 'spray-B')


def _open_station(path):
    db = sqlite3.connect(path)
    initialize_rosters(db)
    initialize_readings(db)
    initialize_issue_archive(db)
    return db


def _baseline(path, station):
    with closing(_open_station(path)) as db:
        register(db, PLATE, SLOTS, PROTOCOL)
        for slot in reversed(SLOTS):
            record(db, PLATE, station, slot, 0, InstrumentSource('camera', f'baseline-{station}-{slot}'))
        return issue(db, freeze(db, PLATE, station))


def _issue_work_order_packs(station_path, base_issue_id):
    with closing(_open_station(station_path)) as db:
        def src(tag, slot):
            return InstrumentSource('camera', f'{tag}-slot-{slot}')

        pack_p, payload_p = issue_correction(db, base_issue_id, {
            '1': (None, 1, src('P', '1')),
            '2': (None, 1, src('P', '2')),
        })
        pack_q, payload_q = issue_correction(db, base_issue_id, {
            '1': (pack_p, 0, src('Q', '1')),
        })
        pack_r, payload_r = issue_correction(db, base_issue_id, {
            '1': (pack_p, 0, src('R', '1')),
        })
        # 按包号复领原字节，仪器出处仅留在站库。
        assert pickup_correction(db, pack_q).payload == payload_q
        return (
            (pack_p, payload_p),
            (pack_q, payload_q),
            (pack_r, payload_r),
        )


def _expect_reject(center, report_id, receipt_ids, label):
    before = center.execute('SELECT COUNT(*) FROM ratification_reports').fetchone()[0]
    try:
        ratify(center, report_id, receipt_ids)
    except ValueError as error:
        after = center.execute('SELECT COUNT(*) FROM ratification_reports').fetchone()[0]
        assert before == after, f'{label}: 拒签不得新增报告'
        print(f'  拒签 {label}: {error}')
        return
    raise AssertionError(f'{label} 应当拒签')


def main():
    with TemporaryDirectory(prefix='blindplate-ratification-') as temporary:
        directory = Path(temporary)
        west_path = directory / 'west.sqlite'
        east_path = directory / 'east.sqlite'
        center_path = directory / 'center.sqlite'

        west_original = _baseline(west_path, 'west')
        east_original = _baseline(east_path, 'east')
        packs = _issue_work_order_packs(west_path, west_original.issue_id)
        (pack_p, payload_p), (pack_q, payload_q), (pack_r, payload_r) = packs
        print(f'站端发行基线 {west_original.issue_id} 与勘误包 {pack_p}、{pack_q}、{pack_r}，站库关闭。')

        with closing(sqlite3.connect(center_path)) as center:
            initialize_receipts(center)
            initialize_reports(center)
            west_receipt = admit(center, west_original.payload)
            east_receipt = admit(center, east_original.payload)
            original = sign(center, west_receipt.receipt_id, east_receipt.receipt_id)
            assert original.probability == Fraction(1)
            print(f'原 V1 报告 {original.report_id} 已签，两站基线均为 (0,0)，概率 {original.probability}。')

            # 离线乱序收包：Q、R、P。
            q_receipt = admit_correction(center, payload_q)
            r_receipt = admit_correction(center, payload_r)
            p_receipt = admit_correction(center, payload_p)
            print('乱序实收包号:', {
                'Q': q_receipt.receipt_id, 'R': r_receipt.receipt_id, 'P': p_receipt.receipt_id,
            })
            # 等价重投返首执；同号异文拒收。
            reformatted = json.dumps(json.loads(payload_q), indent=2).encode('utf-8')
            assert admit_correction(center, reformatted) == q_receipt
            conflict = json.loads(payload_p)
            conflict['changes'][0][2] = 0
            try:
                admit_correction(center, json.dumps(conflict).encode())
                raise AssertionError('同号异文必须拒收')
            except ValueError as error:
                print(f'  同号异文拒收: {error}')

            print('选包签报:')
            _expect_reject(center, original.report_id, [q_receipt.receipt_id], '只选 Q（缺前置 P）')
            only_p = ratify(center, original.report_id, [p_receipt.receipt_id])
            assert only_p['decisions'] == (('1', 1), ('2', 1))
            assert only_p['a_only'] == ('1', '2') and only_p['b_only'] == ()
            assert only_p['probability'] == Fraction(1, 4)
            print(f"  只选 P -> 报告 {only_p['report_id']} 槽图 {only_p['decisions']}，"
                  f"仅甲槽 {only_p['a_only']}，概率 {only_p['probability']}")

            pq = ratify(center, original.report_id, [p_receipt.receipt_id, q_receipt.receipt_id])
            pr = ratify(center, original.report_id, [r_receipt.receipt_id, p_receipt.receipt_id])
            for result, chosen in ((pq, 'P+Q'), (pr, 'P+R')):
                assert result['decisions'] == (('1', 0), ('2', 1))
                assert result['a_only'] == ('2',) and result['b_only'] == ()
                assert result['probability'] == Fraction(1, 2)
                print(f"  选 {chosen} -> 报告 {result['report_id']} 槽图 {result['decisions']}，"
                      f"仅甲槽 {result['a_only']}，概率 {result['probability']}，"
                      f"实收号 {result['pack_receipt_ids']}，回执 {result['acknowledgement']}")
            assert pq['pack_receipt_ids'] != pr['pack_receipt_ids']
            # 收包与选包顺序无关：反序入参给出相同业务值。
            pq_reversed = ratify(center, original.report_id, [q_receipt.receipt_id, p_receipt.receipt_id])
            assert (pq_reversed['decisions'], pq_reversed['probability']) == (pq['decisions'], pq['probability'])

            _expect_reject(
                center, original.report_id,
                [p_receipt.receipt_id, q_receipt.receipt_id, r_receipt.receipt_id],
                'P+Q+R（Q、R 共耗 P 的槽 1 前身，同值亦然）',
            )
            assert read(center, original.report_id) == original

        # 中心重开，按号复领原报告与各追认报告，后续到件不影响既有结果。
        with closing(sqlite3.connect(center_path)) as reopened:
            initialize_receipts(reopened)
            initialize_reports(reopened)
            assert read(reopened, original.report_id) == original
            for saved in (only_p, pq, pr):
                assert read_ratification(reopened, saved['report_id']) == saved
            print(f'重开中心复领：原报告 {original.report_id} 与追认报告 '
                  f"{only_p['report_id']}、{pq['report_id']}、{pr['report_id']} 存值一致。")

    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'ratification-r3',
        'plate': PLATE,
        'slots': list(SLOTS),
        'baseline': [0, 0],
        'packs': {'P': pack_p, 'Q': pack_q, 'R': pack_r},
        'outcomes': {
            'Q_only': 'rejected',
            'P_only': {'decisions': [['1', 1], ['2', 1]], 'probability': '1/4'},
            'P_Q': {'decisions': [['1', 0], ['2', 1]], 'probability': '1/2'},
            'P_R': {'decisions': [['1', 0], ['2', 1]], 'probability': '1/2'},
            'P_Q_R': 'rejected',
        },
    }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
