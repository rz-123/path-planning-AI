"""
============================================================================
LangGraph 工作流 — AI 行程生成（5个 Agent 节点）
============================================================================
工作流拓扑（有向图）：
                        ┌──────────────┐
                        │   research    │  调研景点/餐厅/天气（入口节点）
                        │  (LLM调用)    │
                        └──────┬───────┘
                               │
                               ▼
                        ┌──────────────┐
                        │    plan       │  规划每日路线（时间+酒店安排）
                        │  (LLM调用)    │
                        └──────┬───────┘
                               │
                               ▼
                        ┌──────────────┐
                        │   budget      │  计算费用明细（住宿+餐饮+交通+门票）
                        │  (LLM调用)    │
                        └──────┬───────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  reflection   │  代码检查 + 规则化语义检查（10分扣分制）
                        │  (纯代码)     │──── ≥5分 通过 ────► format
                        └──────┬───────┘
                               │ < 5分 + 有严重问题 → 回到对应Agent修正
                               ▼ (最多修正1次)
                        ┌──────────────┐
                        │   format      │  合成最终JSON + 修正坐标为真实GPS
                        │  (代码合成)   │
                        └──────────────┘

LangGraph 核心概念说明：
  - StateGraph: 有状态的工作流图，节点间通过共享状态通信
  - TypedDict State: 类型安全的状态字典（TypeScript 风格的类型定义）
  - 条件路由: reflection 节点根据评分决定下一步（修正或合成）
  - 编译(compile): 将图定义编译为可执行的 Runnable

面试考点：LangGraph vs 传统 LangChain Chain 的区别？
  - Chain 是线性的（A→B→C），无法实现条件分支和循环
  - LangGraph 是有向图（DAG），支持条件路由、循环、并行
  - LangGraph 有状态管理（State），节点间通过共享状态通信
  - 适合复杂 Agent 编排（多步骤、条件判断、自我修正）
============================================================================
"""
# ===== 标准库导入 =====
import json                                     # JSON 序列化
import re                                       # 正则表达式（用于提取 JSON）
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===== 类型注解导入 =====
from typing import TypedDict, Literal           # TypedDict=类型化字典, Literal=字面量类型
from langgraph.graph import StateGraph, END     # StateGraph=状态图, END=终止节点

# ===== LangChain 消息系统 =====
from langchain_core.messages import HumanMessage, SystemMessage
# HumanMessage: 用户消息（通常包含具体指令和内容）
# SystemMessage: 系统消息（设定 AI 的角色、规则和输出格式）

# ===== 项目内部模块导入 =====
from config import get_llm, get_llm_structured, settings  # LLM 工厂 + 配置
from agents.tools import get_weather, geocode             # 天气 + 地理编码工具


# ========================================================================
# 第1部分：TripState — 工作流共享状态定义
# ========================================================================
class TripState(TypedDict):
    """
    工作流共享状态（所有 Agent 节点通过它通信）
    
    设计模式：状态机模式（State Machine Pattern）
    - 每个节点读取 State 中自己需要的字段
    - 处理完成后写回 State 中自己产出的字段
    - 下一个节点读取上一个节点写回的字段
    
    TypedDict 说明：
    - Python 3.8+ 的类型化字典（类似 TypeScript 的 interface）
    - 提供类型提示但不改变运行时行为（运行时就是普通 dict）
    - 与总类型注解（total=False 表示所有字段可选）
    
    面试考点：为什么用 TypedDict 而不是 Pydantic BaseModel？
    - LangGraph 的 StateGraph 原生支持 TypedDict
    - TypedDict 是无运行时开销的纯类型注解
    - BaseModel 有验证开销，在 Agent 内部不需要
    """
    
    # ===== 输入字段（由 SupervisorAgent 设置） =====
    destination: str                             # 目的地城市（必填）
    origin: str | None                           # 出发城市（可选）
    start_date: str                              # 开始日期（YYYY-MM-DD）
    end_date: str                                # 结束日期（YYYY-MM-DD）
    days: int                                    # 总天数（含首尾）
    nights: int                                  # 住宿晚数
    people: int                                  # 出行总人数
    adults: int                                  # 成人数量
    children: int                                # 儿童数量
    transport: str                               # 出行方式（plane/train/car）
    style: str                                   # 旅行风格代码（leisure/deep/artistic/intensive）
    style_label: str                             # 旅行风格中文标签
    interests: list[str]                         # 兴趣标签列表
    budget: str                                  # 预算档位代码（economy/comfort/quality）
    budget_range: str                            # 预算范围（如 ¥1k-1.5k）
    accommodation: str                           # 住宿偏好（budget/comfort/premium）
    special_needs: str                           # 特殊需求文本
    
    # ===== Agent 产出字段 =====
    research_result: str                         # 调研 Agent 产出的 JSON 字符串
    plan_result: str                             # 规划 Agent 产出的 JSON 字符串
    budget_result: str                           # 预算 Agent 产出的 JSON 字符串
    reflection: str                              # 反思 Agent 的评分结果
    weather_data: str                            # 天气数据 JSON 字符串
    
    # ===== 最终输出 =====
    final_json: str                              # 合成后的完整 TripResult JSON
    
    # ===== 控制字段 =====
    trip_id: str                                 # 当前任务 ID（用于取消检查）
    revision_count: int                          # 修正次数计数（防止死循环）
    next_action: str                             # 下一步动作（由 reflection 设置）


