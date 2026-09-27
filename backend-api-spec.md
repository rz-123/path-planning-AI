# AI旅行规划小程序 - 后端 API 接口规范

> 版本：v1.0  
> 技术栈：Python + Agent（建议 FastAPI + LangChain/LangGraph）  
> 数据库：PostgreSQL / MongoDB

---

## 一、数据结构定义

### 1.1 行程数据 `Trip`

```json
{
  "id": "trip_xian_001",
  "user_id": "user_openid",
  "title": "西安3日红色文化之旅",
  "destination": "西安",
  "startDate": "2024-07-15",
  "endDate": "2024-07-17",
  "days": 3,
  "nights": 2,
  "people": 2,
  "transport": "高铁",
  "style": "深度打卡",
  "interests": ["红色基地", "博物馆", "历史古迹", "美食探店"],
  "totalBudget": 3860,
  "budgetPerPerson": 1930,
  "budgetLevel": "comfort",
  "status": "completed",
  "budgetDetail": { "...见1.2" },
  "dailyPlan": [ "...见1.3" ],
  "books": [ "...见1.4" ],
  "mapImage": "https://...map.jpg",
  "createdAt": "2024-07-14T10:30:00Z",
  "updatedAt": "2024-07-14T10:30:00Z"
}
```

### 1.2 预算明细 `BudgetDetail`

```json
{
  "accommodation": {
    "total": 1800,
    "icon": "🏨",
    "items": [
      {
        "name": "西安钟楼亚朵S酒店",
        "type": "高级双床房 3晚(含双早)",
        "amount": 1800,
        "perNight": 600
      }
    ],
    "tips": "建议提前15-30天预订，旅游旺季价格可能会上浮20%-50%"
  },
  "food": {
    "total": 900,
    "icon": "🍜",
    "items": [
      { "name": "正餐(3天)", "type": "6顿正餐，人均每顿¥60标准", "amount": 720 },
      { "name": "小吃/零食/饮品", "type": "特产、特色小吃、饮料等", "amount": 180 }
    ],
    "tips": "回民街等景区餐饮价格较高，建议选择本地居民区的餐馆用餐"
  },
  "transport": {
    "total": 600,
    "icon": "🚌",
    "items": [
      { "name": "当地交通", "type": "打车、地铁、公交等市内出行", "amount": 300 },
      { "name": "往返大交通", "type": "此预算未包含往返交通费用", "amount": 0, "note": "未计算" }
    ]
  },
  "tickets": {
    "total": 560,
    "icon": "🎫",
    "items": [
      { "name": "陕西历史博物馆(大唐遗宝展)", "type": "2人，¥30/人", "amount": 60 },
      { "name": "兵马俑博物馆", "type": "2人，¥120/人", "amount": 240 },
      { "name": "华清宫", "type": "2人，¥120/人", "amount": 240 },
      { "name": "讲解服务", "type": "重要景点讲解器租赁", "amount": 60 }
    ],
    "discountNote": "学生、军人、65岁以上老人等可享受门票半价或免票政策"
  }
}
```

**预算占比数据**（饼图用）：
```json
{
  "budgetPieData": [
    { "name": "住宿", "value": 1800, "color": "#3B82F6", "percent": 47 },
    { "name": "餐饮", "value": 900, "color": "#22C55E", "percent": 23 },
    { "name": "交通", "value": 600, "color": "#F59E0B", "percent": 15 },
    { "name": "门票", "value": 560, "color": "#EF4444", "percent": 15 }
  ]
}
```

### 1.3 每日行程 `DailyPlan`

