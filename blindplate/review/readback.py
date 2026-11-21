import sqlite3

from blindplate.plate.identity import validate_number
from blindplate.review.report import PairedReport, decode_report
from blindplate.review.signing import decode_ratification


def read(db: sqlite3.Connection, report_id: int) -> PairedReport:
    report_id = validate_number(report_id, 'report ID')
    row = db.execute(
        '''SELECT reports.body, report_receipts.acknowledgement
           FROM reports JOIN report_receipts USING (report_id)
           WHERE report_id = ?''',
        (report_id,),
    ).fetchone()
    if row is None:
        raise KeyError(report_id)
    return decode_report(report_id, row[0], row[1])


def read_ratification(db: sqlite3.Connection, ratification_id: int) -> dict:
    ratification_id = validate_number(ratification_id, 'ratification ID')
    row = db.execute(
        '''SELECT ratification_reports.body, ratification_receipts.acknowledgement
           FROM ratification_reports
           JOIN ratification_receipts USING (report_id)
           WHERE report_id = ?''',
        (ratification_id,),
    ).fetchone()
    if row is None:
        raise KeyError(ratification_id)
    return decode_ratification(ratification_id, row[0], row[1])
