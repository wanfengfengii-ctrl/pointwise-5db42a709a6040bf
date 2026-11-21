from blindplate.issue.document import V1IssueDocument
from blindplate.receipt.ledger import FirstReceipt, ReceivedIssue


def resolve_replay(existing: ReceivedIssue, incoming: V1IssueDocument) -> FirstReceipt:
    if existing.document != incoming:
        raise ValueError(f'conflicting content for issue {incoming.issue_id!r}')
    return existing.first_receipt
