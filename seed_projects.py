"""Import only the bundled fictional project fixtures; never read survey data."""
import json
from datetime import datetime, timezone
from pathlib import Path
from database import get_connection, init_db
from rolemesh_matching.integration import run_request

SOURCE = Path(__file__).resolve().parent / "vendor/RoleMesh_matching_v0_1/examples/input.json"
PROJECT_NAMES = {
    "project.education": "虚构教育项目",
    "project.community": "虚构社区项目",
    "project.research": "虚构研究项目",
}
OWNER_ID = "user.demo.project_owner"


def seed_projects():
    sample = json.loads(SOURCE.read_text(encoding="utf-8"))
    run_request(sample)  # Validate source before any inserts.
    if set(r["project_id"] for r in sample["roles"]) != set(PROJECT_NAMES):
        raise ValueError("Unexpected demo project IDs")
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    c = get_connection()
    try:
        with c:
            c.execute("INSERT INTO users(user_id, display_name, created_at) VALUES (?, ?, ?) "
                      "ON CONFLICT(user_id) DO NOTHING", (OWNER_ID, "虚构项目发起人", now))
            for role in sample["roles"]:
                pid = role["project_id"]
                existing = c.execute("SELECT owner_user_id, is_demo FROM projects WHERE project_id = ?", (pid,)).fetchone()
                if existing and (not existing["is_demo"] or existing["owner_user_id"] != OWNER_ID):
                    raise ValueError("Demo ID collides with a different project")
                c.execute(
                    "INSERT INTO projects(project_id, owner_user_id, name, description, domain_codes_json, "
                    "stage, is_demo, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?) "
                    "ON CONFLICT(project_id) DO NOTHING",
                    (pid, OWNER_ID, PROJECT_NAMES[pid], "仅用于本机联调的虚构项目", json.dumps(role["project_domains"]), "recruiting", now, now),
                )
                existing_role = c.execute("SELECT project_id FROM project_roles WHERE role_id = ?", (role["role_id"],)).fetchone()
                if existing_role and existing_role["project_id"] != pid:
                    raise ValueError("Demo role ID collision")
                derived = {"project_id", "role_id", "role_version", "role_code", "name", "duty", "project_domains", "recruitment_status", "openings_remaining"}
                conditions = {k: v for k, v in role.items() if k not in derived}
                c.execute(
                    "INSERT INTO project_roles(role_id, project_id, role_code, name, duty, role_version, "
                    "recruitment_status, required_count, filled_count, conditions_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?) ON CONFLICT(role_id) DO NOTHING",
                    (role["role_id"], pid, role["role_code"], role.get("name", role["role_code"]), role.get("duty", ""),
                     role["role_version"], role["recruitment_status"], max(1, role["openings_remaining"]), json.dumps(conditions, ensure_ascii=False), now, now),
                )
    finally:
        c.close()


if __name__ == "__main__":
    seed_projects()
    print("虚构项目与岗位已准备好。重复运行不会覆盖已有记录。")
