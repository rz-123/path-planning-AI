<div align="center">

# 🗺️ AI 路线规划 · 智能旅行助手

**基于 FastAPI + LangGraph + DeepSeek 的多 Agent AI 旅行规划平台**

微信小程序端 · 腾讯云 CloudBase 部署

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-4D6BFE)](https://www.deepseek.com/)
[![CloudBase](https://img.shields.io/badge/Deploy-CloudBase-0052D9)](https://cloud.tencent.com/product/tcb)

</div>

---

## 📖 项目简介

一个**从自然语言到完整旅行方案**的 AI 智能助手：用户只需填写目的地、日期、人数和偏好，系统通过 **5 个协作式 AI Agent** 自动完成景点调研、路线规划、预算测算与质量反思，最终生成一份可直接出行使用的多日行程。

> 🎯 亮点：多 Agent 编排 + 真实数据源（高德 / 飞猪）+ 自我反思修正机制

---

## ✨ 核心特性

- 🧠 **5-Agent 协作流水线**：调研 → 规划 → 预算 → 反思 → 合成，LangGraph 有向图编排
- 🔄 **自我反思修正**：反思节点采用 10 分扣分制评分，低于 5 分自动回退重规划
- 🗺️ **真实数据源**：接入高德地图 MCP（景点/天气/搜索）+ 飞猪 FlyAI（酒店/机票/门票价格）
- ⚡ **异步任务 + 进度轮询**：长耗时生成不阻塞请求，前端实时进度条
- 📱 **微信小程序端**：登录、创建、生成、结果展示全流程
- 🔌 **多模型可切换**：DeepSeek / OpenAI / 混元 / 智谱，OpenAI 兼容格式统一接入
- 🐳 **容器化部署**：Docker + CloudBase CloudRun，弹性伸缩 1~3 实例

---

## 🏗️ 系统架构

### Agent 工作流拓扑

```
                    ┌──────────────┐
                    │   research    │  调研景点/餐厅/天气（入口节点）
                    │  (LLM调用)    │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │     plan      │  规划每日路线（时间+酒店安排）
                    │  (LLM调用)    │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │    budget     │  计算费用明细（住宿+餐饮+交通+门票）
                    │  (LLM调用)    │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  reflection   │  代码检查 + 规则化语义检查（10分扣分制）
                    │   (纯代码)    │── ≥5分 通过 ──► format
                    └──────┬───────┘
                           │ < 5分 + 有严重问题 → 回到对应 Agent 修正
                           ▼            （最多修正 1 次）
                    ┌──────────────┐
                    │    format     │  合成最终 JSON + 修正坐标为真实 GPS
                    │  (代码合成)   │
                    └──────────────┘
```

### 目录结构

```
Ai 路线规划/
├── backend/                        # Python 后端（FastAPI + LangGraph）
│   ├── main.py                     # 应用入口（CORS / 路由 / 生命周期）
│   ├── config.py                   # 配置中心 + LLM 工厂（Pydantic Settings）
│   ├── api/v1/                     # RESTful API 路由
│   │   ├── auth.py                 #   微信登录 / JWT
│   │   ├── trips.py                #   行程生成 / 进度 / 取消
│   │   ├── destinations.py         #   目的地推荐
│   │   └── geo.py                  #   逆地理编码
│   ├── agents/                     # 5-Agent 工作流
│   │   ├── graph.py                #   LangGraph 状态图编排
│   │   ├── supervisor.py           #   异步调度封装
│   │   ├── tools.py                #   高德 MCP / 飞猪 FlyAI 工具
│   │   └── utils.py                #   取消 / 进度等共享函数
│   ├── services/                   # 业务逻辑层（任务管理）
│   ├── schemas/                    # Pydantic 数据模型
│   ├── Dockerfile                  # 容器化构建
│   ├── requirements.txt            # Python 依赖
│   └── .env                        # 环境变量（不入 Git）
│
├── miniprogram/                    # 微信小程序前端
│   ├── app.js                      # 入口（云开发初始化 / 登录）
│   ├── pages/
│   │   ├── index/                  #   首页
│   │   ├── create/                 #   创建行程（基本信息）
│   │   ├── preference/             #   偏好设置
│   │   ├── generate/               #   AI 生成中（进度轮询）
│   │   ├── complete/               #   生成完成摘要
│   │   ├── result/                 #   行程详情（时间线 + 预算）
│   │   └── my/                     #   我的（历史行程）
│   └── utils/                      # API / Storage / Mock 工具
│
├── cloudfunctions/                 # 云函数（备用）
└── project.config.json             # 微信小程序项目配置
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| AI 引擎 | LangGraph（5-Agent）+ LangChain + DeepSeek LLM |
| 后端框架 | FastAPI（Python 3.12）+ uvicorn |
| 数据存储 | SQLite + aiosqlite（MVP） |
| 前端 | 微信小程序（WXML / WXSS / JS） |
| 部署 | CloudBase CloudRun（容器型）+ Docker |
| 外部服务 | 高德地图 MCP · 飞猪 FlyAI |

---

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone git@github.com:rz-123/path-planning-AI.git
cd path-planning-AI
```

### 2. 配置后端

```bash
cd backend
# 复制环境变量模板并填写真实密钥
cp .env.example .env
```

编辑 `.env`，填入你的 API Key（DeepSeek、高德、飞猪、微信小程序）。

### 3. 安装依赖并启动

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

访问 `http://localhost:8080/docs` 查看 Swagger 接口文档。

### 4. 运行小程序前端

1. 用微信开发者工具打开 `miniprogram/` 目录
2. 配置 `project.config.json` 中的 `appid`
3. 后端地址默认走云端，本地调试可将 `app.js` 中 `apiBaseUrl` 改为 `http://localhost:8080`

---

## 🔌 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/api/v1/config/map-key` | 获取高德地图 Key |
| `POST` | `/api/v1/auth/login` | 微信登录（code → JWT） |
| `POST` | `/api/v1/trips/generate` | 提交行程生成任务 |
| `GET` | `/api/v1/trips/{id}/status` | 查询生成进度 |
| `GET` | `/api/v1/trips/{id}` | 获取行程结果 |
| `DELETE` | `/api/v1/trips/{id}/cancel` | 取消生成 |
| `GET` | `/api/v1/destinations` | 目的地推荐 |
| `GET` | `/api/v1/geo/reverse` | 逆地理编码 |

---

## 🔧 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `LLM_PROVIDER` | LLM 提供商标识（deepseek / openai / hunyuan / zhipu） | ✅ |
| `LLM_MODEL` | 模型名称 | ✅ |
| `LLM_API_KEY` | LLM API 密钥 | ✅ |
| `LLM_BASE_URL` | LLM API 基础地址 | ✅ |
| `AMAP_KEY` | 高德地图 WebService Key | 推荐 |
| `FLYAI_API_KEY` | 飞猪 FlyAI Key | 可选 |
| `WX_APPID` | 微信小程序 AppID | ✅ |
| `WX_SECRET` | 微信小程序 AppSecret | ✅ |

> 完整模板见 [`backend/.env.example`](backend/.env.example)

---

## 📚 项目文档

- [智能旅行助手开发计划](智能旅行助手开发计划.md) — 需求与 Agent 架构设计
- [后端 API 规范](backend-api-spec.md) — 接口详细定义
- [面试文档](backend/面试文档-AI旅行规划系统.md) — 架构设计与面试考点

---

## 📄 License

[MIT](LICENSE)

---

<div align="center">

**让每一次出发，都始于一次智能规划** ✈️

</div>
