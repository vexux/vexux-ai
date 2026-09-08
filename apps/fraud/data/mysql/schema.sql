CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(32) PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    risk_level ENUM('normal', 'medium', 'high') NOT NULL DEFAULT 'normal',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS merchants (
    merchant_id VARCHAR(32) PRIMARY KEY,
    merchant_name VARCHAR(200) NOT NULL,
    risk_level ENUM('normal', 'medium', 'high') NOT NULL DEFAULT 'normal'
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL,
    account_status ENUM('active', 'frozen', 'closed') NOT NULL DEFAULT 'active',
    opened_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_accounts_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    INDEX idx_accounts_customer (customer_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id VARCHAR(32) PRIMARY KEY,
    account_id VARCHAR(32) NOT NULL,
    customer_id VARCHAR(32) NOT NULL,
    merchant_id VARCHAR(32) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    status ENUM('approved', 'declined', 'reversed') NOT NULL,
    CONSTRAINT fk_transactions_account FOREIGN KEY (account_id) REFERENCES accounts(account_id),
    CONSTRAINT fk_transactions_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    CONSTRAINT fk_transactions_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id),
    INDEX idx_transactions_customer_time (customer_id, occurred_at),
    INDEX idx_transactions_account_time (account_id, occurred_at)
);

CREATE TABLE IF NOT EXISTS fraud_alerts (
    alert_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL,
    transaction_id VARCHAR(32),
    alert_type VARCHAR(80) NOT NULL,
    severity ENUM('low', 'medium', 'high') NOT NULL,
    status ENUM('open', 'closed') NOT NULL DEFAULT 'open',
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_alert_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    CONSTRAINT fk_alert_transaction FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
    INDEX idx_alert_customer_status (customer_id, status)
);

CREATE TABLE IF NOT EXISTS investigations (
    investigation_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL,
    fraud_case_id VARCHAR(32) NOT NULL,
    status ENUM('open', 'monitoring', 'closed') NOT NULL DEFAULT 'open',
    assigned_to VARCHAR(120),
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP NULL,
    CONSTRAINT fk_investigation_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    INDEX idx_investigation_customer_status (customer_id, status)
);

CREATE TABLE IF NOT EXISTS investigation_events (
    event_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    investigation_id VARCHAR(32) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    event_payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_event_investigation FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id),
    INDEX idx_event_investigation_time (investigation_id, created_at)
);