# ========================================================================
# 第2部分：Prompt 模板
# ========================================================================

# 预算计算 Prompt（SystemMessage 方式注入）
# 使用 Python format() 方法填入动态参数
BUDGET_PROMPT = """你是一个旅行费用精算师。

## 用户参数
- 天数: {days}天，{nights}晚 | 人数: {people}人（成人{adults}，儿童{children}）
- 预算档位: {budget} ({budget_range} 单人单日) | 住宿偏好: {accommodation} | 出行: {transport}

## 预算档位参考
- economy: 经济型连锁酒店(150-300元/晚) 人均正餐40-60元
- comfort: 三星舒适型(300-500元/晚) 人均正餐60-100元
- quality: 四星高档型(500-800元/晚) 人均正餐100-150元

## 规划行程
{plan_result}

## 计算规则
1. 住宿 = 每晚价格 × nights | 周五六晚价格上浮20-50%（预算里注明）
2. 餐饮 = 人均 × 天数 × 人数 × 2顿正餐 + 15%小吃零食
3. 本地交通 = 日均50 × 天数 × 人数（一线城市80元）
4. 门票 = 汇总所有景点cost（儿童半价）
5. 四个分类percent之和必须=100
6. 往返大交通标注"未计算"

## 输出
只输出JSON，不要任何额外文字或markdown代码块
{{
  "budgetDetail": {{
    "accommodation": {{
      "total": 0, "icon": "🏨",
      "items": [{{"name": "酒店", "type": "房×{nights}晚", "amount": 0, "perNight": 0}}],
      "tips": "含周末上浮说明"
    }},
    "food": {{
      "total": 0, "icon": "🍜",
      "items": [{{"name": "正餐", "amount": 0}}, {{"name": "小吃", "amount": 0}}]
    }},
    "transport": {{
      "total": 0, "icon": "🚌",
      "items": [{{"name": "当地交通", "amount": 0}}, {{"name": "往返大交通", "amount": 0, "note": "未计算"}}]
    }},
    "tickets": {{
      "total": 0, "icon": "🎫",
      "items": [{{"name": "景点", "type": "人数×单价", "amount": 0}}],
      "discountNote": "儿童半价说明"
    }}
  }},
  "budgetPieData": [
    {{"name": "住宿", "value": 0, "color": "#3B82F6", "percent": 0}},
    {{"name": "餐饮", "value": 0, "color": "#22C55E", "percent": 0}},
    {{"name": "交通", "value": 0, "color": "#F59E0B", "percent": 0}},
    {{"name": "门票", "value": 0, "color": "#EF4444", "percent": 0}}
  ],
  "totalBudget": 0,
  "budgetPerPerson": 0,
  "withinBudget": true
}}
"""

# 最终合成 Prompt
FORMAT_PROMPT = """你是一个 JSON 格式化器。请将以下 Agent 输出合成为最终的 TripResult JSON。

## 输入
- 规划结果: {plan_result}
- 预算结果: {budget_result}

## 参数
- id: {trip_id}
- title: {title}
- origin: {origin}
- destination: {destination}
- startDate: {start_date}
- endDate: {end_date}
- days: {days}
- nights: {nights}
- people: {people}
- adults: {adults}
- children: {children}
- transport: {transport}
- style: {style}
- interests: {interests}
- budgetLevel: {budget}
- createdAt: {created_at}

## 输出
只输出JSON，不要任何额外文字或markdown代码块，包含所有字段
{{
  "id": "...",
  "title": "...",
  "origin": null,
  "destination": "...",
  "startDate": "...",
  "endDate": "...",
  "days": {days},
  "nights": {nights},
  "people": {people},
  "adults": {adults},
  "children": {children},
  "transport": "{transport}",
  "style": "{style}",
  "interests": "{interests}",
  "budgetLevel": "{budget}",
  "createdAt": "{created_at}",
  "budgetDetail": {{...}},
  "budgetPieData": [...],
  "dailyPlan": [...]
}}"""


# ========================================================================
# 第3部分：辅助工具函数
# ========================================================================

from agents.utils import CancelledError, update_progress, check_cancelled


