import sqlite3
from dataclasses import dataclass

from blindplate.receipt.ledger import ReceivedIssue, get_received_issue


@dataclass(frozen=True)
class SelectedPair:
    a: ReceivedIssue
    b: ReceivedIssue


def select_pair(db: sqlite3.Connection, first_receipt_id: int, second_receipt_id: int) -> SelectedPair:
    first = get_received_issue(db, first_receipt_id)
    second = get_received_issue(db, second_receipt_id)
    if first.document.roster.plate_id != second.document.roster.plate_id:
        raise ValueError('paired receipts must identify the same physical plate')
    if first.document.roster != second.document.roster:
        raise ValueError('paired receipts disagree on the fixed plate definition')
    protocol = first.document.roster.protocol
    first_role = protocol.role_for(first.document.station_id)
    second_role = protocol.role_for(second.document.station_id)
    if first_role == second_role:
        raise ValueError('paired receipts must come from different stations')
    if first_role == 'a':
        return SelectedPair(first, second)
    return SelectedPair(second, first)
