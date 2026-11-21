"""Compare two V1 handoffs made from different station histories."""
import json
import sqlite3
from contextlib import closing
from fractions import Fraction

from blindplate.issue.release import issue
from blindplate.reading.correction import correct
from blindplate.reading.freeze import freeze
from blindplate.reading.observation import InstrumentSource
from blindplate.receipt.admit import admit
from blindplate.review.readback import read
from blindplate.review.signing import sign
from tests.fixtures import initialize_center, initialize_station, prepare


PLATE = "R-3"
SLOTS = ("1", "2")


def originals(station, revisions=()):
    with closing(sqlite3.connect(":memory:")) as db:
        initialize_station(db)
        current = prepare(db, PLATE, station, (0, 0), slots=SLOTS)
        base = issue(db, freeze(db, PLATE, station))
        for slot, detected in revisions:
            source = InstrumentSource("camera", "work-order")
            current[slot] = correct(db, current[slot], detected, source)
        latest = issue(db, freeze(db, PLATE, station)) if revisions else base
    return base, latest


def main():
    base, after = originals("west", (("1", 1), ("2", 1), ("1", 0)))
    direct_base, direct = originals("west", (("2", 1),))
    east, _ = originals("east")
    if (base, after) != (direct_base, direct):
        raise AssertionError("the two V1 exports should coincide")

    with closing(sqlite3.connect(":memory:")) as db:
        initialize_center(db)
        b = admit(db, east.payload).receipt_id
        original = sign(db, b, admit(db, base.payload).receipt_id)
        replacement = sign(db, b, admit(db, after.payload).receipt_id)
        if (original.probability, replacement.probability) != (Fraction(1), Fraction(1, 2)):
            raise AssertionError("unexpected paired probabilities")
        if replacement.disagreements.a_only != ("2",) or replacement.disagreements.b_only:
            raise AssertionError("unexpected disagreements in the replacement report")
        if read(db, original.report_id) != original:
            raise AssertionError("the original report changed")

    print(json.dumps({
        "plate": PLATE,
        "same_v1_payloads": after.payload == direct.payload,
        "original_probability": str(original.probability),
        "replacement_probability": str(replacement.probability),
        "replacement_a_only": list(replacement.disagreements.a_only),
    }))


if __name__ == "__main__":
    main()
