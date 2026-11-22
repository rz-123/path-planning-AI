"""测试: 本地 SQLite 数据层 + 行程保存/列表接口

覆盖：
  1. 保存行程后能按用户查到
  2. 用户之间数据隔离（A 看不到 B 的行程）
  3. 未登录访问保存/列表接口 → 401
  4. 登录 upsert 用户：同一 openid 只保留一条
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient


def _token(user_id: str) -> str:
    """生成测试用 JWT（secret 与 conftest 一致）"""
    payload = {
        "user_id": user_id,
        "openid": "test-openid",
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """把数据层指向临时数据库文件，避免污染开发库"""
    import db
    monkeypatch.setattr(db, "_DB_FILE", str(tmp_path / "test_travel.db"))
    db.init_db()
    yield db


class TestTripsStoreApi:

    def test_save_and_list(self, temp_db):
        """保存后能在列表里查到，且 fullData 完整"""
        from main import app
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {_token('u_owner')}"}

        trip = {
            "id": "trip_test_001",
            "title": "杭州3日游",
            "destination": "杭州",
            "startDate": "2026-12-01",
            "endDate": "2026-12-03",
            "days": 3,
            "nights": 2,
            "people": 2,
            "totalBudget": 3000,
            "budgetPerPerson": 1500,
            "interests": ["museum", "food"],
            "dailyPlan": [{"day": 1}],
        }
        resp = client.post("/api/v1/trips", json=trip, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["success"] is True

        resp = client.get("/api/v1/trips?limit=3", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        item = data["trips"][0]
        assert item["_id"] == "trip_test_001"
        assert item["destination"] == "杭州"
        assert item["fullData"]["dailyPlan"] == [{"day": 1}]

    def test_user_isolation(self, temp_db):
        """A 保存的行程，B 查不到"""
        from main import app
        client = TestClient(app)
        trip = {"id": "trip_a_001", "destination": "成都", "days": 2}

        client.post("/api/v1/trips", json=trip,
                    headers={"Authorization": f"Bearer {_token('u_a')}"})
        resp = client.get("/api/v1/trips",
                          headers={"Authorization": f"Bearer {_token('u_b')}"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_save_twice_does_not_duplicate(self, temp_db):
        """同一 id 重复保存 → 覆盖而不是新增（防连点）"""
        from main import app
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {_token('u_c')}"}
        trip = {"id": "trip_same", "destination": "西安", "title": "旧标题"}

        client.post("/api/v1/trips", json=trip, headers=headers)
        trip["title"] = "新标题"
        client.post("/api/v1/trips", json=trip, headers=headers)

        resp = client.get("/api/v1/trips", headers=headers)
        data = resp.json()
        assert data["total"] == 1
        assert data["trips"][0]["title"] == "新标题"

    def test_requires_auth(self, temp_db):
        """未带 Token：列表和保存都应 401"""
        from main import app
        client = TestClient(app)
        assert client.get("/api/v1/trips").status_code == 401
        assert client.post("/api/v1/trips", json={"destination": "北京"}).status_code == 401


class TestUsersTable:

    def test_upsert_user_single_row(self, temp_db):
        """同一 openid 登录两次 → users 表仍只有一条记录"""
        temp_db.upsert_user("openid_x", "u_x")
        temp_db.upsert_user("openid_x", "u_x")

        import sqlite3
        conn = sqlite3.connect(temp_db._DB_FILE)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM users WHERE openid = ?", ("openid_x",)
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1
