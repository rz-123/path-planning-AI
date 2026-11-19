"""测试: api/v1/trips.py — 行程进度/取消接口的鉴权与归属校验

覆盖的安全修复：
  1. 未登录访问 status / cancel → 401
  2. 登录后查询别人的 trip_id → 统一返回 not_found（不泄露任务是否存在）
  3. 登录后取消别人的任务 → success=False
  4. 登录后访问自己的任务 → 正常返回
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient


def _token(user_id: str) -> str:
    """按指定 user_id 生成测试用 JWT（secret 与 conftest 一致）"""
    payload = {
        "user_id": user_id,
        "openid": "test-openid",
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


@pytest.fixture
def seeded_task():
    """在内存任务字典里放一个归属 test-user-123 的处理中任务"""
    import services.trip_service as svc
    svc._generation_tasks.clear()
    svc._cancelled_trips.clear()
    svc._generation_tasks["trip_owner001"] = {
        "status": "processing",
        "progress": 40,
        "currentStep": "规划路线中...",
        "result": None,
        "userId": "test-user-123",
    }
    yield
    svc._generation_tasks.clear()
    svc._cancelled_trips.clear()


class TestStatusAuth:

    def test_status_without_token_returns_401(self):
        """未带 Token 查询进度 → 401"""
        from main import app
        client = TestClient(app)
        resp = client.get("/api/v1/trips/trip_owner001/status")
        assert resp.status_code == 401

    def test_status_with_invalid_token_returns_401(self):
        """伪造 Token → 401"""
        from main import app
        client = TestClient(app)
        resp = client.get(
            "/api/v1/trips/trip_owner001/status",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_status_owner_can_read(self, seeded_task):
        """任务归属者查询 → 返回真实进度"""
        from main import app
        client = TestClient(app)
        resp = client.get(
            "/api/v1/trips/trip_owner001/status",
            headers={"Authorization": f"Bearer {_token('test-user-123')}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processing"
        assert data["progress"] == 40
        # 内部字段 userId 不应透传给前端
        assert "userId" not in data

    def test_status_other_user_gets_not_found(self, seeded_task):
        """别人查询 → not_found（不暴露任务存在）"""
        from main import app
        client = TestClient(app)
        resp = client.get(
            "/api/v1/trips/trip_owner001/status",
            headers={"Authorization": f"Bearer {_token('other-user-999')}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_found"


class TestCancelAuth:

    def test_cancel_without_token_returns_401(self):
        """未带 Token 取消 → 401"""
        from main import app
        client = TestClient(app)
        resp = client.delete("/api/v1/trips/trip_owner001/cancel")
        assert resp.status_code == 401

    def test_cancel_other_user_returns_false(self, seeded_task):
        """取消别人的任务 → success=False，且任务未被标记取消"""
        import services.trip_service as svc
        from main import app
        client = TestClient(app)
        resp = client.delete(
            "/api/v1/trips/trip_owner001/cancel",
            headers={"Authorization": f"Bearer {_token('other-user-999')}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "trip_owner001" not in svc._cancelled_trips

    def test_cancel_owner_returns_true(self, seeded_task):
        """取消自己的任务 → success=True"""
        import services.trip_service as svc
        from main import app
        client = TestClient(app)
        resp = client.delete(
            "/api/v1/trips/trip_owner001/cancel",
            headers={"Authorization": f"Bearer {_token('test-user-123')}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert "trip_owner001" in svc._cancelled_trips
