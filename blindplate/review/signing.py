import sqlite3

from blindplate.receipt.ledger import ReceivedIssue
from blindplate.receipt.select import select_pair
from blindplate.review.pairing import pair_by_slot
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
