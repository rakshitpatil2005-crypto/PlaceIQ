CREATE TABLE IF NOT EXISTS premium_subscriptions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    plan VARCHAR NOT NULL DEFAULT 'free',
    status VARCHAR NOT NULL DEFAULT 'inactive',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_premium_subscriptions_id
    ON premium_subscriptions (id);
CREATE INDEX IF NOT EXISTS ix_premium_subscriptions_user_id
    ON premium_subscriptions (user_id);

CREATE TABLE IF NOT EXISTS premium_access_requests (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_premium_access_requests_id
    ON premium_access_requests (id);
CREATE INDEX IF NOT EXISTS ix_premium_access_requests_user_id
    ON premium_access_requests (user_id);