def _extract_json(text: str) -> dict:
    """
    从 LLM 输出中提取 JSON（容错解析）
    
    LLM 输出往往不是纯 JSON，可能包含：
    - ```json ... ``` Markdown 代码块
    - 前置/后置的解释性文字
    - 特殊字符或格式错误
    
    容错策略：
    1. 去掉 Markdown 代码块标记（```json 和 ```）
    2. 找到第一个 { 到最后一个 } 之间的内容
    3. 用 json.loads() 解析
    
    面试考点：为什么 LLM 输出需要容错解析？
    - LLM 是概率模型，输出格式不保证严格符合要求
    - 即使 Prompt 中强调 "只输出 JSON"，LLM 也可能加解释文字
    - 容错解析是工程化的必要手段（防御性编程）
    """
    # 去掉 Markdown 代码块标记
    text = re.sub(r'```json?\s*', '', text)      # 去掉 ```json 或 ```json 标记
    text = re.sub(r'```\s*', '', text)           # 去掉结束的 ``` 标记
    
    # 截取从第一个 { 到最后一个 } 的内容（排除前后多余文字）
    start = text.find('{')
    end = text.rfind('}') + 1                    # +1 包含 }
    if start >= 0 and end > start:
        text = text[start:end]                   # 截取 JSON 部分
    
    try:
        return json.loads(text)                  # 尝试标准 JSON 解析
    except json.JSONDecodeError:
        # 解析失败返回错误信息（不抛异常，让 Agent 继续执行）
        return {"error": "JSON解析失败", "raw": text[:500]}


def _summarize_plan(plan_result: str) -> str:
    """将 plan_result 的完整 JSON 摘要为简短数据，减少 prompt token。"""
    data = _extract_json(plan_result)
    daily = data.get("dailyPlan", [])
    parts = [f"共{len(daily)}天"]
    for d in daily:
        day_num = d.get("day", "?")
        periods = d.get("periods", [])
        items = sum(len(p.get("items", [])) for p in periods)
        summary = d.get("summary", "")
        parts.append(f"Day{day_num}: {summary} ({items}个行程点)")
    if daily:
        parts.append(f"酒店: {daily[0].get('hotel', {}).get('name', '未指定')}")
    return " | ".join(parts)


# ========================================================================
# 第4部分：Agent 节点函数
# ========================================================================

