from dataclasses import dataclass
from fractions import Fraction

from blindplate.issue.pack import CorrectionPackDocument
from blindplate.receipt.ledger import ReceivedPack, ReceivedIssue
from blindplate.review.pairing import Disagreements
from blindplate.review.tail import exact_upper_tail


@dataclass(frozen=True)
class RatificationPlan:
    station_id: str
    base_issue_id: str
    decisions: tuple[tuple[str, int], ...]
    a_only: tuple[str, ...]
    b_only: tuple[str, ...]
    probability: Fraction


def _as_receipt_ids(pack_receipt_ids: object) -> tuple[int, ...]:
    if not isinstance(pack_receipt_ids, (list, tuple)) or not pack_receipt_ids:
        raise ValueError('pack receipt IDs must be a nonempty list or tuple')
    ids = tuple(pack_receipt_ids)
    if any(type(value) is not int for value in ids):
        raise ValueError('pack receipt IDs must be positive integers')
    if len(set(ids)) != len(ids):
        raise ValueError('pack receipt IDs must be distinct')
    return tuple(sorted(ids))


def _load_selected_packs(db, pack_receipt_ids: tuple[int, ...]) -> tuple[ReceivedPack, ...]:
    from blindplate.receipt.ledger import get_received_pack

    packs = tuple(get_received_pack(db, receipt_id) for receipt_id in pack_receipt_ids)
    pack_ids = [pack.document.pack_id for pack in packs]
    if len(set(pack_ids)) != len(pack_ids):
        raise ValueError('the selected correction packs must be distinct')
    return packs


def _bind_to_report(packs: tuple[ReceivedPack, ...], paired_report) -> tuple[str, str]:
    base_issue_ids = {pack.document.base.issue_id for pack in packs}
    if len(base_issue_ids) != 1:
        raise ValueError('all selected packs must apply to the same station original')
    base_issue_id = next(iter(base_issue_ids))
    report_issue_ids = {paired_report.a.issue_id, paired_report.b.issue_id}
    if base_issue_id not in report_issue_ids:
        raise ValueError('the selected packs do not apply to an original used by the report')
    station_id = packs[0].document.base.station_id
    if any(pack.document.base.station_id != station_id for pack in packs):
        raise ValueError('all selected packs must come from the same station')
    return station_id, base_issue_id


def _replay(
    packs: tuple[ReceivedPack, ...], baseline: dict[str, int], slots: tuple[str, ...]
) -> dict[str, int]:
    documents: dict[str, CorrectionPackDocument] = {
        pack.document.pack_id: pack.document for pack in packs
    }
    selected = set(documents)
    # 每个（槽，前身）至多被一个选包消耗；同值不消除冲突。
    consumptions: dict[tuple[str, str | None], str] = {}
    writes: dict[str, set[str]] = {}
    for document in documents.values():
        for change in document.changes:
            key = (change.slot, change.previous_pack_id)
            if key in consumptions:
                raise ValueError(
                    f'slot {change.slot!r} predecessor {change.previous_pack_id!r} '
                    'is consumed by more than one selected pack'
                )
            consumptions[key] = document.pack_id
            writes.setdefault(document.pack_id, set()).add(change.slot)
    for document in documents.values():
        for change in document.changes:
            if change.previous_pack_id is not None:
                if change.previous_pack_id not in selected:
                    raise ValueError(f'missing selected predecessor pack {change.previous_pack_id!r}')
                if change.slot not in writes[change.previous_pack_id]:
                    raise ValueError(
                        f'predecessor pack {change.previous_pack_id!r} never wrote slot {change.slot!r}'
                    )
    values = dict(baseline)
    for slot in slots:
        # 该槽链头：以前身为 None 的选包为起点；没有选包写此槽时沿用基线。
        heads = [
            document.pack_id
            for document in documents.values()
            for change in document.changes
            if change.slot == slot and change.previous_pack_id is None
        ]
        if len(heads) > 1:
            raise ValueError(f'more than one selected pack restarts slot {slot!r} from the baseline')
        current_value = baseline[slot]
        if not heads:
            touched = {
                change.slot
                for document in documents.values()
                for change in document.changes
                if change.slot == slot
            }
            if touched:
                raise ValueError(f'slot {slot!r} cannot be replayed as a complete pack chain')
            values[slot] = current_value
            continue
        current_pack = heads[0]
        seen = set()
        while True:
            if current_pack in seen:
                raise ValueError(f'predecessor cycle detected at slot {slot!r}')
            seen.add(current_pack)
            document = documents[current_pack]
            slot_changes = [change for change in document.changes if change.slot == slot]
            if len(slot_changes) != 1:
                raise ValueError(f'pack {current_pack!r} cannot be replayed whole on slot {slot!r}')
            current_value = slot_changes[0].detected
            successors = [
                other.pack_id
                for other in documents.values()
                for change in other.changes
                if change.slot == slot and change.previous_pack_id == current_pack
            ]
            if len(successors) > 1:
                raise ValueError(
                    f'the same predecessor of slot {slot!r} is consumed by more than one selected pack'
                )
            if not successors:
                break
            current_pack = successors[0]
        values[slot] = current_value
    return values


def plan_ratification(db, paired_report, pack_receipt_ids: object) -> RatificationPlan:
    from blindplate.receipt.ledger import get_received_issue

    ids = _as_receipt_ids(pack_receipt_ids)
    packs = _load_selected_packs(db, ids)
    station_id, base_issue_id = _bind_to_report(packs, paired_report)
    base_receipt = (
        paired_report.a if paired_report.a.issue_id == base_issue_id else paired_report.b
    )
    other_evidence = (
        paired_report.b if base_receipt is paired_report.a else paired_report.a
    )
    base_received: ReceivedIssue = get_received_issue(db, base_receipt.receipt_id)
    other_received: ReceivedIssue = get_received_issue(db, other_evidence.receipt_id)
    base_document = base_received.document
    if base_document != packs[0].document.base or any(
        pack.document.base != base_document for pack in packs
    ):
        raise ValueError('the embedded V1 base issue does not match the report evidence')
    if other_received.document.roster != base_document.roster:
        raise ValueError('the paired original disagrees on the fixed plate definition')

    slots = base_document.roster.slots.slots
    baseline = {entry.slot: entry.detected for entry in base_document.decisions}
    corrected = _replay(packs, baseline, slots)
    other_values = {entry.slot: entry.detected for entry in other_received.document.decisions}

    role = base_document.roster.protocol.role_for(station_id)
    a_values = corrected if role == 'a' else other_values
    b_values = other_values if role == 'a' else corrected
    a_only, b_only = [], []
    for slot in slots:
        a_reading = a_values[slot]
        b_reading = b_values[slot]
        if a_reading > b_reading:
            a_only.append(slot)
        elif b_reading > a_reading:
            b_only.append(slot)
    disagreements = Disagreements(tuple(a_only), tuple(b_only))
    probability = exact_upper_tail(len(disagreements.a_only), len(disagreements.b_only))
    return RatificationPlan(
        station_id=station_id,
        base_issue_id=base_issue_id,
        decisions=tuple((slot, corrected[slot]) for slot in slots),
        a_only=disagreements.a_only,
        b_only=disagreements.b_only,
        probability=probability,
    )
