"""测试: api/deps.py — JWT Token 认证依赖"""

import jwt
import pytest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from unittest.mock import patch


class TestGetCurrentUser:

    def test_valid_token_returns_user_id(self):
        """合法 Bearer token → 返回 user_id"""
        from api.deps import get_current_user
        token = jwt.encode(
            {"user_id": "user123", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "test-secret", algorithm="HS256",
        )
        result = get_current_user(authorization=f"Bearer {token}")
        # 需要用 pytest-asyncio 运行异步函数
        import asyncio
        user_id = asyncio.run(result)
        assert user_id == "user123"

    def test_missing_header_raises_401(self):
        """无 Authorization 头 → 401"""
        import asyncio
        from api.deps import get_current_user
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_current_user(authorization=None))
        assert exc.value.status_code == 401
        assert "未提供认证令牌" in exc.value.detail

    def test_not_bearer_format_raises_401(self):
        """非 Bearer 格式 → 401"""
        import asyncio
        from api.deps import get_current_user
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_current_user(authorization="Token abc123"))
        assert exc.value.status_code == 401
        assert "未提供认证令牌" in exc.value.detail

    def test_expired_token_raises_401(self):
        """过期 token → 401"""
        import asyncio
        from api.deps import get_current_user
        token = jwt.encode(
            {"user_id": "user123", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
            "test-secret", algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_current_user(authorization=f"Bearer {token}"))
        assert exc.value.status_code == 401
        assert "登录已过期" in exc.value.detail

    def test_invalid_token_raises_401(self):
        """无效 token → 401"""
        import asyncio
        from api.deps import get_current_user
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_current_user(authorization="Bearer invalid.token.here"))
        assert exc.value.status_code == 401
        assert "无效的认证令牌" in exc.value.detail
