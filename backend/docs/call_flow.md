# AI 旅行规划系统 — 完整调用流程

> 文档版本：v1.0 | 更新日期：2026-07-04
> 涵盖：前端小程序 → 后端 API → 服务层 → Agent 编排层 → 工具层 → 外部服务

---

## 一、系统架构总览

### 1.1 分层架构

```
┌──────────────────────────────────────────────────────────────┐
│                    前端小程序 (miniprogram/)                   │
│  pages/index  pages/create  pages/generate  pages/result     │
│  pages/complete  pages/my                                    │
│  utils/api.js  utils/mock.js  utils/cities.js                │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTPS / wx.cloud.callContainer
                       ▼
┌──────────────────────────────────────────────────────────────┐
│             路由层  backend/api/v1/                           │
│  auth.py  trips.py  destinations.py  geo.py                  │
│  deps.py (JWT 认证中间件)                                    │
└──────────────────────┬───────────────────────────────────────┘
                       │ 函数调用
                       ▼
┌──────────────────────────────────────────────────────────────┐
│             服务层  backend/services/                         │
│  trip_service.py (异步任务编排 / 进度管理 / 取消)             │
└──────────────────────┬───────────────────────────────────────┘
                       │ await SupervisorAgent.run()
                       ▼
┌──────────────────────────────────────────────────────────────┐
│           Agent 编排层  backend/agents/                      │
│  supervisor.py (状态构建 + run_in_executor)                  │
│  graph.py (LangGraph 5节点工作流 + 修正循环)                 │
│  utils.py (进度更新 / 取消检查 / CancelledError)             │
└──────────────────────┬───────────────────────────────────────┘
                       │ 工具函数调用
                       ▼
┌──────────────────────────────────────────────────────────────┐
│             工具层  backend/agents/tools.py                   │
│  _amap_mcp()  get_weather()  geocode()  flyai_search()      │
│  _seasonal_avg()                                             │
└──────────────┬──────────────────────┬────────────────────────┘
               │                      │
               ▼                      ▼
        ┌──────────────┐      ┌──────────────┐
        │  高德 MCP    │      │  飞猪 FlyAI  │
        │ (天气/地理)   │      │  (景点/酒店)  │
        └──────────────┘      └──────────────┘
               │
	               ▼
	        ┌───────────────────────┐
	        │  飞猪 FlyAI CLI        │
	        │  (景点/酒店真实价格)    │
        └──────────────┘
```

### 1.2 数据流方向

```
用户操作 → 页面 → API 客户端 → 云托管/云函数 → FastAPI 路由
  → 服务层 → Agent → LangGraph → LLM + 工具 → 结果返回到页面
```

### 1.3 核心设计模式

| 模式 | 使用位置 | 说明 |
|------|---------|------|
| 异步任务 + 轮询 | 行程生成 | POST 提交立即返回 tripId，前端每 3 秒 GET 状态 |
| 依赖注入 | JWT 认证 | Depends(get_current_user) 自动注入 user_id |
| 双 API 回退 | 逆地理编码 | 高德→OSM |
| 工厂 + 缓存 | LLM 实例 | lru_cache 按参数缓存 ChatOpenAI 实例 |
| 观察者 | 进度跟踪 | 图中节点 update_progress → 前端轮询读取 |
| 协作式取消 | 生成取消 | cancelled_trips 集合 + 节点入口检查 |

---

## 二、应用启动流程

### 2.1 流程图

```
小程序冷启动
    │
    ▼
app.onLaunch()
    │
    ├── 1. wx.cloud.init()       初始化云开发环境
    │
    ├── 2. wx.getSystemInfoSync() 获取设备信息
    │   └── statusBarHeight, navBarHeight, screenHeight, screenWidth...
    │
    ├── 3. wxLogin()             微信登录（异步）
    │   │
    │   ├── wx.login() → 临时 code
    │   │   ↓
    │   ├── POST /api/v1/auth/login { code }
    │   │   ↓
    │   ├── 后端：code + appid + secret → 微信 jscode2session → openid
    │   │   ↓
    │   ├── 后端：生成 JWT Token（user_id + openid + 7天过期）
    │   │   ↓
    │   ├── 前端：token / openid / user_id → globalData + wx.setStorageSync
    │   │   ↓
    │   └── 前端：users 集合 → 写入/更新用户记录
    │
    └── 4. fetchMapKey()         获取地图 Key（异步）
        │
        └── GET /api/v1/config/map-key
            ↓
            前端：amapKey → globalData
```

### 2.2 关键代码路径

**前端** (miniprogram/app.js):
- `onLaunch` → `wxLogin()` (第 84 行) → `fetchMapKey()` (第 172 行)
- 缓存检查：优先读取 `wx.getStorageSync('user_token')`，已缓存则跳过登录

**后端** (api/v1/auth.py):
- `POST /api/v1/auth/login` → `wx_login()` (第 100 行)
- `create_jwt_token()` (第 65 行)：HS256 签名，7 天过期
- 开发模式：微信配置不存在时返回 `dev_user_{code[:6]}` 模拟 openid
- 生产模式：`httpx.AsyncClient` 调微信 `jscode2session` 接口

### 2.3 数据转换

