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
INSERT INTO observations VALUES
    (201, 'LEG-04', 'east', '1', 0, 'legacy-east', 'line-201', NULL),
    (202, 'LEG-04', 'east', '2', 0, 'legacy-east', 'line-202', NULL),
    (203, 'LEG-04', 'east', '3', 0, 'legacy-east', 'line-203', NULL),
    (204, 'LEG-04', 'east', '4', 1, 'legacy-east', 'line-204', NULL);
INSERT INTO current_observations VALUES
    ('LEG-04', 'east', '1', 201), ('LEG-04', 'east', '2', 202),
    ('LEG-04', 'east', '3', 203), ('LEG-04', 'east', '4', 204);
INSERT INTO frozen_revisions VALUES (9, 'LEG-04', 'east');
INSERT INTO frozen_slots VALUES (9, 0, 201), (9, 1, 202), (9, 2, 203), (9, 3, 204);
INSERT INTO issued_documents VALUES (9, 'v1:LEG-04:east:9', CAST('{"decisions":[["1",0],["2",0],["3",0],["4",1]],"freeze_id":9,"issue_id":"v1:LEG-04:east:9","plate_id":"LEG-04","protocol":{"a":{"scheme":"spray-A","station":"west"},"b":{"scheme":"spray-B","station":"east"}},"slots":["1","2","3","4"],"station_id":"east","version":1}' || char(10) AS BLOB));
COMMIT;
