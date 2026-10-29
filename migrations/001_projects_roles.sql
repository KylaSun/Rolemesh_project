-- Additive migration: does not change existing users or profiles.
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id),
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    description TEXT NOT NULL DEFAULT '',
    domain_codes_json TEXT NOT NULL CHECK(json_valid(domain_codes_json)),
    stage TEXT NOT NULL CHECK(stage IN ('idea', 'recruiting', 'ongoing', 'sprint', 'finished')),
    is_demo INTEGER NOT NULL DEFAULT 1 CHECK(is_demo IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE project_roles (
    role_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    role_code TEXT NOT NULL,
    name TEXT NOT NULL,
    duty TEXT NOT NULL DEFAULT '',
    role_version INTEGER NOT NULL CHECK(role_version >= 1),
    recruitment_status TEXT NOT NULL CHECK(recruitment_status IN ('open', 'paused', 'closed', 'full')),
    required_count INTEGER NOT NULL CHECK(required_count >= 1),
    filled_count INTEGER NOT NULL DEFAULT 0 CHECK(filled_count >= 0 AND filled_count <= required_count),
    conditions_json TEXT NOT NULL CHECK(json_valid(conditions_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_project_roles_project ON project_roles(project_id);
CREATE INDEX idx_project_roles_recruitment ON project_roles(recruitment_status);
