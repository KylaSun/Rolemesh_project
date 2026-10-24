import json
from datetime import datetime, timezone

from database import get_connection, init_db


def seed_demo():
    init_db()
    now = datetime.now(timezone.utc).isoformat()

    # 仅用于本地开发的虚构画像
    profile = {
        "profile_id": "profile.demo.1",
        "profile_version": 1,
        "skills": [
            {
                "skill_code": "skill.react",
                "level": 3,
                "assessment_source": "self_reported"
            }
        ],
        "intended_roles": ["role.frontend"],
        "primary_role": "role.frontend",
        "domain_interests": ["domain.education"],
        "domain_preference_any": False,
        "availability_hours_per_week": 6,
        "collaboration_modes": ["remote"],
        "collaboration_any": False,
        "languages": ["zh"],
        "field_status": {
            "skills": "provided",
            "intended_roles": "provided",
            "domain_interests": "provided",
            "collaboration_modes": "provided",
            "languages": "provided"
        }
    }

    connection = get_connection()

    try:
        with connection:
            connection.execute(
                """
                INSERT INTO users (
                    user_id, display_name, created_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                ("user.demo.1", "虚构测试用户", now)
            )

            connection.execute(
                """
                INSERT INTO talent_profiles (
                    profile_id,
                    user_id,
                    profile_version,
                    profile_json,
                    visibility,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO NOTHING
                """,
                (
                    profile["profile_id"],
                    "user.demo.1",
                    profile["profile_version"],
                    json.dumps(profile, ensure_ascii=False),
                    "private",
                    now
                )
            )

        row = connection.execute(
            """
            SELECT profile_json, visibility
            FROM talent_profiles
            WHERE profile_id = ?
            """,
            (profile["profile_id"],)
        ).fetchone()

        saved_profile = json.loads(row["profile_json"])

        print("已从数据库读取虚构画像：")
        print(json.dumps(saved_profile, ensure_ascii=False, indent=2))
        print("展示权限：", row["visibility"])
    finally:
        connection.close()


if __name__ == "__main__":
    seed_demo()