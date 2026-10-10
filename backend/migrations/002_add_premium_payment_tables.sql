CREATE TABLE IF NOT EXISTS premium_payment_orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL UNIQUE,
    receipt VARCHAR(40) NOT NULL UNIQUE,
    razorpay_order_id VARCHAR(64) UNIQUE,
    amount INTEGER NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'creating',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_premium_payment_orders_id
    ON premium_payment_orders (id);
CREATE INDEX IF NOT EXISTS ix_premium_payment_orders_user_id
    ON premium_payment_orders (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_premium_payment_order_open_user
    ON premium_payment_orders (user_id)
    WHERE status IN ('creating', 'creation_unknown', 'created');

CREATE TABLE IF NOT EXISTS premium_payment_attempts (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    razorpay_payment_id VARCHAR(64) NOT NULL UNIQUE,
    amount INTEGER NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES premium_payment_orders (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_premium_payment_attempts_id
    ON premium_payment_attempts (id);
CREATE INDEX IF NOT EXISTS ix_premium_payment_attempts_order_id
    ON premium_payment_attempts (order_id);
CREATE INDEX IF NOT EXISTS ix_premium_payment_attempts_user_id
    ON premium_payment_attempts (user_id);

CREATE TABLE IF NOT EXISTS premium_payment_webhook_events (
    id INTEGER PRIMARY KEY,
    provider_event_id VARCHAR(128) NOT NULL UNIQUE,
    event_type VARCHAR(64) NOT NULL,
    processed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_premium_payment_webhook_events_id
    ON premium_payment_webhook_events (id);
