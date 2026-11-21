import json

from blindplate.issue.document import V1_VERSION, SlotDecision, V1IssueDocument, build_v1_document
from blindplate.issue.pack import PACK_KIND, PACK_VERSION, CorrectionPackDocument, PackChange, parse_pack_identity
from blindplate.plate.identity import PlateIdentity
from blindplate.plate.protocol import PlateRoster, protocol_from_values
from blindplate.plate.slots import make_slot_roster


_FIELDS = {'version', 'issue_id', 'plate_id', 'station_id', 'freeze_id', 'protocol', 'slots', 'decisions'}
_PACK_FIELDS = {'version', 'kind', 'pack_id', 'base_issue', 'changes'}


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON field {key!r}')
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f'invalid JSON constant {value!r}')


def _read_decisions(value: object) -> tuple[SlotDecision, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise ValueError('decisions must be an array with one to eight rows')
    decisions = []
    for row in value:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError('each decision must contain a slot and a detection value')
        decisions.append(SlotDecision(row[0], row[1]))
    return tuple(decisions)


def _decode_json_object(payload: bytes) -> dict:
    if not isinstance(payload, bytes):
        raise ValueError('the received original must be UTF-8 bytes')
    try:
        values = json.loads(
            payload.decode('utf-8'), object_pairs_hook=_unique_object, parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('invalid JSON encoding') from error
    if not isinstance(values, dict):
        raise ValueError('the payload must be a JSON object')
    return values


def build_v1_from_values(values: dict) -> V1IssueDocument:
    if values.keys() != _FIELDS:
        raise ValueError('invalid V1 fields')
    if type(values['version']) is not int or values['version'] != V1_VERSION:
        raise ValueError('unsupported issue version')
    if not isinstance(values['slots'], list):
        raise ValueError('the physical slot roster must be an array')
    roster = PlateRoster(
        PlateIdentity(values['plate_id']),
        make_slot_roster(values['slots']),
        protocol_from_values(values['protocol']),
    )
    document = build_v1_document(
        roster, values['station_id'], values['freeze_id'], _read_decisions(values['decisions']),
    )
    if values['issue_id'] != document.issue_id:
        raise ValueError('issue ID does not match plate, station and freeze')
    return document


def decode_verified_v1(payload: bytes) -> V1IssueDocument:
    values = _decode_json_object(payload)
    try:
        return build_v1_from_values(values)
    except KeyError as error:
        raise ValueError('invalid V1 fields') from error


def _read_pack_changes(value: object) -> tuple[PackChange, ...]:
    if not isinstance(value, list) or not value or len(value) > 8:
        raise ValueError('pack changes must be an array with one to eight rows')
    changes = []
    seen = set()
    for row in value:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError('each pack change must contain a slot, previous pack and detection value')
        slot, previous, detected = row
        if previous is not None and not isinstance(previous, str):
            raise ValueError('the previous pack must be null or a pack ID')
        change = PackChange(slot, previous, detected)
        if change.slot in seen:
            raise ValueError('each slot may appear at most once in a correction pack')
        seen.add(change.slot)
        changes.append(change)
    return tuple(changes)


def decode_verified_pack(payload: bytes) -> CorrectionPackDocument:
    values = _decode_json_object(payload)
    if values.keys() != _PACK_FIELDS:
        raise ValueError('invalid correction pack fields')
    if type(values['version']) is not int or values['version'] != PACK_VERSION:
        raise ValueError('unsupported correction pack version')
    if values['kind'] != PACK_KIND:
        raise ValueError('unsupported correction pack kind')
    if not isinstance(values['pack_id'], str):
        raise ValueError('the correction pack ID must be text')
    if not isinstance(values['base_issue'], dict):
        raise ValueError('a correction pack must embed its V1 base issue')
    base = build_v1_from_values(values['base_issue'])
    changes = _read_pack_changes(values['changes'])
    roster_slots = base.roster.slots.slots
    if any(change.slot not in roster_slots for change in changes):
        raise ValueError('correction slots must belong to the base plate roster')
    plate, station, freeze_id, pack_seq = parse_pack_identity(values['pack_id'])
    if plate != base.roster.plate_id or station != base.station_id or freeze_id != base.freeze_id:
        raise ValueError('pack ID does not match the embedded V1 base issue')
    return CorrectionPackDocument(values['pack_id'], base, changes)
