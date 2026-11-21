import sqlite3

from blindplate.issue.document import V1IssueDocument
from blindplate.issue.pack import CorrectionPackDocument


def initialize_issue_archive(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS issued_documents (
            freeze_id INTEGER PRIMARY KEY REFERENCES frozen_revisions(freeze_id),
            issue_id TEXT NOT NULL UNIQUE,
            payload BLOB NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS correction_packs (
            pack_seq INTEGER PRIMARY KEY AUTOINCREMENT,
            pack_id TEXT NOT NULL UNIQUE,
            base_issue_id TEXT NOT NULL,
            payload BLOB NOT NULL
        )
    ''')
    # 仪器出处与私有判读号只留站库；槽级前身链用于整包重放核验。
    db.execute('''
        CREATE TABLE IF NOT EXISTS correction_pack_slots (
            pack_seq INTEGER NOT NULL REFERENCES correction_packs(pack_seq),
            slot TEXT NOT NULL,
            previous_pack_id TEXT,
            detected INTEGER NOT NULL CHECK (detected IN (0, 1)),
            instrument TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            PRIMARY KEY (pack_seq, slot)
        )
    ''')


def find_issued_number(db: sqlite3.Connection, freeze_id: int) -> str | None:
    row = db.execute(
        'SELECT issue_id FROM issued_documents WHERE freeze_id = ?', (freeze_id,),
    ).fetchone()
    return None if row is None else row[0]


def insert_issued_document(db: sqlite3.Connection, document: V1IssueDocument, payload: bytes) -> None:
    db.execute(
        'INSERT INTO issued_documents (freeze_id, issue_id, payload) VALUES (?, ?, ?)',
        (document.freeze_id, document.issue_id, payload),
    )


def next_pack_sequence(db: sqlite3.Connection) -> int:
    row = db.execute('SELECT COALESCE(MAX(pack_seq), 0) + 1 FROM correction_packs').fetchone()
    return int(row[0])


def insert_correction_pack(
    db: sqlite3.Connection,
    document: CorrectionPackDocument,
    payload: bytes,
    sources: dict[str, tuple[str, str]],
) -> int:
    cursor = db.execute(
        '''INSERT INTO correction_packs (pack_id, base_issue_id, payload)
           VALUES (?, ?, ?)''',
        (document.pack_id, document.base.issue_id, payload),
    )
    pack_seq = cursor.lastrowid
    db.executemany(
        '''INSERT INTO correction_pack_slots
           (pack_seq, slot, previous_pack_id, detected, instrument, source_ref)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (
            (pack_seq, change.slot, change.previous_pack_id, change.detected,
             sources[change.slot][0], sources[change.slot][1])
            for change in document.changes
        ),
    )
    return pack_seq


def find_correction_pack(db: sqlite3.Connection, pack_id: str) -> tuple[int, bytes] | None:
    row = db.execute(
        'SELECT pack_seq, payload FROM correction_packs WHERE pack_id = ?', (pack_id,),
    ).fetchone()
    return None if row is None else (row[0], row[1])


def correction_pack_exists(db: sqlite3.Connection, pack_id: str) -> bool:
    row = db.execute(
        'SELECT 1 FROM correction_packs WHERE pack_id = ?', (pack_id,),
    ).fetchone()
    return row is not None


def correction_pack_base_issue(db: sqlite3.Connection, pack_id: str) -> str | None:
    row = db.execute(
        'SELECT base_issue_id FROM correction_packs WHERE pack_id = ?', (pack_id,),
    ).fetchone()
    return None if row is None else row[0]


def correction_pack_wrote_slot(db: sqlite3.Connection, pack_id: str, slot: str) -> bool:
    row = db.execute(
        '''SELECT 1 FROM correction_packs AS packs
           JOIN correction_pack_slots AS written
             ON written.pack_seq = packs.pack_seq
           WHERE packs.pack_id = ? AND written.slot = ?''',
        (pack_id, slot),
    ).fetchone()
    return row is not None
