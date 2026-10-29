CREATE TABLE IF NOT EXISTS survey_profile_details (
    profile_id TEXT PRIMARY KEY,
    source_record_id INTEGER NOT NULL UNIQUE,
    details_json TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES talent_profiles(profile_id) ON DELETE CASCADE
);
