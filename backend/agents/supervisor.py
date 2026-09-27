"""
============================================================================
Supervisor Agent — LangGraph 工作流编排调度器
============================================================================
设计模式：Facade（外观模式）+ Supervisor（监督者模式）

职责：
  1. 接收表单数据，构建 TripState 初始状态
  2. 启动 LangGraph 工作流（在独立线程中运行，避免阻塞 asyncio 事件循环）
  3. 轮询等待完成，返回最终 JSON 结果
  4. 支持取消（通过 CancelledError 机制）

为什么用线程运行 LangGraph？
  - LangGraph 的 invoke() 是同步阻塞调用，会在内部循环调用 LLM
  - 如果直接在 asyncio 事件循环中 await 同步代码，会阻塞整个事件循环
  - 放到 daemon 线程中运行，主循环用 asyncio.sleep() 轮询
  - 面试考点：asyncio + 同步阻塞代码的混合处理方案
    * 方案1: run_in_executor() — 将同步代码放到线程池
    * 方案2: 手动创建线程（本项目方案）— 更灵活的错误处理
    * 方案3: loop.run_until_complete() — 不推荐，会阻塞事件循环
============================================================================
"""
# ===== 标准库导入 =====
import asyncio                                  # 异步 I/O（用于 run_in_executor）
import json
import logging                                  # 日志
from agents.utils import CancelledError
from agents.graph import trip_graph, TripState

logger = logging.getLogger(__name__)

# 风格/预算的中文标签映射表
STYLE_LABEL = {
    "leisure": "轻松休闲",                       # 慢节奏、不赶时间
    "deep": "深度打卡",                          # 文化深度体验
    "artistic": "文艺小资",                      # 网红打卡、小资生活
    "intensive": "特种兵式",                     # 高强度、一天逛完
}

BUDGET_RANGE = {
    "economy": "¥500-1k",                       # 经济型：人均 500~1000/天
    "comfort": "¥1k-1.5k",                      # 舒适型：人均 1000~1500/天
    "quality": "¥1.5k-2k",                      # 品质型：人均 1500~2000/天
}


class SupervisorAgent:
    """
    编排调度 Agent（外观模式）
    
    对外接口：
    - run(form_data, trip_id) → dict: 运行工作流，返回完整 TripResult
    
    面试考点：外观模式（Facade Pattern）的优势？
    - 隐藏复杂子系统（LangGraph 5个 Agent 节点）
    - 提供简洁统一的外部接口
    - 降低调用方成本（只需传 form_data，不需了解内部拓扑）
    - 便于替换底层实现（可以换为其他编排引擎）
    """

    async def run(self, form_data, trip_id: str = "") -> dict:
        """
        运行 LangGraph 工作流生成行程（使用 run_in_executor 避免阻塞事件循环）

        与旧版区别：
        1. threading.Thread → loop.run_in_executor (标准 asyncio 线程池)
        2. 100ms 轮询 → 无需轮询，await 直接返回
        3. 支持外部调用 task.cancel() 取消
        """
        # ===== 第1步：构建初始状态 =====
        state: TripState = {
            "destination": form_data.destination,
            "origin": form_data.origin,
            "start_date": str(form_data.start_date) if form_data.start_date else "",
            "end_date": str(form_data.end_date) if form_data.end_date else "",
            "days": form_data.days,
            "nights": form_data.nights,
            "people": form_data.people,
            "adults": form_data.adults,
            "children": form_data.children,

            "transport": "train",

            "style": form_data.style.value if hasattr(form_data.style, 'value') else str(form_data.style),
            "style_label": STYLE_LABEL.get(
                form_data.style.value if hasattr(form_data.style, 'value') else str(form_data.style),
                "旅行"
            ),

            "interests": form_data.interests,

            "budget": form_data.budget.value if hasattr(form_data.budget, 'value') else str(form_data.budget),
            "budget_range": BUDGET_RANGE.get(
                form_data.budget.value if hasattr(form_data.budget, 'value') else "comfort",
                "¥1k-1.5k"
            ),

            "accommodation": form_data.accommodation.value if hasattr(form_data.accommodation, 'value') else str(form_data.accommodation),

            "special_needs": form_data.special_needs or "",

            "trip_id": trip_id,

            "research_result": "",
            "plan_result": "",
            "budget_result": "",
            "reflection": "",
            "weather_data": "{}",
            "final_json": "",

            "revision_count": 0,
            "next_action": "",
        }

        logger.info(f"[Supervisor] 启动 LangGraph: {state['destination']} {state['days']}天 trip_id={trip_id}")

        # ===== 第2步：在 asyncio 线程池中运行 LangGraph =====
        # loop.run_in_executor(None, fn) 将同步函数提交到默认线程池
        # 返回 asyncio.Future，await 等待结果（不阻塞事件循环）
        loop = asyncio.get_running_loop()

        try:
            result = await loop.run_in_executor(None, trip_graph.invoke, state)
        except CancelledError:
            logger.info(f"[Supervisor] {trip_id} 已取消")
            return {}

        # ===== 第3步：提取并返回最终 JSON =====
        final = json.loads(result.get("final_json", "{}"))
        logger.info(f"[Supervisor] 完成: {final.get('id','?')}")
        return final