```
前端输入: { code: "微信临时凭证" }
  → httpx 调用微信: { appid, secret, js_code, grant_type }
    → 微信返回: { openid, session_key }
      → JWT payload: { user_id: uuid4, openid, exp: now+7d, iat: now }
        → 前端存储: { token, user_id, openid }
```

### 2.4 涉及文件

| 文件 | 关键函数/代码 |
|------|-------------|
| `miniprogram/app.js:84` | `wxLogin()` |
| `miniprogram/app.js:172` | `fetchMapKey()` |
| `miniprogram/utils/api.js` | `apiCall()`, `callCloudRun()`, `devRequest()` |
| `backend/api/v1/auth.py:98` | `wx_login()` |
| `backend/api/v1/auth.py:65` | `create_jwt_token()` |
| `backend/api/deps.py:10` | `get_current_user()` |

---

## 三、首页加载流程

### 3.1 流程图

```
首页 pages/index/index
    │
    ├── onLoad()
    │   ├── 读取 mockHotDestinations (静态数据，20个热门城市)
    │   └── 读取 globalData 获取尺寸参数
    │
    └── onShow() (每次页面显示)
        │
        └── CloudBase 数据库: trips 集合
            └── .orderBy('createdAt', 'desc').limit(3).get()
                ↓
                成功: 映射为卡片格式 (month/day/title/fullData)
                失败: recentTrips = []
```

### 3.2 数据来源

| 数据 | 来源 | 更新频率 |
|------|------|---------|
| 热门目的地 | `utils/mock.js` 硬编码 4 个 | 手动更新 |
| 最近行程 | CloudBase `trips` 集合 | 每次 onShow |
| 用户信息 | globalData (登录时设置) | 每次启动 |

### 3.3 涉及文件

| 文件 | 关键代码 |
|------|---------|
| `miniprogram/pages/index/index.js:35` | 页面 data 和生命周期 |
| `miniprogram/utils/mock.js` | mockHotDestinations |
| `miniprogram/components/trip-card/index.js` | 行程卡片组件 |

---

## 四、行程生成核心流程

这是系统最核心的流程，涵盖从前端表单提交到 AI 生成完整行程的完整链路。

### 4.1 总览流程图

```
用户填写表单
    │
    ▼
create/index.js (2步表单：基本信息 + 偏好设置)
    │ wx.setStorageSync('tripFormData', ...)
    ▼
generate/index.js (生成进度页)
    │
    ├── POST /api/v1/trips/generate ──────────────────────────┐
    │   ← { tripId, status: "processing" }                    │
    │                                                          │
    ├── 开始轮询: GET /api/v1/trips/{tripId}/status (每3秒) ──┤
    │   ← { status, progress, currentStep, result? }          │
    │                                                          │
    │   [后台异步执行]                                          │
    │   trip_service._run_generation()                         │
    │   └── SupervisorAgent.run()                              │
    │       └── run_in_executor(trip_graph.invoke)             │
    │           ├── research_node   (20%)                      │
    │           ├── plan_node       (50%)                      │
    │           ├── budget_node     (70%)                      │
    │           ├── reflection_node (85%)                      │
    │           │   └── 条件路由: 通过→format / 不通过→修正   │
    │           └── format_node     (95%)                      │
    │               └── final_json → _generation_tasks[]       │
    │                                                          │
    │   status === "completed" ←───────────────────────────────┘
    │   result → wx.setStorageSync('tripResult', result)
    │   wx.navigateTo('/pages/complete/index')
    ▼
complete/index.js (生成完成摘要)
    │
    ├── "查看完整行程" → result/index.js
    └── "不满意，重新生成" → generate/index.js
```

### 4.2 第1阶段：表单提交 (前端)

**位置**: `miniprogram/pages/create/index.js`

**2 步表单流程**:
```
第1步: 基本信息
  ├── 出发地/目的地 (城市选择器弹窗, utils/cities.js)
  ├── 日期 (picker 组件, formatDateISO)
  ├── 成人数/儿童数 (步进器)
  └── "下一步" → 第2步

第2步: 偏好设置
  ├── 旅行风格 (4选1: 轻松休闲/深度打卡/文艺小资/特种兵式)
  ├── 兴趣偏好 (8选多: 美食/博物馆/自然/亲子/购物/红色/夜生活/拍照)
  ├── 预算范围 (3选1: 经济/舒适/品质)
  ├── 住宿偏好 (3选1: 经济/舒适/高档)
  └── "生成行程" → wx.setStorageSync → wx.navigateTo(generate)
```

**关键代码**: `onGenerate()` (第 100 行附近):
```javascript
// 合并表单数据
var formData = {
  origin: this.data.origin,
  destination: this.data.destination,
  startDate: this.data.startDate,
  endDate: this.data.endDate,
  adults: this.data.adults,
  children: this.data.children,
  style: this.data.style,
  interests: this.data.interests,
  budget: this.data.budget,
  accommodation: this.data.accommodation,
  specialNeeds: this.data.specialNeeds,
};
wx.setStorageSync('tripFormData', formData);
wx.navigateTo('/pages/generate/index');
```

### 4.3 第2阶段：提交生成 (前端 → 后端路由)

