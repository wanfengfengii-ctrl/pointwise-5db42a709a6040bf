import sqlite3

from blindplate.plate.register import get_roster
from blindplate.reading.revisions import get_current_observations, insert_frozen_revision


def freeze(db: sqlite3.Connection, plate_id: str, station_id: str) -> int:
    db.execute('BEGIN IMMEDIATE')
    with db:
        roster = get_roster(db, plate_id)
        roster.protocol.role_for(station_id)
        current = get_current_observations(db, plate_id, station_id)
        slots = roster.slots.slots
        if current.keys() != set(slots):
            missing = tuple(slot for slot in slots if slot not in current)
            raise ValueError(f'current readings do not cover the plate exactly, missing slots {missing!r}')
        ordered = tuple(current[slot] for slot in slots)
        return insert_frozen_revision(db, roster, station_id, ordered)
