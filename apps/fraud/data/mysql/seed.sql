INSERT INTO customers (customer_id, full_name, risk_level) VALUES
('C1001', 'Alice Smith', 'high'),
('C1002', 'Bob Jones', 'normal'),
('C1003', 'Carol Patel', 'medium'),
('C1004', 'David Chen', 'normal'),
('C1005', 'Evan Brooks', 'high'),
('C1006', 'Farah Khan', 'medium'),
('C1007', 'Grace Miller', 'normal'),
('C1008', 'Hugo Silva', 'normal'),
('C1009', 'Imani Reed', 'medium'),
('C1010', 'Jonas Weber', 'normal')
ON DUPLICATE KEY UPDATE full_name = VALUES(full_name), risk_level = VALUES(risk_level);

INSERT INTO merchants (merchant_id, merchant_name, risk_level) VALUES
('M7001', 'Northwind Electronics', 'high'),
('M7002', 'Green Market', 'normal'),
('M7003', 'Rapid Digital Goods', 'medium'),
('M7004', 'Silverline Travel', 'normal'),
('M7005', 'Vertex Mobile', 'high'),
('M7006', 'Harbor Pharmacy', 'normal')
ON DUPLICATE KEY UPDATE merchant_name = VALUES(merchant_name), risk_level = VALUES(risk_level);

INSERT INTO accounts (account_id, customer_id, account_status, opened_at) VALUES
('A1001', 'C1001', 'active', '2024-01-15 09:00:00'),
('A1002', 'C1001', 'active', '2024-02-20 09:00:00'),
('A1003', 'C1002', 'active', '2023-06-10 09:00:00'),
('A1004', 'C1003', 'frozen', '2022-11-03 09:00:00'),
('A1005', 'C1004', 'active', '2021-09-17 09:00:00'),
('A1006', 'C1005', 'active', '2023-01-08 09:00:00'),
('A1007', 'C1005', 'active', '2024-04-19 09:00:00'),
('A1008', 'C1006', 'active', '2022-05-12 09:00:00'),
('A1009', 'C1007', 'closed', '2020-08-22 09:00:00'),
('A1010', 'C1008', 'active', '2024-03-02 09:00:00'),
('A1011', 'C1009', 'active', '2021-12-14 09:00:00'),
('A1012', 'C1010', 'active', '2023-07-27 09:00:00'),
('A1013', 'C1002', 'active', '2024-08-05 09:00:00'),
('A1014', 'C1003', 'active', '2025-01-04 09:00:00'),
('A1015', 'C1004', 'active', '2022-06-30 09:00:00'),
('A1016', 'C1006', 'active', '2023-09-11 09:00:00')
ON DUPLICATE KEY UPDATE account_status = VALUES(account_status);

INSERT INTO transactions
    (transaction_id, account_id, customer_id, merchant_id, amount, currency, occurred_at, status)
