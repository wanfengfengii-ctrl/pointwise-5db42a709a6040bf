from dataclasses import dataclass

from blindplate.plate.identity import validate_text


def validate_binary_reading(value: int) -> int:
    if type(value) is not int or value not in (0, 1):
        raise ValueError('a detection reading must be the integer 0 or 1')
    return value


@dataclass(frozen=True)
class InstrumentSource:
    instrument: str
    reference: str

    def __post_init__(self) -> None:
        validate_text(self.instrument, 'instrument')
        validate_text(self.reference, 'instrument reference')


@dataclass(frozen=True)
class Observation:
    observation_id: int
    plate_id: str
    station_id: str
    slot: str
    detected: int
    source: InstrumentSource
    supersedes_id: int | None
