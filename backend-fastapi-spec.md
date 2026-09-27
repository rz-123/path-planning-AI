# AI 旅行规划 — FastAPI 后端接口规范

> 版本: v2.0  
> 对应前端: 微信小程序 6 个页面  
> 数据库: PostgreSQL (主库) + Redis (缓存/队列)

---

## 一、架构映射

```
前端                              后端
────────────────────────────────────────────
Storage.getItem('tripFormData')  →  POST /api/trips/generate
Storage.setItem('tripResult')    →  response

mockHotDestinations              →  GET  /api/destinations/hot
mockRecentTrips                  →  GET  /api/trips/recent
mockHistoryTrips                 →  GET  /api/trips/history

create → generate → complete     →  表单提交 → AI生成 → 保存/返回
index → result / my              →  列表查询 → 详情查询
```

---

## 二、Pydantic 数据模型

### 2.1 枚举常量

```python
from enum import Enum

class TransportEnum(str, Enum):
    plane = "plane"    # 飞机
    train = "train"    # 高铁
    car = "car"        # 自驾

class StyleEnum(str, Enum):
    leisure = "leisure"        # 轻松休闲
    deep = "deep"              # 深度打卡
    artistic = "artistic"      # 文艺小资
    intensive = "intensive"    # 特种兵式

class BudgetEnum(str, Enum):
    economy = "economy"        # 经济 (¥500-1k/人/天)
    comfort = "comfort"        # 舒适 (¥1k-1.5k/人/天)
    quality = "quality"        # 品质 (¥1.5k-2k/人/天)

class AccommodationEnum(str, Enum):
    budget = "budget"          # 经济型
    comfort = "comfort"        # 舒适型
    premium = "premium"        # 高档型

class TripStatusEnum(str, Enum):
    draft = "draft"            # 草稿
    completed = "completed"    # 已完成
    canceled = "canceled"      # 已取消
```

### 2.2 用户表单输入

```python
from pydantic import BaseModel, Field, field_validator
from datetime import date

class TripFormData(BaseModel):
    """创建页面 2 步表单提交的数据"""
    # ---- 步骤1: 基本信息 ----
    origin: str | None = Field(None, examples=["北京"], description="出发城市")
    destination: str = Field(..., examples=["西安"], description="目的地城市")
    start_date: date = Field(..., alias="startDate", description="出发日期")
    end_date: date = Field(..., alias="endDate", description="结束日期")
    adults: int = Field(default=2, ge=1, le=10, description="成人数")
    children: int = Field(default=0, ge=0, le=5, description="儿童数")
    transport: TransportEnum = Field(default=TransportEnum.plane, description="出行方式")

    # ---- 步骤2: 偏好设置 ----
    style: StyleEnum = Field(default=StyleEnum.leisure, description="旅行风格")
    interests: list[str] = Field(
        default_factory=lambda: ["food", "museum"],
        description="兴趣标签: food/museum/nature/family/shopping/red/nightlife/photo"
    )
    budget: BudgetEnum = Field(default=BudgetEnum.comfort, description="预算档位")
    accommodation: AccommodationEnum = Field(
        default=AccommodationEnum.comfort, description="住宿偏好"
    )
    special_needs: str | None = Field(
        default=None, max_length=500, alias="specialNeeds",
        description="特殊需求（如想去的地方、无障碍需求等）"
    )

    @field_validator("end_date")
    @classmethod
    def end_not_before_start(cls, v, info):
        if "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("结束日期不能早于开始日期")
        return v
```

### 2.3 行程结果（AI 生成）

