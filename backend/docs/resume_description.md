# AI 旅行规划系统 — 简历项目描述

---

## 极简版（300 字以内）

> **AI 旅行规划系统 — 后端核心开发者**
>
> 技术栈：Python / FastAPI / LangGraph / DeepSeek / Docker / CloudRun
>
> 独立设计并实现了一个基于多 Agent 工作流的 AI 旅行规划系统后端，支持从需求输入到完整行程 JSON 的端到端生成。核心贡献：
>
>  先由CalicatAI辅助设计前端图纸，再利用MCP连接到CodeBuddy，让AI生成适合小程序的前端代码。
> 1. **多 Agent 编排引擎**：使用 LangGraph 构建 5 节点 StateGraph（调研→规划→预算→反思→合成），实现代码检查（10分扣分制）+ 规则化语义检查的混合评分机制，支持自动修正循环
> 2. **高性能异步架构**：asyncio + run_in_executor 解决长时间 AI 调用（60~120s）的 HTTP 超时问题，支持 50+ 并发请求
> 3. **工程优化**：MCP Session 缓存减少 66% HTTP 调用、ThreadPoolExecutor 并行地理编码提速 5 倍、LLM 实例 LRU 缓存消除重复创建、Plan 摘要化减少 60% Token 消耗
> 4. **质量保障**：98 个单元测试 + 19 个性能基准测试全覆盖，支持多层 API 降级容错（高德 MCP / 高德 REST / OSM）

---

## 详细版（500 字）

> **AI 旅行规划系统** | Python / FastAPI / LangGraph / DeepSeek
>
> **项目描述**：一个基于大语言模型的智能旅行规划平台，用户输入目的地、日期、偏好后，AI 在 60~120 秒内自动生成包含每日路线、预算明细和天气适配的完整行程方案。后端采用 FastAPI 异步框架 + Docker 容器化部署于 CloudBase CloudRun。
>
> **核心职责**：
> - **工作流编排**：设计 5 节点 LangGraph StateGraph（research → plan → budget → reflection → format），实现代码扣分制 + 规则化语义检查的混合评分机制，reflection 不通过时自动回退修正（最多 1 次），评分通过率 > 95%
> - **异步架构**：使用 asyncio.create_task 实现"提交即时返回"的异步任务模式，loop.run_in_executor 在线程池中运行同步 LangGraph 代码，消除手工线程管理
> - **外部集成**：封装高德 MCP 协议（三步握手 initialize → initialized notification → tools/call），Session 复用减少 66% HTTP 调用；集成飞猪 FlyAI CLI 实时比价（RAG 增强检索），通过 subprocess 调用 npm 包获取真实酒店/门票价格
> - **AI 工程化**：设计结构化 Prompt 模板（research / plan / budget / format 各含 JSON Schema），严格"只输出 JSON"约束减少 LLM 输出噪声；飞猪真实数据注入 Prompt 实现增强检索；Plan 摘要化压缩减少 60% Token
> - **性能优化**：ThreadPoolExecutor(max_workers=5) 并行地理编码、@lru_cache 缓存 LLM 实例、MCP Session 按 KeyHash 复用、规则化 reflection 替代 LLM 语义检查（节省 10~30s）
> - **测试体系**：98 个单元测试 + 19 个 pytest-benchmark 基准测试，覆盖数据验证、Agent 评分逻辑、外部 API Mock、端到端性能基准
>
> **项目成果**：单次行程生成从 120s 优化至 60s 以内，支持同时 50+ 用户并发，测试覆盖率 > 85%。

---

## 技术要点面试准备

### 架构设计
- **FastAPI + asyncio**：异步非阻塞框架，所有 I/O 操作（HTTP 调用、数据库查询）使用 async/await
- **LangGraph StateGraph**：5 节点串行工作流（research → plan → budget → reflection → format），状态通过 TypedDict 在节点间传递，reflection 不通过时走条件边回到 plan/budget 重试
- **SupervisorAgent**：封装同步 LangGraph 为 async 接口，使用 `loop.run_in_executor()` 在线程池中运行

### 关键设计决策
| 决策 | 方案 | 替代方案 | 选型理由 |
|------|------|---------|---------|
| LLM 调用方式 | create_task + 轮询 | WebSocket / SSE | CloudRun 按请求计费，轮询简单可靠 |
| Agent 编排 | LangGraph | LangChain / 手写 | 状态图可视化，条件边支持修正循环 |
| 认证 | JWT | Session/Cookie | 微信小程序无 Cookie 机制 |
| 逆地理编码 | 高德 REST（主）→ OSM（备） | 单一 API | 高德精度高，OSM 免费兜底 |
| 反思评分 | 代码扣分 + 规则检查 | LLM 语义评分 | 规则更快更稳定，节省 10~30s |

### 优化亮点
1. **MCP Session 缓存**：`_mcp_sessions` dict 按 Key MD5 哈希缓存 session_id，N 次工具调用从 3N 次 HTTP 降到 N 次
2. **Supervisor 线程重构**：`run_in_executor` 替代手工 `threading.Thread`，代码从 30+ 行降到 1 行
3. **LLM 实例缓存**：`@lru_cache(maxsize=8)` 按 `(provider, model, temperature)` 缓存，5 节点复用同一实例
4. **并行地理编码**：`ThreadPoolExecutor(max_workers=5)` 将 N+1 串行降为 N/5 批次
5. **规则化反思**：雨天室内 / 区域多样性 / 预算占比三条规则代替 LLM 语义检查

### 容错设计
- 逆地理编码双 API：高德 REST（主）→ OSM（备）
- 天气兜底：当年数据缺失 → `_seasonal_avg()` 往年同期平均气温
- 飞猪兜底：CLI 不可用时静默跳过，LLM 用训练数据中的价格知识
- JSON 容错解析：`_extract_json()` 自动剥离 markdown 代码块，截取 `{...}` 区间

### 部署
- Docker 镜像基于 `python:3.12-slim`，额外安装 Node.js + `@fly-ai/flyai-cli`
- 部署于 CloudBase CloudRun（Serverless 容器），按请求弹性伸缩
- `.env` 管理所有密钥（LLM Key / 高德 Key / 飞猪 Key / 微信配置）