```json
[
  {
    "day": 1,
    "date": "7.15",
    "periods": [
      {
        "timeSlot": "上午",
        "icon": "☀️",
        "color": "#F59E0B",
        "bgColor": "#FEF3C7",
        "items": [
          {
            "time": "08:30 - 09:30",
            "name": "八路军西安办事处纪念馆",
            "address": "新城区北新街七贤庄",
            "tag": "红色教育基地",
            "tagColor": "#EF4444",
            "tagBg": "#FEF2F2",
            "description": "全国重点文物保护单位...",
            "image": "https://...image.jpg",
            "tips": "凭身份证免费进入，周一闭馆",
            "cost": 0
          }
        ]
      },
      {
        "timeSlot": "中午",
        "icon": "🍜",
        "color": "#F97316",
        "bgColor": "#FFEDD5",
        "items": [
          {
            "time": "12:10 - 13:30",
            "name": "同盛祥(钟楼店)",
            "address": "钟鼓楼广场西大街5号",
            "tag": "4.7分 人均¥65",
            "tagColor": "#D97706",
            "tagBg": "#FEF3C7",
            "description": "西安百年老字号...",
            "image": null,
            "tips": "",
            "cost": 130,
            "dishes": [
              { "name": "羊肉泡馍", "image": "https://...dish.jpg" },
              { "name": "肉夹馍", "image": "https://...dish.jpg" },
              { "name": "麻酱凉皮", "image": "https://...dish.jpg" }
            ]
          }
        ]
      },
      {
        "timeSlot": "下午",
        "icon": "🏛️",
        "color": "#3B82F6",
        "bgColor": "#DBEAFE",
        "items": [
          {
            "time": "14:30 - 17:30",
            "name": "陕西历史博物馆",
            "address": "雁塔区小寨东路9号",
            "tag": "国家一级博物馆",
            "tagColor": "#3B82F6",
            "tagBg": "#EFF6FF",
            "description": "中国第一座大型现代化国家级博物馆...",
            "image": "https://...museum.jpg",
            "tips": "需提前3天在官方公众号预约",
            "cost": 60
          }
        ]
      },
      {
        "timeSlot": "晚上",
        "icon": "🌃",
        "color": "#8B5CF6",
        "bgColor": "#EDE9FE",
        "items": [
          {
            "time": "19:00 - 21:30",
            "name": "大唐不夜城步行街",
            "address": "雁塔区大雁塔脚下",
            "tag": "5A景区",
            "tagColor": "#8B5CF6",
            "tagBg": "#FAF5FF",
            "description": "以盛唐文化为背景的步行街...",
            "image": "https://...street.jpg",
            "tips": "免费开放，人流量较大",
            "cost": 0,
            "schedule": [
              { "name": "不倒翁表演", "times": "19:30 / 20:30 / 21:30" },
              { "name": "敦煌飞天表演", "times": "20:00 / 21:00" }
            ]
          }
        ]
      }
    ]
  }
]
```

### 1.4 推荐书单 `BookItem`

```json
[
  {
    "title": "陕西历史博物馆馆刊",
    "author": "陕西历史博物馆 编",
    "cover": "https://...cover.jpg",
    "description": "深入了解陕博馆藏文物的前世今生..."
  }
]
```

### 1.5 表单输入数据 `TripFormData`

用户在前端 3 步表单中填写的原始数据：

```json
{
  "destination": "西安",
  "startDate": "2024-07-15",
  "endDate": "2024-07-17",
  "people": 2,
  "transport": "train",
  "style": "deep",
  "interests": ["red", "museum", "history", "food"],
  "budget": "comfort",
  "accommodation": "comfort",
  "specialNeeds": "有老人同行，需要少走路的路线"
}
```

### 1.6 热门目的地 `Destination`

```json
{
  "id": "xian",
  "name": "西安",
  "tags": "历史名城 | 红色基地",
  "image": "https://...dest.jpg",
  "description": "兵马俑、大雁塔、回民街",
  "basePrice": 2200
}
```

---

## 二、API 接口列表

### 2.1 生成行程（核心 AI 接口）

```
POST /api/trips/generate
```

**描述**：提交用户表单数据，AI Agent 生成完整行程（含每日安排、预算构成、推荐书单）

**请求体**：
```json
{
  "formData": { "...见1.5" }
}
```

**响应体**：见 `Trip` 完整数据结构（1.1）

**AI Agent 处理流程**（Python 端实现）：

```
1. 接收 formData → 解析目的地、日期、人数、偏好
2. Agent Step 1: 分析偏好和需求 → 确定旅行主题
3. Agent Step 2: 检索目的地景点和活动 → 调用搜索/知识库 API
4. Agent Step 3: 规划每日路线和时间 → 按上午/中午/下午/晚上分段
5. Agent Step 4: 计算预算和费用明细 → 住宿/餐饮/交通/门票
6. Agent Step 5: 优化行程，确保体验最佳 → 添加贴士和建议
7. 返回结构化 Trip JSON
```

