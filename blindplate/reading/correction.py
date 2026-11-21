import sqlite3

from blindplate.reading.observation import InstrumentSource, validate_binary_reading
from blindplate.reading.revisions import (
    get_current_observations,
    get_observation,
    insert_observation,
    replace_current_observation,
)


def correct(db: sqlite3.Connection, observation_id: int, detected: int, source: InstrumentSource) -> int:
    validate_binary_reading(detected)
    if not isinstance(source, InstrumentSource):
        raise ValueError('an instrument source is required')
    db.execute('BEGIN IMMEDIATE')
    with db:
        previous = get_observation(db, observation_id)
        current = get_current_observations(db, previous.plate_id, previous.station_id)
        if current.get(previous.slot) != previous:
            raise ValueError(f'observation {observation_id} is no longer current')
        replacement_id = insert_observation(
            db, previous.plate_id, previous.station_id, previous.slot,
            detected, source, supersedes_id=observation_id,
        )
        replace_current_observation(db, previous, replacement_id)
        return replacement_id
