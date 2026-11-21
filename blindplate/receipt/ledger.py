import sqlite3
from dataclasses import dataclass
from typing import NamedTuple

from blindplate.issue.document import V1IssueDocument
from blindplate.issue.pack import CorrectionPackDocument
from blindplate.plate.identity import validate_number
from blindplate.receipt.verify import decode_verified_pack, decode_verified_v1


@dataclass(frozen=True)
class FirstReceipt:
    receipt_id: int
    issue_id: str
    acknowledgement: str


@dataclass(frozen=True)
class ReceivedIssue:
    first_receipt: FirstReceipt
    document: V1IssueDocument
    payload: bytes


class PackReceipt(NamedTuple):
    receipt_id: int
    pack_id: str
    acknowledgement: str


@dataclass(frozen=True)
class ReceivedPack:
    first_receipt: PackReceipt
    document: CorrectionPackDocument
    payload: bytes


def initialize_receipts(db: sqlite3.Connection) -> None:
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('''
        CREATE TABLE IF NOT EXISTS received_issues (
            receipt_id INTEGER PRIMARY KEY,
            issue_id TEXT NOT NULL UNIQUE,
            payload BLOB NOT NULL,
            acknowledgement TEXT NOT NULL UNIQUE
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS received_correction_packs (
            receipt_id INTEGER PRIMARY KEY,
            pack_id TEXT NOT NULL UNIQUE,
            payload BLOB NOT NULL,
            acknowledgement TEXT NOT NULL UNIQUE
        )
    ''')


def _restore(row: tuple) -> ReceivedIssue:
    receipt_id, issue_id, payload, acknowledgement = row
    return ReceivedIssue(FirstReceipt(receipt_id, issue_id, acknowledgement), decode_verified_v1(payload), payload)


def find_by_issue_id(db: sqlite3.Connection, issue_id: str) -> ReceivedIssue | None:
    row = db.execute(
        '''SELECT receipt_id, issue_id, payload, acknowledgement
           FROM received_issues WHERE issue_id = ?''',
        (issue_id,),
    ).fetchone()
    return None if row is None else _restore(row)


def store_first_receipt(
    db: sqlite3.Connection, document: V1IssueDocument, payload: bytes
) -> FirstReceipt:
    acknowledgement = f'received:{document.issue_id}'
    receipt_id = db.execute(
        'INSERT INTO received_issues (issue_id, payload, acknowledgement) VALUES (?, ?, ?)',
        (document.issue_id, payload, acknowledgement),
    ).lastrowid
    return FirstReceipt(receipt_id, document.issue_id, acknowledgement)


def get_received_issue(db: sqlite3.Connection, receipt_id: int) -> ReceivedIssue:
    receipt_id = validate_number(receipt_id, 'receipt ID')
    row = db.execute(
        '''SELECT receipt_id, issue_id, payload, acknowledgement
           FROM received_issues WHERE receipt_id = ?''',
        (receipt_id,),
    ).fetchone()
    if row is None:
        raise KeyError(receipt_id)
    return _restore(row)


def _restore_pack(row: tuple) -> ReceivedPack:
    receipt_id, pack_id, payload, acknowledgement = row
    return ReceivedPack(PackReceipt(receipt_id, pack_id, acknowledgement), decode_verified_pack(payload), payload)


def find_pack_by_id(db: sqlite3.Connection, pack_id: str) -> ReceivedPack | None:
    row = db.execute(
        '''SELECT receipt_id, pack_id, payload, acknowledgement
           FROM received_correction_packs WHERE pack_id = ?''',
        (pack_id,),
    ).fetchone()
    return None if row is None else _restore_pack(row)


def store_first_pack(
    db: sqlite3.Connection, document: CorrectionPackDocument, payload: bytes
) -> PackReceipt:
    acknowledgement = f'received:{document.pack_id}'
    receipt_id = db.execute(
        '''INSERT INTO received_correction_packs (pack_id, payload, acknowledgement)
           VALUES (?, ?, ?)''',
        (document.pack_id, payload, acknowledgement),
    ).lastrowid
    return PackReceipt(receipt_id, document.pack_id, acknowledgement)


def get_received_pack(db: sqlite3.Connection, receipt_id: int) -> ReceivedPack:
    receipt_id = validate_number(receipt_id, 'receipt ID')
    row = db.execute(
        '''SELECT receipt_id, pack_id, payload, acknowledgement
           FROM received_correction_packs WHERE receipt_id = ?''',
        (receipt_id,),
    ).fetchone()
    if row is None:
        raise KeyError(receipt_id)
    return _restore_pack(row)
