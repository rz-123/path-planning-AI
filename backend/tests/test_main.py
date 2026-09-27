"""测试: main.py — FastAPI 应用入口"""

from fastapi.testclient import TestClient


class TestAppCreation:

    def test_app_has_correct_title(self):
        """应用标题应来自 settings"""
        from main import app
        assert app.title == "AI旅行规划 API"

    def test_routes_registered(self):
        """所有路由应已注册"""
        from main import app
        routes = [r.path for r in app.routes]

        # 健康检查
        assert "/health" in routes
        assert "/" in routes

        # API 路由前缀
        assert any("/api/v1/trips" in r for r in routes)
        assert any("/api/v1/destinations" in r for r in routes)
        assert any("/api/v1/geo" in r for r in routes)
        assert any("/api/v1/auth" in r for r in routes)

    def test_cors_middleware_registered(self):
        """CORS 中间件应已注册"""
        from main import app
        middlewares = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middlewares


class TestEndpoints:

    def test_health_endpoint(self):
        """GET /health → 200 + {"status": "ok"}"""
        from main import app
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_root_endpoint(self):
        """GET / → 200 + 包含 name/version/docs"""
        from main import app
        client = TestClient(app)
        resp = client.get("/")
        data = resp.json()
        assert data["name"] == "AI旅行规划 API"
        assert "version" in data
        assert "docs" in data

    def test_map_key_endpoint(self):
        """GET /api/v1/config/map-key → 200"""
        from main import app
        client = TestClient(app)
        resp = client.get("/api/v1/config/map-key")
        assert resp.status_code == 200
        assert "amapKey" in resp.json()

    def test_hot_destinations_endpoint(self):
        """GET /api/v1/destinations/hot → 200"""
        from main import app
        client = TestClient(app)
        resp = client.get("/api/v1/destinations/hot")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 20

    def test_random_destination_endpoint(self):
        """GET /api/v1/destinations/random → 200"""
        from main import app
        client = TestClient(app)
        resp = client.get("/api/v1/destinations/random")
        assert resp.status_code == 200
        assert "name" in resp.json()

    def test_map_key_returns_empty_when_not_configured(self, mock_settings):
        """未配置高德 Key → 返回空字符串"""
        mock_settings.amap_key = ""
        from main import app
        client = TestClient(app)
        resp = client.get("/api/v1/config/map-key")
        assert resp.json()["amapKey"] == ""
