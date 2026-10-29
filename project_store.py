"""Database-to-algorithm conversion for explicitly marked demo projects."""
import json
from database import get_connection


def role_to_dto(row):
    # Server-owned identifiers and derived counts override the conditions blob.
    return {
        **json.loads(row["conditions_json"]),
        "project_id": row["project_id"], "role_id": row["role_id"],
        "role_version": row["role_version"], "role_code": row["role_code"],
        "name": row["name"], "duty": row["duty"],
        "project_domains": json.loads(row["domain_codes_json"]),
        "recruitment_status": row["recruitment_status"],
        "openings_remaining": row["required_count"] - row["filled_count"],
    }


def load_demo_roles():
    c = get_connection()
    try:
        rows = c.execute(
            "SELECT r.*, p.domain_codes_json FROM project_roles r "
            "JOIN projects p ON p.project_id = r.project_id "
            "WHERE p.is_demo = 1 ORDER BY r.role_id"
        ).fetchall()
        return [role_to_dto(row) for row in rows]
    finally:
        c.close()


def list_demo_projects(limit, offset):
    c = get_connection()
    try:
        c.execute("BEGIN")
        total = c.execute("SELECT count(*) FROM projects WHERE is_demo = 1").fetchone()[0]
        rows = c.execute(
            "SELECT project_id, name, description, stage, domain_codes_json, updated_at "
            "FROM projects WHERE is_demo = 1 ORDER BY project_id LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["project_domains"] = json.loads(item.pop("domain_codes_json"))
            items.append(item)
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        c.close()


def get_demo_project(project_id):
    c = get_connection()
    try:
        c.execute("BEGIN")
        row = c.execute(
            "SELECT project_id, name, description, stage, domain_codes_json, updated_at "
            "FROM projects WHERE project_id = ? AND is_demo = 1", (project_id,)
        ).fetchone()
        if row is None:
            return None
        project = dict(row)
        project["project_domains"] = json.loads(project.pop("domain_codes_json"))
        roles = c.execute(
            "SELECT r.*, p.domain_codes_json FROM project_roles r "
            "JOIN projects p ON p.project_id = r.project_id "
            "WHERE r.project_id = ? ORDER BY r.role_id", (project_id,)
        ).fetchall()
        project["roles"] = [
            {**role_to_dto(r), "required_count": r["required_count"], "filled_count": r["filled_count"]}
            for r in roles
        ]
        return project
    finally:
        c.close()
