"""测试: services/trip_service.py — 行程生成服务"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock


class TestGenerateTrip:

    @pytest.mark.asyncio
    async def test_returns_immediately(self, trip_form_data):
        """generate_trip 应立即返回 processing 状态"""
        with patch("services.trip_service.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abc123def456"
            with patch("services.trip_service.asyncio.create_task") as mock_task:
                mock_task.return_value = MagicMock()
                with patch("agents.supervisor.SupervisorAgent"):

                    from services.trip_service import generate_trip
                    resp = await generate_trip(trip_form_data, "user1")

                    assert resp.tripId == "trip_abc123def456"
                    assert resp.status == "processing"
                    assert resp.message

    @pytest.mark.asyncio
    async def test_creates_background_task(self, trip_form_data):
        """应创建后台 asyncio Task"""
        with patch("services.trip_service.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "test12345678"
            with patch("services.trip_service.asyncio.create_task") as mock_task:
                mock_task.return_value = MagicMock()
                with patch("agents.supervisor.SupervisorAgent"):

                    from services.trip_service import generate_trip
                    await generate_trip(trip_form_data, "user1")

                    mock_task.assert_called_once()


class TestGetGenerationStatus:

    def setup_tasks(self, tasks_dict):
        """辅助方法：设置 _generation_tasks"""
        import services.trip_service as svc
        svc._generation_tasks.clear()
        svc._generation_tasks.update(tasks_dict)

    @pytest.mark.asyncio
    async def test_not_found(self):
        """不存在的 trip_id → status = not_found"""
        import services.trip_service as svc
        svc._generation_tasks.clear()

        from services.trip_service import get_generation_status
        resp = await get_generation_status("nonexistent_id")
        assert resp.status == "not_found"

    @pytest.mark.asyncio
    async def test_processing(self):
        """存在的 processing 任务 → 返回正确进度"""
        self.setup_tasks({
            "trip_test1": {
                "status": "processing",
                "progress": 50,
                "currentStep": "规划中...",
                "result": None,
            }
        })
        from services.trip_service import get_generation_status
        resp = await get_generation_status("trip_test1")
        assert resp.status == "processing"
        assert resp.progress == 50
        assert resp.currentStep == "规划中..."

    @pytest.mark.asyncio
    async def test_completed(self):
        """已完成任务返回 100% 和 result"""
        self.setup_tasks({
            "trip_test2": {
                "status": "completed",
                "progress": 100,
                "currentStep": "完成",
                "result": {"title": "杭州3日游"},
            }
        })
        from services.trip_service import get_generation_status
        resp = await get_generation_status("trip_test2")
        assert resp.status == "completed"
        assert resp.progress == 100
        assert resp.result == {"title": "杭州3日游"}


class TestCancelTrip:

    def teardown_method(self):
        import services.trip_service as svc
        svc._generation_tasks.clear()
        svc._cancelled_trips.clear()

    @pytest.mark.asyncio
    async def test_cancel_active_task(self):
        """processing 任务可被取消 → True"""
        import services.trip_service as svc
        svc._generation_tasks["trip_active"] = {
            "status": "processing", "progress": 50, "currentStep": "...", "result": None,
        }
        from services.trip_service import cancel_trip
        result = await cancel_trip("trip_active")
        assert result is True
        assert "trip_active" in svc._cancelled_trips

    @pytest.mark.asyncio
    async def test_cancel_completed_task(self):
        """已完成任务不可取消 → False"""
        import services.trip_service as svc
        svc._generation_tasks["trip_done"] = {
            "status": "completed", "progress": 100, "currentStep": "", "result": {},
        }
        from services.trip_service import cancel_trip
        result = await cancel_trip("trip_done")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self):
        """不存在任务不可取消 → False"""
        import services.trip_service as svc
        svc._generation_tasks.clear()
        from services.trip_service import cancel_trip
        result = await cancel_trip("no_such_trip")
        assert result is False