def research_node(state: TripState) -> TripState:
    """
    调研 Agent：搜索目的地景点、餐厅、酒店、天气
    
    执行顺序：
    1. 检查取消信号
    2. 更新前端进度（20%）
    3. 调用飞猪获取真实景点数据（可选）
    4. 深度优先：飞猪有数据 → LLM 基于真实数据输出
    5. 调用高德获取天气信息
    6. LLM 综合所有信息输出结构化 JSON
    
    面试考点：Agent 为什么要"增强检索"（RAG增强）？
    - LLM 的知识截止日期固定（训练数据有滞后性）
    - 外部工具提供实时数据（门票价格、天气、营业状态）
    - 飞猪数据补充真实价格（LLM 的价格估算可能不准确）
    - 这就是 RAG（Retrieval-Augmented Generation）的简化版实现
    """
    check_cancelled(state["trip_id"])
    update_progress(state["trip_id"], "检索目的地景点和餐厅", 20)
    
    print(f"[Research] 搜索 {state['destination']} 景点/餐厅...")
    llm = get_llm()                              # 获取 LLM 实例

    # === 获取飞猪真实数据（增强检索） ===
    flyai_data = ""
    try:
        from agents.tools import flyai_search
        # 搜索目的地相关景点
        for kw in [f"{state['destination']}必去景点", f"{state['destination']}热门景点门票"]:
            r = flyai_search.invoke({"query": kw, "category": "poi", "destination": state["destination"]})
            if r and "不可用" not in str(r) and "未配置" not in str(r):
                flyai_data += f"[飞猪] {r[:1500]}\n"  # 截取前1500字
    except Exception as e:
        print(f"  [Research] 飞猪调用跳过: {e}")  # 飞猪不可用时忽略，LLM 用知识库兜底

    # 仅在查到真实数据时才加入飞猪段落，避免空标题误导 LLM
    flyai_section = f"\n=== 飞猪真实数据 ===\n{flyai_data}\n" if flyai_data else ""

    # === 构建 LLM Prompt ===
    # 将搜索到的数据 + 用户偏好 + 规则要求组合成 Prompt
    prompt = (
        f"你是 {state['destination']} 旅行专家。为用户推荐景点和餐厅:\n"
        f"风格:{state['style_label']} 兴趣:{','.join(state['interests'])}\n"
        f"天数:{state['days']}天 预算:{state['budget_range']}/人/天 特殊需求:{state.get('special_needs','')}\n"
        f"{flyai_section}"
        f"筛选标准:\n"
        f"- 评分≥4.0优先，地理分散覆盖城市不同区域\n"
        f"- 类别多样:历史人文+自然风光+现代地标+特色街区至少各1个\n"
        f"- 参考飞猪数据给出真实门票价格\n"
        f"- visit_duration分钟为单位合理估计\n"
        f"- tips包含:是否需预约/是否有闭馆日/旺季排队时长\n"
        f"- 景点≥{state['days']*3+2}个，餐厅≥{state['days']+1}个\n"
        f"只输出JSON，不要任何额外文字或markdown代码块:\n"
        f'{{"attractions":[{{"name":"","address":"","ticketPrice":0,"estimatedDuration":90,"bestTimeSlot":"上午",'
        f'"area":"区域","category":"类别","tags":[],"description":"20字亮点","tips":"周一闭馆/需预约","closedDays":"周一"}}],'
        f'"restaurants":[{{"name":"","address":"","avgPrice":0,"tags":[],"recommendDishes":[],"bestTimeSlot":"中午"}}],'
        f'"hotels":[{{"name":"","address":"","area":"区域","pricePerNight":0,"rating":"4.5","type":"舒适型","tags":["近地铁"],"tips":"提前预订"}}],'
        f'"notes":"季节提醒/人流量说明"}}'
    )

    # === 并行执行：LLM 调用 + 天气获取 ===
    with ThreadPoolExecutor(max_workers=3) as pool:
        llm_future = pool.submit(lambda: llm.invoke([HumanMessage(content=prompt)]))
        weather_future = pool.submit(
            get_weather, state["destination"], state["days"], state["start_date"]
        )

        # 等 LLM 结果（瓶颈）
        response = llm_future.result()
        raw = response.content

        # 并行拿到天气结果（LLM 更快时几乎不花时间）
        try:
            weather = weather_future.result()
            state["weather_data"] = json.dumps(weather, ensure_ascii=False)
            live = weather.get("live", {})
            print(f"  [Research] 天气: {live.get('weather','?')} {live.get('temperature','?')} | 预报{len(weather.get('forecast',[]))}天")
        except Exception as e:
            state["weather_data"] = "{}"
            print(f"  [Research] 天气获取失败: {e}")

    # === 解析 + 日志 ===
    data = _extract_json(raw)                    # 容错 JSON 解析
    attrs = data.get("attractions", [])          # 景点列表
    rests = data.get("restaurants", [])          # 餐厅列表

    # === 结果处理 ===
    print(f"  [Research] === 完成 === 景点 {len(attrs)} 个 + 餐厅 {len(rests)} 个")

    if not attrs and not rests:
        print(f"  [Research] WARN: JSON解析失败，原始输出: {raw[:300]}")
        fallback = llm.invoke([HumanMessage(content=(
            f"列出 {state['destination']} 的 {state['days']*3+2} 个著名景点和 {state['days']+1} 个推荐餐厅，"
            f"输出纯JSON: {{\"attractions\":[...],\"restaurants\":[...]}}"
        ))])
        state["research_result"] = fallback.content
    else:
        state["research_result"] = response.content

    return state


def plan_node(state: TripState) -> TripState:
    """
    规划 Agent：设计每日路线 + 酒店安排
    
    前置条件：需要 research_result（景点和餐厅列表）
    
    核心逻辑：
    - 根据天数生成每天 4 个时段（上午/中午/下午/晚上）
    - 同行政区划的景点安排在同一天
    - 晚上最后一个点尽量靠近酒店
    - 考虑天气因素（雨天安排室内活动）
    """
    check_cancelled(state["trip_id"])
    update_progress(state["trip_id"], "规划每日路线和时间", 50)
    print(f"[Plan] 设计 {state['days']} 天路线...")
    llm = get_llm()

    # 从 research 结果中提取关键信息
    research = _extract_json(state.get("research_result", "{}"))
    names = [a.get("name","") for a in research.get("attractions",[])[:10]]    # 前10个景点名
    rests = [r.get("name","") for r in research.get("restaurants",[])[:6]]     # 前6个餐厅名
    hotels = [h.get("name","") for h in research.get("hotels",[])[:3]]         # 前3个酒店名
    weather_info = state.get("weather_data","{}")                              # 天气信息

    prompt = (
        f"⚠️必须生成{state['days']}天完整行程，每天至少上午/中午/下午/晚上4个时段，缺一天算失败\n"
        f"{state['destination']} {state['days']}天 {state['people']}人 风格:{state['style_label']}\n"
        f"日期:{state['start_date']}~{state['end_date']} 兴趣:{','.join(state['interests'])}\n"
        f"景点:{', '.join(names[:8])} 餐厅:{', '.join(rests[:5])} 酒店:{', '.join(hotels[:2])}\n"
        f"天气:{weather_info[:150]}\n"             # 截取前150字（天气信息可能很长）
        f"规则:同区同天|上午1核心|中午餐厅|下午1-2|晚上近酒店\n"
        f"时段:上午☀️#F59E0B 中午🍜#F97316 下午🏛️#3B82F6 晚上🌃#8B5CF6\n"
        f"⚠️address必须填完整地址（区+街道+门牌号），如'东城区景山前街4号'，不能只填区名\n"
        f"只输出JSON，不要任何额外文字或markdown代码块\n"
        f'{{"dailyPlan":[\n'
        f'  {{"day":1,"date":"","summary":"","hotel":{{"name":"","pricePerNight":0}},\n'
        f'  "periods":[{{"timeSlot":"上午","icon":"☀️","color":"#F59E0B","bgColor":"#FEF3C7",\n'
        f'  "items":[{{"time":"","name":"","address":"","description":"","tips":"","cost":0,"latitude":0,"longitude":0}}]\n'
        f'  }}]}}\n'
        f']}}'
    )

    response = llm.invoke([HumanMessage(content=prompt)])
    state["plan_result"] = response.content
    
    # 打印生成结果摘要
    data = _extract_json(response.content)
    daily = data.get("dailyPlan", [])
    print(f"  [Plan]  === 完成 === {len(daily)} 天路线")
    for d in daily:
        periods = d.get("periods", [])
        day_items = sum(len(p.get("items", [])) for p in periods)
        print(f"    Day{d.get('day', '?')}: {d.get('summary', '')} ({day_items}个行程点)")
    return state


