import sqlite3

from blindplate.plate.register import get_roster
from blindplate.reading.observation import InstrumentSource, validate_binary_reading
from blindplate.reading.revisions import get_current_observations, insert_observation


def record(
    db: sqlite3.Connection,
    plate_id: str,
    station_id: str,
    slot: str,
    detected: int,
    source: InstrumentSource,
) -> int:
    validate_binary_reading(detected)
    if not isinstance(source, InstrumentSource):
        raise ValueError('an instrument source is required')
    db.execute('BEGIN IMMEDIATE')
    with db:
        roster = get_roster(db, plate_id)
        roster.protocol.role_for(station_id)
        roster.slots.position(slot)
        if slot in get_current_observations(db, plate_id, station_id):
            raise ValueError(f'slot {slot!r} already has a current reading')
        observation_id = insert_observation(db, plate_id, station_id, slot, detected, source)
        db.execute(
            '''INSERT INTO current_observations (plate_id, station_id, slot, observation_id)
               VALUES (?, ?, ?, ?)''',
            (plate_id, station_id, slot, observation_id),
        )
        return observation_id
