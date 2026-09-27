"""
Agent 工具函数 — 共享状态操作 + 自定义异常

提取原因：
- 避免 graph.py 与 trip_service.py 之间的循环导入问题
- _update_progress / _check_cancelled 被多个 Agent 模块共用
"""


class CancelledError(Exception):
    """
    自定义异常：任务被取消

    用途：在 Agent 节点检测到取消信号时抛出，中断 LangGraph 执行
    """
    pass


def update_progress(trip_id: str, step: str, progress: int):
    """
    更新前端进度条显示

    写入 trip_service._generation_tasks 内存字典，
    前端通过轮询 GET /:id/status 读取。
    """
    from services.trip_service import _generation_tasks
    if trip_id and trip_id in _generation_tasks:
        _generation_tasks[trip_id]["currentStep"] = step
        _generation_tasks[trip_id]["progress"] = progress


def check_cancelled(trip_id: str):
    """
    检查任务是否被取消（协作式取消机制）

    在每个 Agent 节点的开头调用，发现取消信号立即抛出异常。
    """
    from services.trip_service import _cancelled_trips
    if trip_id and trip_id in _cancelled_trips:
        _cancelled_trips.discard(trip_id)
        raise CancelledError(f"任务 {trip_id} 已取消")
