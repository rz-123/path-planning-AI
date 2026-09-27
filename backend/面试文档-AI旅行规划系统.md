# AI 旅行规划系统 — 面试文档

---

## 目录
1. [项目概述](#1-项目概述)
2. [技术架构](#2-技术架构)
3. [LangGraph 多 Agent 工作流](#3-langgraph-多-agent-工作流)
4. [工具层设计](#4-工具层设计)
5. [异步并发架构](#5-异步并发架构)
6. [API 设计](#6-api-设计)
7. [数据流与状态管理](#7-数据流与状态管理)
8. [Prompt 工程](#8-prompt-工程)
9. [性能优化](#9-性能优化)
10. [容错与降级](#10-容错与降级)
11. [测试体系](#11-测试体系)
12. [部署运维](#12-部署运维)
13. [面试高频问题](#13-面试高频问题)

---

## 1. 项目概述

### 1.1 一句话描述
基于 LangGraph 多 Agent 工作流的 AI 旅行规划系统——用户输入目的地、日期、预算，AI 自动生成包含路线、预算、天气适配的完整行程。

### 1.2 技术栈
| 层级 | 技术 | 说明 |
|------|------|------|
| 框架 | FastAPI | 异步 Web 框架，原生 async/await |
| Agent 编排 | LangGraph | StateGraph + 条件边，状态图驱动 |
| LLM | DeepSeek V4 | 首选 LLM，也支持 OpenAI / 混元 / 智谱 |
| 外部服务 | 高德 MCP + 飞猪 FlyAI | 天气/地理编码/路线 + 门票/酒店比价 |
| 异步 | asyncio + run_in_executor | 非阻塞 HTTP + 线程池跑同步代码 |
| 容器化 | Docker | python:3.12-slim + Node.js |
| 部署 | CloudBase CloudRun | Serverless 容器 |

### 1.3 关键数字
- **98 个**单元测试 + **19 个**性能基准测试
- **5 个**LangGraph 节点 + **1 个**条件边（修正循环）
- **2 个**LangChain @tool（amap / flyai_search）
- **8 条**API 路由（含健康检查、配置下发）
- 行程生成耗时 **60~120s**
- 并发支持 **50+** 用户

---

## 2. 技术架构

### 2.1 分层架构

```
小程序前端 ──HTTP──▶ FastAPI ──▶ SupervisorAgent ──▶ LangGraph
                          │              │
                    ┌─────┼──────┐   ThreadPoolExecutor
                    │     │      │         │
                   DB   高德   飞猪   research→plan→budget→reflection→format
```

### 2.2 文件结构

| 目录/文件 | 职责 |
|-----------|------|
| `main.py` | FastAPI 应用入口，CORS 中间件，路由注册 |
| `config.py` | Settings 单例（Pydantic BaseSettings），自动加载 .env |
| `agents/` | Agent 核心：graph.py（工作流）、tools.py（工具）、supervisor.py（异步封装）、utils.py（进度/取消） |
| `api/v1/` | REST 端点：auth.py（登录）、trips.py（行程CRUD）、destinations.py（热门目的地）、geo.py（逆地理编码） |
| `schemas/` | Pydantic 数据模型：TripFormData、TripResult |
| `services/` | 业务逻辑：trip_service.py（异步任务管理） |
| `tests/` | 12 个测试文件，98 个用例 |

---

## 3. LangGraph 多 Agent 工作流

### 3.1 工作流拓扑

```
   START
     │
     ▼
┌──────────┐      ┌─────────┐      ┌──────────┐      ┌────────────┐      ┌──────────┐
│ research │ ──▶  │  plan   │ ──▶  │  budget  │ ──▶  │ reflection │ ──▶  │  format  │
│  调研节点 │      │  规划节点 │      │  预算节点 │      │   反思节点   │      │  合成节点 │
└──────────┘      └─────────┘      └──────────┘      └────────────┘      └──────────┘
                                                            │
                                                   评分 < 5 + 有严重问题
                                                            │
                                                   回到 plan / budget
```

### 3.2 五个节点详解

#### Node 1: research_node（调研节点，进度 20%）
**做什么**：搜索目的地景点、餐厅、酒店信息
1. 调用飞猪 `search-poi` 获取真实景点数据（RAG 增强检索）
2. 并行调用 `get_weather()` 获取天气预报
3. LLM 综合所有信息，输出结构化 JSON（attractions + restaurants + hotels）

**输入**：`destination`, `days`, `style_label`, `interests`, `budget_range`
**输出**：`research_result`（景点列表 + 餐厅列表 + 酒店候选 + 旅游提示）

**面试考点**：为什么要并行天气和 LLM？
- LLM 调用是瓶颈（10~30s），天气 API 是 I/O（2~5s）
- 两个操作互不依赖，并行可节省 2~5s
- 用 `ThreadPoolExecutor.submit()` 而非 asyncio，因为 LLM 是同步调用

#### Node 2: plan_node（规划节点，进度 50%）
**做什么**：将调研结果编排为每天的具体路线
1. 从 research_result 提取景点名、餐厅名、酒店候选
2. LLM 生成每天 4 个时段（上午/中午/下午/晚上）的行程安排
3. 规则约束：同区景点同天、上午1个核心景点、中午安排餐厅、晚上选近酒店景点

**输入**：`research_result`, `start_date`, `end_date`, `weather_info`
**输出**：`plan_result`（dailyPlan 数组，每天含 4 个 periods）

**面试考点**：为什么需要 plan 节点而不直接让 research 输出完整行程？
- 职责分离：调研=信息收集，规划=路线编排，单一职责
- research 输出的景点质量影响 plan 质量，分步便于 reflection 精确定位问题节点

#### Node 3: budget_node（预算节点，进度 70%）
**做什么**：计算住宿+餐饮+交通+门票四项费用
1. 调用飞猪 `search-hotels` 获取真实酒店价格
2. LLM 基于 BUDGET_PROMPT 模板计算费用明细和饼图数据
3. 规则：周末上浮 20-50%、儿童半价、往返大交通标注"未计算"

**输入**：`plan_result`, `budget_range`, `accommodation`, `days`, `people`
**输出**：`budget_result`（budgetDetail + budgetPieData + totalBudget）

#### Node 4: reflection_node（反思节点，进度 85%）— 混合评分机制
**做什么**：代码+规则双重检查行程质量
1. **代码客观检查（10 分扣分制）**：
   - 调研结果为空 → -5 分
   - 某天完全无内容 → -2 分/天
   - 时段不足 → -1 分/天
   - 景点总数不足 → -2 分
   - 未计算预算 → -3 分
2. **规则化语义检查**（代替 LLM，节省 10~30s）：
   - 雨天是否安排了过多户外景点
   - 景点区域多样性是否覆盖足够
   - 预算四项占比是否合理
3. **评分决策**：
   - ≥5 分 → 通过，进入 format
   - <5 分且有严重问题 → 回到对应 Agent 修正（最多 1 次）
   - 否则 → 勉强通过

**面试考点**：为什么用"代码+规则"而不是 LLM 做反思？
- 代码检查：精确、可复现、快（毫秒级），覆盖已知规则
- 规则检查：覆盖雨天/区域/预算等高频场景，比 LLM 更稳定
- LLM 检查：不稳定，每次结果不同，额外耗时 10~30s
- 混合方案 = 代码保底，规则提效，LLM 仅作最后兜底

#### Node 5: format_node（合成节点，进度 95%）
**做什么**：将 plan + budget 合并为最终 TripResult JSON
1. 填入所有静态参数（id, title, dates, people 等）
2. 嵌入 budgetDetail 和 budgetPieData
3. 嵌入 dailyPlan
4. 容错：如果 JSON 解析失败，回退到 LLM 合成

### 3.3 状态管理

状态通过 `TripState` (TypedDict) 在节点间传递：

```python
class TripState(TypedDict):
    trip_id: str            # 任务 ID
    destination: str        # 目的地
    days: int               # 天数
    start_date: str         # 开始日期
    # ... 用户参数
    research_result: str    # 调研输出（JSON 字符串）
    plan_result: str        # 规划输出
    budget_result: str      # 预算输出
    revision_count: int     # 修正计数（最多 1 次）
```

每个节点读取上游状态、写入自己产出的字段，状态不可变（返回新 dict）。

### 3.4 条件边与修正循环

当 reflection 评分 < 5 且存在 critical 级别问题时，触发条件边回到 plan 或 budget 节点：

```python
workflow.add_conditional_edges("reflection", decide_next, {
    "plan": "plan",
    "budget": "budget",
    "format": "format"
})
```

`revision_count` 上限为 1，防止无限循环。

---

## 4. 工具层设计

### 4.1 工具清单

| 工具 | 实现 | 用途 | 调用者 |
|------|------|------|--------|
| `_amap_mcp()` | MCP 协议（3步握手） | 天气/地理编码/搜索/路线 | get_weather, geocode |
| `get_weather()` | 封装 _amap_mcp + 往年兜底 | 7天天气预报 | research 节点 |
| `geocode()` | 高德 MCP maps_geo | 地址→坐标（反幻觉） | 内部 _fix_coordinates |
| `flyai_search()` | subprocess 调 flyai CLI | 景点门票/酒店价格/机票 | research + budget 节点 |

### 4.2 高德 MCP 协议（面试重点）

**MCP 三步握手流程**：
1. `initialize` → 获取 session_id
2. `notifications/initialized` → 确认就绪
3. `tools/call` → 调用具体工具

**Session 缓存机制**：
```python
_mcp_sessions: dict[str, dict] = {}  # key = amap_key 的 MD5 哈希

def _amap_mcp(tool_name: str, **kwargs) -> str:
    key = hashlib.md5(settings.amap_key.encode()).hexdigest()
    if key not in _mcp_sessions:
        # 三步握手，缓存 session
        _mcp_sessions[key] = {"headers": {...}}
    # 直接 tools/call，跳过握手
```

**面试考点：MCP vs Function Calling？**
- Function Calling：LLM 服务商的能力（如 OpenAI function_call），耦合于服务商
- MCP（Model Context Protocol）：独立于 LLM 的通用工具协议
- 优势：工具与服务解耦，可独立开发、测试、部署
- Session 缓存：N 次调用从 3N 次 HTTP 降到 N 次（减少 66%）

### 4.3 飞猪 FlyAI 集成

**为什么用 subprocess 而不是 SDK？**
- 飞猪只提供 npm CLI 包（`@fly-ai/flyai-cli`），没有 Python SDK
- subprocess 是唯一调用方式
- `text=False` + UTF-8 手动解码解决 Windows GBK 编码问题

**RAG 增强检索模式**：
1. research 节点调用 `search-poi --city-name X --keyword Y` 获取景点真实数据
2. budget 节点调用 `search-hotels --dest-name X` 获取酒店真实价格
3. 结果截取前 1500 字注入 Prompt
4. LLM 基于真实数据而非训练记忆给出价格推荐

**飞猪不可用时的降级**：
- CLI 未安装 → 静默跳过，LLM 用训练数据中的价格估算
- API Key 无效 → 同上
- 超时/异常 → 同上

---

## 5. 异步并发架构

### 5.1 问题背景

AI 行程生成耗时 60~120s，HTTP 请求不能阻塞等待。

### 5.2 解决方案："提交即返回"模式

```
前端 POST /trips/generate
       │
       ▼
FastAPI handler ──▶ asyncio.create_task(trip_service.generate())
       │                     │
       ▼                     ▼
返回 {"taskId": "xxx"}   后台 run_in_executor(SupervisorAgent.run)
       │                     │
       ▼                     ▼
前端轮询 GET /trips/{id}/status    LangGraph 5节点执行
                                          │
                                          ▼
                                    写入 _generation_cache
```

### 5.3 SupervisorAgent 封装

```python
class SupervisorAgent:
    """将同步 LangGraph 封装为 async 接口"""
    async def run(self, state: TripState) -> TripState:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_run, state)
    
    def _sync_run(self, state: TripState) -> TripState:
        return self._graph.invoke(state)  # LangGraph 同步执行
```

**面试考点：为什么用 run_in_executor 而不是 asyncio.to_thread？**
- `asyncio.to_thread` 是 Python 3.9+ 的语法糖，底层也是 run_in_executor
- `run_in_executor` 更明确地表达"在线程池中运行阻塞代码"
- 可以重用线程池，避免频繁创建/销毁线程

### 5.4 前端轮询机制

```
GET /api/v1/trips/{trip_id}/status
       │
       ▼
查 _generation_cache[trip_id]
       │
  ┌────┼────┐
  │    │    │
None processing completed
 404   progress%  返回完整结果
```

为什么不选 WebSocket？
- CloudRun 按请求计费，WebSocket 长连接成本高
- 轮询实现简单，前端只需每 2s 请求一次
- 取消操作通过 `_cancelled_trips` 集合实现

### 5.5 进度通知与取消

```python
_progress_store: dict[str, dict] = {}   # {"trip_id": {"percent": 50, "message": "规划中..."}}
_cancelled_trips: set = set()            # 被取消的 trip_id 集合
```

每个节点执行前调用 `check_cancelled()`，取消时抛出 `CancelledError`：
```python
def check_cancelled(trip_id: str):
    if trip_id in _cancelled_trips:
        _cancelled_trips.remove(trip_id)
        raise CancelledError(trip_id)
```

---

## 6. API 设计

### 6.1 路由总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/` | 应用信息 |
| GET | `/api/v1/config/map-key` | 高德 Key 下发 |
| GET | `/api/v1/destinations/hot` | 热门目的地（20个） |
| GET | `/api/v1/destinations/random` | 随机目的地 |
| POST | `/api/v1/trips/generate` | 提交行程生成任务 |
| GET | `/api/v1/trips/{id}/status` | 查询生成进度 |
| GET | `/api/v1/geo/reverse?lat=&lng=` | 逆地理编码（坐标→地址） |
| POST | `/api/v1/auth/wx-login` | 微信小程序登录 |

### 6.2 核心接口：行程生成

**请求**：
```json
POST /api/v1/trips/generate
{
    "destination": "北京",
    "startDate": "2026-07-10",
    "endDate": "2026-07-13",
    "adults": 2, "children": 0,
    "budget": "comfort",
    "style": "culture",
    "interests": ["历史", "美食"],
    "accommodation": "三星舒适型",
    "transport": "地铁+出租车",
    "origin": null
}
```

**即时返回**：
```json
{"taskId": "abc123-def456"}
```

**轮询结果**（处理中）：
```json
{"status": "processing", "progress": 50, "message": "规划路线中..."}
```

**轮询结果**（完成）：
```json
{
    "status": "completed",
    "result": {
        "id": "...", "title": "北京 4 天文化之旅",
        "dailyPlan": [...], "budgetDetail": {...}, "budgetPieData": [...]
    }
}
```

### 6.3 数据校验（Pydantic）

```python
class TripFormData(BaseModel):
    destination: str = Field(..., min_length=1, max_length=50)
    startDate: str        # "YYYY-MM-DD"
    endDate: str
    adults: int = Field(1, ge=1, le=10)
    children: int = Field(0, ge=0, le=5)
    budget: Literal["economy", "comfort", "quality"]
    style: Literal["culture", "nature", "food", "leisure", "adventure"]
    interests: list[str]
    accommodation: str
    transport: str
    origin: str | None = None
    specialNeeds: str = ""
```

---

## 7. 数据流与状态管理

### 7.1 完整调用链路

```
1. 用户打开小程序
      ├── GET /health                    → 200
      ├── GET /api/v1/config/map-key     → {"amapKey": "..."}
      ├── GET /api/v1/destinations/hot   → 热门目的地 20 个
      └── GET /api/v1/destinations/random→ 随机推荐

2. 用户提交行程
      POST /api/v1/trips/generate → {"taskId": "xxx"}
          │
          ├── Pydantic 校验 form
          ├── 创建 TripState（7项默认映射）
          ├── asyncio.create_task(generate())
          │       └── SupervisorAgent.run()
          │               └── loop.run_in_executor(graph.invoke)
          │                       │
          │              research_node (20%)
          │              │    ├── flyai_search (search-poi)
          │              │    ├── get_weather (高德MCP)
          │              │    └── LLM 综合输出
          │              │
          │              plan_node (50%)
          │              │    └── LLM 规划每日路线
          │              │
          │              budget_node (70%)
          │              │    ├── flyai_search (search-hotels)
          │              │    └── LLM 计算费用
          │              │
          │              reflection_node (85%)
          │              │    ├── 代码检查 (10分扣分制)
          │              │    ├── 规则检查 (雨天/区域/预算)
          │              │    └── 决策: pass / 回到plan-budget / 勉强pass
          │              │
          │              format_node (95%)
          │                   └── 合成 TripResult JSON
          │
          └── 写入 _generation_cache[trip_id] = result

3. 前端轮询进度
      GET /api/v1/trips/{id}/status
          └── 查 _generation_cache 和 _progress_store
```

### 7.2 坐标反幻觉处理

LLM 可能生成不存在的坐标（幻觉），`_fix_coordinates()` 在 format 阶段修正：

```
LLM输出: {"name": "某景点", "latitude": 0, "longitude": 0}
                        │
                        ▼
              _fix_coordinates()
              ├── 提取所有景点名
              ├── ThreadPoolExecutor(max_workers=5)
              │     └── geocode(景点名 + 城市名) → 真实坐标
              └── 回填到最终 JSON
```

---

## 8. Prompt 工程

### 8.1 四个 Prompt 模板

| Prompt | 节点 | 角色 | 关键约束 |
|--------|------|------|----------|
| Research Prompt | research | 目的地旅行专家 | 景点≥N×3+2个，类别多样，参考飞猪价格 |
| Plan Prompt | plan | 路线规划师 | ⚠️必须生成N天完整行程，每天4时段 |
| BUDGET_PROMPT | budget | 费用精算师 | 四项占比=100，周末上浮，儿童半价 |
| FORMAT_PROMPT | format | JSON 格式化器 | 合并 plan + budget，填入参数 |

### 8.2 Prompt 设计原则

1. **强制 JSON 输出**：每个 prompt 都有 `只输出JSON，不要任何额外文字或markdown代码块`
2. **结构化 JSON Schema**：Prompt 中给出完整 JSON 模板，LLM 只需填值
3. **参数化模板**：BUDGET_PROMPT 和 FORMAT_PROMPT 使用 `str.format()` 填入动态参数
4. **RAG 注入**：飞猪真实数据注入 Prompt，LLM 参考而非完全依赖
5. **规则硬编码**：计算规则写死在 Prompt 中，不依赖 LLM 推理

### 8.3 JSON 容错解析

```python
def _extract_json(text: str) -> dict:
    # 1. 去掉 ```json ... ``` markdown 包裹
    text = re.sub(r'```json?\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    # 2. 截取第一个 { 到最后一个 }
    start = text.find('{')
    end = text.rfind('}') + 1
    if start >= 0 and end > start:
        text = text[start:end]
    # 3. 标准 JSON 解析
    return json.loads(text)
```

---

## 9. 性能优化

### 9.1 优化清单

| 优化项 | 方法 | 效果 |
|--------|------|------|
| MCP Session 缓存 | `_mcp_sessions` dict 按 KeyHash 复用 | HTTP 调用减少 66% |
| LLM 实例缓存 | `@lru_cache(maxsize=8)` | 5 节点不再重复创建 ChatOpenAI |
| 并行天气查询 | `ThreadPoolExecutor.submit()` | 与 LLM 并行，节省 2~5s |
| 并行地理编码 | `ThreadPoolExecutor(max_workers=5)` | N+1 串行 → N/5 批次 |
| Plan 摘要化 | `_summarize_plan()` | Token 消耗减少 60% |
| 规则化 reflection | 代码+规则 代替 LLM | 反思阶段节省 10~30s |
| run_in_executor | 代替手工 Thread | 代码从 30+ 行降到 1 行 |

### 9.2 优化前后对比

| 阶段 | 优化前 | 优化后 |
|------|--------|--------|
| 单次行程生成 | ~120s | ~60s |
| MCP 50次地理编码 | 150 次 HTTP | 50 次 HTTP |
| LLM 实例创建 | 每个节点 new 一个 | 5 节点复用 1 个 |
| 串行天气查询 | 等待 LLM 后才查 | 与 LLM 并行 |

---

## 10. 容错与降级

### 10.1 多层降级策略

| 功能 | 第1层（主） | 第2层（备） | 第3层（兜底） |
|------|-----------|-----------|------------|
| 逆地理编码 | 高德 REST API | OSM Nominatim | 返回坐标原文 |
| 天气查询 | 高德 MCP 实时 | `_seasonal_avg()` 往年平均 | 默认气温数组 |
| 飞猪搜索 | FlyAI CLI | — | 静默跳过，LLM 估价 |
| LLM | DeepSeek V4 | — | 可配 OpenAI/混元/智谱 |
| JSON 解析 | `json.loads()` | `_extract_json()` 容错 | 返回 error dict |

### 10.2 关键容错代码

```python
# 天气：当年数据缺失 → 往年同期平均
def get_weather(city: str, days: int = 3, start_date: str = "") -> dict:
    data = _amap_mcp("maps_weather", city=city)
    if not data or "未查询到" in str(data):
        return _seasonal_avg(city, 6, 8, start_date)  # 兜底
    return data
```

---

## 11. 测试体系

### 11.1 测试规模

| 类别 | 数量 | 说明 |
|------|------|------|
| 单元测试 | 98 个 | 覆盖所有模块 |
| 基准测试 | 19 个 | pytest-benchmark |
| 测试文件 | 12 个 | 粒度：每模块一个测试文件 |

### 11.2 测试覆盖

| 测试文件 | 覆盖模块 | 关键测试 |
|----------|----------|----------|
| `test_agents_graph.py` | graph.py | JSON 解析、评分逻辑、取消机制 |
| `test_agents_tools.py` | tools.py | MCP 调用、天气查询、地理编码 |
| `test_agents_supervisor.py` | supervisor.py | 异步封装、取消支持 |
| `test_config.py` | config.py | LLM 缓存、设置加载 |
| `test_main.py` | main.py | 路由注册、端点响应 |
| `test_api_auth.py` | auth.py | JWT 生成、微信登录 |
| `test_api_deps.py` | deps.py | 认证依赖 |
| `test_api_destinations.py` | destinations.py | 热门目的地、随机推荐 |
| `test_schemas_trip.py` | schemas/trip.py | Pydantic 校验 |
| `test_services_trip.py` | trip_service.py | 任务生命周期 |
| `test_benchmark_speed.py` | 性能基准 | 各节点耗时基准 |

### 11.3 Mock 策略

```python
@pytest.fixture
def mock_settings(monkeypatch):
    """统一 mock Settings 实例，所有测试隔离外部依赖"""
    from config import Settings
    mock = Settings(
        llm_provider="mock",
        llm_api_key="test-key",
        amap_key="",
        flyai_api_key="",
        wx_appid="", wx_secret="",
    )
    monkeypatch.setattr("config.settings", mock)
    return mock
```

---

## 12. 部署运维

### 12.1 Dockerfile 关键步骤

```dockerfile
FROM python:3.12-slim              # Debian 基础，glibc 兼容

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Node.js + 飞猪 CLI（subprocess 调用需要）
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*
RUN npm i -g @fly-ai/flyai-cli

COPY . .
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 12.2 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `LLM_PROVIDER` | 是 | deepseek / openai / hunyuan / zhipu |
| `LLM_API_KEY` | 是 | LLM 服务商 API Key |
| `LLM_MODEL` | 是 | 模型名 |
| `AMAP_KEY` | 推荐 | 高德地图 Key（影响天气和地理编码） |
| `FLYAI_API_KEY` | 否 | 飞猪 FlyAI（无 Key 时 LLM 用训练数据） |
| `WX_APPID` | 否 | 微信小程序 AppID（开发环境可省略） |
| `WX_SECRET` | 否 | 微信小程序 Secret |

### 12.3 CloudBase CloudRun 特点

- Serverless 容器：按请求自动扩缩容，无请求时缩到 0
- 端口 8080：CloudRun 默认健康检查端口
- 请求计费：因此选择轮询模式而非 WebSocket 长连接
- 冷启动：首次请求可能有延迟（Docker 镜像拉取）

---

## 13. 面试高频问题

### Q1: 为什么用 LangGraph 而不是 LangChain Agent？

**答**：LangChain Agent 的 ReAct 模式让 LLM 自主决策调用哪些工具，不确定性大、token 消耗高。LangGraph StateGraph 让我显式控制节点执行顺序，流程可预测，且 reflection 的条件边机制实现了可控的修正循环。

### Q2: 为什么 reflection 不用 LLM 语义评分？

**答**：三个原因。①速度：LLM 评分额外耗时 10~30s，规则检查毫秒级。②稳定性：LLM 评分每次不同，可能同一份行程两次评分差 3 分。③成本：每次 LLM 调用都消耗 token。关键是：雨天室内、区域多样性、预算占比这三条规则已经覆盖了 90% 的典型质量问题。

### Q3: MCP Session 缓存为什么能减少 66% 的 HTTP 调用？

**答**：MCP 完整调用需要三步握手——initialize（获取 session_id）、notifications/initialized（确认）、tools/call（执行工具）。如果不缓存，每次调高德都是 3 次 HTTP。Sessions 按 API Key 的 MD5 哈希缓存后，同一 Key 只需一次握手，后续都是 1 次 HTTP。50 次地理编码从 150 次 HTTP 降到 50 次，减少 66%。

### Q4: `run_in_executor` 做了什么？为什么要用它？

**答**：LangGraph 的 `graph.invoke()` 是同步方法，包含 LLM 调用会阻塞当前线程。如果直接在 async handler 中调用，会阻塞整个 event loop，其他请求无法处理。`run_in_executor` 将阻塞操作扔到线程池中执行，主线程的 event loop 继续处理其他请求。

### Q5: 飞猪 CLI 不可用时怎么办？

**答**：静默降级。`flyai_search()` 捕获 `FileNotFoundError`（CLI 未安装）和所有异常，返回 `{"note":"飞猪不可用"}` 标记。调用方（research/budget 节点）检测到标记后跳过飞猪数据注入，LLM 完全基于训练数据给出价格估算。飞猪是增强检索（RAG），不是必须依赖。

### Q6: JSON 解析失败怎么处理？

**答**：两级容错。第一级：`_extract_json()` 自动剥离 markdown 代码块、截取 `{...}` 区间。第二级：如果 format 节点解析 plan_result 或 budget_result 失败，回退到 LLM 重新合成（用 FORMAT_PROMPT）。确保最终输出一定是合法 JSON。

### Q7: 如何保证坐标的准确性？

**答**：LLM 生成的坐标可能不准确（幻觉），通过 `_fix_coordinates()` 在 format 阶段修正：提取所有 `latitude==0` 的景点，用 `geocode(景点名+城市名)` 通过高德 MCP 查真实坐标，并行回填。这是数据验证层，不依赖 LLM 自身修正。

### Q8: 为什么选择 DeepSeek 而不是 GPT-4？

**答**：①成本：DeepSeek 价格远低于 GPT-4。②中文能力：DeepSeek 对中文旅行场景理解好。③可替换：config.py 的 `Settings` 支持动态切换 provider，模型选择与业务逻辑解耦。

### Q9: 有哪些可以做但没做的优化？

**答**：①Streaming 输出：当前是批量生成后返回，可以改为 SSE 流式推送每个节点结果。②更多修正循环：当前 reflection 最多修正 1 次，可以放宽到 2-3 次。③缓存相似行程：如果两个用户查询相似目的地+天数，可以复用调研结果。④飞猪结果结构化：当前直接注入文本，可以解析为结构化数据再注入 Prompt。
文档覆盖了技术面 80% 的内容，但面试官通常会追问三类东西：

#### 1. 文档已有的（能答出来就不错） LangGraph 工作流、MCP 协议、异步架构、容错降级、优化手段

#### 2. 文档没覆盖但可能问的

* 为什么不用数据库持久化？ — 当前用内存 dict，重启丢数据；是因为 MVP 阶段快速验证，后续可接 MySQL/Redis
* 如果 1000 人同时请求怎么办？ — CloudRun 自动扩容 + 设置最大并发数 + 考虑消息队列削峰
* LLM 返回格式不对你是怎么排查的？ — 看日志里的 raw output，检查 prompt 约束是否被忽略，调整 temperature
* Token 消耗怎么控制？ — Plan 摘要化、截取飞猪数据前 1500 字、reflection 用规则不用 LLM
#### 3. 必须结合实际场景说的 面试官大概率会问"你遇到过什么坑"——最好的答案来自真实经历：

* 飞猪 CLI 的 Windows GBK 编码崩溃 → 改 text=False + UTF-8 手动解码
* DeepSeek 老在 JSON 外包 json → 加了 _extract_json() 容错 + Prompt 加"不要 markdown 代码块"
* run_in_executor 之前的 threading.Thread 代码又臭又长 → 重构到 1 行
* 建议：把文档看熟 + 准备 2-3 个"踩坑→分析→修复"的真实故事 + 对着镜子讲一遍架构图，基本就够了。