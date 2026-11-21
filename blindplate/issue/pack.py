from dataclasses import dataclass, field
from urllib.parse import quote

from blindplate.issue.document import V1IssueDocument
from blindplate.plate.identity import (
    validate_number,
    validate_plate_id,
    validate_station_id,
    validate_text,
)


PACK_VERSION = 1
PACK_KIND = 'correction-pack'


def make_pack_id(plate_id: str, station_id: str, freeze_id: int, pack_seq: int) -> str:
    plate = quote(validate_plate_id(plate_id), safe='')
    station = quote(validate_station_id(station_id), safe='')
    revision = validate_number(freeze_id, 'freeze ID')
    sequence = validate_number(pack_seq, 'pack sequence')
    return f'pack:{plate}:{station}:{revision}:{sequence}'


def parse_pack_identity(pack_id: str) -> tuple[str, str, int, int]:
    validate_text(pack_id, 'pack ID')
    parts = pack_id.split(':')
    if len(parts) != 5 or parts[0] != 'pack':
        raise ValueError('malformed correction pack ID')
    plate, station, freeze_text, seq_text = parts[1:]
    if not freeze_text.isdigit() or not seq_text.isdigit():
        raise ValueError('malformed correction pack ID')
    freeze_id = int(freeze_text)
    pack_seq = int(seq_text)
    validate_number(freeze_id, 'freeze ID')
    validate_number(pack_seq, 'pack sequence')
    return plate, station, freeze_id, pack_seq


@dataclass(frozen=True)
class PackChange:
    slot: str
    previous_pack_id: str | None
    detected: int

    def __post_init__(self) -> None:
        validate_text(self.slot, 'slot')
        if self.previous_pack_id is not None:
            validate_text(self.previous_pack_id, 'previous pack ID')
        if type(self.detected) is not int or self.detected not in (0, 1):
            raise ValueError('a detection reading must be the integer 0 or 1')


@dataclass(frozen=True)
class CorrectionPackDocument:
    pack_id: str
    base: V1IssueDocument
    changes: tuple[PackChange, ...]
    version: int = field(default=PACK_VERSION, init=False)

    def __post_init__(self) -> None:
        validate_text(self.pack_id, 'pack ID')
        if not isinstance(self.base, V1IssueDocument):
            raise ValueError('a correction pack must bind a V1 issue document')
        if not isinstance(self.changes, tuple) or not self.changes:
            raise ValueError('a correction pack must change at least one slot')
        slots = [change.slot for change in self.changes]
        if len(set(slots)) != len(slots):
            raise ValueError('each slot may appear at most once in a correction pack')
        roster_slots = self.base.roster.slots.slots
        if any(slot not in roster_slots for slot in slots):
            raise ValueError('correction slots must belong to the base plate roster')

    def to_values(self) -> dict:
        return {
            'version': self.version,
            'kind': PACK_KIND,
            'pack_id': self.pack_id,
            'base_issue': self.base.to_values(),
            'changes': [[change.slot, change.previous_pack_id, change.detected] for change in self.changes],
        }
