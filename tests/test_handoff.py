import json
from contextlib import closing

from blindplate.issue.pickup import pickup_issue
from blindplate.issue.release import issue
from blindplate.reading.correction import correct
from blindplate.reading.freeze import freeze
from blindplate.reading.observation import InstrumentSource
from blindplate.reading.revisions import get_current_observations, load_frozen_revision
from blindplate.receipt.admit import admit
from blindplate.receipt.ledger import get_received_issue
from tests.fixtures import (
    DatabaseCase, LEGACY, initialize_station, make_original, open_center, open_station, prepare, restore_legacy,
)


class TestHandoff(DatabaseCase):
    def test_offline_admission_and_replay(self):
        station_path = self.directory / 'west.sqlite'
        with closing(open_station(station_path)) as west:
            ids = prepare(west, 'P-4', 'west', (1, 1, 1, 0))
            old = freeze(west, 'P-4', 'west')
            correct(west, ids['1'], 0, InstrumentSource('local-calibration', 'private-correction'))
            new = freeze(west, 'P-4', 'west')
            self.assertEqual(0, load_frozen_revision(west, new).observations[0].detected)
            self.assertEqual(1, load_frozen_revision(west, old).observations[0].detected)
            with self.assertRaises(KeyError):
                issue(west, 9000)
            self.assertEqual((0,), west.execute('SELECT COUNT(*) FROM issued_documents').fetchone())
            west_original = issue(west, old)
            self.assertEqual('v1:P-4:west:1', west_original.issue_id)
            self.assertEqual(west_original, issue(west, old))
            self.assertEqual(west_original, pickup_issue(west, west_original.issue_id))
            with self.assertRaises(KeyError):
                pickup_issue(west, 'v1:P-4:west:9000')
        with closing(open_station(station_path)) as reopened:
            self.assertEqual(west_original, issue(reopened, old))
            self.assertEqual(west_original, pickup_issue(reopened, west_original.issue_id))
        east_original = make_original(self.directory / 'east.sqlite', 'P-4', 'east', (0, 0, 0, 1))
        west_values = json.loads(west_original.payload)
        east_values = json.loads(east_original.payload)
        self.assertEqual(old, west_values['freeze_id'])
        self.assertEqual([['1', 1], ['2', 1], ['3', 1], ['4', 0]], west_values['decisions'])
        self.assertEqual([['1', 0], ['2', 0], ['3', 0], ['4', 1]], east_values['decisions'])
        expected_fields = {'version', 'issue_id', 'plate_id', 'station_id', 'freeze_id',
                           'protocol', 'slots', 'decisions'}
        for original, values in ((west_original, west_values), (east_original, east_values)):
            self.assertEqual(expected_fields, values.keys())
            self.assertEqual({'a': {'scheme': 'spray-A', 'station': 'west'},
                              'b': {'scheme': 'spray-B', 'station': 'east'}}, values['protocol'])
            for private in (b'observation_id', b'supersedes_id', b'instrument', b'private-trace', b'private-correction'):
                self.assertNotIn(private, original.payload)

        with closing(open_center(self.directory / 'center.sqlite')) as center:
            east = admit(center, east_original.payload)
            west = admit(center, west_original.payload)
            self.assertLess(east.receipt_id, west.receipt_id)
            reformatted = json.dumps(dict(reversed(list(west_values.items()))), indent=2).encode('utf-8')
            self.assertNotEqual(west_original.payload, reformatted)
            self.assertEqual(west, admit(center, reformatted))
            self.assertEqual(west, admit(center, west_original.payload))
            stored = get_received_issue(center, west.receipt_id)
            self.assertEqual(west, stored.first_receipt)
            self.assertEqual(west_original.payload, stored.payload)
            self.assertEqual(east_original.payload, get_received_issue(center, east.receipt_id).payload)
            self.assertEqual((2,), center.execute('SELECT COUNT(*) FROM received_issues').fetchone())

    def test_conflicting_replay(self):
        original = make_original(self.directory / 'station.sqlite', 'P-5', 'west', (1, 0, 0, 1))
        center_path = self.directory / 'center.sqlite'
        with closing(open_center(center_path)) as center:
            first = admit(center, original.payload)
            malformed = {
                'encoding': b'\xff',
                'duplicate field': original.payload.replace(b'"version":1', b'"version":1,"version":1'),
                'duplicate role field': original.payload.replace(b'"scheme":"spray-A"',
                                                                  b'"scheme":"spray-A","scheme":"spray-A"'),
            }
            for name in ('missing slot', 'wrong order', 'nonbinary', 'bool', 'station', 'version', 'missing field',
                         'identity mismatch'):
                values = json.loads(original.payload)
                if name == 'missing slot':
                    values['decisions'].pop()
                elif name == 'wrong order':
                    values['decisions'].reverse()
                elif name == 'nonbinary':
                    values['decisions'][0][1] = 2
                elif name == 'bool':
                    values['decisions'][0][1] = True
                elif name == 'station':
                    values['station_id'] = 'north'
                elif name == 'version':
                    values['version'] = 2
                elif name == 'missing field':
                    del values['protocol']
                else:
                    values['freeze_id'] += 1
                malformed[name] = json.dumps(values).encode('utf-8')
            for name, payload in malformed.items():
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        admit(center, payload)
                    self.assertEqual((1,), center.execute('SELECT COUNT(*) FROM received_issues').fetchone())
            conflict = json.loads(original.payload)
            conflict['decisions'][0][1] = 0
            with self.assertRaises(ValueError):
                admit(center, json.dumps(conflict).encode('utf-8'))
            self.assertEqual((1,), center.execute('SELECT COUNT(*) FROM received_issues').fetchone())
        with closing(open_center(center_path)) as reopened:
            self.assertEqual(first, admit(reopened, original.payload))
            stored = get_received_issue(reopened, first.receipt_id)
            self.assertEqual(first, stored.first_receipt)
            self.assertEqual(original.payload, stored.payload)

    def test_legacy_admission(self):
        originals = {}
        for station, freeze_id in (('west', 7), ('east', 9)):
            path = self.directory / f'legacy-{station}.sqlite'
            restore_legacy(path, f'{station}.sql')
            issue_id = f'v1:LEG-04:{station}:{freeze_id}'
            expected = (LEGACY / f'{station}-v1.json').read_bytes()
            with closing(open_station(path)) as db:
                initialize_station(db)
                picked_up = pickup_issue(db, issue_id)
                self.assertEqual(expected, picked_up.payload)
                self.assertEqual(picked_up, issue(db, freeze_id))
                self.assertEqual(4, len(load_frozen_revision(db, freeze_id).observations))
                if station == 'west':
                    old = load_frozen_revision(db, 6).observations[0]
                    current = get_current_observations(db, 'LEG-04', 'west')['1']
                    self.assertEqual((0, 'line-101'), (old.detected, old.source.reference))
                    self.assertEqual((1, 'line-105', old.observation_id),
                                     (current.detected, current.source.reference, current.supersedes_id))
                    updated = correct(db, current.observation_id, 0, InstrumentSource('legacy-west', 'line-106'))
                    self.assertNotEqual(current.observation_id, updated)
                    later = freeze(db, 'LEG-04', 'west')
                    self.assertGreater(later, freeze_id)
                    self.assertEqual(expected, pickup_issue(db, issue_id).payload)
                originals[station] = picked_up
        with closing(open_center(self.directory / 'offline.sqlite')) as center:
            for station in ('east', 'west'):
                original = originals[station]
                first = admit(center, original.payload)
                expected = (LEGACY / f'{station}-v1.json').read_bytes()
                self.assertEqual(original.issue_id, first.issue_id)
                self.assertEqual(expected, get_received_issue(center, first.receipt_id).payload)
