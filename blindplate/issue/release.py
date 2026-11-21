import sqlite3

from blindplate.issue.archive import (
    correction_pack_base_issue,
    correction_pack_wrote_slot,
    find_issued_number,
    insert_correction_pack,
    insert_issued_document,
    next_pack_sequence,
)
from blindplate.issue.document import SlotDecision, build_v1_document
from blindplate.issue.document import make_issue_id as make_issue_id
from blindplate.issue.encoding import encode_pack, encode_v1
from blindplate.issue.pack import CorrectionPackDocument, PackChange, make_pack_id
from blindplate.issue.pickup import IssuedOriginal, pickup_correction, pickup_issue
from blindplate.plate.identity import validate_number, validate_text
from blindplate.reading.observation import InstrumentSource
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


def _validate_changes(changes: object) -> dict:
    if not isinstance(changes, dict) or not changes:
        raise ValueError('changes must be a nonempty mapping of slots to (previous, detected, source)')
    normalized = {}
    for slot, entry in changes.items():
        validate_text(slot, 'slot')
        if not isinstance(entry, tuple) or len(entry) != 3:
            raise ValueError('each change must be a (previous, detected, source) triple')
        previous, detected, source = entry
        if previous is not None:
            validate_text(previous, 'previous pack ID')
        if type(detected) is not int or detected not in (0, 1):
            raise ValueError('a detection reading must be the integer 0 or 1')
        if not isinstance(source, InstrumentSource):
            raise ValueError('an instrument source is required')
        if slot in normalized:
            raise ValueError(f'slot {slot!r} appears more than once')
        normalized[slot] = (previous, detected, source)
    return normalized


def issue_correction(
    db: sqlite3.Connection, base_issue_id: str, changes: dict
) -> tuple[str, bytes]:
    base_issue_id = validate_text(base_issue_id, 'base issue ID')
    normalized = _validate_changes(changes)
    db.execute('BEGIN IMMEDIATE')
    with db:
        base = pickup_issue(db, base_issue_id)
        revision = load_frozen_revision(db, base.freeze_id)
        roster = revision.roster
        expected_issue_id = make_issue_id(roster.plate_id, revision.station_id, revision.freeze_id)
        if base.issue_id != expected_issue_id:
            raise ValueError('base issue identity does not match its frozen revision')
        for slot, (previous, _detected, _source) in normalized.items():
            roster.slots.position(slot)
            if previous is not None:
                previous_base = correction_pack_base_issue(db, previous)
                if previous_base is None:
                    raise KeyError(previous)
                if previous_base != base_issue_id:
                    raise ValueError(
                        f'previous pack {previous!r} was issued against a different baseline'
                    )
                if not correction_pack_wrote_slot(db, previous, slot):
                    raise ValueError(
                        f'previous pack {previous!r} never wrote slot {slot!r}'
                    )
        base_document = build_v1_document(
            roster,
            revision.station_id,
            revision.freeze_id,
            (SlotDecision(row.slot, row.detected) for row in revision.observations),
        )
        ordered_slots = sorted(normalized, key=roster.slots.position)
        pack_seq = next_pack_sequence(db)
        pack_id = make_pack_id(roster.plate_id, revision.station_id, revision.freeze_id, pack_seq)
        pack_document = CorrectionPackDocument(
            pack_id,
            base_document,
            tuple(
                PackChange(slot, normalized[slot][0], normalized[slot][1])
                for slot in ordered_slots
            ),
        )
        payload = encode_pack(pack_document)
        sources = {slot: (entry[2].instrument, entry[2].reference) for slot, entry in normalized.items()}
        insert_correction_pack(db, pack_document, payload, sources)
        return pickup_correction(db, pack_id)
