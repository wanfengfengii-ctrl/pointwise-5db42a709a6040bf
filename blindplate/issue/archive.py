import sqlite3

from blindplate.issue.document import V1IssueDocument


def initialize_issue_archive(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS issued_documents (
            freeze_id INTEGER PRIMARY KEY REFERENCES frozen_revisions(freeze_id),
            issue_id TEXT NOT NULL UNIQUE,
            payload BLOB NOT NULL
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
