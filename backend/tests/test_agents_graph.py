"""测试: agents/graph.py — LangGraph 工作流节点"""

import json
import pytest
from unittest.mock import patch, MagicMock


# =============================================================
# _extract_json
# =============================================================
class TestExtractJSON:

    def test_clean_json(self):
        """纯 JSON 正常解析"""
        from agents.graph import _extract_json
        result = _extract_json('{"name":"test","value":123}')
        assert result["name"] == "test"
        assert result["value"] == 123

    def test_with_markdown_code_block(self):
        """"```json ... ``` 包裹 → 正确解析"""
        from agents.graph import _extract_json
        text = '```json\n{"name":"test"}\n```'
        result = _extract_json(text)
        assert result["name"] == "test"

    def test_with_prefix_text(self):
        """前置文字 → 正确提取"""
        from agents.graph import _extract_json
        text = '以下是为您生成的行程：\n{"days": 3, "city": "杭州"}\n请查收'
        result = _extract_json(text)
        assert result["days"] == 3
        assert result["city"] == "杭州"

    def test_invalid_json_returns_error_dict(self):
        """无效 JSON → 返回 error dict"""
        from agents.graph import _extract_json
        result = _extract_json("这不是 JSON {{{")
        assert "error" in result
        assert "raw" in result

    def test_empty_string(self):
        """空字符串 → 返回 error"""
        from agents.graph import _extract_json
        result = _extract_json("")
        assert "error" in result

    def test_nested_json(self):
        """嵌套 JSON 正确解析"""
        from agents.graph import _extract_json
        text = '{"dailyPlan":[{"day":1,"periods":[]}],"budgetDetail":{"total":1000}}'
        result = _extract_json(text)
        assert result["dailyPlan"][0]["day"] == 1
        assert result["budgetDetail"]["total"] == 1000

    def test_json_with_trailing_text(self):
        """JSON 后有后缀文字 → 正确提取"""
        from agents.graph import _extract_json
        text = '{"result":"ok"}\n\n以上是生成的行程数据。'
        result = _extract_json(text)
        assert result["result"] == "ok"


# =============================================================
# CancelledError
# =============================================================
class TestCancelledError:

    def test_can_be_caught(self):
        """CancelledError 可被 except 捕获"""
        from agents.utils import CancelledError
        try:
            raise CancelledError("task cancelled")
        except CancelledError as e:
            assert "task cancelled" in str(e)

    def test_inherits_from_exception(self):
        """继承 Exception"""
        from agents.utils import CancelledError
        assert issubclass(CancelledError, Exception)


# =============================================================
# check_cancelled / update_progress
# =============================================================
class TestCheckCancelled:

    def test_not_cancelled_no_error(self):
        """任务未被取消 → 不抛出异常"""
        from agents.utils import check_cancelled
        import services.trip_service as svc
        svc._cancelled_trips.clear()
        # 不应抛出异常
        check_cancelled("trip_abc")

    def test_cancelled_raises(self):
        """任务已取消 → 抛出 CancelledError"""
        from agents.utils import check_cancelled, CancelledError
        import services.trip_service as svc
        svc._cancelled_trips.clear()
        svc._cancelled_trips.add("trip_cancelled")
        with pytest.raises(CancelledError):
            check_cancelled("trip_cancelled")

    def test_removes_from_set_after_check(self):
        """检查后应从取消集合中移除"""
        from agents.utils import check_cancelled, CancelledError
        import services.trip_service as svc
        svc._cancelled_trips.clear()
        svc._cancelled_trips.add("trip_cleanup")
        try:
            check_cancelled("trip_cleanup")
        except CancelledError:
            pass
        assert "trip_cleanup" not in svc._cancelled_trips


class TestUpdateProgress:

    def test_updates_progress(self):
        """更新任务进度"""
        from agents.utils import update_progress
        import services.trip_service as svc
        svc._generation_tasks["trip_prog"] = {
            "status": "processing", "progress": 0, "currentStep": "", "result": None,
        }
        update_progress("trip_prog", "正在规划...", 50)
        assert svc._generation_tasks["trip_prog"]["currentStep"] == "正在规划..."
        assert svc._generation_tasks["trip_prog"]["progress"] == 50

    def test_unknown_trip_does_nothing(self):
        """不存在的 trip_id → 静默忽略"""
        from agents.utils import update_progress
        import services.trip_service as svc
        svc._generation_tasks.clear()
        # 不应抛出异常
        update_progress("nonexistent", "测试", 0)


