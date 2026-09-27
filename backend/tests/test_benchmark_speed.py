"""基准测试: 测量每个 Agent 节点和工具调用的延迟

使用方法:
  # 仅运行 benchmark
  pytest tests/test_benchmark_speed.py --benchmark-only -v

  # 跳过 benchmark（与现有测试一起运行）
  pytest tests/ -v --benchmark-skip

  # JSON 输出
  pytest tests/test_benchmark_speed.py --benchmark-only --benchmark-json=bench_results.json
"""

import asyncio
import json
import time
from itertools import cycle
from unittest.mock import patch, MagicMock

import pytest


# =============================================================
# 辅助函数
# =============================================================

def _make_delayed_llm(delay: float = 0.0, content: str = '{"result":"ok"}'):
    """创建可控延迟的 mock LLM。invoke() 先 sleep delay 秒再返回固定 content。"""
    mock = MagicMock()
    def _invoke(*args, **kwargs):
        time.sleep(delay)
        r = MagicMock()
        r.content = content
        return r
    mock.invoke.side_effect = _invoke
    return mock


def _make_minimal_state():
    """创建最小的 TripState，基准测试各个节点用。

    确保数据可以穿过所有节点的主路径（不会触发免回退或修正循环）。
    """
    return {
        "destination": "北京", "origin": "上海",
        "start_date": "2025-06-01", "end_date": "2025-06-03",
        "days": 3, "nights": 2, "people": 2, "adults": 2, "children": 0,
        "transport": "train", "style": "leisure", "style_label": "轻松休闲",
        "interests": ["food", "museum"], "budget": "comfort",
        "budget_range": "¥1k-1.5k", "accommodation": "comfort",
        "special_needs": "",
        "trip_id": "bench_trip",
        "research_result": "", "plan_result": "", "budget_result": "",
        "reflection": "", "weather_data": "{}", "final_json": "",
        "revision_count": 0, "next_action": "",
    }


# =============================================================
# 1. 节点延迟基准
# =============================================================