def budget_node(state: TripState) -> TripState:
    """
    预算 Agent：计算全部费用
    
    前置条件：需要 plan_result（规划的路线）
    
    计算维度：住宿 + 餐饮 + 当地交通 + 门票
    特殊规则：
    - 周末酒店价格上浮 20-50%
    - 儿童门票半价
    - 往返大交通标注为"未计算"（用户自己订票）
    """
    check_cancelled(state["trip_id"])
    update_progress(state["trip_id"], "计算预算和费用明细", 70)
    print(f"[Budget] 计算开销...")
    llm = get_llm()
    plan = state.get("plan_result") or json.dumps({"dailyPlan": []}, ensure_ascii=False)

    # === 用飞猪查酒店真实价格 ===
    flyai_data = ""
    try:
        from agents.tools import flyai_search
        dest = state["destination"]
        acc = state.get("accommodation", "舒适")
        r = flyai_search.invoke({"query": f"{dest}{acc}型酒店", "category": "hotel", "destination": dest})
        if r and "不可用" not in str(r) and "未配置" not in str(r):
            flyai_data += f"[飞猪酒店] {r[:1200]}\n"
    except Exception as e:
        print(f"  [Budget] 飞猪跳过: {e}")

    # 使用 BUDGET_PROMPT 模板（.format() 填入动态参数）
    # plan_result 用 _summarize_plan 压缩为摘要，减少 prompt token
    prompt = BUDGET_PROMPT.format(
        days=state["days"], nights=state["nights"], people=state["people"],
        adults=state["adults"], children=state["children"],
        budget=state["budget"], budget_range=state["budget_range"],
        accommodation=state["accommodation"], transport=state["transport"],
        plan_result=_summarize_plan(state.get("plan_result", "{}")),
    ) + f"\n\n=== 飞猪真实价格参考 ===\n{flyai_data}"
    
    # SystemMessage：将 Prompt 作为系统设定（比 HumanMessage 更权威）
    response = llm.invoke([SystemMessage(content=prompt)])
    state["budget_result"] = response.content
    
    # 打印预算摘要
    data = _extract_json(response.content)
    print(f"  [Budget]  === 完成 === 总额 ¥{data.get('totalBudget',0)} | 人均 ¥{data.get('budgetPerPerson',0)}")
    return state


