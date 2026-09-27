"""测试: agents/supervisor.py — SupervisorAgent"""

import pytest
from unittest.mock import patch, MagicMock


class TestStateConstruction:

    @pytest.mark.asyncio
    async def test_state_fields(self, trip_form_data):
        """TripState 字段应正确填充"""
        from agents.supervisor import SupervisorAgent

        # 不 mock threading.Thread，让真实线程运行
        # 只 mock trip_graph.invoke 返回固定值
        with patch("agents.supervisor.trip_graph") as mock_graph:
            mock_graph.invoke.return_value = {"final_json": '{"title":"test","id":"t1"}'}

            agent = SupervisorAgent()
            result = await agent.run(trip_form_data, "trip_test")

            assert result == {"title": "test", "id": "t1"}

    def test_style_label_mapping(self):
        """所有 style 值应有对应的中文标签"""
        from agents.supervisor import STYLE_LABEL
        assert STYLE_LABEL["leisure"] == "轻松休闲"
        assert STYLE_LABEL["deep"] == "深度打卡"
        assert STYLE_LABEL["artistic"] == "文艺小资"
        assert STYLE_LABEL["intensive"] == "特种兵式"
        assert len(STYLE_LABEL) == 4

    def test_budget_range_mapping(self):
        """所有 budget 值应有对应的价格范围"""
        from agents.supervisor import BUDGET_RANGE
        assert BUDGET_RANGE["economy"] == "¥500-1k"
        assert BUDGET_RANGE["comfort"] == "¥1k-1.5k"
        assert BUDGET_RANGE["quality"] == "¥1.5k-2k"
        assert len(BUDGET_RANGE) == 3


class TestCancelSupport:

    @pytest.mark.asyncio
    async def test_cancelled_task_returns_empty(self, trip_form_data):
        """取消的任务应返回空 dict"""
        from agents.supervisor import SupervisorAgent
        from agents.utils import CancelledError

        with patch("agents.supervisor.trip_graph") as mock_graph:
            mock_graph.invoke.side_effect = CancelledError("cancelled")

            agent = SupervisorAgent()
            result = await agent.run(trip_form_data, "trip_cancel")
            assert result == {}