**Strict 输出格式要求**：
- `dailyPlan` 必须按 `periods` > `items` 结构填充
- 每个 item 必须包含：`time`, `name`, `address`, `description`, `tips`, `cost`
- `budgetDetail` 必须包含 4 个分类：accommodation, food, transport, tickets
- `budgetPieData` 中的 `percent` 必须是整数百分比，4项之和 = 100
- 菜品推荐用 `dishes`，演出时间表用 `schedule`

### 2.2 保存行程

```
POST /api/trips
```

**请求体**：`Trip` 完整数据  
**响应**：`{ "id": "trip_xxx", "createdAt": "..." }`

### 2.3 获取行程详情

```
GET /api/trips/{trip_id}
```

**响应**：`Trip` 完整数据

### 2.4 获取用户行程列表

```
GET /api/trips?user_id={user_id}&status={status}&page=1&pageSize=10
```

**响应**：
```json
{
  "items": [ "Trip[] 简版（含 title, destination, startDate, endDate, totalBudget, status）" ],
  "total": 20,
  "page": 1,
  "pageSize": 10
}
```

### 2.5 删除行程

```
DELETE /api/trips/{trip_id}
```

**响应**：`{ "success": true }`

### 2.6 获取热门目的地

```
GET /api/destinations/hot
```

**响应**：`Destination[]`（1.6）

### 2.7 随机推荐目的地

```
GET /api/destinations/random
```

**响应**：`{ "name": "成都", "id": "chengdu" }`

### 2.8 重新生成行程

```
POST /api/trips/{trip_id}/regenerate
```

**描述**：基于已有行程数据，调整部分参数重新生成  
**请求体**：`{ "formData": { "...见1.5" } }`  
**响应**：新的 `Trip` 完整数据

---

## 三、AI Agent 建议实现方案

### 3.1 技术选型

| 组件 | 推荐方案 |
|------|---------|
| Web框架 | FastAPI |
| AI框架 | LangChain / LangGraph |
| LLM | DeepSeek-v4 / Hunyuan / GPT-4o |
| 知识检索 | 向量数据库（ChromaDB / Pinecone）或搜索 API |
| 数据存储 | PostgreSQL + JSONB 或 MongoDB |
| 部署 | CloudBase CloudRun |

### 3.2 Agent 架构建议

```python
# 伪代码示例
from langgraph.graph import StateGraph

class TripState(TypedDict):
    form_data: dict
    destination_info: dict
    attractions: list
    daily_plan: list
    budget: dict
    books: list

graph = StateGraph(TripState)
graph.add_node("analyze_preferences", analyze_node)
graph.add_node("search_attractions", search_node)
graph.add_node("plan_route", plan_node)
graph.add_node("calculate_budget", budget_node)
graph.add_node("optimize", optimize_node)
```

### 3.3 关键要求

1. **结构化输出**：LLM 输出必须是合法 JSON，建议使用 `structured_output` / `with_structured_output`
2. **领域知识**：建议准备目的地的景点数据库或知识库，确保推荐内容真实可用
3. **时间合理性**：行程项的时间安排应符合逻辑（如博物馆上午9点开门、午餐12点左右）
4. **价格准确性**：预算应基于实际市场价格估算，可在知识库中维护价格数据
5. **贴士实用性**：每个景点应附带实用的游览贴士（预约方式、注意事项等）

---

## 四、示例 Prompt（供参考）

```
你是一个专业的旅行规划师。请根据以下用户需求，生成一份详细的旅行计划。

用户需求：
- 目的地：{destination}
- 日期：{startDate} 至 {endDate}（共{days}天{nights}晚）
- 人数：{people}人
- 出行方式：{transport}
- 旅行风格：{style}
- 兴趣偏好：{interests}
- 预算档位：{budget}
- 住宿偏好：{accommodation}
- 特殊需求：{specialNeeds}

请生成包含以下内容的 JSON：
1. 每日行程（按时段分：上午/中午/下午/晚上）
2. 每个景点的时间、地址、描述、游览贴士、预估费用
3. 预算构成（住宿/餐饮/交通/门票 4 项）
4. 推荐书单（与目的地相关的书籍）
5. 节省预算建议

输出格式严格按照 Trip 数据结构。
```
