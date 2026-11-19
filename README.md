# AI 旅行规划系统

> 基于 **FastAPI + LangGraph + DeepSeek** 的多 Agent AI 旅行规划平台，微信小程序端，部署于腾讯云 CloudBase。

[![Powered by CloudBase](https://7463-tcb-advanced-a656fc-1257967285.tcb.qcloud.la/mcp/powered-by-cloudbase-badge.svg)](https://github.com/TencentCloudBase/CloudBase-AI-ToolKit)

## 项目架构

```
前端/
├── backend/                    # Python 后端 (FastAPI + LangGraph)
│   ├── main.py                 # 应用入口
│   ├── config.py               # 配置 + LLM 工厂
│   ├── api/v1/                 # RESTful API 路由
│   ├── agents/                 # 5-Agent LangGraph 工作流
│   ├── services/               # 业务逻辑层
│   ├── schemas/                # Pydantic 数据模型
│   ├── Dockerfile              # 容器化部署
│   └── .env                    # 环境变量 (不入 Git)
│
├── miniprogram/                # 微信小程序前端
│   ├── app.js                  # 入口 (云开发初始化/登录/安全区)
│   ├── pages/
│   │   ├── index/              # 首页 (热门目的地 + 最近行程)
│   │   ├── create/             # 创建行程 (2步表单)
│   │   ├── generate/           # AI 生成中 (进度轮询)
│   │   ├── complete/           # 生成完成摘要
│   │   ├── result/             # 行程详情 (时间线 + 预算饼图)
│   │   └── my/                 # 我的 (历史行程 + 统计)
│   └── utils/                  # 工具函数 (API/Storage/Mock)
│
├── project.config.json         # 微信小程序项目配置
└── cloudfunctions/             # 云函数 (备用)
```

## 技术栈

| 层级 | 技术 |
|------|------|
| AI 引擎 | LangGraph (5-Agent 工作流) + LangChain + DeepSeek LLM |
| 后端框架 | FastAPI (Python 3.12) |
| 前端 | 微信小程序 (WXML/WXSS/JS) |
| 部署 | CloudBase CloudRun (容器型) + Docker |
| 数据库 | CloudBase 云数据库 (NoSQL) |
| 外部服务 | 高德 MCP、飞猪 FlyAI、博查搜索 |

## 部署信息

### 后端 (CloudBase CloudRun)

| 配置项 | 值 |
|--------|-----|
| 服务名称 | `ai-travel-backend` |
| 访问地址 | `https://ai-travel-backend-262776-10-1427844883.sh.run.tcloudbase.com` |
| 环境 ID | `cloud1-d2gzje1i7ba287acb` |
| 规格 | CPU 0.5核 / 内存 1GB |
| 实例 | **必须固定为 1**（任务状态存进程内存，多实例会导致轮询打到其他实例返回 `not_found`） |
| 端口 | 8080 |
| 最新版本 | `ai-travel-backend-006` |

**API 端点**：
- `GET /health` — 健康检查
- `POST /api/v1/trips/generate` — 提交行程生成
- `GET /api/v1/trips/{id}/status` — 查询生成进度
- `DELETE /api/v1/trips/{id}/cancel` — 取消生成
- `POST /api/v1/auth/login` — 微信登录
- `GET /api/v1/config/map-key` — 获取地图 Key

### 前端 (微信小程序)

- AppID: `wx0b239ce65bab54dc`
- 在微信开发者工具中打开 `miniprogram/` 目录即可运行
- 小程序通过 `wx.cloud.callContainer` 内网调用后端，无需域名配置

### CloudBase 资源

| 资源 | 用途 |
|------|------|
| CloudRun (ai-travel-backend) | 后端 API + AI Agent |
| 云数据库 (trips 集合) | 行程数据存储 |
| 云托管内网调用 | 小程序→后端通信 |

## 重新部署

```bash
# 后端：通过 CloudBase AI ToolKit 或 CLI 部署
tcb cloudrun deploy --service ai-travel-backend --path ./backend
```

## 部署前必读

- 生产环境必须设置 `JWT_SECRET`（随机 32 字节以上）。不设置时会使用代码里的默认值，存在被伪造 Token 的风险。
- `LLM_API_KEY`、`WX_SECRET`、`AMAP_KEY` 只放在 `.env` 或云托管环境变量里，不要提交到仓库；配置模板见 [backend/.env.example](backend/.env.example)。
- CloudRun 实例数固定为 1（原因见上表）。要扩实例必须先做任务状态持久化。
- `GET /api/v1/config/map-key`、行程进度/取消接口都需要登录 Token。
