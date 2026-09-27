"""
Agent 模块 — LangChain + LangGraph 多 Agent 工作流

该模块是 AI 旅行规划系统的「大脑」，负责协调多个 AI Agent 协作完成行程生成。

架构层次：
  ┌─────────────────────────────────────────────────┐
  │  agents/__init__.py   模块入口、架构总览          │
  ├─────────────────────────────────────────────────┤
  │  agents/graph.py      LangGraph StateGraph      │
  │                       (5 节点编排引擎)            │
  ├─────────────────────────────────────────────────┤
  │  agents/supervisor.py SupervisorAgent           │
  │                       (异步调度封装 + 状态构建)    │
  ├─────────────────────────────────────────────────┤
  │  agents/tools.py      工具层                    │
  │                       (高德MCP / 飞猪 / 搜索)    │
  ├─────────────────────────────────────────────────┤
  │  agents/utils.py      共享工具函数               │
  │                       (取消检查 / 进度更新)       │
  └─────────────────────────────────────────────────┘

工作流拓扑（有向图）：
  Research ──→ Plan ──→ Budget ──→ Reflection ──→ Format ──→ END
    (调研)      (规划)    (预算)      (反思评分)     (合成JSON)
                                         │
                                         ├── ≥5分 → Format (通过)
                                         └── <5分 → 回到对应Agent修正 (最多1次)

LLM 配置说明：
  配置文件在 config.py 的 get_llm() 中，支持 ChatGPT-OpenAI 兼容格式的 LLM：
  - DeepSeek (推荐：性价比最高，中文理解优秀)
  - OpenAI GPT (备选：国际通用)
  - 腾讯混元 / 智谱 GLM (国内合规首选)

其他模块说明：
  - graph.py: LangGraph StateGraph（5 节点: research→plan→budget→reflection→format）
  - supervisor.py: 异步调度封装（run_in_executor + 线程池，避免阻塞事件循环）
  - tools.py: LangChain Tools（高德地图 MCP / 飞猪 FlyAI）
  - utils.py: 共享工具函数（CancelledError / update_progress / check_cancelled）
"""
