import sqlite3

from blindplate.receipt.deduplicate import resolve_pack_replay, resolve_replay
from blindplate.receipt.ledger import (
    FirstReceipt,
    PackReceipt,
    find_by_issue_id,
    find_pack_by_id,
    store_first_pack,
    store_first_receipt,
)
from blindplate.receipt.verify import decode_verified_pack, decode_verified_v1


def admit(db: sqlite3.Connection, payload: bytes) -> FirstReceipt:
    document = decode_verified_v1(payload)
    db.execute('BEGIN IMMEDIATE')
    with db:
        existing = find_by_issue_id(db, document.issue_id)
        if existing is not None:
            return resolve_replay(existing, document)
        return store_first_receipt(db, document, payload)


def admit_correction(db: sqlite3.Connection, payload: bytes) -> PackReceipt:
    document = decode_verified_pack(payload)
    db.execute('BEGIN IMMEDIATE')
    with db:
        existing = find_pack_by_id(db, document.pack_id)
        if existing is not None:
            return resolve_pack_replay(existing, document)
        return store_first_pack(db, document, payload)
