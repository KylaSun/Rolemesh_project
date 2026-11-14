-- Opt-in standalone matching analytics store. NOT an automatic business migration.
CREATE TABLE IF NOT EXISTS matching_events (
    event_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'recommendation_generated', 'application_submitted', 'member_confirmed', 'feedback_recorded')),
    occurred_at TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    subject_user_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    recommendation_id TEXT NOT NULL REFERENCES matching_events(event_id),
    application_id TEXT,
    membership_id TEXT,
    event_json TEXT NOT NULL CHECK(json_valid(event_json))
);
CREATE INDEX IF NOT EXISTS matching_events_cohort ON matching_events(event_type, occurred_at);
CREATE INDEX IF NOT EXISTS matching_events_attribution ON matching_events(recommendation_id, event_type);
CREATE UNIQUE INDEX IF NOT EXISTS matching_event_application_once
    ON matching_events(application_id) WHERE event_type = 'application_submitted';
CREATE UNIQUE INDEX IF NOT EXISTS matching_event_membership_once
    ON matching_events(membership_id) WHERE event_type = 'member_confirmed';
