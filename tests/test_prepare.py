from contextlib import closing

from blindplate.plate.protocol import build_protocol
from blindplate.plate.register import get_roster, register
from blindplate.reading.admission import record
from blindplate.reading.correction import correct
from blindplate.reading.freeze import freeze
from blindplate.reading.observation import InstrumentSource
from blindplate.reading.revisions import get_current_observations, get_observation, load_frozen_revision
from tests.fixtures import DatabaseCase, PROTOCOL, initialize_station, open_station, source


class TestPrepare(DatabaseCase):
    def test_freeze_complete_board(self):
        slots = ('3', '1', '4', '2')
        readings = {'3': 0, '1': 1, '4': 0, '2': 1}
        with closing(open_station(self.directory / 'station.sqlite')) as db:
            roster = register(db, 'P-1', slots, PROTOCOL)
            self.assertEqual(slots, roster.slots.slots)
            self.assertEqual(roster, register(db, 'P-1', list(slots), PROTOCOL))
            self.assertEqual(2, roster.slots.position('4'))
            for invalid in ((), ('1', '1'), tuple(str(i) for i in range(9)), ('',), ('1', 2), '123'):
                with self.subTest(roster=invalid), self.assertRaises(ValueError):
                    register(db, 'invalid', invalid, PROTOCOL)
            with self.assertRaises(KeyError):
                get_roster(db, 'invalid')
            with self.assertRaises(ValueError):
                build_protocol('west', 'spray-A', 'west', 'spray-B')
            with self.assertRaises(ValueError):
                register(db, 'P-1', tuple(reversed(slots)), PROTOCOL)
            with self.assertRaises(ValueError):
                register(db, 'P-1', slots, build_protocol('east', 'spray-A', 'west', 'spray-B'))
            self.assertEqual(roster, get_roster(db, 'P-1'))

            for slot in reversed(slots):
                record(db, 'P-1', 'west', slot, readings[slot], source('west', slot))
            before = get_current_observations(db, 'P-1', 'west')
            with self.assertRaises(KeyError):
                record(db, 'unknown', 'west', '3', 0, source('west', '3'))
            for station, slot, value in (('north', '3', 0), ('west', '5', 1), ('west', '3', 1),
                                         ('east', '3', 2), ('east', '3', True), ('east', '3', 1.0)):
                with self.subTest(station=station, slot=slot, value=value), self.assertRaises(ValueError):
                    record(db, 'P-1', station, slot, value, source(station, slot))
            with self.assertRaises(ValueError):
                record(db, 'P-1', 'east', '3', 1, None)
            self.assertEqual(before, get_current_observations(db, 'P-1', 'west'))
            self.assertEqual({}, get_current_observations(db, 'P-1', 'east'))
            frozen = load_frozen_revision(db, freeze(db, 'P-1', 'west'))
            self.assertEqual(('3', '1', '4', '2'), tuple(row.slot for row in frozen.observations))
            self.assertEqual((0, 1, 0, 1), tuple(row.detected for row in frozen.observations))
            self.assertEqual(tuple(before[slot] for slot in slots), frozen.observations)

    def test_missing_slot_rejects_freeze(self):
        with closing(open_station(self.directory / 'station.sqlite')) as db:
            register(db, 'P-2', ('2', '1'), PROTOCOL)
            record(db, 'P-2', 'east', '2', 1, source('east', '2'))
            with self.assertRaises(KeyError):
                freeze(db, 'unknown', 'east')
            with self.assertRaises(ValueError):
                freeze(db, 'P-2', 'north')
            with self.assertRaises(ValueError):
                freeze(db, 'P-2', 'east')
            self.assertEqual((0,), db.execute('SELECT COUNT(*) FROM frozen_revisions').fetchone())
            self.assertEqual((0,), db.execute('SELECT COUNT(*) FROM frozen_slots').fetchone())
            record(db, 'P-2', 'east', '1', 0, source('east', '1'))
            completed = load_frozen_revision(db, freeze(db, 'P-2', 'east'))
            self.assertEqual([('2', 1), ('1', 0)], [(row.slot, row.detected) for row in completed.observations])

    def test_correction_does_not_change_prior_freeze(self):
        path = self.directory / 'station.sqlite'
        first_source = InstrumentSource('spectrometer-2', 'trace-45')
        corrected_source = InstrumentSource('spectrometer-2', 'trace-45-confirmed')
        with closing(open_station(path)) as db:
            register(db, 'P-3', ('2', '1'), PROTOCOL)
            old_id = record(db, 'P-3', 'west', '2', 0, first_source)
            record(db, 'P-3', 'west', '1', 1, source('west', '1'))
            old_freeze = freeze(db, 'P-3', 'west')
            first = load_frozen_revision(db, old_freeze)
            with self.assertRaises(KeyError):
                correct(db, 9000, 1, corrected_source)
            with self.assertRaises(ValueError):
                correct(db, old_id, 2, corrected_source)
            new_id = correct(db, old_id, 1, corrected_source)
            self.assertNotEqual(old_id, new_id)
            with self.assertRaises(ValueError):
                correct(db, old_id, 0, first_source)
            new_freeze = freeze(db, 'P-3', 'west')
            second = load_frozen_revision(db, new_freeze)
            self.assertNotEqual(old_freeze, new_freeze)
            original, replacement = first.observations[0], second.observations[0]
            self.assertEqual((old_id, '2', 0, first_source),
                             (original.observation_id, original.slot, original.detected, original.source))
            self.assertEqual((new_id, '2', 1, corrected_source, old_id),
                             (replacement.observation_id, replacement.slot, replacement.detected,
                              replacement.source, replacement.supersedes_id))
            self.assertEqual(first.observations[1], second.observations[1])
            self.assertEqual(replacement, get_current_observations(db, 'P-3', 'west')['2'])
        with closing(open_station(path)) as reopened:
            initialize_station(reopened)
            self.assertEqual(first, load_frozen_revision(reopened, old_freeze))
            self.assertEqual(second, load_frozen_revision(reopened, new_freeze))
            self.assertEqual(original, get_observation(reopened, old_id))
            self.assertEqual(replacement, get_current_observations(reopened, 'P-3', 'west')['2'])