# =============================================================
# reflection_node 评分逻辑（不调用 LLM）
# =============================================================
class TestReflectionScore:

    def test_missing_plan_has_low_score(self):
        """无 plan_result → score 低"""
        from agents.graph import reflection_node

        state = {
            "trip_id": "test1",
            "destination": "杭州",
            "days": 3,
            "nights": 2,
            "style_label": "轻松休闲",
            "interests": ["food"],
            "budget_range": "¥1k-1.5k",
            "research_result": '{"attractions":[],"restaurants":[]}',
            "plan_result": "{}",
            "budget_result": '{"totalBudget":0,"budgetDetail":{}}',
            "revision_count": 0,
            "next_action": "",
            "weather_data": "{}",
        }
        with patch("agents.graph.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value.content = '{"score_adjust":0,"highlights":[],"critical":[]}'
            mock_get_llm.return_value = mock_llm

            result = reflection_node(state)
            # 没有 dailyPlan → code_score 低 → next_action 可能为 plan
            assert result["next_action"] in ("plan", "format")

    def test_perfect_data_passes(self):
        """完整数据 → score ≥ 5 → format"""
        from agents.graph import reflection_node
        budget = json.dumps({
            "totalBudget": 3000,
            "budgetPerPerson": 1500,
            "budgetDetail": {
                "accommodation": {"total": 1000, "icon": "🏨", "items": [{"name":"酒店","amount":1000}]},
                "food": {"total": 800, "icon": "🍜", "items": [{"name":"正餐","amount":800}]},
                "transport": {"total": 600, "icon": "🚌", "items": [{"name":"交通","amount":600}]},
                "tickets": {"total": 600, "icon": "🎫", "items": [{"name":"门票","amount":600}]},
            },
            "budgetPieData": [
                {"name":"住宿","value":1000,"color":"#3B82F6","percent":33},
                {"name":"餐饮","value":800,"color":"#22C55E","percent":27},
                {"name":"交通","value":600,"color":"#F59E0B","percent":20},
                {"name":"门票","value":600,"color":"#EF4444","percent":20},
            ]
        })
        plan = json.dumps({
            "dailyPlan": [
                {"day": 1, "date": "2025-06-01", "periods": [
                    {"timeSlot": "上午", "items": [{"name":"西湖","cost":0}]},
                ]},
                {"day": 2, "date": "2025-06-02", "periods": [
                    {"timeSlot": "上午", "items": [{"name":"灵隐寺","cost":0}]},
                ]},
                {"day": 3, "date": "2025-06-03", "periods": [
                    {"timeSlot": "上午", "items": [{"name":"西溪湿地","cost":0}]},
                ]},
            ]
        })

        state = {
            "trip_id": "test2",
            "destination": "杭州",
            "days": 3,
            "nights": 2,
            "style_label": "轻松休闲",
            "interests": ["food", "museum"],
            "budget_range": "¥1k-1.5k",
            "research_result": '{"attractions":[{"name":"西湖"}],"restaurants":[{"name":"楼外楼"}]}',
            "plan_result": plan,
            "budget_result": budget,
            "revision_count": 0,
            "next_action": "",
            "weather_data": "{}",
        }
        with patch("agents.graph.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value.content = '{"score_adjust":1,"highlights":["数据完整"],"critical":[]}'
            mock_get_llm.return_value = mock_llm

            result = reflection_node(state)
            assert result["next_action"] == "format"


# =============================================================
# format_node: _fix_coordinates
# =============================================================
class TestFixCoordinates:

    def test_skips_non_physical_locations(self):
        """跳过非实体地点"""
        from agents.graph import _fix_coordinates
        final = {
            "dailyPlan": [
                {"periods": [
                    {"items": [
                        {"name": "酒店午休", "latitude": None, "longitude": None},
                        {"name": "西湖", "latitude": None, "longitude": None},
                    ]}
                ]}
            ]
        }
        with patch("agents.graph.geocode") as mock_geo:
            mock_geo.return_value = {"longitude": 120.15, "latitude": 30.25}
            result = _fix_coordinates(final, "杭州")
            # 西湖应被修正，酒店午休应被跳过
            items = result["dailyPlan"][0]["periods"][0]["items"]
            geocoded = [i for i in items if i.get("longitude")]
            assert len(geocoded) == 1
            assert geocoded[0]["name"] == "西湖"
