from dataclasses import dataclass

from blindplate.receipt.select import SelectedPair


@dataclass(frozen=True)
class Disagreements:
    a_only: tuple[str, ...]
    b_only: tuple[str, ...]


def pair_by_slot(pair: SelectedPair) -> Disagreements:
    a_document = pair.a.document
    a_by_slot = {row.slot: row.detected for row in a_document.decisions}
    b_by_slot = {row.slot: row.detected for row in pair.b.document.decisions}
    a_only = []
    b_only = []
    for slot in a_document.roster.slots.slots:
        a_reading = a_by_slot[slot]
        b_reading = b_by_slot[slot]
        if a_reading > b_reading:
            a_only.append(slot)
        elif b_reading > a_reading:
            b_only.append(slot)
    return Disagreements(tuple(a_only), tuple(b_only))