VALUES
('T11001', 'A1001', 'C1001', 'M7001', 1299.99, 'GBP', '2025-01-10 10:15:00', 'approved'),
('T11002', 'A1001', 'C1001', 'M7001', 1180.00, 'GBP', '2025-01-10 10:22:00', 'approved'),
('T11003', 'A1002', 'C1001', 'M7002', 45.60, 'GBP', '2025-01-11 12:05:00', 'approved'),
('T11004', 'A1003', 'C1002', 'M7002', 62.10, 'GBP', '2025-01-11 13:15:00', 'approved'),
('T11005', 'A1004', 'C1003', 'M7003', 799.00, 'GBP', '2025-01-12 16:30:00', 'declined'),
('T11006', 'A1005', 'C1004', 'M7003', 210.25, 'GBP', '2025-01-13 14:40:00', 'approved'),
('T11007', 'A1006', 'C1005', 'M7005', 1800.00, 'GBP', '2025-02-01 08:10:00', 'approved'),
('T11008', 'A1006', 'C1005', 'M7005', 1640.00, 'GBP', '2025-02-01 08:18:00', 'approved'),
('T11009', 'A1007', 'C1005', 'M7001', 420.00, 'GBP', '2025-02-02 10:00:00', 'approved'),
('T11010', 'A1008', 'C1006', 'M7004', 95.20, 'GBP', '2025-02-03 11:35:00', 'approved'),
('T11011', 'A1008', 'C1006', 'M7002', 144.80, 'GBP', '2025-02-04 12:05:00', 'approved'),
('T11012', 'A1008', 'C1006', 'M7003', 310.00, 'GBP', '2025-02-05 13:45:00', 'reversed'),
('T11013', 'A1009', 'C1007', 'M7002', 28.50, 'GBP', '2025-02-06 09:20:00', 'approved'),
('T11014', 'A1009', 'C1007', 'M7004', 72.00, 'GBP', '2025-02-07 16:10:00', 'approved'),
('T11015', 'A1010', 'C1008', 'M7001', 560.00, 'GBP', '2025-02-08 14:30:00', 'approved'),
('T11016', 'A1010', 'C1008', 'M7004', 83.75, 'GBP', '2025-02-09 10:10:00', 'approved'),
('T11017', 'A1011', 'C1009', 'M7003', 1250.00, 'GBP', '2025-02-10 18:30:00', 'declined'),
('T11018', 'A1011', 'C1009', 'M7005', 860.00, 'GBP', '2025-02-11 19:05:00', 'approved'),
('T11019', 'A1012', 'C1010', 'M7002', 210.00, 'GBP', '2025-02-12 08:25:00', 'approved'),
('T11020', 'A1012', 'C1010', 'M7004', 44.95, 'GBP', '2025-02-13 17:15:00', 'approved'),
('T11021', 'A1006', 'C1005', 'M7004', 31.40, 'GBP', '2025-02-14 09:45:00', 'approved'),
('T11022', 'A1008', 'C1006', 'M7002', 67.30, 'GBP', '2025-02-15 15:20:00', 'approved'),
('T11023', 'A1010', 'C1008', 'M7003', 230.00, 'GBP', '2025-02-16 12:40:00', 'approved'),
('T11024', 'A1012', 'C1010', 'M7001', 149.99, 'GBP', '2025-02-17 20:05:00', 'approved'),
('T11025', 'A1013', 'C1002', 'M7004', 118.25, 'GBP', '2025-02-18 09:15:00', 'approved'),
('T11026', 'A1013', 'C1002', 'M7006', 39.90, 'GBP', '2025-02-18 18:25:00', 'approved'),
('T11027', 'A1014', 'C1003', 'M7002', 54.10, 'GBP', '2025-02-19 08:35:00', 'approved'),
('T11028', 'A1014', 'C1003', 'M7006', 88.00, 'GBP', '2025-02-19 15:50:00', 'approved'),
('T11029', 'A1015', 'C1004', 'M7004', 175.40, 'GBP', '2025-02-20 10:05:00', 'approved'),
('T11030', 'A1015', 'C1004', 'M7002', 246.80, 'GBP', '2025-02-20 17:30:00', 'approved'),
('T11031', 'A1016', 'C1006', 'M7006', 24.30, 'GBP', '2025-02-21 09:40:00', 'approved'),
('T11032', 'A1016', 'C1006', 'M7004', 92.75, 'GBP', '2025-02-21 16:15:00', 'approved'),
('T11033', 'A1001', 'C1001', 'M7004', 65.00, 'GBP', '2025-02-22 11:20:00', 'approved'),
('T11034', 'A1002', 'C1001', 'M7006', 35.50, 'GBP', '2025-02-22 19:10:00', 'approved'),
('T11035', 'A1006', 'C1005', 'M7002', 78.90, 'GBP', '2025-02-23 07:55:00', 'approved'),
('T11036', 'A1007', 'C1005', 'M7004', 143.00, 'GBP', '2025-02-23 13:45:00', 'approved'),
('T11037', 'A1008', 'C1006', 'M7003', 45.00, 'GBP', '2025-02-24 09:05:00', 'approved'),
('T11038', 'A1009', 'C1007', 'M7006', 28.75, 'GBP', '2025-02-24 15:35:00', 'approved'),
('T11039', 'A1009', 'C1007', 'M7004', 91.20, 'GBP', '2025-02-25 12:25:00', 'approved'),
('T11040', 'A1009', 'C1007', 'M7002', 22.10, 'GBP', '2025-02-25 18:50:00', 'approved'),
('T11041', 'A1010', 'C1008', 'M7006', 114.00, 'GBP', '2025-02-26 08:40:00', 'approved'),
('T11042', 'A1010', 'C1008', 'M7002', 75.60, 'GBP', '2025-02-26 16:55:00', 'approved'),
('T11043', 'A1011', 'C1009', 'M7004', 43.20, 'GBP', '2025-02-27 10:30:00', 'approved'),
('T11044', 'A1011', 'C1009', 'M7002', 112.00, 'GBP', '2025-02-27 18:05:00', 'approved'),
('T11045', 'A1012', 'C1010', 'M7006', 61.35, 'GBP', '2025-02-28 09:25:00', 'approved'),
('T11046', 'A1012', 'C1010', 'M7004', 87.40, 'GBP', '2025-02-28 17:45:00', 'approved'),
('T11047', 'A1003', 'C1002', 'M7002', 25.00, 'GBP', '2025-03-01 11:10:00', 'approved'),
('T11048', 'A1004', 'C1003', 'M7004', 33.50, 'GBP', '2025-03-01 18:20:00', 'approved'),
('T11049', 'A1005', 'C1004', 'M7006', 19.95, 'GBP', '2025-03-02 09:00:00', 'approved'),
('T11050', 'A1008', 'C1006', 'M7002', 57.15, 'GBP', '2025-03-02 16:40:00', 'approved')
ON DUPLICATE KEY UPDATE status = VALUES(status), amount = VALUES(amount);

INSERT INTO fraud_alerts
    (alert_id, customer_id, transaction_id, alert_type, severity, status, created_at)
