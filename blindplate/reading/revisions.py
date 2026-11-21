import sqlite3
from dataclasses import dataclass

from blindplate.plate.identity import validate_number
from blindplate.plate.protocol import PlateRoster
from blindplate.plate.register import get_roster
from blindplate.reading.observation import InstrumentSource, Observation


@dataclass(frozen=True)
class FrozenRevision:
    freeze_id: int
    roster: PlateRoster
    station_id: str
    observations: tuple[Observation, ...]


_OBSERVATION_COLUMNS = (
    'o.observation_id, o.plate_id, o.station_id, o.slot, '
    'o.detected, o.instrument, o.source_ref, o.supersedes_id'
)


def initialize_readings(db: sqlite3.Connection) -> None:
    db.executescript('''
        CREATE TABLE IF NOT EXISTS observations (
            observation_id INTEGER PRIMARY KEY,
            plate_id TEXT NOT NULL REFERENCES plate_rosters(plate_id),
            station_id TEXT NOT NULL,
            slot TEXT NOT NULL,
            detected INTEGER NOT NULL CHECK (detected IN (0, 1)),
            instrument TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            supersedes_id INTEGER UNIQUE REFERENCES observations(observation_id)
        );
        CREATE TABLE IF NOT EXISTS current_observations (
            plate_id TEXT NOT NULL REFERENCES plate_rosters(plate_id),
            station_id TEXT NOT NULL,
            slot TEXT NOT NULL,
            observation_id INTEGER NOT NULL UNIQUE REFERENCES observations(observation_id),
            PRIMARY KEY (plate_id, station_id, slot)
        );
        CREATE TABLE IF NOT EXISTS frozen_revisions (
            freeze_id INTEGER PRIMARY KEY,
            plate_id TEXT NOT NULL REFERENCES plate_rosters(plate_id),
            station_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS frozen_slots (
            freeze_id INTEGER NOT NULL REFERENCES frozen_revisions(freeze_id),
            position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 7),
            observation_id INTEGER NOT NULL REFERENCES observations(observation_id),
            PRIMARY KEY (freeze_id, position),
            UNIQUE (freeze_id, observation_id)
        );
    ''')


def _restore_observation(row: tuple) -> Observation:
    observation_id, plate, station, slot, detected, instrument, reference, predecessor = row
    return Observation(
        observation_id, plate, station, slot, detected,
        InstrumentSource(instrument, reference), predecessor,
    )


def get_observation(db: sqlite3.Connection, observation_id: int) -> Observation:
    observation_id = validate_number(observation_id, 'observation ID')
    row = db.execute(
        f'SELECT {_OBSERVATION_COLUMNS} FROM observations AS o WHERE o.observation_id = ?',
        (observation_id,),
    ).fetchone()
    if row is None:
        raise KeyError(observation_id)
    return _restore_observation(row)


def get_current_observations(
    db: sqlite3.Connection, plate_id: str, station_id: str
) -> dict[str, Observation]:
    rows = db.execute(
        f'''SELECT {_OBSERVATION_COLUMNS}
            FROM current_observations AS active
            JOIN observations AS o ON o.observation_id = active.observation_id
            WHERE active.plate_id = ? AND active.station_id = ?''',
        (plate_id, station_id),
    )
    observations = map(_restore_observation, rows)
    return {observation.slot: observation for observation in observations}


def insert_observation(
    db: sqlite3.Connection,
    plate_id: str,
    station_id: str,
    slot: str,
    detected: int,
    source: InstrumentSource,
    supersedes_id: int | None = None,
) -> int:
    row = db.execute(
        '''INSERT INTO observations
           (plate_id, station_id, slot, detected, instrument, source_ref, supersedes_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (plate_id, station_id, slot, detected, source.instrument, source.reference, supersedes_id),
    )
    return row.lastrowid


def replace_current_observation(
    db: sqlite3.Connection, previous: Observation, replacement_id: int
) -> None:
    update = db.execute(
        '''UPDATE current_observations SET observation_id = ?
           WHERE plate_id = ? AND station_id = ? AND slot = ? AND observation_id = ?''',
        (replacement_id, previous.plate_id, previous.station_id, previous.slot, previous.observation_id),
    )
    if update.rowcount != 1:
        raise ValueError(f'observation {previous.observation_id} is no longer current')


def insert_frozen_revision(
    db: sqlite3.Connection, roster: PlateRoster, station_id: str, observations: tuple[Observation, ...]
) -> int:
    freeze_id = db.execute(
        'INSERT INTO frozen_revisions (plate_id, station_id) VALUES (?, ?)',
        (roster.plate_id, station_id),
    ).lastrowid
    db.executemany(
        'INSERT INTO frozen_slots (freeze_id, position, observation_id) VALUES (?, ?, ?)',
        ((freeze_id, position, row.observation_id) for position, row in enumerate(observations)),
    )
    return freeze_id


def load_frozen_revision(db: sqlite3.Connection, freeze_id: int) -> FrozenRevision:
    freeze_id = validate_number(freeze_id, 'freeze ID')
    identity = db.execute(
        'SELECT plate_id, station_id FROM frozen_revisions WHERE freeze_id = ?', (freeze_id,),
    ).fetchone()
    if identity is None:
        raise KeyError(freeze_id)
    plate_id, station_id = identity
    roster = get_roster(db, plate_id)
    rows = db.execute(
        f'''SELECT {_OBSERVATION_COLUMNS}
            FROM frozen_slots AS frozen
            JOIN observations AS o ON o.observation_id = frozen.observation_id
            WHERE frozen.freeze_id = ? ORDER BY frozen.position''',
        (freeze_id,),
    )
    return FrozenRevision(freeze_id, roster, station_id, tuple(map(_restore_observation, rows)))
