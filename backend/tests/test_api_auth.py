"""测试: api/v1/auth.py — 用户认证 API"""

import jwt
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestCreateJWTToken:

    def test_returns_jwt_string(self):
        """create_jwt_token 应返回合法 JWT"""
        from api.v1.auth import create_jwt_token
        token = create_jwt_token("user123", "openid_abc")
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        assert payload["user_id"] == "user123"
        assert payload["openid"] == "openid_abc"

    def test_has_expiry(self):
        """JWT 应包含过期时间"""
        from api.v1.auth import create_jwt_token
        token = create_jwt_token("user123", "openid_abc")
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        assert "exp" in payload
        assert "iat" in payload


class TestWxLogin:

    @pytest.mark.asyncio
    async def test_dev_mode_no_wx_config(self):
        """未配置 WX_APPID/WX_SECRET → 返回模拟 openid"""
        from api.v1.auth import wx_login
        from api.v1.auth import LoginRequest
        resp = await wx_login(LoginRequest(code="test_code_123"))
        assert resp.token
        assert resp.openid.startswith("dev_user_")
        assert resp.user_id

    @pytest.mark.asyncio
    async def test_success(self):
        """wx.login 成功路径 → 返回正常 openid"""
        import api.v1.auth
        from api.v1.auth import wx_login, LoginRequest

        api.v1.auth.settings.wx_appid = "mock_appid"
        api.v1.auth.settings.wx_secret = "mock_secret"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client

        # get 方法是 async 的，await 后需要 self-returning mock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "openid": "real_openid_123",
            "session_key": "sk_abc",
        }
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = await wx_login(LoginRequest(code="valid_code"))
            assert resp.openid == "real_openid_123"
            assert resp.user_id

    @pytest.mark.asyncio
    async def test_wechat_api_error(self):
        """wx.login 返回 errcode → 错误处理"""
        import api.v1.auth
        from api.v1.auth import wx_login, LoginRequest

        api.v1.auth.settings.wx_appid = "mock_appid"
        api.v1.auth.settings.wx_secret = "mock_secret"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "errcode": 40029,
            "errmsg": "invalid code",
        }
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = await wx_login(LoginRequest(code="bad_code"))
            assert "wx_error" in resp.openid

    @pytest.mark.asyncio
    async def test_network_error(self):
        """wx.login 网络异常 → 容错"""
        import api.v1.auth
        from api.v1.auth import wx_login, LoginRequest

        api.v1.auth.settings.wx_appid = "mock_appid"
        api.v1.auth.settings.wx_secret = "mock_secret"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock()
        mock_client.get.side_effect = Exception("Connection refused")

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = await wx_login(LoginRequest(code="code"))
            assert resp.openid == "wx_network_error"
