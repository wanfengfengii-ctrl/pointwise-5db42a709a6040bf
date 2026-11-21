import sqlite3
from dataclasses import dataclass

from blindplate.plate.identity import validate_text


@dataclass(frozen=True)
class IssuedOriginal:
    issue_id: str
    freeze_id: int
    payload: bytes


def pickup_issue(db: sqlite3.Connection, issue_id: str) -> IssuedOriginal:
    issue_id = validate_text(issue_id, 'issue ID')
    row = db.execute(
        'SELECT freeze_id, payload FROM issued_documents WHERE issue_id = ?', (issue_id,),
    ).fetchone()
    if row is None:
        raise KeyError(issue_id)
    return IssuedOriginal(issue_id, row[0], row[1])
