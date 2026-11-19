"""
============================================================================
行程生成服务 — 核心业务逻辑层（Service Layer）
============================================================================
架构定位：
  路由层 (api/v1/trips.py) → 处理 HTTP 请求/响应
  服务层 (services/trip_service.py) → 核心业务逻辑，调度 Agent 和任务管理
  工具层 (agents/tools.py) → 调用外部 API（高德、飞猪、搜索）
  Agent层 (agents/graph.py) → LLM + LangGraph 工作流

任务管理设计：
  - 使用内存字典 _generation_tasks 跟踪所有生成任务的进度
  - 使用内存集合 _cancelled_trips 实现取消机制
  - 当前采用内存存储（非持久化），服务重启后旧任务丢失

⚠️ 部署限制（重要，勿擅自改多实例）：
  任务状态只存在「当前进程内存」里，所以 CloudRun 必须固定为单实例（最大实例数 = 1）。
  一旦扩到多实例：POST /generate 打到实例 A，GET /status 轮询可能打到实例 B，
  B 的内存里没有这个 trip_id，会一直返回 not_found（概率性故障，极难排查）。
  要支持多实例必须先把任务状态换成共享存储（CloudBase 云数据库 / Redis）。

面试考点：为什么不用数据库存储任务状态？
  - 任务状态是临时性的（生成完成就结束），不需要持久化
  - 内存操作比数据库快 100~1000 倍
  - 减少数据库的读写压力
  - 生产环境可考虑 Redis 替代（支持过期 + 持久化 + 分布式）

面试考点：asyncio.create_task() 的工作原理？
  - create_task 将协程包装为 Task 对象并注册到事件循环
  - Task 在后台并发执行（不阻塞当前协程）
  - 如果 Task 没有被任何变量引用，可能被 GC 回收
  - _background_tasks 集合持有所有 Task 引用，防止 GC 回收
  - add_done_callback: Task 完成时自动从集合中移除引用
============================================================================
"""
# ===== 标准库导入 =====
import asyncio                                  # 异步 I/O 库
import logging                                  # 日志
import traceback                                # 调用栈追踪（用于异常日志）
import uuid                                     # 唯一 ID 生成

# ===== 项目 Schema =====
from schemas.trip import (
    TripFormData,                                # 表单数据（Pydantic 验证）
    GenerateResponse,                            # 生成响应
    GenerateStatusResponse,                      # 进度响应
)

logger = logging.getLogger(__name__)            # 日志实例

# ===== 任务管理数据结构 =====
# 所有正在生成/已完成/已失败的任务状态字典
# 键: trip_id (如 "trip_a1b2c3d4e5f6")
# 值: {"status":"processing", "progress":50, "currentStep":"规划路线...", "result":{...}}
_generation_tasks: dict[str, dict] = {}

# 已取消的任务 ID 集合
# Agent 节点在每个步骤开始时检查此集合，如果 trip_id 在其中则抛出 CancelledError
_cancelled_trips: set = set()


