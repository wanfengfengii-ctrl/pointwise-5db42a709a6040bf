from dataclasses import dataclass

from blindplate.plate.identity import (
    PlateIdentity,
    StationIdentity,
    validate_station_id,
    validate_text,
)
from blindplate.plate.slots import SlotRoster


@dataclass(frozen=True)
class PlateProtocol:
    a_station: StationIdentity
    a_scheme: str
    b_station: StationIdentity
    b_scheme: str

    def __post_init__(self) -> None:
        if not isinstance(self.a_station, StationIdentity) or not isinstance(self.b_station, StationIdentity):
            raise ValueError('the protocol needs two station identities')
        if self.a_station == self.b_station:
            raise ValueError('comparison roles require distinct stations')
        validate_text(self.a_scheme, 'scheme A')
        validate_text(self.b_scheme, 'scheme B')

    def role_for(self, station_id: str) -> str:
        station_id = validate_station_id(station_id)
        if station_id == self.a_station.value:
            return 'a'
        if station_id == self.b_station.value:
            return 'b'
        raise ValueError(f'station {station_id!r} does not belong to the protocol')

    def to_values(self) -> dict:
        return {
            'a': {'station': self.a_station.value, 'scheme': self.a_scheme},
            'b': {'station': self.b_station.value, 'scheme': self.b_scheme},
        }


@dataclass(frozen=True)
class PlateRoster:
    identity: PlateIdentity
    slots: SlotRoster
    protocol: PlateProtocol

    @property
    def plate_id(self) -> str:
        return self.identity.value


def build_protocol(a_station: str, a_scheme: str, b_station: str, b_scheme: str) -> PlateProtocol:
    return PlateProtocol(StationIdentity(a_station), a_scheme, StationIdentity(b_station), b_scheme)


def protocol_from_values(value: object) -> PlateProtocol:
    if not isinstance(value, dict) or value.keys() != {'a', 'b'}:
        raise ValueError('protocol must define roles a and b')
    for role in value.values():
        if not isinstance(role, dict) or role.keys() != {'station', 'scheme'}:
            raise ValueError('each protocol role needs a station and scheme')
    a, b = value['a'], value['b']
    return build_protocol(a['station'], a['scheme'], b['station'], b['scheme'])
