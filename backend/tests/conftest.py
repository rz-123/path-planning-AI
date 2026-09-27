"""共享 Fixtures — 所有测试模块复用"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest


# =============================================================
# 日期常量（测试用）
# =============================================================
START_DATE = date(2025, 6, 1)
END_DATE = date(2025, 6, 3)


# =============================================================
# Fixture: 模拟 Settings（原地打补丁，不替换对象）
# =============================================================
@pytest.fixture(autouse=True)
def mock_settings():
    """
    原地打补丁 config.settings 实例的属性值。

    与原有方案区别：
    - 原有方案: patch("config.settings") 替换整个对象为 MagicMock
      导致已导入模块缓存旧引用，patch.object 失效
    - 本方案: patch.multiple 直接修改 config.settings 原实例的属性
      所有 from config import settings 引用均受影响
    """
    import config as config_module
    with patch.multiple(
        config_module.settings,
        app_name="AI旅行规划 API",
        debug=True,
        database_url="sqlite+aiosqlite:///:memory:",
        llm_provider="deepseek",
        llm_model="deepseek-v3-0324",
        llm_api_key="test-key",
        llm_base_url="https://api.deepseek.com/v1",
        llm_temperature=0.7,
        llm_max_tokens=16384,
        amap_key="",
        flyai_api_key="",
        wx_appid="",
        wx_secret="",
        jwt_secret="test-secret",
        jwt_expire_days=7,
    ):
        yield config_module.settings


# =============================================================
# Fixture: 合法的测试 JWT Token
# =============================================================
@pytest.fixture
def valid_jwt_token():
    from datetime import datetime, timedelta, timezone
    payload = {
        "user_id": "test-user-123",
        "openid": "test-openid",
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


# =============================================================
# Fixture: 标准的 TripFormData 实例
# =============================================================
@pytest.fixture
def trip_form_data():
    """标准行程表单数据：杭州3天2人舒适型"""
    from schemas.trip import TripFormData, StyleEnum, BudgetEnum, AccommodationEnum
    return TripFormData(
        origin="北京",
        destination="杭州",
        startDate="2025-06-01",
        endDate="2025-06-03",
        adults=2,
        children=0,
        style=StyleEnum.leisure,
        interests=["food", "museum"],
        budget=BudgetEnum.comfort,
        accommodation=AccommodationEnum.comfort,
    )


# =============================================================
# Fixture: 模拟 get_llm 返回的 ChatOpenAI 实例
# =============================================================
@pytest.fixture
def mock_llm():
    """模拟 LLM 的 invoke 方法返回固定 JSON"""
    mock = MagicMock()
    mock.invoke.return_value.content = '{"attractions":[],"restaurants":[],"hotels":[]}'
    return mock


# =============================================================
# Fixture: 模拟 httpx.AsyncClient
# =============================================================
@pytest.fixture
def mock_httpx_client():
    """模拟 httpx.AsyncClient 的 GET/POST 方法"""
    mock = AsyncMock()
    mock.__aenter__.return_value = mock
    return mock


@pytest.fixture
def mock_httpx_post():
    """模拟 httpx.post （同步版本，用于飞猪）"""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"code": 200, "value": []}
    return mock
