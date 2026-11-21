from collections.abc import Sequence
from dataclasses import dataclass

from blindplate.plate.identity import validate_text


@dataclass(frozen=True)
class SlotRoster:
    slots: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.slots, tuple) or not 1 <= len(self.slots) <= 8:
            raise ValueError('a roster must contain one to eight slots')
        for slot in self.slots:
            validate_text(slot, 'slot')
        if len(set(self.slots)) != len(self.slots):
            raise ValueError('physical slots must be distinct')

    def position(self, slot: str) -> int:
        validate_text(slot, 'slot')
        try:
            return self.slots.index(slot)
        except ValueError:
            raise ValueError(f'slot {slot!r} does not belong to the plate') from None


def make_slot_roster(slots: Sequence[str]) -> SlotRoster:
    if not isinstance(slots, Sequence) or isinstance(slots, (str, bytes, bytearray)):
        raise ValueError('slots must be an ordered sequence of names')
    if not 1 <= len(slots) <= 8:
        raise ValueError('a roster must contain one to eight slots')
    return SlotRoster(tuple(slots))
