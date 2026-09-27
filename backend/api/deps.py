"""API 依赖注入 — JWT Token 用户认证"""
import jwt
from fastapi import Header, HTTPException
from config import settings


async def get_current_user(
    authorization: str = Header(None, alias="Authorization"),
) -> str:
    """
    从 Authorization 头验证 JWT Token，返回 user_id

    使用方式：请求头带 Authorization: Bearer <token>
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌，请先登录")

    token = authorization.removeprefix("Bearer ")

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload["user_id"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的认证令牌")