def reflection_node(state: TripState) -> TripState:
    """
    反思 Agent：代码检查 + 规则化语义检查（满分10分，无 LLM 调用）

    这是工作流的质量控制关卡：
    1. 代码客观检查（10分扣分制）：检查天数/时段/景点数量/预算完整性
    2. 规则化语义检查（毫秒级）：雨天室内安排、区域多样性、预算占比
    3. 评分决策：
       - ≥5分 → 通过，进入 format
       - <5分 + 有严重问题 → 回到对应 Agent 修正（最多1次）
       - 否则 → 勉强通过

    面试考点：为什么用"代码+规则"而不是 LLM 做反思？
    - 代码检查：精确、可复现、毫秒级，覆盖已知结构规则
    - 规则检查：雨天/区域/预算三条规则覆盖 90% 的典型质量问题，稳定可靠
    - 不用 LLM：节省 10~30s 且结果可复现，避免 LLM 评分不稳定的问题
    """
    check_cancelled(state["trip_id"])
    update_progress(state["trip_id"], "优化行程，确保体验最佳", 85)
    print(f"[Reflection] 校验中...")
    state["revision_count"] = state.get("revision_count", 0)

    # ===== 第1步：代码客观检查 =====
    code_score = 10                              # 起始满分
    code_issues = []                             # 问题列表

    # 检查0：调研结果是否为空（需重新搜索）
    if not state.get("research_result", "").strip():
        code_score -= 5
        code_issues.append(
            {"severity": "critical", "description": "调研结果为空，需重新搜索", "target_agent": "research"})
    plan = _extract_json(state.get("plan_result", "{}"))
    daily = plan.get("dailyPlan", [])            # 每日行程
    budget = _extract_json(state.get("budget_result", "{}"))
    detail = budget.get("budgetDetail", {})      # 预算明细

    # 检查1：是否有行程
    if not daily:
        code_score -= 5                          # 严重：没有行程
        code_issues.append({"severity":"critical","description":"未生成任何行程","target_agent":"plan"})
    else:
        # 检查2：每天是否有内容
        empty_days = 0
        for d in daily:
            periods = d.get("periods", [])
            items_count = sum(len(p.get("items",[])) for p in periods)
            if not periods or items_count == 0:
                empty_days += 1
                code_score -= 2                  # 严重：某天完全空白
                code_issues.append({"severity":"critical","description":f"Day{d.get('day','?')}完全无内容","target_agent":"plan"})
            elif len(periods) < 2:
                code_score -= 1                  # 警告：时段不足
                code_issues.append({"severity":"warning","description":f"Day{d.get('day','?')}时段不足","target_agent":"plan"})
        
        # 检查3：景点数量是否合理
        total_spots = sum(len(p.get("items",[])) for d in daily for p in d.get("periods",[]))
        if total_spots < state["days"] * 2:
            code_score -= 2
            code_issues.append({"severity":"warning","description":f"景点仅{total_spots}个偏少","target_agent":"plan"})

    # 检查4：预算是否计算
    if detail:
        if detail.get("accommodation",{}).get("total",0) == 0:
            code_score -= 1
            code_issues.append({"severity":"warning","description":"住宿费未计算","target_agent":"budget"})
        pie = budget.get("budgetPieData",[])
        if pie and sum(p.get("percent",0) for p in pie) != 100:
            code_score -= 1
            code_issues.append({"severity":"warning","description":"预算占比≠100","target_agent":"budget"})
    else:
        code_score -= 3
        code_issues.append({"severity":"critical","description":"未计算预算","target_agent":"budget"})
    
    code_score = max(code_score, 0)              # 最低0分

    # ===== 第2步：规则化语义检查（替代原 LLM 调用，节省 10~30s） =====
    llm_adjust = 0
    highlights = []
    try:
        # 检查雨天是否有室内安排
        weather = _extract_json(state.get("weather_data", "{}"))
        forecast = weather.get("forecast", [])
        for day_idx, f in enumerate(forecast):
            if "雨" in f.get("dayWeather", "") and day_idx < len(daily):
                periods = daily[day_idx].get("periods", [])
                has_indoor = any(
                    "室内" in (item.get("category", "") or "")
                    for p in periods for item in p.get("items", [])
                )
                if not has_indoor:
                    code_score -= 1
                    code_issues.append({"severity":"warning","description":f"Day{day_idx+1}有雨但无室内安排","target_agent":"plan"})

        # 检查同区景点是否安排在同一天
        for d in daily:
            areas = set()
            for p in d.get("periods", []):
                for item in p.get("items", []):
                    area = item.get("area", "")
                    if area:
                        areas.add(area)
            if len(areas) > 4:
                highlights.append(f"Day{d.get('day')}覆盖{len(areas)}个区域，路线合理")

        # 预算占比检查
        budget = _extract_json(state.get("budget_result", "{}"))
        pie = budget.get("budgetPieData", [])
        if pie:
            total_pct = sum(p.get("percent", 0) for p in pie)
            if abs(total_pct - 100) < 1:
                highlights.append("预算计算完整")
    except Exception as e:
        print(f"  [Reflection] 规则检查异常: {e}")

    # ===== 第3步：评分决策 =====
    score = min(max(code_score + llm_adjust, 0), 10)  # 最终分数 = 代码分 + 规则调整（0~10）
    issues = code_issues

    print(f"  [Reflection] === 评分 {score}/10 (代码检查{code_score}分) | 问题{len(issues)} | 亮点{len(highlights)} ===")
    
    if score == 0:
        state["next_action"] = "format"          # 0分也进入合成（不阻塞）
    elif score >= 5:
        state["next_action"] = "format"          # ≥5分通过
    elif any(i.get("severity")=="critical" for i in issues) and state["revision_count"] < 1:
        # <5分 + 有严重问题 + 还没修正过 → 回去修正
        target = issues[0].get("target_agent","plan")  # 确定要回到哪个 Agent
        if target not in ("research","plan","budget"):
            target = "plan"
        state["revision_count"] += 1             # 增加修正计数
        state["next_action"] = target            # 设置路由目标
        print(f"  [Reflection] -> {score}分不通过，回到{target}")
    else:
        state["next_action"] = "format"          # 已经修正过或没有严重问题 → 进入合成
    
    return state


