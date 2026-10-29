import json
import logging

from rolemesh_matching.integration import ContractError, run_request

from fastapi import FastAPI, HTTPException, Response, Query

from database import get_connection
from project_store import load_demo_roles, list_demo_projects, get_demo_project

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

logger = logging.getLogger(__name__)


@app.get(
    "/demo/matches",
    tags=["本地演示"],
    summary="数据库虚构画像与数据库岗位匹配",
    description=(
        "仅供本机演示，固定读取 profile.demo.1。"
        "岗位读取数据库中标记为演示的项目，样例由 seed_projects.py 导入。"
        "无正式登录，不可作为真实用户画像接口部署。"
        "每次请求重新计算，不缓存旧版本结果。"
    ),
)
def get_demo_matches(response: Response):
    response.headers["Cache-Control"] = "no-store"
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT profile_json, profile_version FROM talent_profiles "
            "WHERE profile_id = ? AND user_id = ?",
            ("profile.demo.1", "user.demo.1"),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise HTTPException(status_code=404, detail="虚构画像不存在，请先运行 seed_demo.py")

    try:
        profile = json.loads(row["profile_json"])
        if (
            profile.get("profile_id") != "profile.demo.1"
            or profile.get("profile_version") != row["profile_version"]
        ):
            raise ValueError("Stored profile identity or version mismatch")
        roles = load_demo_roles()
        result = run_request({
            "contract_version": "0.1.0",
            "profile": profile,
            "roles": roles,
        })
    except ContractError as error:
        # Input is read from server storage, not submitted by this request.
        # Do not expose stored values or disguise server errors as an empty list.
        logger.error("Demo matching contract error: %s", error.code)
        raise HTTPException(status_code=500, detail="演示数据不符合算法契约，请检查后端数据") from error
    except Exception as error:
        logger.error("Demo matching failed: %s", type(error).__name__)
        raise HTTPException(status_code=500, detail="匹配服务暂不可用，请检查后端日志") from error

    return {
        "data": result,
        "meta": {
            "demo_only": True,
            "profile_source": "sqlite",
            "roles_source": "sqlite",
            "profile_id": profile["profile_id"],
            "profile_version": profile["profile_version"],
        },
    }


@app.get("/demo/projects", tags=["本地演示"], summary="查看数据库中的虚构项目列表")
def demo_project_list(response: Response, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    response.headers["Cache-Control"] = "no-store"
    return {"data": list_demo_projects(limit, offset), "meta": {"demo_only": True, "source": "sqlite"}}


@app.get("/demo/projects/{project_id}", tags=["本地演示"], summary="查看虚构项目及其岗位要求")
def demo_project_detail(project_id: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    project = get_demo_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="虚构项目不存在")
    return {"data": project, "meta": {"demo_only": True, "source": "sqlite"}}
