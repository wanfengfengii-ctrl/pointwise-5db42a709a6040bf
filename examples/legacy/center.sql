PRAGMA foreign_keys = ON;
BEGIN;
CREATE TABLE received_issues (
    receipt_id INTEGER PRIMARY KEY, issue_id TEXT NOT NULL UNIQUE,
    payload BLOB NOT NULL, acknowledgement TEXT NOT NULL UNIQUE
);
CREATE TABLE reports (report_id INTEGER PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE report_receipts (
    report_id INTEGER PRIMARY KEY REFERENCES reports(report_id), acknowledgement TEXT NOT NULL UNIQUE
);
INSERT INTO received_issues VALUES (
    11, 'v1:LEG-04:east:9',
    CAST('{"decisions":[["1",0],["2",0],["3",0],["4",1]],"freeze_id":9,"issue_id":"v1:LEG-04:east:9","plate_id":"LEG-04","protocol":{"a":{"scheme":"spray-A","station":"west"},"b":{"scheme":"spray-B","station":"east"}},"slots":["1","2","3","4"],"station_id":"east","version":1}' || char(10) AS BLOB),
    'received:v1:LEG-04:east:9'
);
INSERT INTO received_issues VALUES (
    12, 'v1:LEG-04:west:7',
    CAST('{"decisions":[["1",1],["2",1],["3",1],["4",0]],"freeze_id":7,"issue_id":"v1:LEG-04:west:7","plate_id":"LEG-04","protocol":{"a":{"scheme":"spray-A","station":"west"},"b":{"scheme":"spray-B","station":"east"}},"slots":["1","2","3","4"],"station_id":"west","version":1}' || char(10) AS BLOB),
    'received:v1:LEG-04:west:7'
);
INSERT INTO reports VALUES (17, '{"a":{"freeze_id":7,"issue_id":"v1:LEG-04:west:7","receipt_id":12},"a_only":["1","2","3"],"b":{"freeze_id":9,"issue_id":"v1:LEG-04:east:9","receipt_id":11},"b_only":["4"],"plate_id":"LEG-04","probability":[5,16]}');
INSERT INTO report_receipts VALUES (17, 'signed:17');
COMMIT;