```python
from datetime import datetime

class ScheduleItem(BaseModel):
    """演出时间表"""
    name: str
    times: str

class FoodDish(BaseModel):
    """推荐菜品"""
    name: str
    image: str | None = None

class TimelineItem(BaseModel):
    """每日行程中的单个活动"""
    time: str = Field(..., examples=["08:30 - 09:30"])
    name: str = Field(..., examples=["八路军西安办事处纪念馆"])
    address: str
    tag: str = ""
    tag_color: str = Field(default="#3B82F6", alias="tagColor")
    tag_bg: str = Field(default="#DBEAFE", alias="tagBg")
    description: str
    image: str | None = None
    tips: str = ""
    cost: float = 0.0
    dishes: list[FoodDish] | None = None
    schedule: list[ScheduleItem] | None = None

class PeriodItem(BaseModel):
    """一天内的时段（上午/中午/下午/晚上）"""
    time_slot: str = Field(alias="timeSlot", examples=["上午"])
    icon: str = Field(examples=["☀️"])
    color: str = Field(examples=["#F59E0B"])
    bg_color: str = Field(alias="bgColor", examples=["#FEF3C7"])
    items: list[TimelineItem]

class DailyPlan(BaseModel):
    """单日行程"""
    day: int
    date: str = Field(examples=["7.15"])
    periods: list[PeriodItem]

class BudgetItem(BaseModel):
    """预算明细项"""
    name: str
    type: str = ""
    amount: float
    per_night: float | None = Field(default=None, alias="perNight")
    note: str | None = None

class BudgetCategory(BaseModel):
    """预算分类（住宿/餐饮/交通/门票）"""
    total: float
    icon: str
    items: list[BudgetItem]
    tips: str = ""

class BudgetDetail(BaseModel):
    """完整预算明细"""
    accommodation: BudgetCategory
    food: BudgetCategory
    transport: BudgetCategory
    tickets: BudgetCategory

class BudgetPieItem(BaseModel):
    """饼图数据"""
    name: str
    value: float
    color: str
    percent: int

class BookItem(BaseModel):
    """推荐书单"""
    title: str
    author: str
    cover: str
    description: str

class TripResult(BaseModel):
    """完整的行程结果"""
    id: str
    user_id: str | None = Field(default=None, alias="userId")
    title: str
    origin: str | None = None
    destination: str
    start_date: str = Field(alias="startDate")
    end_date: str = Field(alias="endDate")
    days: int
    nights: int
    people: int
    adults: int = 0
    children: int = 0
    transport: str
    style: str
    interests: list[str]
    total_budget: float = Field(alias="totalBudget")
    budget_per_person: float = Field(alias="budgetPerPerson")
    budget_level: str = Field(alias="budgetLevel")
    status: TripStatusEnum = TripStatusEnum.completed
    budget_detail: BudgetDetail = Field(alias="budgetDetail")
    budget_pie_data: list[BudgetPieItem] = Field(alias="budgetPieData")
    daily_plan: list[DailyPlan] = Field(alias="dailyPlan")
    books: list[BookItem] = []
    map_image: str | None = Field(default=None, alias="mapImage")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
```

### 2.4 列表接口返回模型

```python
class TripSummary(BaseModel):
    """首页 / 我的页 列表项"""
    id: str
    title: str
    destination: str
    start_date: str = Field(alias="startDate")
    end_date: str = Field(alias="endDate")
    days: int
    people: int
    tags: str
    status: TripStatusEnum
    status_text: str = Field(alias="statusText")
    budget: float
    # 我的页额外字段
    month: str | None = None
    day: str | None = None

class DestinationItem(BaseModel):
    """热门目的地"""
    id: str
    name: str
    tags: str
    image: str
    description: str
    base_price: float = Field(alias="basePrice")

class PaginatedResponse(BaseModel):
    items: list[TripSummary]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")
```

---

## 三、API 接口清单

### 3.1 行程生成（核心接口）

```
POST /api/v1/trips/generate
```

**描述**: 提交用户表单数据，AI Agent 异步生成完整行程。

**请求体**: `TripFormData`

**响应** (201):
```json
{
  "tripId": "trip_xian_20240714_a3f2",
  "status": "processing",
  "message": "行程生成中，预计 30-60 秒完成"
}
```

**轮询结果**:
```
GET /api/v1/trips/{tripId}/status
```

**响应** (200):
```json
{
  "tripId": "trip_xian_20240714_a3f2",
  "status": "completed",          // processing | completed | failed
  "progress": 100,                 // 0-100
  "currentStep": "优化行程中...",   // 当前步骤描述
  "result": { "...TripResult..." } // status=completed 时返回
}
```

**后端处理流程** (Celery / BackgroundTasks):

```
步骤1: 解析偏好 (5%)   → 分析用户风格、兴趣、预算
步骤2: 检索景点 (20%)  → 查目的地景点数据库 / 实时搜索
步骤3: 规划路线 (40%)  → 按天分配景点，排序时间
步骤4: 计算预算 (20%)  → 住宿/餐饮/交通/门票 费用估算
步骤5: 生成书单 (10%)  → 推荐相关书籍
步骤6: 优化输出 (5%)   → 结构调整，贴士补充
```

### 3.2 保存 / 更新行程

```
POST   /api/v1/trips
PUT    /api/v1/trips/{tripId}
```

**请求体**: `TripResult` (POST 时 id 可为空，由服务端生成)

**响应** (200):
```json
{
  "id": "trip_xian_20240714_a3f2",
  "createdAt": "2024-07-14T10:30:00Z"
}
```

