PRAGMA foreign_keys = ON;
BEGIN;
CREATE TABLE plate_rosters (plate_id TEXT NOT NULL PRIMARY KEY, definition TEXT NOT NULL);
CREATE TABLE observations (
    observation_id INTEGER PRIMARY KEY,
    plate_id TEXT NOT NULL REFERENCES plate_rosters(plate_id),
    station_id TEXT NOT NULL, slot TEXT NOT NULL,
    detected INTEGER NOT NULL CHECK (detected IN (0, 1)),
    instrument TEXT NOT NULL, source_ref TEXT NOT NULL,
    supersedes_id INTEGER UNIQUE REFERENCES observations(observation_id)
);
CREATE TABLE current_observations (
    plate_id TEXT NOT NULL REFERENCES plate_rosters(plate_id),
    station_id TEXT NOT NULL, slot TEXT NOT NULL,
    observation_id INTEGER NOT NULL UNIQUE REFERENCES observations(observation_id),
    PRIMARY KEY (plate_id, station_id, slot)
);
CREATE TABLE frozen_revisions (
    freeze_id INTEGER PRIMARY KEY,
    plate_id TEXT NOT NULL REFERENCES plate_rosters(plate_id), station_id TEXT NOT NULL
);
CREATE TABLE frozen_slots (
    freeze_id INTEGER NOT NULL REFERENCES frozen_revisions(freeze_id),
    position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 7),
    observation_id INTEGER NOT NULL REFERENCES observations(observation_id),
    PRIMARY KEY (freeze_id, position), UNIQUE (freeze_id, observation_id)
);
CREATE TABLE issued_documents (
    freeze_id INTEGER PRIMARY KEY REFERENCES frozen_revisions(freeze_id),
    issue_id TEXT NOT NULL UNIQUE, payload BLOB NOT NULL
);
INSERT INTO plate_rosters VALUES ('LEG-04', '{"slots":["1","2","3","4"],"protocol":{"a":{"station":"west","scheme":"spray-A"},"b":{"station":"east","scheme":"spray-B"}}}');
INSERT INTO observations VALUES (101, 'LEG-04', 'west', '1', 0, 'legacy-west', 'line-101', NULL);
INSERT INTO observations VALUES
    (102, 'LEG-04', 'west', '2', 1, 'legacy-west', 'line-102', NULL),
    (103, 'LEG-04', 'west', '3', 1, 'legacy-west', 'line-103', NULL),
    (104, 'LEG-04', 'west', '4', 0, 'legacy-west', 'line-104', NULL),
    (105, 'LEG-04', 'west', '1', 1, 'legacy-west', 'line-105', 101);
INSERT INTO current_observations VALUES
    ('LEG-04', 'west', '1', 105), ('LEG-04', 'west', '2', 102),
    ('LEG-04', 'west', '3', 103), ('LEG-04', 'west', '4', 104);
INSERT INTO frozen_revisions VALUES (6, 'LEG-04', 'west'), (7, 'LEG-04', 'west');
INSERT INTO frozen_slots VALUES
    (6, 0, 101), (6, 1, 102), (6, 2, 103), (6, 3, 104),
    (7, 0, 105), (7, 1, 102), (7, 2, 103), (7, 3, 104);
INSERT INTO issued_documents VALUES (7, 'v1:LEG-04:west:7', CAST('{"decisions":[["1",1],["2",1],["3",1],["4",0]],"freeze_id":7,"issue_id":"v1:LEG-04:west:7","plate_id":"LEG-04","protocol":{"a":{"scheme":"spray-A","station":"west"},"b":{"scheme":"spray-B","station":"east"}},"slots":["1","2","3","4"],"station_id":"west","version":1}' || char(10) AS BLOB));
COMMIT;
