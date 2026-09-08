INSERT INTO customers (customer_id, full_name, risk_level) VALUES
('C1001', 'Alice Smith', 'high'),
('C1002', 'Bob Jones', 'normal'),
('C1003', 'Carol Patel', 'medium'),
('C1004', 'David Chen', 'normal')
ON DUPLICATE KEY UPDATE full_name = VALUES(full_name), risk_level = VALUES(risk_level);

INSERT INTO merchants (merchant_id, merchant_name, risk_level) VALUES
('M7001', 'Northwind Electronics', 'high'),
('M7002', 'Green Market', 'normal'),
('M7003', 'Rapid Digital Goods', 'medium')
ON DUPLICATE KEY UPDATE merchant_name = VALUES(merchant_name), risk_level = VALUES(risk_level);

INSERT INTO accounts (account_id, customer_id, account_status, opened_at) VALUES
('A1001', 'C1001', 'active', '2024-01-15 09:00:00'),
('A1002', 'C1001', 'active', '2024-02-20 09:00:00'),
('A1003', 'C1002', 'active', '2023-06-10 09:00:00'),
('A1004', 'C1003', 'frozen', '2022-11-03 09:00:00'),
('A1005', 'C1004', 'active', '2021-09-17 09:00:00')
ON DUPLICATE KEY UPDATE account_status = VALUES(account_status);

INSERT INTO transactions
    (transaction_id, account_id, customer_id, merchant_id, amount, currency, occurred_at, status)
VALUES
('T11001', 'A1001', 'C1001', 'M7001', 1299.99, 'GBP', '2025-01-10 10:15:00', 'approved'),
('T11002', 'A1001', 'C1001', 'M7001', 1180.00, 'GBP', '2025-01-10 10:22:00', 'approved'),
('T11003', 'A1002', 'C1001', 'M7002', 45.60, 'GBP', '2025-01-11 12:05:00', 'approved'),
('T11004', 'A1003', 'C1002', 'M7002', 62.10, 'GBP', '2025-01-11 13:15:00', 'approved'),
('T11005', 'A1004', 'C1003', 'M7003', 799.00, 'GBP', '2025-01-12 16:30:00', 'declined'),
('T11006', 'A1005', 'C1004', 'M7003', 210.25, 'GBP', '2025-01-13 14:40:00', 'approved')
ON DUPLICATE KEY UPDATE status = VALUES(status), amount = VALUES(amount);

INSERT INTO fraud_alerts
    (alert_id, customer_id, transaction_id, alert_type, severity, status, created_at)
VALUES
('ALERT6001', 'C1001', 'T11001', 'shared_device', 'high', 'open', '2025-01-10 10:30:00'),
('ALERT6002', 'C1001', 'T11002', 'transaction_velocity', 'high', 'open', '2025-01-10 10:35:00'),
('ALERT6003', 'C1003', 'T11005', 'watchlist_merchant', 'medium', 'closed', '2025-01-12 16:45:00')
ON DUPLICATE KEY UPDATE status = VALUES(status), severity = VALUES(severity);

INSERT INTO investigations
    (investigation_id, customer_id, fraud_case_id, status, assigned_to, opened_at)
VALUES
('INV3001', 'C1001', 'F9001', 'open', 'investigator', '2025-01-10 11:00:00'),
('INV3002', 'C1003', 'F9002', 'monitoring', 'investigator', '2025-01-12 17:00:00')
ON DUPLICATE KEY UPDATE status = VALUES(status), assigned_to = VALUES(assigned_to);

INSERT INTO investigation_events (investigation_id, event_type, event_payload, created_at) VALUES
('INV3001', 'case_opened', JSON_OBJECT('reason', 'shared_device_and_velocity'), '2025-01-10 11:01:00'),
('INV3002', 'alert_reviewed', JSON_OBJECT('reason', 'watchlist_merchant'), '2025-01-12 17:01:00');