async def generate_trip(form: TripFormData, user_id: str) -> GenerateResponse:
    """
    提交行程生成任务（创建异步后台任务并立即返回）
    
    这个方法是整个系统的核心入口，处理流程：
    1. 生成唯一 trip_id
    2. 在内存中创建任务状态追踪记录
    3. 用 asyncio.create_task 创建后台任务
    4. 将 Task 引用保存到 _background_tasks（防止 GC 回收）
    5. 立即返回 tripId 让前端开始轮询
    
    参数：
    - form: Pydantic 验证后的表单数据
    - user_id: 当前用户 ID
    
    返回：
    - GenerateResponse: { tripId, status:"processing", message }
    
    面试考点：为什么不在 generate_trip 中直接 await supervisor.run()？
    - await 会阻塞当前 HTTP 请求，直到 LLM 生成完成（60~120秒）
    - 用户浏览器会超时（HTTP 超时通常 30~60 秒）
    - CloudRun 的网关也有超时限制（默认 60 秒）
    - 异步任务模式（提交→轮询）是最佳实践：
      * 适合长时间处理（LLM 调用、图像处理、报表生成）
      * 用户体验好（立即反馈 + 进度条）
      * 资源利用率高（请求线程不阻塞）
    """
    from agents.supervisor import SupervisorAgent  # 惰性导入（延迟加载 Agent，避免循环导入）

    # 生成唯一 trip_id：前缀 trip_ + 12位随机 hex
    trip_id = "trip_" + uuid.uuid4().hex[:12]
    
    # 初始化任务状态（记录到内存字典中）
    _generation_tasks[trip_id] = {
        "status": "processing",                  # 状态：processing/completed/failed/cancelled
        "progress": 0,                           # 初始进度 0%
        "currentStep": "启动 LangGraph...",       # 当前步骤描述（前端展示用）
        "result": None,                           # 完成后才填充完整 TripResult
        "userId": user_id,                        # 归属用户：查询/取消时校验，防止越权访问别人的行程
    }

    # 创建 SupervisorAgent 实例（编排 LangGraph 工作流）
    supervisor = SupervisorAgent()
    
    # === 核心：异步任务创建 ===
    # asyncio.create_task: 将协程包装为 Task，注册到事件循环后台运行
    # 注意：这里不回等待，Task 在后台执行，当前函数立即继续
    task = asyncio.create_task(_run_generation(trip_id, form, user_id, supervisor))
    
    # === 防止 GC 回收 ===
    # 将 Task 引用保存到集合中，防止垃圾回收器回收未完成的 Task
    # 不保存引用的话，如果 Task 被 GC 回收，生成就会中断
    from main import _background_tasks          # 导入 main.py 中的后台任务集合
    _background_tasks.add(task)                  # 添加引用
    
    # add_done_callback: 注册回调函数，Task 完成时自动调用
    # discard: 集合的 discard 方法（与 remove 的区别：不存在时不报错）
    task.add_done_callback(_background_tasks.discard)
    
    # 立即返回 tripId（不等待生成完成）
    return GenerateResponse(
        tripId=trip_id,                          # 任务 ID（前端轮询凭证）
        status="processing",                     # 状态：处理中
        message="LangGraph Agent 生成中..."       # 状态消息
    )


async def _run_generation(trip_id: str, form: TripFormData, user_id: str, supervisor):
    """
    后台运行 LangGraph 生成流程（核心执行函数）
    
    这个函数在 asyncio Task 中运行，不阻塞 HTTP 响应线程
    
    执行流程：
    1. 更新进度 → 分析偏好（10%）
    2. 调用 supervisor.run() → Agent 工作流（research→plan→budget→reflection→format）
    3. 检查是否被取消（从 _cancelled_trips 中查找）
    4. 填充 userId 和 id 到结果中
    5. 更新任务状态为 completed 或 failed
    
    面试考点：try/except 在生产代码中的正确用法？
    - 捕获具体异常类型（Exception）而非 BaseException（会捕获 SystemExit/KeyboardInterrupt）
    - 记录完整 traceback（traceback.print_exc()）
    - 更新任务状态为 failed，让前端可以感知错误
    - 不要静默吞掉异常（上层的 catch 是合理的：这里是错误处理，不是忽略）
    """
    try:
        # 更新进度：分析阶段（10%）
        _generation_tasks[trip_id]["currentStep"] = "分析你的偏好和需求"
        _generation_tasks[trip_id]["progress"] = 10

        # === 运行 LangGraph 工作流 ===
        # 这是最耗时的部分：5个 Agent 串行 + 可能的修正循环
        # 每个 Agent 调用一次 LLM（research→plan→budget→reflection→format）
        # 单次调用约 10~30 秒，总计 50~150 秒
        result = await supervisor.run(form, trip_id)

        # 检查用户是否已取消（在生成过程中点击了返回按钮）
        if trip_id in _cancelled_trips:
            _cancelled_trips.discard(trip_id)    # 从取消集合中移除（清理）
            # 为什么用 update 而不是整体重新赋值：整体赋值会丢掉 userId，导致后续无法校验归属
            _generation_tasks[trip_id].update({
                "status": "cancelled",            # 状态：已取消
                "progress": 0,
                "currentStep": "已取消",
                "result": None
            })
            return                                # 直接返回，不继续处理结果

        # 将用户 ID 和 trip ID 注入到结果中
        result["userId"] = user_id               # 关联用户
        result["id"] = trip_id                   # 设置 trip ID
        result["status"] = "completed"           # 设置状态为完成

        # 打印关键结果到控制台（方便调试和监控）
        print(f"[Agent] {trip_id} 生成完成: {result.get('title','')} ¥{result.get('totalBudget',0)}")

        # 更新任务状态：完成（用 update 保留 userId 归属字段）
        _generation_tasks[trip_id].update({
            "status": "completed",
            "progress": 100,                     # 进度 100%
            "currentStep": "完成",                # 步骤描述
            "result": result,                    # 完整结果（TripResult dict）
        })
        
    except Exception as e:
        # 任何异常都记录日志并标记任务为失败
        logger.error(f"生成失败 {trip_id}: {e}")
        traceback.print_exc()
        
        # 更新任务状态：失败（用 update 保留 userId 归属字段）
        _generation_tasks[trip_id].update({
            "status": "failed",                  # 状态：失败
            "progress": 0,
            "currentStep": str(e),               # 错误信息作为当前步骤（前端展示）
            "result": None
        })