**位置**: `miniprogram/pages/generate/index.js` → `utils/api.js`

```javascript
// generate/index.js onLoad → _callBackend()
_callBackend: function () {
  var formData = wx.getStorageSync('tripFormData');
  api.generateTrip(formData).then(res => {
    this._tripId = res.tripId;
    this._pollStatus();        // 开始轮询
  });
}
```

**API 客户端** (utils/api.js) 自动选择传输方式:
- 生产: `wx.cloud.callContainer` (云托管内网)
- 开发: `wx.request` (localhost:8080)

### 4.4 第3阶段：路由层处理 (后端)

**位置**: `backend/api/v1/trips.py`

```
HTTP POST /api/v1/trips/generate
  Headers: Authorization: Bearer <JWT>
  Body: TripFormData JSON
    │
    ▼
FastAPI 自动解析:
  ├── TripFormData (Pydantic 验证)
  │   ├── destination (必填)
  │   ├── startDate / endDate (含 end_not_before_start 验证器)
  │   ├── adults=2, children=0
  │   ├── style, interests, budget, accommodation (枚举默认值)
  │   └── origin?, specialNeeds?
  │
  ├── Depends(get_current_user) → JWT 解码 → user_id
  │
  ▼
trip_service.generate_trip(form, user_id)
  │
  ▼
返回 GenerateResponse(tripId, status="processing", message)
```

### 4.5 第4阶段：服务层 (后端)

**位置**: `backend/services/trip_service.py`

```python
async def generate_trip(form: TripFormData, user_id: str) -> GenerateResponse:
    # 1. 生成唯一 tripId
    trip_id = "trip_" + uuid.uuid4().hex[:12]

    # 2. 创建内存中的任务状态记录
    _generation_tasks[trip_id] = {
        "status": "processing",
        "progress": 0,
        "currentStep": "启动 LangGraph...",
        "result": None,
    }

    # 3. 实例化 SupervisorAgent
    supervisor = SupervisorAgent()

    # 4. 创建后台异步任务（不 await，立即返回）
    task = asyncio.create_task(
        _run_generation(trip_id, form, user_id, supervisor)
    )
    # 防止 GC 回收后台任务
    main._background_tasks.add(task)
    task.add_done_callback(main._background_tasks.discard)

    # 5. 立即返回，不等待 LLM
    return GenerateResponse(tripId=trip_id, status="processing", ...)
```

**后台任务 `_run_generation`**:
```python
async def _run_generation(trip_id, form, user_id, supervisor):
    try:
        # 更新进度为 10%
        update_progress(trip_id, 10, "分析你的偏好和需求...")

        # 在线程池中运行同步 LangGraph（核心调用）
        result = await supervisor.run(form, trip_id)

        # 检查是否被取消
        if trip_id in _cancelled_trips:
            _generation_tasks[trip_id]["status"] = "cancelled"
            return

        # 注入用户和状态信息
        result["userId"] = user_id
        result["id"] = trip_id
        result["status"] = "completed"

        # 更新为完成状态
        _generation_tasks[trip_id] = {
            "status": "completed",
            "progress": 100,
            "currentStep": "生成完成",
            "result": result,
        }
    except Exception as e:
        _generation_tasks[trip_id]["status"] = "failed"
        _generation_tasks[trip_id]["currentStep"] = str(e)[:200]
```

### 4.6 第5阶段：SupervisorAgent 编排

**位置**: `backend/agents/supervisor.py`

```python
class SupervisorAgent:
    async def run(self, form_data: TripFormData, trip_id: str) -> dict:
        # 1. 构建初始 TripState（TypedDict）
        state = {
            "destination": form_data.destination,
            "origin": form_data.origin or "",
            "start_date": str(form_data.startDate),
            "end_date": str(form_data.endDate),
            "days": (form_data.endDate - form_data.startDate).days,
            "nights": (form_data.endDate - form_data.startDate).days,
            "people": form_data.adults + (form_data.children or 0),
            "adults": form_data.adults,
            "children": form_data.children or 0,
            "transport": "train",
            "style": form_data.style.value,
            "style_label": STYLE_LABEL[form_data.style.value],
            "interests": form_data.interests,
            "budget": form_data.budget.value,
            "budget_range": BUDGET_RANGE[form_data.budget.value],
            "accommodation": form_data.accommodation.value,
            "special_needs": form_data.special_needs or "",
            "trip_id": trip_id,

            # 处理字段（节点间传递的中间结果）
            "research_result": "",
            "plan_result": "",
            "budget_result": "",
            "reflection": "",
            "weather_data": "{}",
            "final_json": "",

            # 控制字段
            "revision_count": 0,
            "next_action": "",
        }

        # 2. 在线程池中运行同步 LangGraph
        try:
            loop = asyncio.get_running_loop()
            result_state = await loop.run_in_executor(
                None, trip_graph.invoke, state
            )
            return json.loads(result_state["final_json"])
        except CancelledError:
            return {}  # 取消时返回空字典
```

### 4.7 第6阶段：LangGraph 5 节点工作流

**位置**: `backend/agents/graph.py`

这是整个系统的 AI 核心，5 个节点串行执行，含最多 1 次修正循环。

#### 节点 1: research_node (调研)