### 3.3 获取行程详情

```
GET /api/v1/trips/{tripId}
```

**响应** (200): `TripResult`

### 3.4 删除行程

```
DELETE /api/v1/trips/{tripId}
```

**响应** (200):
```json
{ "success": true }
```

### 3.5 行程列表查询

```
GET /api/v1/trips
```

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 否 | `completed` / `draft` / `canceled`，不传=全部 |
| `page` | int | 否 | 页码，默认 1 |
| `pageSize` | int | 否 | 每页条数，默认 10，最大 50 |
| `sort` | string | 否 | `createdAt`(默认) / `startDate` |
| `order` | string | 否 | `desc`(默认) / `asc` |

**响应** (200): `PaginatedResponse`

### 3.6 首页快捷查询

```
GET /api/v1/trips/recent
```

**描述**: 返回最近 3 条已完成行程（首页"最近规划"卡片）

**响应** (200):
```json
{
  "items": [ TripSummary × 3 ]
}
```

### 3.7 我的页历史查询

```
GET /api/v1/trips/history
```

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `days` | int | 否 | 近 N 天，默认 30 |
| `page` | int | 否 | 默认 1 |
| `pageSize` | int | 否 | 默认 20 |

**响应** (200): `PaginatedResponse` (items 含 `month`/`day` 字段)

### 3.8 我的页统计

```
GET /api/v1/trips/stats
```

**响应** (200):
```json
{
  "totalTrips": 12,
  "totalDays": 38,
  "favoriteDestination": "西安",
  "favoriteCount": 3,
  "totalBudget": 45200,
  "avgBudgetPerTrip": 3767
}
```

### 3.9 热门目的地

```
GET /api/v1/destinations/hot
```

**响应** (200):
```json
{
  "items": [ DestinationItem × 20 ]
}
```

### 3.10 随机目的地推荐

```
GET /api/v1/destinations/random
```

**响应** (200):
```json
{
  "name": "成都",
  "id": "chengdu",
  "tags": "美食之都 | 亲子友好",
  "description": "熊猫基地、宽窄巷子、火锅美食"
}
```

### 3.11 重新生成行程

```
POST /api/v1/trips/{tripId}/regenerate
```

**描述**: 基于已有行程，修改部分参数后重新生成。

**请求体**: `TripFormData` (可部分更新)

**响应**: 同 3.1 (201)

### 3.12 逆地理编码

```
GET /api/v1/geo/reverse
```

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `lat` | float | 是 | 纬度 |
| `lng` | float | 是 | 经度 |

**响应** (200):
```json
{
  "city": "广州",
  "province": "广东省",
  "district": "天河区",
  "fullAddress": "广东省广州市天河区xxx路"
}
```

---

## 四、FastAPI 项目结构建议

```
backend/
├── main.py                    # FastAPI 入口
├── config.py                  # 配置 (DB/Redis/AI Key)
├── requirements.txt
├── alembic/                   # 数据库迁移
│
├── models/                    # SQLAlchemy / Tortoise ORM
│   ├── __init__.py
│   ├── trip.py                # Trip 表
│   ├── destination.py         # Destination 表
│   └── user.py                # User 表
│
├── schemas/                   # Pydantic 请求/响应
│   ├── __init__.py
│   ├── trip.py                # TripFormData, TripResult, TripSummary
│   ├── destination.py         # DestinationItem
│   └── common.py              # PaginatedResponse, ErrorResponse
│
├── api/                       # 路由
│   ├── __init__.py
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── trips.py           # 行程 CRUD + 生成
│   │   ├── destinations.py    # 目的地
│   │   └── geo.py             # 逆地理编码
│   └── deps.py                # 依赖注入 (get_db, get_current_user)
│
├── services/                  # 业务逻辑
│   ├── __init__.py
│   ├── trip_service.py        # 行程业务
│   ├── ai_service.py          # AI Agent 生成
│   └── geo_service.py         # 逆地理编码
│
├── agents/                    # AI Agent (LangChain/LangGraph)
│   ├── __init__.py
│   ├── graph.py               # StateGraph 定义
│   ├── nodes.py               # 各步骤节点
│   └── prompts.py             # Prompt 模板
│
├── workers/                   # 后台任务
│   ├── __init__.py
│   └── trip_generator.py      # Celery 生成任务
│
└── db/                        # 数据库
    ├── __init__.py
    └── session.py             # 连接池
```

---

## 五、接口汇总表

