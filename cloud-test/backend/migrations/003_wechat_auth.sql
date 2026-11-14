CREATE TABLE wechat_accounts (
    app_id TEXT NOT NULL,
    open_id TEXT NOT NULL,
    user_id TEXT NOT NULL UNIQUE REFERENCES users(user_id),
    PRIMARY KEY (app_id, open_id)
);
CREATE TABLE auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    expires_at INTEGER NOT NULL
);
CREATE INDEX auth_sessions_expiry ON auth_sessions(expires_at);
