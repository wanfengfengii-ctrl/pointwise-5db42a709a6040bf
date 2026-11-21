import json

from blindplate.issue.document import V1IssueDocument


def encode_v1(document: V1IssueDocument) -> bytes:
    text = json.dumps(
        document.to_values(), ensure_ascii=False, sort_keys=True, separators=(',', ':'),
    )
    return (text + '\n').encode('utf-8')