| # | 方法 | 路径 | 前端触发位置 | 说明 |
|---|------|------|-------------|------|
| 1 | POST | /api/v1/trips/generate | create→generate 页 | 提交表单，AI 生成 |
| 2 | GET | /api/v1/trips/{id}/status | generate 页轮询 | 查询生成进度 |
| 3 | POST | /api/v1/trips | complete 页保存 | 保存行程 |
| 4 | PUT | /api/v1/trips/{id} | — | 更新行程 |
| 5 | GET | /api/v1/trips/{id} | result 页 | 行程详情 |
| 6 | DELETE | /api/v1/trips/{id} | — | 删除行程 |
| 7 | GET | /api/v1/trips | — | 行程列表 |
| 8 | GET | /api/v1/trips/recent | index 首页 | 最近 3 条 |
| 9 | GET | /api/v1/trips/history | my 我的页 | 近 N 天历史 |
| 10 | GET | /api/v1/trips/stats | my 我的页 | 统计数据 |
| 11 | GET | /api/v1/destinations/hot | index 首页 | 热门目的地 |
| 12 | GET | /api/v1/destinations/random | create 页 | 随机推荐 |
| 13 | POST | /api/v1/trips/{id}/regenerate | result 页 | 重新生成 |
| 14 | GET | /api/v1/geo/reverse | create 起始地 | GPS→城市名 |

---

## 六、用户认证

前端使用微信登录，后端通过 CloudBase 鉴权：

```python
from fastapi import Depends, HTTPException, Header

async def get_current_user(authorization: str = Header(...)) -> str:
    """
    从 Authorization header 提取 CloudBase token，验证后返回 userId (openid)
    前端调用: const { data } = await app.auth().getAccessToken()
               wx.request({ header: { Authorization: `Bearer ${data.accessToken}` } })
    """
    # 调用 CloudBase Auth API 验证 token
    ...
    return user_id
```

所有 `/api/v1/trips/*` 接口需要认证，`/api/v1/destinations/*` 和 `/api/v1/geo/*` 无需认证。

---

## 七、错误响应规范

```json
{
  "error": {
    "code": "TRIP_NOT_FOUND",
    "message": "行程不存在",
    "detail": "trip_id=xxx not found"
  }
}
```

| HTTP | code | 说明 |
|------|------|------|
| 400 | VALIDATION_ERROR | 参数校验失败 |
| 401 | UNAUTHORIZED | 未认证 |
| 404 | TRIP_NOT_FOUND | 行程不存在 |
| 409 | GENERATION_IN_PROGRESS | 正在生成中 |
| 422 | INVALID_FORM_DATA | 表单数据不合法 |
| 500 | AI_GENERATION_FAILED | AI 生成失败 |
| 503 | GEO_SERVICE_UNAVAILABLE | 逆地理编码不可用 |

---

## 八、数据库表设计 (PostgreSQL)

```sql
CREATE TABLE trips (
    id          VARCHAR(32) PRIMARY KEY,
    user_id     VARCHAR(64) NOT NULL,
    title       VARCHAR(100) NOT NULL,
    origin      VARCHAR(50),
    destination VARCHAR(50) NOT NULL,
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    days        SMALLINT NOT NULL,
    nights      SMALLINT NOT NULL,
    people      SMALLINT NOT NULL,
    adults      SMALLINT DEFAULT 2,
    children    SMALLINT DEFAULT 0,
    transport   VARCHAR(10) NOT NULL,
    style       VARCHAR(20) NOT NULL,
    interests   TEXT[] NOT NULL DEFAULT '{}',
    total_budget DECIMAL(10,2) NOT NULL,
    budget_per_person DECIMAL(10,2),
    budget_level VARCHAR(10),
    status      VARCHAR(20) DEFAULT 'completed',
    data        JSONB NOT NULL,        -- 完整 TripResult JSON
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP
);

CREATE INDEX idx_trips_user_id ON trips(user_id);
CREATE INDEX idx_trips_status ON trips(status);
CREATE INDEX idx_trips_date ON trips(start_date DESC);

CREATE TABLE destinations (
    id          VARCHAR(32) PRIMARY KEY,
    name        VARCHAR(50) NOT NULL,
    tags        VARCHAR(100),
    image       VARCHAR(500),
    description VARCHAR(500),
    base_price  DECIMAL(10,2),
    sort_order  INT DEFAULT 0
);

CREATE TABLE users (
    id          VARCHAR(64) PRIMARY KEY,  -- openid
    nickname    VARCHAR(50),
    avatar      VARCHAR(500),
    created_at  TIMESTAMP DEFAULT NOW()
);
```
