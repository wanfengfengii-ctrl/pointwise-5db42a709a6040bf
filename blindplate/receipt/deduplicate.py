from blindplate.issue.document import V1IssueDocument
from blindplate.issue.pack import CorrectionPackDocument
from blindplate.receipt.ledger import FirstReceipt, PackReceipt, ReceivedIssue, ReceivedPack


def resolve_replay(existing: ReceivedIssue, incoming: V1IssueDocument) -> FirstReceipt:
    if existing.document != incoming:
        raise ValueError(f'conflicting content for issue {incoming.issue_id!r}')
    return existing.first_receipt


def resolve_pack_replay(existing: ReceivedPack, incoming: CorrectionPackDocument) -> PackReceipt:
    # 等价重投返首执；同号异文拒收，首次记录原样保留。
    if existing.document != incoming:
        raise ValueError(f'conflicting content for correction pack {incoming.pack_id!r}')
    return existing.first_receipt