```
输入: TripState { destination, style_label, interests, days, ... }

处理流程:
  1. check_cancelled(trip_id)        ← 取消检查点
  2. update_progress(20, "检索景点信息...")
  3. flyai_search("北京必去景点")    ← 飞猪真实数据
  4. flyai_search("北京热门景点门票")
  5. 构建 research_prompt（含飞猪数据）
  6. ThreadPoolExecutor(3) 并行:
     ├── Thread 1: llm.invoke(prompt)     ← LLM 生成景点/餐厅/酒店
     └── Thread 2: get_weather("北京", 3) ← 高德天气 (同时执行)
  7. _extract_json(llm_output)           ← JSON 解析
  8. state["research_result"] = json_str
  9. state["weather_data"] = json_str

输出: TripState { research_result, weather_data }
```

**关键数据结构** (research_result JSON):
```json
{
  "attractions": [
    {"name":"故宫","address":"...","ticketPrice":60,
     "estimatedDuration":"3-4小时","bestTimeSlot":"上午",
     "area":"东城区","category":"古迹","tags":"...","description":"...","closedDays":"周一"},
    ...
  ],
  "restaurants": [...],
  "hotels": [...]
}
```

**涉及文件**: `agents/tools.py:290` `geocode()`, `agents/tools.py:195` `get_weather()`
**数据来源**: 飞猪 FlyAI 真实数据 + LLM 训练数据 + 高德 MCP 实时天气

#### 节点 2: plan_node (规划)

```
输入: TripState { research_result, weather_data, days, style_label, ... }

处理流程:
  1. check_cancelled(trip_id)
  2. update_progress(50, "规划每日路线和时间...")
  3. 从 research_result 提取:
     ├── 前10个景点名, 前6个餐厅名, 前3个酒店名
     └── 天气摘要(前150字符)
  4. 构建 plan_prompt（含强制约束）
  5. llm.invoke(prompt)

约束:
  - 每天4个时段: 上午/中午/下午/晚上
  - 同区域景点安排在同一天
  - 上午=1核心景点, 中午=餐厅, 下午=1-2景点, 晚上=近酒店
  - 颜色: ☀️ #F59E0B / 🍜 #F97316 / 🏛️ #3B82F6 / 🌃 #8B5CF6

输出: TripState { plan_result }
```

**关键数据** (plan_result JSON):
```json
{
  "dailyPlan": [
    {
      "day": 1, "date": "2025-06-01", "summary": "第一天",
      "periods": [
        {"timeSlot": "上午", "icon": "☀️", "color": "#F59E0B",
         "items": [{"name": "故宫", "time": "09:00-12:00",
                    "type": "scenic", "address": "...", "area": "东城区", ...}]},
        {"timeSlot": "中午", "icon": "🍜", ...},
        {"timeSlot": "下午", "icon": "🏛️", ...},
        {"timeSlot": "晚上", "icon": "🌃", ...}
      ],
      "hotel": {"name": "...", "address": "..."}
    },
    ...
  ]
}
```

#### 节点 3: budget_node (预算)

```
输入: TripState { plan_result, budget, budget_range, accommodation, ... }

处理流程:
  1. check_cancelled(trip_id)
  2. update_progress(70, "计算预算和费用明细...")
  3. flyai_search("北京舒适型酒店")     ← 飞猪真实酒店价格
  4. _summarize_plan(plan_result)       ← 压缩 plan(减少60% token)
  5. llm.invoke([SystemMessage(prompt)]) ← SystemMessage 约束更强

输出: TripState { budget_result }
```

**关键数据** (budget_result JSON):
```json
{
  "totalBudget": 6500,
  "budgetPerPerson": 3250,
  "budgetDetail": {
    "accommodation": {"total": 2400, "icon": "🏨", "items": [...]},
    "food": {"total": 1800, "icon": "🍜", "items": [...]},
    "transport": {"total": 1300, "icon": "🚌", "items": [...]},
    "tickets": {"total": 1000, "icon": "🎫", "items": [...]}
  },
  "budgetPieData": [
    {"name": "住宿", "value": 2400, "percent": 37, "color": "#3B82F6"},
    {"name": "餐饮", "value": 1800, "percent": 28, "color": "#22C55E"},
    {"name": "交通", "value": 1300, "percent": 20, "color": "#F59E0B"},
    {"name": "门票", "value": 1000, "percent": 15, "color": "#EF4444"}
  ]
}
```

#### 节点 4: reflection_node (反思 — 质量门禁)

```
输入: TripState { research_result, plan_result, budget_result, revision_count }

处理流程:
  1. check_cancelled(trip_id)
  2. update_progress(85, "优化行程，确保体验最佳...")
  3. 代码客观评分 (满分10，扣分制):

     扣分规则:
     ├── research_result 为空           → -5 (严重, target="research")
     ├── 无 dailyPlan                  → -5 (严重, target="plan")
     ├── 每天完全空白                   → -2/天
     ├── 每天时段不足 (<2个)           → -1/天
     ├── 景点过少 (< days*2)           → -2
     ├── 住宿费用未计算                → -1
     ├── 预算占比 ≠ 100%              → -1
     ├── 完全未计算预算                → -3
     └── score = max(score, 0)

  4. 规则检查 (替代了旧版 LLM 语义检查，节省 10~30秒):
     ├── 雨天室内: 遍历 forecast 找"雨", 检查当天是否有 indoor 类别
     ├── 区域分散: 检测跨区域行程标记
     └── 预算占比: 验证 pieData percent 总和为 100

  5. 决策:
     ├── score >= 5 → next_action = "format"             ← 通过
     ├── score < 5 + 有严重问题 + revision_count < 1
     │   → next_action = target, revision_count += 1    ← 修正
     └── 其他 → next_action = "format"

输出: TripState { reflection, next_action, revision_count }
```

