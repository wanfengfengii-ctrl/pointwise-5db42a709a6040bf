import json

from blindplate.issue.document import V1IssueDocument
from blindplate.issue.pack import CorrectionPackDocument


def _canonical(values: dict) -> bytes:
    text = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return (text + '\n').encode('utf-8')


def encode_v1(document: V1IssueDocument) -> bytes:
    return _canonical(document.to_values())


def encode_pack(document: CorrectionPackDocument) -> bytes:
    # 业务值只取决于文档字段；键序和 JSON 空白不影响中心等价判读。
    return _canonical(document.to_values())
