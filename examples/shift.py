import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from blindplate.issue.archive import initialize_issue_archive
from blindplate.issue.pickup import pickup_issue
from blindplate.issue.release import issue
from blindplate.plate.protocol import build_protocol
from blindplate.plate.register import initialize_rosters, register
from blindplate.reading.admission import record
from blindplate.reading.correction import correct
from blindplate.reading.freeze import freeze
from blindplate.reading.observation import InstrumentSource
from blindplate.reading.revisions import initialize_readings
from blindplate.receipt.admit import admit
from blindplate.receipt.ledger import initialize_receipts
from blindplate.review.readback import read
from blindplate.review.signing import initialize_reports, sign


PLATE, SLOTS = 'SHIFT-04', ('1', '2', '3', '4')
WEST_ENTERED = {'1': 1, '2': 0, '3': 1, '4': 0}
EAST_ENTERED = {'1': 0, '2': 0, '3': 0, '4': 1}


def _station_original(path, station, inputs, protocol):
    with closing(sqlite3.connect(path)) as db:
        initialize_rosters(db)
        initialize_readings(db)
        initialize_issue_archive(db)
        register(db, PLATE, SLOTS, protocol)
        numbers = {}
        for slot in reversed(SLOTS):
            origin = InstrumentSource(f'{station}-camera', f'work-order-04-frame-{slot}')
            numbers[slot] = record(db, PLATE, station, slot, inputs[slot], origin)
        if station == 'west':
            correct(db, numbers['2'], 1, InstrumentSource('west-camera', 'work-order-04-frame-2-checked'))
        original = issue(db, freeze(db, PLATE, station))
        return pickup_issue(db, original.issue_id)


def _result_values(report):
    return {
        'a_only': list(report.disagreements.a_only),
        'b_only': list(report.disagreements.b_only),
        'probability': [report.probability.numerator, report.probability.denominator],
    }


def _evidence_values(evidence):
    return [evidence.receipt_id, evidence.issue_id, evidence.freeze_id]


def main():
    protocol = build_protocol('west', 'spray-A', 'east', 'spray-B')
    with TemporaryDirectory(prefix='blindplate-shift-') as temporary:
        directory = Path(temporary)
        a = _station_original(directory / 'west.sqlite', 'west', WEST_ENTERED, protocol)
        b = _station_original(directory / 'east.sqlite', 'east', EAST_ENTERED, protocol)
        center_path = directory / 'center.sqlite'
        with closing(sqlite3.connect(center_path)) as center:
            initialize_receipts(center)
            initialize_reports(center)
            east = admit(center, b.payload)
            west = admit(center, a.payload)
            signed = sign(center, east.receipt_id, west.receipt_id)
        with closing(sqlite3.connect(center_path)) as center:
            initialize_receipts(center)
            initialize_reports(center)
            reopened = read(center, signed.report_id)

    expected = {'a_only': ['1', '2', '3'], 'b_only': ['4'], 'probability': [5, 16]}
    actual = _result_values(signed)
    downstream_expected = {
        'result': expected,
        'report_id': signed.report_id,
        'a': [west.receipt_id, a.issue_id, a.freeze_id],
        'b': [east.receipt_id, b.issue_id, b.freeze_id],
        'acknowledgement': f'signed:{signed.report_id}',
    }
    downstream_actual = {
        'result': _result_values(reopened),
        'report_id': reopened.report_id,
        'a': _evidence_values(reopened.a),
        'b': _evidence_values(reopened.b),
        'acknowledgement': reopened.receipt.acknowledgement,
    }
    if actual != expected or downstream_actual != downstream_expected or reopened != signed:
        raise AssertionError('the offline report or pickup differs from the work-order evidence')

    print(f'盲板 {reopened.plate_id} 的配对概率为 {reopened.probability}，已复领报告 {reopened.report_id}。')
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'v6',
        'input': {
            'plate': PLATE,
            'slots': list(SLOTS),
            'west_entered': WEST_ENTERED,
            'west_correction': {'2': 1},
            'east_entered': EAST_ENTERED,
            'receipt_request': [east.receipt_id, west.receipt_id],
        },
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': [
            'blindplate/reading/correction.py', 'blindplate/issue/release.py', 'blindplate/receipt/admit.py',
            'blindplate/receipt/select.py', 'blindplate/review/pairing.py', 'blindplate/review/tail.py',
            'blindplate/review/signing.py', 'blindplate/review/readback.py',
        ],
        'oracle': '原槽逐项比对得三比一。四个等概率方向共有十六种，恰三次有四种，四次有一种。复领出处与实收号及站件身份逐项核对。',
    }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