**条件路由函数** `should_revise()`:
```python
def should_revise(state: TripState) -> Literal["research", "plan", "budget", "format"]:
    return state["next_action"] or "format"
```

#### 节点 5: format_node (合成)

```
输入: TripState { research_result, plan_result, budget_result, weather_data, trip_id }

处理流程:
  1. check_cancelled(trip_id)
  2. update_progress(95, "整理行程数据...")

  3. 两条合成路径:
     ├── 路径A (LLM合成): plan/budget 解析含 error
     │   → get_llm_structured() + FORMAT_PROMPT
     │
     └── 路径B (代码组装) ← 默认路径，更快
         ├── 解析 plan_result, budget_result JSON
         ├── 组装 TripResult 字典(标题/日期/预算/每日计划...)
         └── weather, mapImage=None, createdAt 等元数据

  4. _fix_coordinates(final, city)     ← 对抗幻觉!
     ├── 遍历所有行程项的 name
     ├── 跳过非实体名称(酒店午休/返程晚餐等)
     ├── ThreadPoolExecutor(5) 并行 geocode(f"{city}{name}")
     └── 用真实坐标覆盖 LLM 编造的坐标

  5. state["final_json"] = json.dumps(final)

输出: TripState { final_json: 完整 TripResult JSON }
```

### 4.8 第7阶段：结果返回与访问

**数据返回路径**:
```
graph.invoke(state) 返回 state dict
  → supervisor.run() → json.loads(state["final_json"])
    → _run_generation() 写入 _generation_tasks[trip_id]["result"]
      → 前端轮询 GET /api/v1/trips/{trip_id}/status 读取
        → status="completed" → complete/index.js
```

**前端渲染路径**:
```
complete/index.js → 从 storage 读取 tripResult
  → "查看完整行程" → result/index.js
    → 从 storage 读取 tripResult
      → 渲染 5 个区域:
        1. 行程摘要头部 (标题/日期/人数/预算/标签)
        2. 日期选择器 + 天气图标
        3. 每日时间线 (timeline-item 组件)
        4. 预算饼图 (Canvas 绘制)
        5. 省钱小贴士
      → "保存行程" → CloudBase trips 集合 .add()
```

### 4.9 涉及文件

| 层 | 文件 | 关键函数 |
|----|------|---------|
| 前端表单 | `miniprogram/pages/create/index.js` | `onGenerate()`, `goNext()` |
| 前端生成 | `miniprogram/pages/generate/index.js` | `_callBackend()`, `_pollStatus()` |
| 前端结果 | `miniprogram/pages/result/index.js` | `onLoad()`, `onSave()` |
| 前端完成 | `miniprogram/pages/complete/index.js` | `onLoad()` |
| API 客户端 | `miniprogram/utils/api.js` | `generateTrip()`, `getTripStatus()` |
| 路由层 | `backend/api/v1/trips.py` | `generate_trip()`, `get_generation_status()`, `cancel_trip()` |
| 服务层 | `backend/services/trip_service.py` | `generate_trip()`, `_run_generation()`, `get_generation_status()`, `cancel_trip()` |
| 编排层 | `backend/agents/supervisor.py` | `SupervisorAgent.run()` |
| 工作流 | `backend/agents/graph.py` | `research_node`, `plan_node`, `budget_node`, `reflection_node`, `format_node`, `_fix_coordinates` |
| 工具层 | `backend/agents/tools.py` | `_amap_mcp()`, `get_weather()`, `geocode()`, `flyai_search()` |
| 工具函数 | `backend/agents/utils.py` | `update_progress()`, `check_cancelled()`, `CancelledError` |
| Schema | `backend/schemas/trip.py` | `TripFormData`, `TripResult`, `GenerateResponse`, `GenerateStatusResponse` |

---

## 五、前端轮询与取消流程

### 5.1 轮询机制

```
generate/index.js
  │
  ├── onLoad → _callBackend()
  │   └── POST /api/v1/trips/generate → { tripId }
  │
  └── _pollStatus()
      ├── setInterval 每 3000ms 执行:
      │   ├── GET /api/v1/trips/{tripId}/status
      │   ├── 更新 5 步进度条 (分析/检索/规划/预算/优化)
      │   ├── 更新 currentStep 文字
      │   │
      │   ├── status === "completed" + result
      │   │   → clearInterval
      │   │   → wx.setStorageSync('tripResult', result)
      │   │   → wx.navigateTo('/pages/complete/index')
      │   │
      │   ├── status === "failed"
      │   │   → clearInterval → 显示错误弹窗
      │   │
      │   ├── status === "cancelled"
      │   │   → clearInterval → 停止轮询
      │   │
      │   └── 连续 10 次错误
      │       → 显示"连接失败"弹窗
      │
      └── 最多轮询 60 次 (3分钟)
```

