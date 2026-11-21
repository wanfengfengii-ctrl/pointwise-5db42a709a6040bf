import json
import sqlite3
from collections.abc import Sequence

from blindplate.plate.identity import PlateIdentity, validate_plate_id
from blindplate.plate.protocol import PlateProtocol, PlateRoster, protocol_from_values
from blindplate.plate.slots import make_slot_roster


def initialize_rosters(db: sqlite3.Connection) -> None:
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('''
        CREATE TABLE IF NOT EXISTS plate_rosters (
            plate_id TEXT NOT NULL PRIMARY KEY,
            definition TEXT NOT NULL
        )
    ''')


def _restore(plate_id: str, definition: str) -> PlateRoster:
    values = json.loads(definition)
    return PlateRoster(
        PlateIdentity(plate_id),
        make_slot_roster(values['slots']),
        protocol_from_values(values['protocol']),
    )


def get_roster(db: sqlite3.Connection, plate_id: str) -> PlateRoster:
    plate_id = validate_plate_id(plate_id)
    row = db.execute('SELECT definition FROM plate_rosters WHERE plate_id = ?', (plate_id,)).fetchone()
    if row is None:
        raise KeyError(plate_id)
    return _restore(plate_id, row[0])


def register(
    db: sqlite3.Connection, plate_id: str, slots: Sequence[str], protocol: PlateProtocol
) -> PlateRoster:
    if not isinstance(protocol, PlateProtocol):
        raise ValueError('a fixed comparison protocol is required')
    roster = PlateRoster(PlateIdentity(plate_id), make_slot_roster(slots), protocol)
    db.execute('BEGIN IMMEDIATE')
    with db:
        try:
            existing = get_roster(db, roster.plate_id)
        except KeyError:
            definition = json.dumps(
                {'slots': roster.slots.slots, 'protocol': protocol.to_values()},
                ensure_ascii=False,
                separators=(',', ':'),
                sort_keys=True,
            )
            db.execute(
                'INSERT INTO plate_rosters (plate_id, definition) VALUES (?, ?)',
                (roster.plate_id, definition),
            )
            return roster
        if existing != roster:
            raise ValueError(f'conflicting definition for plate {roster.plate_id!r}')
        return existing
