import json

from blindplate.issue.document import V1_VERSION, SlotDecision, V1IssueDocument, build_v1_document
from blindplate.plate.identity import PlateIdentity
from blindplate.plate.protocol import PlateRoster, protocol_from_values
from blindplate.plate.slots import make_slot_roster


_FIELDS = {'version', 'issue_id', 'plate_id', 'station_id', 'freeze_id', 'protocol', 'slots', 'decisions'}


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


def decode_verified_v1(payload: bytes) -> V1IssueDocument:
    if not isinstance(payload, bytes):
        raise ValueError('the received original must be UTF-8 bytes')
    try:
        values = json.loads(
            payload.decode('utf-8'), object_pairs_hook=_unique_object, parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('invalid V1 JSON encoding') from error
    if not isinstance(values, dict) or values.keys() != _FIELDS:
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
