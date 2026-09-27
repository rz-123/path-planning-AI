"""
============================================================================
行程 API — 生成 / 进度查询 / 取消
============================================================================
RESTful API 设计说明：
  - POST   /api/v1/trips/generate     → 提交生成任务（异步，立即返回 tripId）
  - GET    /api/v1/trips/:id/status   → 轮询生成进度（前端每 3 秒请求）
  - DELETE /api/v1/trips/:id/cancel   → 取消正在生成的任务

设计模式：异步任务 + 轮询（Async Task + Polling）
  原因：LLM 生成行程需要 30~120 秒，HTTP 请求不能一直等待
  流程：客户端 POST 提交 → 后端返回 tripId → 客户端每 3 秒 GET 查询进度 → 完成后获取结果

面试考点：为什么不用 WebSocket 实时推送？
  - WebSocket 需要长连接，CloudRun 按请求计费不划算
  - 轮询简单可靠，前端 setInterval 每 3 秒请求一次，对服务器压力小
  - 如果未来有实时要求，可改用 SSE（Server-Sent Events）

面试考点：为什么 create_task 而不是 await？
  - await 会阻塞当前请求直到生成完成（用户等的太久）
  - create_task 将任务放入事件循环后台执行，立即返回 tripId
  - 这是典型的"提交即返回"异步模式
============================================================================
"""
# ===== 标准库导入 =====
import logging                                  # Python 日志模块，记录运行信息和错误

# ===== FastAPI 导入 =====
# APIRouter: FastAPI 子路由注册器，支持 prefix/tags 等分组配置
# Depends: 依赖注入系统，自动解析函数参数
# HTTPException: 标准 HTTP 错误响应（如 404 Not Found）
from fastapi import APIRouter, Depends, HTTPException
from api.deps import get_current_user           # 用户认证依赖（解析 JWT Token 获取 user_id）

# ===== 项目内部模块导入 =====
from schemas.trip import (
    TripFormData,                                # 表单输入 Pydantic Schema（自动验证 JSON 请求体）
    GenerateResponse,                            # 生成响应 Schema（tripId + status）
    GenerateStatusResponse,                      # 进度查询响应 Schema（含 progress/currentStep/result）
)
from services import trip_service               # 行程生成业务逻辑层（Service 层）

# ===== 创建子路由 =====
# prefix="/trips": 该路由器下所有路由自动带 /trips 前缀
# 挂载到 main.py 时加了 prefix="/api/v1"，所以完整路径是 /api/v1/trips/generate
router = APIRouter(prefix="/trips", tags=["行程"])
# tags=["行程"]: 在 Swagger 文档中自动分组到 "行程" 标签下
logger = logging.getLogger(__name__)            # 获取当前模块的日志实例


@router.post("/generate", response_model=GenerateResponse, status_code=201)
# @router.post: 注册 POST 方法路由，路径为 /api/v1/trips/generate
# response_model=GenerateResponse: 自动序列化响应并生成 OpenAPI 文档
# status_code=201: HTTP 201 Created（资源创建成功，语义上比 200 OK 更准确）
async def generate_trip(
    form: TripFormData,                          # FastAPI 自动将 JSON 请求体解析为 TripFormData（含 Pydantic 验证）
    user_id: str = Depends(get_current_user),    # Depends: 依赖注入，自动调用 get_current_user() 获取当前用户 ID
):
    """
    提交行程生成请求（POST /api/v1/trips/generate）

    请求体：TripFormData（目的地、日期、人数、风格偏好等）
    响应体：GenerateResponse { tripId, status: "processing", message }

    处理流程：
    1. FastAPI 自动将 JSON body 解析为 TripFormData（Pydantic 数据验证）
    2. 调用 trip_service.generate_trip() 创建后台异步任务
    3. 后台任务运行 LangGraph 5 节点工作流（不阻塞 HTTP 响应）
    4. 立即返回 tripId，客户端根据 tripId 轮询进度

    面试考点：response_model 在 FastAPI 中的作用？
    1. 自动过滤多余字段（只输出 Schema 定义的字段）
    2. 类型转换和序列化（正确转化 datetime 等复杂类型）
    3. 生成精确的 OpenAPI / Swagger 文档
    4. 验证响应的正确性（返回不符合 Schema 时报错）
    """
    # 记录关键业务日志，方便排查问题
    logger.info(f"生成行程: {form.destination} {form.days}天")

    # 委托给 Service 层处理，保持路由层简洁（Route → Service 分层）
    return await trip_service.generate_trip(form, user_id)


@router.get("/{trip_id}/status", response_model=GenerateStatusResponse)
# {trip_id}: 路径参数，FastAPI 自动从 URL 中提取
# 例如 GET /api/v1/trips/trip_a1b2c3d4/status → trip_id = "trip_a1b2c3d4"
async def get_generation_status(trip_id: str):
    """
    查询行程生成进度（GET /api/v1/trips/{trip_id}/status）

    URL 参数：
    - trip_id: 由 generate_trip 返回的任务 ID

    响应体（GenerateStatusResponse）：
    - tripId: 任务 ID
    - status: processing(生成中) / completed(完成) / failed(失败) / cancelled(已取消) / not_found(不存在)
    - progress: 进度百分比（0~100）
    - currentStep: 当前步骤描述文字（如 "规划路线中..."）
    - result: 生成完成后返回的完整 TripResult（dict 格式）

    轮询机制说明：
    - 前端 generate/index.js 使用 setInterval 每 3000ms 调用此接口
    - status="completed" 时 result 字段包含完整行程 JSON
    - status 变为 completed/failed/cancelled 后，前端停止轮询
    """
    # 委托给 Service 层查询任务状态
    return await trip_service.get_generation_status(trip_id)


@router.delete("/{trip_id}/cancel")
# DELETE 请求：符合 RESTful 语义，表示"删除/取消一个资源"
async def cancel_trip(trip_id: str):
    """
    取消正在生成的行程（DELETE /api/v1/trips/{trip_id}/cancel）

    触发时机：用户在生成页面点击"返回"按钮
    实现方式（协作式取消）：
    1. 请求 → trip_service.cancel_trip() → 将 trip_id 加入 _cancelled_trips 集合
    2. Agent 节点在每次执行前调用 check_cancelled() 检查集合
    3. 发现 trip_id 在集合中时抛出 CancelledError → 中断生成

    局限性（已知问题）：
    - LangGraph 的 invoke() 是同步阻塞的，LLM 调用期间无法中断
    - 取消检查点在各 Agent 节点开头，所以取消有延迟
    - 如果所有节点都在快速执行（无 LLM 调用），可能取消不生效
    """
    # 调用 Service 层取消逻辑
    ok = await trip_service.cancel_trip(trip_id)
    return {"success": ok, "tripId": trip_id}
