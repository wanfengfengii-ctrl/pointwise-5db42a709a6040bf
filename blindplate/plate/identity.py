from dataclasses import dataclass


_MAX_SQLITE_INTEGER = (1 << 63) - 1


def validate_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or not value.isprintable() or value != value.strip():
        raise ValueError(f'{field} must be nonempty printable text without surrounding whitespace')
    return value


def validate_number(value: int, field: str) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_SQLITE_INTEGER:
        raise ValueError(f'{field} must be a positive SQLite integer')
    return value


def validate_plate_id(value: str) -> str:
    return validate_text(value, 'plate ID')


def validate_station_id(value: str) -> str:
    return validate_text(value, 'station ID')


@dataclass(frozen=True)
class PlateIdentity:
    value: str

    def __post_init__(self) -> None:
        validate_plate_id(self.value)


@dataclass(frozen=True)
class StationIdentity:
    value: str

    def __post_init__(self) -> None:
        validate_station_id(self.value)