class TestBenchmarkNodeLatency:
    """测量每个 Graph 节点在 LLM 调用之外的纯开销。

    每个节点都 mock 掉实际的 LLM 调用（替换为固定延迟），
    这样测量出的时间就是 prompt 构造 + JSON 解析 + 逻辑运算的净开销。
    """

    @pytest.mark.benchmark(min_rounds=5)
    def test_research_node_overhead(self, benchmark):
        """research_node: 0.5s mock LLM + mock 天气/飞猪 → 净开销 < 50ms"""
        from agents.graph import research_node
        state = _make_minimal_state()

        with patch("agents.graph.get_llm", return_value=_make_delayed_llm(0.5)):
            with patch("agents.graph.get_weather", return_value={"live": {}, "forecast": []}):
                with patch("agents.tools.flyai_search") as mock_fly:
                    mock_fly.invoke.return_value = ""
                    result = benchmark(research_node, state)

        assert result is not None

    @pytest.mark.benchmark(min_rounds=5)
    def test_plan_node_overhead(self, benchmark):
        """plan_node: 0.5s mock LLM → 净开销"""
        from agents.graph import plan_node
        state = _make_minimal_state()
        state["research_result"] = json.dumps({
            "attractions": [{"name": "故宫"}, {"name": "天坛"}, {"name": "颐和园"},
                            {"name": "长城"}, {"name": "鸟巢"}, {"name": "国家博物馆"},
                            {"name": "北海公园"}, {"name": "南锣鼓巷"}, {"name": "恭王府"},
                            {"name": "圆明园"}],
            "restaurants": [{"name": "全聚德"}, {"name": "东来顺"}, {"name": "大董"},
                            {"name": "海底捞"}, {"name": "老北京炸酱面"}],
            "hotels": [{"name": "如家"}, {"name": "汉庭"}],
        }, ensure_ascii=False)

        with patch("agents.graph.get_llm", return_value=_make_delayed_llm(0.5)):
            result = benchmark(plan_node, state)

        assert result is not None

    @pytest.mark.benchmark(min_rounds=5)
    def test_budget_node_overhead(self, benchmark):
        """budget_node: 0.5s mock LLM + mock 飞猪 → 净开销"""
        from agents.graph import budget_node
        state = _make_minimal_state()
        state["plan_result"] = json.dumps({
            "dailyPlan": [{
                "day": 1, "date": "2025-06-01",
                "periods": [{"timeSlot": "上午", "items": [{"name": "故宫"}]}]
            }]
        })

        with patch("agents.graph.get_llm", return_value=_make_delayed_llm(0.5)):
            with patch("agents.tools.flyai_search") as mock_fly:
                mock_fly.invoke.return_value = ""
                result = benchmark(budget_node, state)

        assert result is not None

    @pytest.mark.benchmark(min_rounds=5)
    def test_reflection_node_overhead(self, benchmark):
        """reflection_node: 0.3s mock LLM(语义检查) → 净开销"""
        from agents.graph import reflection_node
        state = _make_minimal_state()
        state["research_result"] = "mock research data"
        state["plan_result"] = json.dumps({
            "dailyPlan": [{
                "day": 1, "periods": [{"timeSlot": "上午", "items": [{"name": "景点1"}]}]
            }]
        })
        state["budget_result"] = json.dumps({
            "budgetDetail": {"accommodation": {"total": 500, "items": []}},
            "budgetPieData": [
                {"name": "住宿", "percent": 50, "color": "#3B82F6", "value": 500},
                {"name": "餐饮", "percent": 30, "color": "#22C55E", "value": 300},
                {"name": "交通", "percent": 10, "color": "#F59E0B", "value": 100},
                {"name": "门票", "percent": 10, "color": "#EF4444", "value": 100},
            ],
            "totalBudget": 1000, "budgetPerPerson": 500,
        })

        with patch("agents.graph.get_llm",
                   return_value=_make_delayed_llm(0.3,
                       '{"score_adjust":1,"highlights":["地理合理"],"critical":[]}')):
            result = benchmark(reflection_node, state)

        assert result is not None
        # 数据完整，不应触发修正
        assert result["next_action"] == "format" or result["revision_count"] == 0

    @pytest.mark.benchmark(min_rounds=5)
    def test_format_node_code_path(self, benchmark):
        """format_node: 代码拼接路径（无 LLM 调用），mock geocode → 净开销 < 20ms"""
        from agents.graph import format_node
        state = _make_minimal_state()
        state["trip_id"] = "bench_trip"
        state["plan_result"] = json.dumps({
            "dailyPlan": [{
                "day": 1, "date": "2025-06-01", "summary": "第一天",
                "periods": [{"timeSlot": "上午", "items": [{"name": "故宫"}]}]
            }]
        })
        state["budget_result"] = json.dumps({
            "budgetDetail": {
                "accommodation": {"total": 500, "icon": "🏨", "items": []},
                "food": {"total": 300, "icon": "🍜", "items": []},
                "transport": {"total": 200, "icon": "🚌", "items": []},
                "tickets": {"total": 100, "icon": "🎫", "items": []},
            },
            "budgetPieData": [],
            "totalBudget": 1100, "budgetPerPerson": 550,
        })
        state["weather_data"] = json.dumps({"city": "北京", "live": {}, "forecast": []})

        with patch("agents.graph.geocode", return_value={"longitude": 116.4, "latitude": 39.9}):
            result = benchmark(format_node, state)

        assert "final_json" in result
        final = json.loads(result["final_json"])
        assert final["id"] == "bench_trip"


# =============================================================
# 2. 全图端到端延迟
# =============================================================

class TestBenchmarkAgentGraphLatency:
    """完整 5 节点 LangGraph 图的端到端延迟。"""

    @pytest.mark.benchmark(min_rounds=3)
    def test_full_graph_instant_llm(self, benchmark):
        """全图 + mock LLM 即时返回 → 纯编排开销 + _fix_coordinates"""
        from agents.graph import trip_graph
        state = _make_minimal_state()
        state["trip_id"] = "graph_bench"

        with patch("agents.graph.get_llm", return_value=_make_delayed_llm(0.0)):
            with patch("agents.graph.get_weather",
                       return_value={"live": {"weather": "晴"}, "forecast": []}):
                with patch("agents.tools.flyai_search") as mock_fly:
                    mock_fly.invoke.return_value = ""
                    with patch("agents.graph.geocode",
                               return_value={"longitude": 116.4, "latitude": 39.9}):
                        result = benchmark(trip_graph.invoke, state)

        assert "final_json" in result
        final = json.loads(result["final_json"])
        assert final["id"] == "graph_bench"

    @pytest.mark.benchmark(min_rounds=3)
    def test_full_graph_fast_llm(self, benchmark):
        """全图 + 每个节点 mock LLM 0.5s → 预期约 2.5s"""
        from agents.graph import trip_graph
        state = _make_minimal_state()
        state["trip_id"] = "graph_bench_fast"

        with patch("agents.graph.get_llm", return_value=_make_delayed_llm(0.5)):
            with patch("agents.graph.get_weather",
                       return_value={"live": {"weather": "晴"}, "forecast": []}):
                with patch("agents.tools.flyai_search") as mock_fly:
                    mock_fly.invoke.return_value = ""
                    with patch("agents.graph.geocode",
                               return_value={"longitude": 116.4, "latitude": 39.9}):
                        result = benchmark(trip_graph.invoke, state)

        assert "final_json" in result