### 5.2 取消机制

```
用户点击"返回" (onUnload)
    │
    ├── wx.cloud.callContainer({
    │     path: '/api/v1/trips/{tripId}/cancel',
    │     method: 'DELETE',
    │   })
    │
    ▼
后端 trip_service.cancel_trip(trip_id)
    │
    ├── trip_id 在 _generation_tasks 中
    │   └── status 为 "processing"
    │       → 加入 _cancelled_trips 集合
    │       → return True
    │
    ├── status 已为 "completed"/"failed"
    │   → return False (不可取消)
    │
    └── trip_id 不存在
        → return False

    ▼
LangGraph 各节点入口 → check_cancelled(trip_id)
    │
    ├── trip_id 在 _cancelled_trips 中
    │   → 从集合移除
    │   → raise CancelledError
    │
    └── 未在集合中 → 正常继续

    ▼
CancelledError 被 supervisor.run() 捕获 → 返回 {}
    → _run_generation() 检测空结果 → 标记 cancelled
    → 前端轮询读到 cancelled → 停止
```

**局限性**:
- LLM `invoke()` 执行期间（10~30秒）无法中断
- 取消检查仅在节点边界处发生
- 如果所有节点都在快速执行（无 LLM 调用），可能取消不生效

### 5.3 涉及文件

| 文件 | 关键代码 |
|------|---------|
| `miniprogram/pages/generate/index.js` | `_pollStatus()`, `onUnload()` 中的 cancel 调用 |
| `backend/services/trip_service.py` | `cancel_trip()`, `_cancelled_trips` |
| `backend/agents/utils.py` | `check_cancelled()`, `CancelledError` |
| `backend/agents/graph.py` | 各节点头部的 `check_cancelled()` |

---

## 六、逆地理编码流程

### 6.1 流程图

```
前端 (当前未使用此接口，后续可能用于"附近热门目的地")
    │
    │ GET /api/v1/geo/reverse?lat=39.90&lng=116.40
    ▼
api/v1/geo.py reverse_geocode()
    │
    ├── settings.amap_key 存在?
    │   YES → _amap_reverse(lat, lng)
    │   │       │
    │   │       ▼
    │   │   httpx GET https://restapi.amap.com/v3/geocode/regeo
    │   │   params: { output=json, location="116.40,39.90", key="...", radius=1000 }
    │   │       │
    │   │       ▼
    │   │   解析: data.regeocode.addressComponent
    │   │   { city, province, district, formatted_address }
    │   │       │
    │   │       ▼
    │   │   return { city, province, district, fullAddress }
    │   │
    │   NO  → _osm_reverse(lat, lng)
    │           │
    │           ▼
    │       httpx GET https://nominatim.openstreetmap.org/reverse
    │       params: { lat, lon, format=json, accept-language=zh, zoom=8 }
    │           │
    │           ▼
    │       解析 OSM 地址 (兼容 city/state/county/town 格式)
    │       return { city, province, district, fullAddress }
    │
    ▼
响应: { "city": "北京", "province": "北京市", "district": "东城区", "fullAddress": "..." }
```

### 6.2 关键差异: 高德 vs 腾讯

| 项目 | 高德 (当前) | 腾讯 (已替换) |
|------|------------|--------------|
| URL | `restapi.amap.com/v3/geocode/regeo` | `apis.map.qq.com/ws/geocoder/v1/` |
| 参数 | `location=经度,纬度` | `location=纬度,经度` |
| 成功标志 | `status == "1"` (字符串) | `status == 0` (数字) |
| 地址字段 | `regeocode.addressComponent` | `result.address_component` |
| 完整地址 | `regeocode.formatted_address` | `result.address` |

### 6.3 独立云函数 (微信侧)

`cloudfunctions/reverseGeocoder/index.js` 提供了同样的功能，通过 `wx.cloud.callFunction` 调用，使用高德 REST API。

### 6.4 涉及文件

| 文件 | 关键函数 |
|------|---------|
| `backend/api/v1/geo.py:40` | `reverse_geocode()` |
| `backend/api/v1/geo.py:65` | `_amap_reverse()` |
| `backend/api/v1/geo.py:127` | `_osm_reverse()` |
| `cloudfunctions/reverseGeocoder/index.js` | 云函数版本 |

---

## 七、目的地 API 流程

### 7.1 流程图

```
前端 (首页 /pages/index/index)
    │
    │ 当前: 使用 mockHotDestinations (静态数据)
    │ 后端接口: GET /api/v1/destinations/hot (备用)
    │
    ▼
api/v1/destinations.py
    │
    ├── GET /hot
    │   → HOT_DESTINATIONS 硬编码列表 (20个城市)
    │   → { "items": [DestinationItem.model_dump()] }
    │
    └── GET /random
        → random.choice(HOT_DESTINATIONS)
        → { "name": ..., "id": ..., "tags": ..., "description": ... }
```

### 7.2 数据来源

20 个硬编码的 `DestinationItem`，包含: id, name, tags, image, description, basePrice。

