from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import quote

from blindplate.plate.identity import validate_number, validate_plate_id, validate_station_id, validate_text
from blindplate.plate.protocol import PlateRoster
from blindplate.reading.observation import validate_binary_reading


V1_VERSION = 1


def make_issue_id(plate_id: str, station_id: str, freeze_id: int) -> str:
    plate = quote(validate_plate_id(plate_id), safe='')
    station = quote(validate_station_id(station_id), safe='')
    revision = validate_number(freeze_id, 'freeze ID')
    return f'v1:{plate}:{station}:{revision}'


@dataclass(frozen=True)
class SlotDecision:
    slot: str
    detected: int

    def __post_init__(self) -> None:
        validate_text(self.slot, 'slot')
        validate_binary_reading(self.detected)


@dataclass(frozen=True)
class V1IssueDocument:
    issue_id: str
    roster: PlateRoster
    station_id: str
    freeze_id: int
    decisions: tuple[SlotDecision, ...]
    version: int = field(default=V1_VERSION, init=False)

    def to_values(self) -> dict:
        return {
            'version': self.version,
            'issue_id': self.issue_id,
            'plate_id': self.roster.plate_id,
            'station_id': self.station_id,
            'freeze_id': self.freeze_id,
            'protocol': self.roster.protocol.to_values(),
            'slots': list(self.roster.slots.slots),
            'decisions': [[entry.slot, entry.detected] for entry in self.decisions],
        }


def build_v1_document(
    roster: PlateRoster,
    station_id: str,
    freeze_id: int,
    decisions: Iterable[SlotDecision],
) -> V1IssueDocument:
    roster.protocol.role_for(station_id)
    issue_id = make_issue_id(roster.plate_id, station_id, freeze_id)
    ordered = tuple(decisions)
    if tuple(entry.slot for entry in ordered) != roster.slots.slots:
        raise ValueError('decisions must cover every slot once in roster order')
    return V1IssueDocument(issue_id, roster, station_id, freeze_id, ordered)