async def cancel_trip(trip_id: str, user_id: str | None = None) -> bool:
    """
    取消正在生成的任务

    user_id 说明（安全修复）：
    - 传了 user_id 且任务有归属时，必须与任务归属一致才允许取消
    - 不一致直接返回 False（不提示"任务存在但不是你的"，避免探测他人 trip_id）
    
    取消机制：
    1. 将 trip_id 加入 _cancelled_trips 集合
    2. Agent 节点（research/plan/budget/reflection/format）在执行前都调用 _check_cancelled()
    3. _check_cancelled() 发现 trip_id 在集合中时抛出 CancelledError
    4. CancelledError 传播到 _run_generation 的 except 块
    
    局限性（已知问题）：
    - LLM 调用期间无法中断（invoke() 是同步阻塞的）
    - 会在当前 LLM 调用完成后的下一个 Agent 节点检查取消信号
    
    面试考点：Python 中如何实现优雅的任务取消？
    - 协作式取消（Cooperative Cancellation）：被取消方主动检查取消信号
    - 不同于操作系统的强制 kill（SIGKILL）
    - asyncio 的 cancel() 也是协作式的：抛出 CancelledError，协程需要自己处理
    """
    task = _generation_tasks.get(trip_id)        # 获取任务状态，不存在返回 None
    if not task:
        return False                             # 任务不存在
    # 归属校验：任务有归属且不是当前用户 → 不允许取消（防止取消别人的生成任务）
    if user_id is not None and task.get("userId") and task["userId"] != user_id:
        return False
    if task["status"] == "processing":           # 只有正在处理的任务才能被取消
        _cancelled_trips.add(trip_id)            # 加入取消集合（信号传递）
        return True                              # 返回取消成功
    return False                                 # 任务已完成，无法取消


async def get_generation_status(trip_id: str, user_id: str | None = None) -> GenerateStatusResponse:
    """
    查询生成进度（前端轮询调用）

    user_id 说明（安全修复）：
    - 传了 user_id 且任务有归属时，非归属用户一律按 not_found 返回
    - 为什么返回 not_found 而不是 403：403 等于告诉对方"这个 trip_id 是存在的"，属于信息泄露
    """
    task = _generation_tasks.get(trip_id)        # 安全获取任务状态
    if not task:
        # 任务不存在：可能已过期、输入错误、或服务重启后丢失
        return GenerateStatusResponse(
            tripId=trip_id, 
            status="not_found"
        )

    # 归属校验：不是自己的任务，按"不存在"处理
    if user_id is not None and task.get("userId") and task["userId"] != user_id:
        return GenerateStatusResponse(tripId=trip_id, status="not_found")

    # 显式挑字段构造响应：task 里有 userId 等内部字段，不能原样透传给前端
    return GenerateStatusResponse(
        tripId=trip_id,
        status=task["status"],
        progress=task.get("progress", 0),
        currentStep=task.get("currentStep", ""),
        result=task.get("result"),
    )