VALUES
('ALERT6001', 'C1001', 'T11001', 'shared_device', 'high', 'open', '2025-01-10 10:30:00'),
('ALERT6002', 'C1001', 'T11002', 'transaction_velocity', 'high', 'open', '2025-01-10 10:35:00'),
('ALERT6003', 'C1003', 'T11005', 'watchlist_merchant', 'medium', 'closed', '2025-01-12 16:45:00'),
('ALERT6004', 'C1005', 'T11007', 'transaction_velocity', 'high', 'open', '2025-02-01 08:25:00'),
('ALERT6005', 'C1005', 'T11008', 'high_value_activity', 'high', 'open', '2025-02-01 08:30:00'),
('ALERT6006', 'C1006', 'T11012', 'reversal_pattern', 'medium', 'closed', '2025-02-05 14:00:00'),
('ALERT6007', 'C1008', 'T11015', 'merchant_review', 'low', 'closed', '2025-02-08 15:00:00'),
('ALERT6008', 'C1009', 'T11017', 'watchlist_merchant', 'medium', 'open', '2025-02-10 18:45:00'),
('ALERT6009', 'C1010', 'T11024', 'unusual_location', 'low', 'closed', '2025-02-17 20:30:00'),
('ALERT6010', 'C1002', 'T11004', 'shared_device_review', 'low', 'closed', '2025-01-11 13:30:00'),
('ALERT6011', 'C1004', 'T11006', 'merchant_review', 'low', 'closed', '2025-02-20 18:00:00'),
('ALERT6012', 'C1007', 'T11013', 'account_review', 'medium', 'closed', '2025-02-07 17:00:00')
ON DUPLICATE KEY UPDATE status = VALUES(status), severity = VALUES(severity);

INSERT INTO investigations
    (investigation_id, customer_id, fraud_case_id, status, assigned_to, opened_at)
VALUES
('INV3001', 'C1001', 'F9001', 'open', 'investigator', '2025-01-10 11:00:00'),
('INV3002', 'C1003', 'F9002', 'monitoring', 'investigator', '2025-01-12 17:00:00'),
('INV3003', 'C1005', 'F9003', 'open', 'investigator', '2025-02-01 09:00:00'),
('INV3004', 'C1006', 'F9004', 'closed', 'investigator', '2025-02-06 09:00:00'),
('INV3005', 'C1008', 'F9005', 'monitoring', 'investigator', '2025-02-10 09:00:00'),
('INV3006', 'C1009', 'F9006', 'open', 'investigator', '2025-02-12 09:00:00')
ON DUPLICATE KEY UPDATE status = VALUES(status), assigned_to = VALUES(assigned_to);

INSERT INTO investigation_events (investigation_id, event_type, event_payload, created_at)
SELECT 'INV3001', 'case_opened', JSON_OBJECT('reason', 'shared_device_and_velocity'), '2025-01-10 11:01:00'
WHERE NOT EXISTS (
    SELECT 1 FROM investigation_events
    WHERE investigation_id = 'INV3001' AND event_type = 'case_opened'
);
INSERT INTO investigation_events (investigation_id, event_type, event_payload, created_at)
SELECT 'INV3002', 'alert_reviewed', JSON_OBJECT('reason', 'watchlist_merchant'), '2025-01-12 17:01:00'
WHERE NOT EXISTS (
    SELECT 1 FROM investigation_events
    WHERE investigation_id = 'INV3002' AND event_type = 'alert_reviewed'
);
INSERT INTO investigation_events (investigation_id, event_type, event_payload, created_at)
SELECT 'INV3003', 'case_opened', JSON_OBJECT('reason', 'velocity_and_high_value'), '2025-02-01 09:01:00'
WHERE NOT EXISTS (
    SELECT 1 FROM investigation_events
    WHERE investigation_id = 'INV3003' AND event_type = 'case_opened'
);
INSERT INTO investigation_events (investigation_id, event_type, event_payload, created_at)
SELECT 'INV3004', 'case_closed', JSON_OBJECT('reason', 'reversal_review'), '2025-02-06 09:01:00'
WHERE NOT EXISTS (
    SELECT 1 FROM investigation_events
    WHERE investigation_id = 'INV3004' AND event_type = 'case_closed'
);
INSERT INTO investigation_events (investigation_id, event_type, event_payload, created_at)
SELECT 'INV3005', 'monitoring_started', JSON_OBJECT('reason', 'merchant_review'), '2025-02-10 09:01:00'
WHERE NOT EXISTS (
    SELECT 1 FROM investigation_events
    WHERE investigation_id = 'INV3005' AND event_type = 'monitoring_started'
);
INSERT INTO investigation_events (investigation_id, event_type, event_payload, created_at)
SELECT 'INV3006', 'case_opened', JSON_OBJECT('reason', 'watchlist_merchant'), '2025-02-12 09:01:00'
WHERE NOT EXISTS (
    SELECT 1 FROM investigation_events
    WHERE investigation_id = 'INV3006' AND event_type = 'case_opened'
);