def format_node(state: TripState) -> TripState:
    """
    合成 Agent：将各 Agent 结果合成最终 JSON + 修正坐标
    
    两个路径：
    1. 有解析错误 → LLM 合成（用 FORMAT_PROMPT 模板）
    2. 解析正常 → 代码直接拼接（更快、更稳定）
    
    坐标修正（_fix_coordinates）：
    - LLM 生成的坐标通常是编造的（幻觉）
    - 用高德地理编码将景点名称转为真实 GPS 坐标
    - 这是工程上对抗 LLM 幻觉的典型案例
    """
    check_cancelled(state["trip_id"])
    update_progress(state["trip_id"], "优化行程，确保体验最佳", 95)
    print(f"[Format] 合成最终结果...")
    from datetime import datetime, timezone
    import uuid

    trip_id = state["trip_id"]                   # 使用 state 中的 trip ID
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # UTC 时间

    plan = _extract_json(state.get("plan_result", "{}"))
    budget = _extract_json(state.get("budget_result", "{}"))

    # === 路径1：LLM 合成（有解析错误时） ===
    if "error" in plan or "error" in budget:
        llm = get_llm_structured()               # 用低温度的 LLM 提高输出质量
        prompt = FORMAT_PROMPT.format(
            plan_result=state.get("plan_result",""),
            budget_result=state.get("budget_result",""),
            trip_id=trip_id,
            title=f"{state['destination']}{state['days']}日{state['style_label']}",
            origin=state.get("origin") or "",
            destination=state["destination"],
            start_date=state["start_date"], end_date=state["end_date"],
            days=state["days"], nights=state["nights"],
            people=state["people"], adults=state["adults"], children=state["children"],
            transport=state["transport"], style=state["style"],
            interests=json.dumps(state["interests"], ensure_ascii=False),
            budget=state["budget"], created_at=now,
        )
        response = llm.invoke([SystemMessage(content=prompt)])
        final = _extract_json(response.content)
    else:
        # === 路径2：代码直接拼接（高效稳定） ===
        final = {
            "id": trip_id,
            "title": f"{state['destination']}{state['days']}日{state['style_label']}",
            "origin": state.get("origin"),
            "destination": state["destination"],
            "startDate": state["start_date"], "endDate": state["end_date"],
            "days": state["days"], "nights": state["nights"],
            "people": state["people"], "adults": state["adults"], "children": state["children"],
            "transport": state["transport"], "style": state["style"],
            "interests": state["interests"],
            "totalBudget": budget.get("totalBudget", 0),
            "budgetPerPerson": budget.get("budgetPerPerson", 0),
            "budgetLevel": state["budget"],
            "status": "completed",
            "budgetDetail": budget.get("budgetDetail", {}),
            "budgetPieData": budget.get("budgetPieData", []),
            "dailyPlan": plan.get("dailyPlan", []),
            "weather": _extract_json(state.get("weather_data", "{}")) if state.get("weather_data") else {},
            "mapImage": None,
            "createdAt": now,
        }

    # === 坐标修正：对抗 LLM 幻觉 ===
    # LLM 生成的经纬度通常是编造的，需要用高德真实地理编码修正
    corrected = _fix_coordinates(final, state["destination"])
    final.update(corrected)

    state["final_json"] = json.dumps(final, ensure_ascii=False)
    print(f"[Format] 完成 tripId={trip_id}")
    return state