# =============================================================
# 3. MCP 工具延迟
# =============================================================

class TestBenchmarkMCPToolLatency:
    """测量 MCP 3 步握手和工具调用的延迟。

    每个 _amap_mcp 调用包含：
      1. POST initialize（获取 session ID）
      2. POST notifications/initialized
      3. POST tools/call（+ JSON 解析）
    """

    @pytest.mark.benchmark(min_rounds=10)
    def test_mcp_handshake_overhead(self, benchmark):
        """纯 3 步握手开销（httpx mock 即时返回）"""
        import config
        config.settings.amap_key = "test_key"
        from agents.tools import _amap_mcp, _mcp_sessions

        # 手动构造 mock（使用属性赋值而非构造函数关键字参数，避免 MagicMock 包装问题）
        init_mock = MagicMock()
        init_mock.headers = {"mcp-session-id": "sess_bench"}
        init_mock.json.return_value = {}

        notif_mock = MagicMock()
        notif_mock.headers = {}
        notif_mock.json.return_value = {}

        tool_mock = MagicMock()
        tool_mock.headers = {}
        tool_mock.json.return_value = {
            "result": {"content": [{"type": "text", "text": '{"ok":1}'}]}
        }

        side_effects = [init_mock, notif_mock, tool_mock]

        with patch("httpx.post", side_effect=cycle(side_effects)):
            # 每次调用前清除会话缓存，确保每次都走完整 3 步握手
            def _bench():
                _mcp_sessions.clear()
                return _amap_mcp("maps_weather", city="北京")
            result = benchmark(_bench)

        data = json.loads(result)
        assert "ok" in data

    @pytest.mark.benchmark(min_rounds=10)
    def test_get_weather_parsing(self, benchmark):
        """get_weather JSON 解析 + 格式化的纯开销（mock _amap_mcp）"""
        from agents.tools import get_weather

        mock_mcp_data = json.dumps({
            "lives": [{"city": "北京", "weather": "晴", "temperature": "25",
                       "winddirection": "南风", "windpower": "4", "humidity": "45"}],
            "forecasts": [{
                "casts": [
                    {"date": "2025-06-01", "dayweather": "晴", "nightweather": "晴",
                     "daytemp": "32", "nighttemp": "18", "daywind": "南风", "daypower": "3"},
                ]
            }]
        }, ensure_ascii=False)

        with patch("agents.tools._amap_mcp", return_value=mock_mcp_data):
            result = benchmark(get_weather, "北京", 3)

        assert result["city"] == "北京"
        assert len(result["forecast"]) >= 1

    @pytest.mark.benchmark(min_rounds=10)
    def test_geocode_parsing(self, benchmark):
        """geocode JSON 解析的纯开销（mock _amap_mcp）"""
        from agents.tools import geocode

        mock_mcp_data = json.dumps({"results": [{"location": "120.15,30.25"}]})

        with patch("agents.tools._amap_mcp", return_value=mock_mcp_data):
            result = benchmark(geocode, "杭州西湖")

        assert result["longitude"] == 120.15
        assert result["latitude"] == 30.25


# =============================================================
# 4. Supervisor 轮询开销
# =============================================================

class TestBenchmarkSupervisorPolling:
    """测量 SupervisorAgent 轮询循环的开销。

    当前实现：threading.Thread + asyncio.sleep(0.1) 每 100ms 轮询。
    如果 mock graph 运行 0.5s，轮询约 5~7 次。
    """

    @pytest.mark.benchmark(min_rounds=5)
    def test_polling_overhead_fast(self, benchmark, trip_form_data):
        """mock graph 0.1s → 轮询约 2 次，测量额外开销"""
        from agents.supervisor import SupervisorAgent

        async def _run():
            with patch("agents.supervisor.trip_graph") as mock_graph:
                mock_graph.invoke.return_value = {"final_json": '{"title":"t","id":"b"}'}
                agent = SupervisorAgent()
                return await agent.run(trip_form_data, "bench_fast")

        result = benchmark(lambda: asyncio.run(_run()))
        assert result == {"title": "t", "id": "b"}

    @pytest.mark.benchmark(min_rounds=5)
    def test_polling_overhead_slow(self, benchmark, trip_form_data):
        """mock graph 1.0s → 轮询约 10~12 次，放大相对开销"""
        from agents.supervisor import SupervisorAgent

        async def _run():
            with patch("agents.supervisor.trip_graph") as mock_graph:
                def _delayed_invoke(state):
                    time.sleep(1.0)
                    return {"final_json": '{"title":"t","id":"b2"}'}
                mock_graph.invoke.side_effect = _delayed_invoke
                agent = SupervisorAgent()
                return await agent.run(trip_form_data, "bench_slow")

        result = benchmark(lambda: asyncio.run(_run()))
        assert result == {"title": "t", "id": "b2"}


