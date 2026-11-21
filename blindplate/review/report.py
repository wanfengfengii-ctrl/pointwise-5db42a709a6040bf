import json
from dataclasses import dataclass
from fractions import Fraction

from blindplate.review.pairing import Disagreements


@dataclass(frozen=True)
class ReportEvidence:
    receipt_id: int
    issue_id: str
    freeze_id: int


@dataclass(frozen=True)
class ReportReceipt:
    report_id: int
    acknowledgement: str


@dataclass(frozen=True)
class PairedReport:
    report_id: int
    plate_id: str
    a: ReportEvidence
    b: ReportEvidence
    disagreements: Disagreements
    probability: Fraction
    receipt: ReportReceipt


def _evidence_values(evidence: ReportEvidence) -> dict:
    return {
        'receipt_id': evidence.receipt_id,
        'issue_id': evidence.issue_id,
        'freeze_id': evidence.freeze_id,
    }


def encode_report(
    plate_id: str,
    a: ReportEvidence,
    b: ReportEvidence,
    disagreements: Disagreements,
    probability: Fraction,
) -> str:
    values = {
        'plate_id': plate_id,
        'a': _evidence_values(a),
        'b': _evidence_values(b),
        'a_only': disagreements.a_only,
        'b_only': disagreements.b_only,
        'probability': [probability.numerator, probability.denominator],
    }
    return json.dumps(values, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def decode_report(report_id: int, body: str, acknowledgement: str) -> PairedReport:
    values = json.loads(body)
    return PairedReport(
        report_id=report_id,
        plate_id=values['plate_id'],
        a=ReportEvidence(**values['a']),
        b=ReportEvidence(**values['b']),
        disagreements=Disagreements(tuple(values['a_only']), tuple(values['b_only'])),
        probability=Fraction(*values['probability']),
        receipt=ReportReceipt(report_id, acknowledgement),
    )