def _fix_coordinates(final: dict, city: str) -> dict:
    """
    用高德 MCP 地理编码修正 LLM 生成的虚假坐标（并行版本）

    将串行 geocode 调用改为 ThreadPoolExecutor 并行执行，
    max_workers=5 时，50 个项目的墙钟时间从 15s 降到 ~3s。

    这是工程上对抗 LLM 幻觉（Hallucination）的典型案例：
    - LLM 生成经纬度时经常编造一个"看起来合理"但实际不存在的坐标
    - 用高德真实地理编码将"城市+景点名"转为真实 GPS 坐标
    - 跳过非实体地点（如"酒店午休"、"返程晚餐"）

    面试考点：LLM 幻觉有几种类型？
    1. 事实性幻觉：编造不存在的景点/餐厅
    2. 数值性幻觉：门票价格/距离严重偏差
    3. 空间性幻觉：坐标、路线不合理
    4. 时间性幻觉：营业时间、闭馆日错误
    对抗策略：外部知识库（RAG）+ 结构化验证 + API 修正
    """
    skip_names = {"酒店午休", "返程晚餐（简餐）", "酒店午休 & 退房",
                  "抵达与入住", "酒店周边散步+晚餐"}
    items_to_fix = []  # [(item, name, address), ...]

    for day in final.get("dailyPlan", []):
        for period in day.get("periods", []):
            for item in period.get("items", []):
                name = item.get("name", "")
                if not name or name in skip_names:
                    continue
                addr = item.get("address", "")
                items_to_fix.append((item, name, addr))

    if not items_to_fix:
        return {"dailyPlan": final.get("dailyPlan", [])}

    items_fixed = 0

    def _do_geocode(item_name: str, item_addr: str) -> tuple:
        """单次地理编码，供线程池调用。优先用完整地址提高精度。"""
        # 有详细地址时拼接城市+完整地址（如"北京东城区景山前街4号"），精度远高于纯名称
        loc = {}
        if item_addr:
            loc = geocode(f"{city}{item_addr}")
        # 地址编码失败或返回空 → 回退到名称编码（如"北京故宫博物院"）
        if not loc:
            loc = geocode(f"{city}{item_name}")
        return item_name, loc

    with ThreadPoolExecutor(max_workers=5) as pool:
        future_map = {
            pool.submit(_do_geocode, name, addr): (item, name)
            for item, name, addr in items_to_fix
        }
        for future in as_completed(future_map):
            item, name = future_map[future]
            try:
                _name, loc = future.result()
                if loc.get("longitude") and loc.get("latitude"):
                    item["longitude"] = loc["longitude"]
                    item["latitude"] = loc["latitude"]
                    print(f"  [Format] 地理编码 {name}: {loc}")
                    items_fixed += 1
            except Exception as e:
                print(f"  [Format] 编码失败 {name}: {e}")

    print(f"[Format] 坐标修正: {items_fixed}/{len(items_to_fix)} 个成功")
    return {"dailyPlan": final.get("dailyPlan", [])}


# ========================================================================
# 第5部分：路由函数 + 图构建
# ========================================================================
def should_revise(state: TripState) -> Literal["research", "plan", "budget", "format"]:
    """
    条件路由：决定 reflection 之后去哪个节点
    
    reflection 节点设置 state["next_action"]：
    - "format" → 直接合成（评分通过）
    - "plan" → 回到规划 Agent 修正
    - "budget" → 回到预算 Agent 修正
    - "research" → 回到调研 Agent 修正
    
    Literal 类型注解：告诉类型检查器返回值只能是这4个值之一
    """
    action = state.get("next_action", "format")
    valid = {"research", "plan", "budget", "format"}
    if action not in valid:
        print(f"[Router] 无效路由 '{action}'，回退到 format")
        action = "format"
    return action


def build_trip_graph() -> StateGraph:
    """
    构建 LangGraph 工作流图
    
    图结构（有向图）：
    research ─→ plan ─→ budget ─→ reflection ──→ format ──→ END
                                    ↑    │
                                    └────┘ (条件路由：修正循环)
    
    add_node: 注册节点函数
    set_entry_point: 设置入口节点
    add_edge: 添加固定边（无条件跳转）
    add_conditional_edges: 添加条件边（根据函数返回值决定跳转）
    compile(): 编译为可执行的 Runnable
    """
    workflow = StateGraph(TripState)             # 创建状态图

    # 注册所有节点
    workflow.add_node("research", research_node)
    workflow.add_node("plan", plan_node)
    workflow.add_node("budget", budget_node)
    workflow.add_node("reflection", reflection_node)
    workflow.add_node("format", format_node)

    # 主流程：research → plan → budget → reflection
    workflow.set_entry_point("research")         # 入口
    workflow.add_edge("research", "plan")        # 调研 → 规划
    workflow.add_edge("plan", "budget")          # 规划 → 预算
    workflow.add_edge("budget", "reflection")    # 预算 → 反思

    # 条件路由：reflection → 修正 或 合成
    # should_revise 返回的值 → 目标节点（通过映射表解析）
    workflow.add_conditional_edges(
        "reflection",
        should_revise,
        {
            "research": "research",              # 回到调研
            "plan": "plan",                      # 回到规划
            "budget": "budget",                  # 回到预算
            "format": "format",                  # 进入合成
        },
    )

    workflow.add_edge("format", END)             # 合成 → 结束

    return workflow.compile()                    # 编译为可运行对象


# 全局图实例（模块加载时编译一次，后续复用）
trip_graph = build_trip_graph()
