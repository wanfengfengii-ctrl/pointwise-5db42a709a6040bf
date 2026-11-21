import sqlite3

from blindplate.issue.archive import find_issued_number, insert_issued_document
from blindplate.issue.document import SlotDecision, build_v1_document
from blindplate.issue.document import make_issue_id as make_issue_id
from blindplate.issue.encoding import encode_v1
from blindplate.issue.pickup import IssuedOriginal, pickup_issue
from blindplate.plate.identity import validate_number
from blindplate.reading.revisions import load_frozen_revision


def issue(db: sqlite3.Connection, freeze_id: int) -> IssuedOriginal:
    freeze_id = validate_number(freeze_id, 'freeze ID')
    db.execute('BEGIN IMMEDIATE')
    with db:
        existing = find_issued_number(db, freeze_id)
        if existing is not None:
            return pickup_issue(db, existing)
        revision = load_frozen_revision(db, freeze_id)
        decisions = (SlotDecision(row.slot, row.detected) for row in revision.observations)
        document = build_v1_document(revision.roster, revision.station_id, revision.freeze_id, decisions)
        payload = encode_v1(document)
        insert_issued_document(db, document, payload)
        return IssuedOriginal(document.issue_id, revision.freeze_id, payload)
