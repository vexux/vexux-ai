CREATE TABLE accounts (
    account_id TEXT,
    customer_id TEXT,
    status TEXT
);
INSERT INTO accounts VALUES ('A100', 'C1001', 'active');
INSERT INTO accounts VALUES ('A200', 'C1002', 'active');

CREATE TABLE transactions (
    transaction_id TEXT,
    account_id TEXT,
    customer_id TEXT,
    merchant_id TEXT,
    amount REAL,
    status TEXT,
    occurred_at TEXT
);
INSERT INTO transactions
VALUES ('T1001', 'A100', 'C1001', 'M100', 120.0, 'posted', '2026-01-01');
INSERT INTO transactions
VALUES ('T2001', 'A200', 'C1002', 'M200', 70.0, 'posted', '2026-01-02');
INSERT INTO transactions
VALUES ('T2002', 'A200', 'C1002', 'M200', 25.0, 'posted', '2026-01-03');

CREATE TABLE fraud_alerts (
    alert_id TEXT,
    customer_id TEXT,
    transaction_id TEXT,
    alert_type TEXT,
    severity TEXT,
    status TEXT,
    created_at TEXT
);
INSERT INTO fraud_alerts
VALUES ('AL1001', 'C1001', 'T1001', 'velocity', 'high', 'open', '2026-01-01');
INSERT INTO fraud_alerts
VALUES ('AL2001', 'C1002', 'T2001', 'device_review', 'low', 'closed', '2026-01-02');

CREATE TABLE investigations (
    investigation_id TEXT,
    customer_id TEXT,
    fraud_case_id TEXT,
    status TEXT,
    opened_at TEXT
);
INSERT INTO investigations
VALUES ('I1001', 'C1001', 'F900', 'open', '2026-01-01');
