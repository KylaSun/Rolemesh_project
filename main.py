import json

from fastapi import FastAPI, HTTPException

from database import get_connection

from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="RoleMesh Backend", version="0.1.0")


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "RoleMesh 后端运行正常"
    }


@app.get("/demo/profile", tags=["本地演示"])
def get_demo_profile():
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT profile_json
            FROM talent_profiles
            WHERE profile_id = ? AND user_id = ?
            """,
            ("profile.demo.1", "user.demo.1")
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="虚构画像不存在，请先运行 seed_demo.py"
        )

    return {
        "data": json.loads(row["profile_json"])
    }

class DemoHoursUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    availability_hours_per_week: float = Field(
        ge=0,
        le=168,
        allow_inf_nan=False,
        strict=True
    )


@app.patch("/demo/profile/hours", tags=["本地演示"])
def update_demo_hours(body: DemoHoursUpdate):
    connection = get_connection()

    try:
        # 将读取和修改放在同一个写事务里
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            """
            SELECT profile_json, profile_version
            FROM talent_profiles
            WHERE profile_id = ? AND user_id = ?
            """,
            ("profile.demo.1", "user.demo.1")
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="虚构画像不存在，请先运行 seed_demo.py"
            )

        profile = json.loads(row["profile_json"])
        new_version = row["profile_version"] + 1

        profile["availability_hours_per_week"] = (
            body.availability_hours_per_week
        )
        profile["profile_version"] = new_version
        profile.setdefault("field_status", {})[
            "availability_hours_per_week"
        ] = "provided"

        now = datetime.now(timezone.utc).isoformat()

        connection.execute(
            """
            UPDATE talent_profiles
            SET profile_json = ?,
                profile_version = ?,
                updated_at = ?
            WHERE profile_id = ? AND user_id = ?
            """,
            (
                json.dumps(profile, ensure_ascii=False),
                new_version,
                now,
                "profile.demo.1",
                "user.demo.1"
            )
        )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return {"data": profile}