# =============================================================
# 5. _fix_coordinates N+1 问题
# =============================================================

class TestBenchmarkFixCoordinates:
    """测量 _fix_coordinates 中 N+1 地理编码的累计延迟。"""

    @pytest.fixture
    def final_with_items(self, request):
        """生成包含 N 个行程项目的 final dict。"""
        n = request.param
        items = [{"name": f"place_{i}", "latitude": None, "longitude": None}
                 for i in range(n)]
        return {"dailyPlan": [{"periods": [{"items": items}]}]}

    @pytest.mark.parametrize("final_with_items", [5, 20, 50], indirect=True)
    @pytest.mark.benchmark(min_rounds=5)
    def test_fix_coordinates_n_plus_one(self, benchmark, final_with_items):
        """N 个 items → N 次 geocode HTTP 调用。串行时每次增加累计延迟。"""
        from agents.graph import _fix_coordinates

        # mock geocode 返回固定坐标
        with patch("agents.graph.geocode",
                   return_value={"longitude": 116.4, "latitude": 39.9}):
            result = benchmark(_fix_coordinates, final_with_items, "北京")

        items = final_with_items["dailyPlan"][0]["periods"][0]["items"]
        if items:
            assert result["dailyPlan"][0]["periods"][0]["items"][0].get("longitude") == 116.4


# =============================================================
# 6. LLM 工厂实例化开销
# =============================================================

class TestBenchmarkLLMFactory:
    """测量 ChatOpenAI 实例化的开销。每次 get_llm() 创建新实例。"""

    @pytest.mark.benchmark(min_rounds=100)
    def test_get_llm_instantiation(self, benchmark):
        """get_llm() 创建 ChatOpenAI 实例的纯开销"""
        from config import get_llm
        llm = benchmark(get_llm)
        assert llm is not None

    @pytest.mark.benchmark(min_rounds=100)
    def test_get_llm_structured_instantiation(self, benchmark):
        """get_llm_structured() 调用 get_llm() 并覆盖 temperature"""
        from config import get_llm_structured
        llm = benchmark(get_llm_structured)
        assert llm is not None
        assert llm.temperature == 0.3


# =============================================================
# 7. Research 节点串行分析
# =============================================================

class TestBenchmarkResearchSerialVsParallel:
    """展示 research_node 中天气获取在 LLM 之后串行的额外开销。"""

    @pytest.mark.benchmark(min_rounds=5)
    def test_research_with_weather(self, benchmark):
        """完整 research_node：0.5s mock LLM → 天气获取串行在 LLM 之后"""
        from agents.graph import research_node
        state = _make_minimal_state()

        with patch("agents.graph.get_llm", return_value=_make_delayed_llm(0.5)):
            with patch("agents.tools.flyai_search") as mock_fly:
                mock_fly.invoke.return_value = ""
                with patch("agents.graph.get_weather",
                           return_value={"live": {"weather": "晴"}, "forecast": []}):
                    result = benchmark(research_node, state)

        assert result is not None
        assert result["weather_data"] not in ("", "{}")

    @pytest.mark.benchmark(min_rounds=5)
    def test_research_no_weather(self, benchmark):
        """research_node 跳过天气：只有 0.5s mock LLM → 对比有无天气的时间差"""
        from agents.graph import research_node
        state = _make_minimal_state()

        with patch("agents.graph.get_llm", return_value=_make_delayed_llm(0.5)):
            with patch("agents.tools.flyai_search") as mock_fly:
                mock_fly.invoke.return_value = ""
                with patch("agents.graph.get_weather") as mock_weather:
                    # 模拟天气延迟（30ms，模拟 MCP 调用）
                    def _weather(*a, **kw):
                        time.sleep(0.03)
                        return {"live": {"weather": "晴"}, "forecast": []}
                    mock_weather.side_effect = _weather
                    result = benchmark(research_node, state)

        assert result is not None
