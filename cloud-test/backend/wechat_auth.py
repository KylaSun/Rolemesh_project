"""Exchange a mini-program login code and issue a server-side session."""
import hashlib
import json
import os
import secrets
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

from database import get_connection

router = APIRouter(prefix="/api/v1/auth", tags=["微信登录"])
APP_ID = "wxf1025b3e76e1fe29"
SESSION_SECONDS = 7 * 24 * 60 * 60


class LoginBody(BaseModel):
    code: str = Field(min_length=1, max_length=256)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def exchange_code(code):
    secret = os.environ.get("ROLEMESH_WECHAT_APP_SECRET", "").strip()
    if not secret:
        raise HTTPException(503, "微信登录服务尚未配置")
    query = urlencode({
        "appid": APP_ID,
        "secret": secret,
        "js_code": code,
        "grant_type": "authorization_code",
    })
    try:
        with urlopen("https://api.weixin.qq.com/sns/jscode2session?" + query, timeout=5) as result:
            payload = json.loads(result.read(16384))
    except (OSError, ValueError):
        raise HTTPException(502, "微信登录服务暂不可用") from None
    if not isinstance(payload, dict):
        raise HTTPException(502, "微信登录服务返回异常")
    if payload.get("errcode") in (40029, 40163):
        raise HTTPException(401, "登录凭证已失效，请重试")
    open_id = payload.get("openid")
    if payload.get("errcode") or not isinstance(open_id, str) or not open_id:
        raise HTTPException(502, "微信身份验证暂不可用")
    return open_id


@router.post("/login")
def login(body: LoginBody, response: Response):
    open_id = exchange_code(body.code)
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    with closing(get_connection()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        account = db.execute(
            "SELECT user_id FROM wechat_accounts WHERE app_id=? AND open_id=?",
            (APP_ID, open_id),
        ).fetchone()
        if account:
            user_id = account["user_id"]
        else:
            user_id = f"user.wx.{uuid.uuid4().hex}"
            db.execute(
                "INSERT INTO users (user_id, display_name, created_at) VALUES (?, ?, ?)",
                (user_id, "RoleMesh 用户", datetime.now(timezone.utc).isoformat()),
            )
            db.execute("INSERT INTO wechat_accounts VALUES (?, ?, ?)", (APP_ID, open_id, user_id))
        db.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))
        db.execute("INSERT INTO auth_sessions VALUES (?, ?, ?)", (digest(token), user_id, now + SESSION_SECONDS))
    response.headers["Cache-Control"] = "no-store"
    return {"code": 0, "data": {"token": token, "user_id": user_id}}


@router.get("/me")
def me(response: Response, authorization: str = Header(default="")):
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 128:
        raise HTTPException(401, "请先登录")
    with closing(get_connection()) as db:
        user = db.execute(
            "SELECT users.user_id, users.display_name FROM auth_sessions JOIN users USING(user_id) "
            "WHERE token_hash=? AND expires_at>?",
            (digest(token), int(time.time())),
        ).fetchone()
    if not user:
        raise HTTPException(401, "登录已失效")
    response.headers["Cache-Control"] = "no-store"
    return {"code": 0, "data": dict(user)}
