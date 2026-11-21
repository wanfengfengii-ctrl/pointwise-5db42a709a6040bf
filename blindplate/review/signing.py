import json
import sqlite3

from blindplate.receipt.ledger import ReceivedIssue
from blindplate.receipt.select import select_pair
from blindplate.review.pairing import pair_by_slot
from blindplate.review.ratification import plan_ratification
from blindplate.review.report import PairedReport, ReportEvidence, decode_report, encode_report
from blindplate.review.tail import exact_upper_tail


def initialize_reports(db: sqlite3.Connection) -> None:
    db.executescript('''
        CREATE TABLE IF NOT EXISTS reports (
            report_id INTEGER PRIMARY KEY,
            body TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS report_receipts (
            report_id INTEGER PRIMARY KEY REFERENCES reports(report_id),
            acknowledgement TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS ratification_reports (
            report_id INTEGER PRIMARY KEY,
            body TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ratification_receipts (
            report_id INTEGER PRIMARY KEY REFERENCES ratification_reports(report_id),
            acknowledgement TEXT NOT NULL UNIQUE
        );
    ''')


def _evidence(received: ReceivedIssue) -> ReportEvidence:
    return ReportEvidence(
        received.first_receipt.receipt_id, received.document.issue_id, received.document.freeze_id,
    )


def sign(db: sqlite3.Connection, first_receipt_id: int, second_receipt_id: int) -> PairedReport:
    db.execute('BEGIN IMMEDIATE')
    with db:
        pair = select_pair(db, first_receipt_id, second_receipt_id)
        disagreements = pair_by_slot(pair)
        probability = exact_upper_tail(len(disagreements.a_only), len(disagreements.b_only))
        body = encode_report(
            pair.a.document.roster.plate_id, _evidence(pair.a), _evidence(pair.b), disagreements, probability,
        )
        report_id = db.execute('INSERT INTO reports (body) VALUES (?)', (body,)).lastrowid
        acknowledgement = f'signed:{report_id}'
        db.execute(
            'INSERT INTO report_receipts (report_id, acknowledgement) VALUES (?, ?)',
            (report_id, acknowledgement),
        )
        return decode_report(report_id, body, acknowledgement)


def encode_ratification(original_report_id: int, plan, pack_receipt_ids: tuple[int, ...]) -> str:
    values = {
        'original_report_id': original_report_id,
        'station_id': plan.station_id,
        'base_issue_id': plan.base_issue_id,
        'pack_receipt_ids': list(pack_receipt_ids),
        'decisions': [[slot, detected] for slot, detected in plan.decisions],
        'a_only': list(plan.a_only),
        'b_only': list(plan.b_only),
        'probability': [plan.probability.numerator, plan.probability.denominator],
    }
    return json.dumps(values, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def decode_ratification(report_id: int, body: str, acknowledgement: str) -> dict:
    from fractions import Fraction

    values = json.loads(body)
    return {
        'report_id': report_id,
        'original_report_id': values['original_report_id'],
        'station_id': values['station_id'],
        'pack_receipt_ids': tuple(values['pack_receipt_ids']),
        'decisions': tuple((slot, detected) for slot, detected in values['decisions']),
        'a_only': tuple(values['a_only']),
        'b_only': tuple(values['b_only']),
        'probability': Fraction(*values['probability']),
        'acknowledgement': acknowledgement,
    }


def ratify(db: sqlite3.Connection, report_id: int, pack_receipt_ids) -> dict:
    from blindplate.plate.identity import validate_number
    from blindplate.review.readback import read

    report_id = validate_number(report_id, 'report ID')
    db.execute('BEGIN IMMEDIATE')
    with db:
        original = read(db, report_id)
        plan = plan_ratification(db, original, pack_receipt_ids)
        ordered_ids = tuple(sorted(set(pack_receipt_ids)))
        body = encode_ratification(report_id, plan, ordered_ids)
        new_report_id = db.execute(
            'INSERT INTO ratification_reports (body) VALUES (?)', (body,)
        ).lastrowid
        acknowledgement = f'ratified:{new_report_id}'
        db.execute(
            'INSERT INTO ratification_receipts (report_id, acknowledgement) VALUES (?, ?)',
            (new_report_id, acknowledgement),
        )
        return decode_ratification(new_report_id, body, acknowledgement)