**设计原因**: 热门目的地变化频率极低（按季度），硬编码 = 零数据库查询 = 极速响应。

### 7.3 涉及文件

| 文件 | 关键代码 |
|------|---------|
| `backend/api/v1/destinations.py:41` | `HOT_DESTINATIONS` 列表 |
| `backend/api/v1/destinations.py:108` | `get_hot()` |
| `backend/api/v1/destinations.py:125` | `get_random()` |

---

## 八、地图 Key 下发流程

### 8.1 流程图

```
前端 app.js fetchMapKey() (onLaunch)
    │
    │ GET /api/v1/config/map-key
    ▼
main.py get_map_key()
    │
    └── return { "amapKey": settings.amap_key or "" }
    │
    ▼
前端 globalData.amapKey = "xxx"
    ↓
前端 map 组件使用此 Key 渲染地图
(地图功能当前标注为"开发中")
```

### 8.2 设计原因

- 地图 Key 属于敏感信息，不应硬编码在前端代码
- 通过后端 API 动态下发，管理员可随时更换 Key
- 若后端不可达，降级使用前端硬编码的 `_fallbackMapKey`

### 8.3 涉及文件

| 文件 | 关键代码 |
|------|---------|
| `miniprogram/app.js:172` | `fetchMapKey()` |
| `backend/main.py:128` | `get_map_key()` |

---

## 九、CloudBase 数据库调用汇总

### 9.1 所有集合操作

| 集合 | 操作 | 触发时机 | 位置 |
|------|------|---------|------|
| `users` | `.count()` + `.add()` / `.update()` | 登录成功后 | `app.js` wxLogin 回调 |
| `trips` | `.get()` (最近3条) | 首页 onShow | `pages/index/index.js` |
| `trips` | `.add()` | 用户点击"保存" | `pages/result/index.js` onSave |
| `trips` | `.get()` (最多50条) | "我的"页面 onShow | `pages/my/index.js` |

### 9.2 数据格式

**users 集合**:
```json
{
  "_id": "自动生成",
  "openid": "微信 OpenID",
  "user_id": "JWT 中的 user_id",
  "nickname": "",
  "avatar_url": "",
  "created_at": "serverDate()",
  "last_login": "serverDate()"
}
```

**trips 集合**:
```json
{
  "_id": "自动生成",
  "title": "北京3日深度游",
  "destination": "北京",
  "startDate": "2025-06-01",
  "endDate": "2025-06-03",
  "days": 3, "nights": 2,
  "people": 2, "adults": 2, "children": 0,
  "totalBudget": 6500,
  "dailyPlan": [...],
  "createdAt": "serverDate()"
}
```

---

## 十、外部服务依赖

### 10.1 服务矩阵

| 外部服务 | 用途 | 协议 | 是否有 Key 限制 | 回退策略 |
|---------|------|------|---------------|---------|
| 高德地图 MCP | 天气/地理编码/POI搜索/路线 | MCP (JSON-RPC 2.0) | 需要 amap_key | 天气→往年平均 |
| 高德地图 REST | 逆地理编码 | HTTP GET | 需要 amap_key | OSM Nominatim |
| 飞猪 FlyAI | 景点/酒店真实价格 | CLI (subprocess) | 需要 flyai_key | LLM 训练数据 |
| 微信登录 | jscode2session | HTTP GET | 需要 appid+secret | 开发模式 mock |

### 10.2 高德 MCP 协议详解

```
客户端                               高德 MCP 服务器
  │                                          │
  │  1. POST /mcp?key=xxx                    │
  │     JSON-RPC initialize                  │
  │     { method, params, id: 0 }            │
  │ ──────────────────────────────────────►   │
  │     Response: headers[mcp-session-id]     │
  │ ◄──────────────────────────────────────   │
  │                                          │
  │  2. POST /mcp?key=xxx                    │
  │     JSON-RPC notifications/initialized   │
  │     headers[Mcp-Session-Id]             │
  │ ──────────────────────────────────────►   │
  │     (无响应体)                            │
  │                                          │
  │  [缓存 session]                          │
  │                                          │
  │  3. POST /mcp?key=xxx                    │
  │     JSON-RPC tools/call                  │
  │     { method, params: {name, arguments}, │
  │       id: 1 }                            │
  │     headers[Mcp-Session-Id]             │
  │ ──────────────────────────────────────►   │
  │     { result: { content: [{type, text}] }}│
  │ ◄──────────────────────────────────────   │
```

后续相同 amap_key 的调用跳过第 1、2 步，直接发送 tools/call。

### 10.3 涉及文件

| 文件 | 关键代码 |
|------|---------|
| `backend/agents/tools.py:44` | `_amap_mcp()` — MCP 统一客户端 |
| `backend/agents/tools.py:160` | `amap()` — LangChain @tool 接口 |
| `backend/agents/tools.py:195` | `get_weather()` |
| `backend/agents/tools.py:290` | `geocode()` |
| `backend/agents/tools.py:380` | `flyai_search()` |

---

## 十一、完整页面导航路由图

