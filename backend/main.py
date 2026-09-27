"""
============================================================================
AI 旅行规划系统 — FastAPI 后端入口
============================================================================
整体架构说明：
  - Web 框架: FastAPI（异步高性能 Python Web 框架）
  - AI 引擎: LangGraph（有状态的多 Agent 工作流编排）
  - LLM: DeepSeek / OpenAI / 混元 / 智谱（通过 LangChain 统一调用）
  - 数据: SQLite + CloudBase 云数据库
  - 部署: CloudBase CloudRun 容器化部署
  - 外部服务: 高德（天气/搜索/路线走MCP，逆地理编码走REST API）、飞猪 FlyAI
============================================================================
"""
# ===== 标准库导入 =====
import asyncio                                  # Python 标准异步 I/O 库，提供事件循环和协程支持
import logging                                  # 日志模块，用于记录应用运行状态

# ===== 第三方库导入 =====
from contextlib import asynccontextmanager      # 异步上下文管理器装饰器，用于管理异步资源的生命周期
from fastapi import FastAPI                     # FastAPI 核心类，创建 Web 应用实例
from fastapi.middleware.cors import CORSMiddleware  # CORS 中间件，处理跨域请求

# ===== 项目内部模块导入 =====
from config import settings                    # 从 config.py 导入全局配置单例（Pydantic Settings 自动加载 .env）

# ===== 日志配置 =====
# basicConfig: 配置日志的基础格式和级别
# level=logging.INFO: 记录 INFO 及以上级别的日志
# format: 时间戳 | 级别 | 消息内容
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)            # 获取当前模块名称的 Logger 实例

# ===== 后台任务跟踪 =====
# 使用 Python 集合（set）持有所有后台异步任务（asyncio.Task）的引用
# 原因：asyncio 中如果 Task 没有被任何变量引用，GC 可能会回收它导致任务中断
# set() 是 hash 集合，查找 O(1)，适合只增不减的场景
_background_tasks = set()


# ===== 应用生命周期管理 =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期上下文管理器（替代旧版的 on_event 钩子）
    
    工作原理：
    - @asynccontextmanager 装饰器将生成器函数转为异步上下文管理器
    - yield 之前的代码在「应用启动」时执行
    - yield 之后的代码在「应用关闭」时执行
    - FastAPI 的 lifespan 参数将这个函数注册为生命周期处理器
    
    面试考点：为什么用 lifespan 而不是 @app.on_event？
    - FastAPI 推荐 lifespan 替代 on_event，更符合 asyncio 最佳实践
    - 单个 lifespan 管理所有启停逻辑，避免多个 on_event 的执行顺序问题
    - 支持上下文变量（contextvars）的作用域管理
    """
    logger.info("启动中...")                     # 启动时：记录启动日志
    yield                                        # yield = 应用运行期间的暂停点，应用关闭后恢复执行
    logger.info("已关闭")                        # 关闭时：记录关闭日志


# ===== 创建 FastAPI 应用实例 =====
app = FastAPI(
    title=settings.app_name,                    # 应用名称（显示在 Swagger 文档顶部）
    version="2.0.0",                            # API 版本号
    lifespan=lifespan,                          # 注册生命周期管理器
)

# ===== 注册 CORS 中间件 =====
# CORSMiddleware: 跨域资源共享中间件
# 作用：允许浏览器从不同域名/端口的前端页面请求后端 API
# 面试考点：什么是 CORS？为什么需要它？
# - 浏览器的同源策略（Same-Origin Policy）阻止不同源的 AJAX 请求
# - 后端设置 CORS 响应头告诉浏览器允许哪些来源跨域访问
# - allow_origins=["*"]: 允许所有来源（开发/测试用，生产环境应指定具体域名）
# - allow_methods=["*"]: 允许所有 HTTP 方法（GET/POST/PUT/DELETE 等）
# - allow_headers=["*"]: 允许所有请求头
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 注册路由模块 =====
# 使用懒加载方式在创建 app 后导入路由（避免循环导入问题）
# include_router: 将子路由挂载到主应用，prefix 指定 URL 前缀
from api.v1.trips import router as trips_router              # 行程相关 API（生成/进度/取消）
from api.v1.destinations import router as destinations_router  # 目的地推荐 API
from api.v1.geo import router as geo_router                  # 地理编码 API
from api.v1.auth import router as auth_router                # 用户登录 API

app.include_router(trips_router, prefix="/api/v1")           # 挂载行程路由 → 实际路径 /api/v1/trips/...
app.include_router(destinations_router, prefix="/api/v1")    # 挂载目的地路由 → /api/v1/destinations/...
app.include_router(geo_router, prefix="/api/v1")             # 挂载地理路由 → /api/v1/geo/...
app.include_router(auth_router, prefix="/api/v1")            # 挂载认证路由 → /api/v1/auth/...

# ===== 根路由 =====
@app.get("/")                                   # 装饰器：将函数注册为 GET / 路由处理器
async def root():
    """
    根路径健康检查
        
    返回应用基本信息。
    面试考点：为什么要有一个根路由？
    - 用于负载均衡器的健康探测
    - 用于 CloudRun/容器平台的存活性检查
    - Swagger 文档位于 /docs，用 docs 字段方便开发者发现
    """
    return {"name": settings.app_name, "version": "2.0.0", "docs": "/docs"}


# ===== 健康检查路由 =====
@app.get("/health")                             # GET /health
async def health():
    """
    健康检查端点
        
    用途：
    - CloudBase CloudRun 使用此端点判断容器是否就绪
    - 返回 {"status": "ok"} 表示服务正常运行
    - 生产环境中可以扩展为检查数据库连接、外部服务可达性等
    """
    return {"status": "ok"}


# ===== 地图 Key 获取接口 =====
@app.get("/api/v1/config/map-key")             # GET /api/v1/config/map-key
async def get_map_key():
    """
    前端获取高德地图 API Key

    设计原因：
    - 地图 Key 属于敏感信息，不应硬编码在前端代码里
    - 通过后端 API 动态下发，可以由管理员随时更换 Key
    - 前端小程序在 app.js 的 onLaunch 中调用此接口获取 Key

    历史变更：原为腾讯地图 Key，2026-07 统一替换为高德地图
    """
    return {"amapKey": settings.amap_key or ""}