```
┌──────────┐     wx.navigateTo     ┌──────────┐
│  首页    │ ────────────────────► │ 创建行程  │
│ index    │                      │ create   │
│          │ ◄── wx.switchTab ─── │ (2步表单) │
└────┬─────┘                      └────┬─────┘
     │                                 │
     │ wx.navigateTo                   │ wx.navigateTo
     │ (点击行程卡片)                   │ (onGenerate)
     ▼                                 ▼
┌──────────┐                     ┌──────────┐
│ 行程详情  │                     │ AI生成中  │
│ result   │                     │ generate │
│          │                     │ (轮询3s)  │
└────┬─────┘                     └────┬─────┘
     │ ▲                              │
     │ │ wx.redirectTo                │ status=completed
     │ │ (onViewDetail)               │ wx.navigateTo
     │ └──────────────────             ▼
     │                        ┌──────────┐
     │                        │ 完成预览  │
     │                        │ complete │
     │                        └────┬─────┘
     │                              │
     │                              ├── "查看完整" → result
     │                              ├── "重新生成" → generate
     │                              └── "返回首页" → index (switchTab)
     │
     │ wx.switchTab
     ▼
┌──────────┐
│  我的    │
│ my       │
│          │──── 点击行程 → wx.navigateTo → result
└──────────┘
```

**页面间数据传递**:
| 页面 → 页面 | 传递方式 | 数据 |
|------------|---------|------|
| create → generate | `wx.setStorageSync('tripFormData')` | 完整表单数据 |
| generate → complete | `wx.setStorageSync('tripResult')` | AI 生成的 TripResult |
| complete → result | `wx.setStorageSync('tripResult')` | 同上 |
| index → result | `wx.setStorageSync('tripResult')` | 从 CloudBase 读取的历史行程 |
| my → result | `wx.setStorageSync('tripResult')` | 从 CloudBase 读取的历史行程 |

---

## 附录

### A. 所有 API 端点清单

| 端点 | 方法 | 认证 | 用途 | 响应时间 |
|------|------|------|------|---------|
| `/api/v1/auth/login` | POST | 否 | 微信登录换取 JWT | <1s |
| `/api/v1/trips/generate` | POST | JWT | 提交行程生成请求 | 立即返回 (201) |
| `/api/v1/trips/{id}/status` | GET | 否 | 查询生成进度 | <10ms |
| `/api/v1/trips/{id}/cancel` | DELETE | 否 | 取消生成 | <10ms |
| `/api/v1/destinations/hot` | GET | 否 | 热门目的地列表 | <5ms |
| `/api/v1/destinations/random` | GET | 否 | 随机推荐目的地 | <5ms |
| `/api/v1/geo/reverse` | GET | 否 | 逆地理编码 | <500ms |
| `/api/v1/config/map-key` | GET | 否 | 下发地图 Key | <5ms |
| `/health` | GET | 否 | 健康检查 | <5ms |
| `/` | GET | 否 | 应用信息 | <5ms |

### B. 所有文件依赖关系图

```
main.py
  ├── api/v1/trips.py → services/trip_service.py → agents/supervisor.py
  │                                                    └── agents/graph.py
  │                                                        ├── agents/tools.py
  │                                                        │   ├── config.py
  │                                                        │   ├── httpx (MCP)
  │                                                        │   ├── subprocess (FlyAI)
  │                                                        │   └── duckduckgo_search
  │                                                        └── agents/utils.py
  │                                                            └── services/trip_service.py
  ├── api/v1/destinations.py → schemas/trip.py
  ├── api/v1/geo.py → config.py, httpx
  ├── api/v1/auth.py → config.py, httpx, jwt
  └── api/deps.py → config.py, jwt
```

### C. 面试考点索引

| 考点 | 说明 | 模块 |
|------|------|------|
| 为什么用轮询而非 WebSocket？ | CloudRun 按请求计费，轮询简单可靠 | `api/v1/trips.py` |
| 为什么 create_task 而非 await？ | 避免阻塞 HTTP 响应，实现"提交即返回" | `api/v1/trips.py` |
| FastAPI response_model 的作用？ | 过滤字段、类型转换、生成 OpenAPI 文档 | `api/v1/trips.py` |
| 为什么用 JWT 而非 Session？ | 小程序无 Cookie，JWT 无状态易扩展 | `api/v1/auth.py` |
| Double API 回退策略？ | 渐进增强：有 Key 用最好的，没 Key 也能用 | `api/v1/geo.py` |
| 为什么目的地硬编码？ | 零数据库查询，冷启动兜底数据 | `api/v1/destinations.py` |
| 反射节点为什么不调 LLM？ | 代码检查+规则（雨天室内/预算占比）节省 10~30s | `agents/graph.py` |
| MCP 为什么需要 session？ | HTTP 无状态，session 维持连接上下文 | `agents/tools.py` |
| run_in_executor 替代手工线程？ | 1 行 vs 30+ 行，无需轮询，异常直接传播 | `agents/supervisor.py` |
| lru_cache 缓存 LLM 实例？ | 同参数只创建一次，节省内存，GIL 保证线程安全 | `config.py` |
| patch.multiple 而非 patch.object？ | direct modify 原实例，所有 import 引用均受影响 | `tests/conftest.py` |
| _fix_coordinates 对抗幻觉？ | 用真实坐标覆盖 LLM 编造的坐标 | `agents/graph.py` |
