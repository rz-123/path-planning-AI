"""
============================================================================
行程相关 Schema — Pydantic 数据模型定义
============================================================================
Schema 层级结构（自底向上）：
  FoodDish → ScheduleItem → TimelineItem → PeriodItem → DailyPlan
                                                          ↓
  BudgetItem → BudgetCategory → BudgetDetail → BudgetPieItem
                                                          ↓
                    TripResult（顶层，包含 dailyPlan + budgetDetail）
                    
输入 Schema：TripFormData（2步表单）
输出 Schema：TripResult（完整行程JSON）
进度 Schema：GenerateResponse / GenerateStatusResponse

面试考点：Pydantic Field() 的作用？
  - 设置默认值：Field(default=2)
  - 添加验证约束：ge=1（≥1）, le=10（≤10）, min_length, max_length
  - 字段别名：alias="startDate"（JSON 用驼峰，Python 用蛇形）
  - 添加文档描述：description="..."

面试考点：@field_validator（字段级验证器）vs @model_validator（模型级验证器）？
  - field_validator：验证单个字段，在字段赋值后触发
  - model_validator：验证整个模型，在所有字段赋值后触发
  - 本项目使用 field_validator 验证日期逻辑（end_date ≥ start_date）
============================================================================
"""
# ===== 标准库导入 =====
from __future__ import annotations              # 启用延迟注解求值（PEP 604: str | None 语法）
from datetime import date, datetime             # date=日期类型, datetime=日期时间类型
from enum import Enum                           # Python 枚举基类

# ===== Pydantic 导入 =====
from pydantic import BaseModel, Field, field_validator
# BaseModel: Pydantic 数据模型基类
# Field: 字段元数据配置（默认值、验证规则、别名、描述）
# field_validator: 字段级自定义验证器装饰器


# ========================================================================
# 第1层：枚举定义（限制值为预定义的几种选项）
# ========================================================================
class StyleEnum(str, Enum):
    """
    旅行风格枚举
    
    继承 str + Enum 的好处：既是枚举又是字符串，可以直接用于 JSON 序列化和字符串比较
    面试考点：str, Enum vs Enum 的区别？
    - 普通 Enum 的 json.dumps() 输出是数字或枚举名，不是实际值
    - str, Enum 的 json.dumps() 直接输出字符串值
    - FastAPI 中自动将字符串 "leisure" 转为 StyleEnum.leisure
    """
    leisure = "leisure"                          # 轻松休闲
    deep = "deep"                                # 深度打卡
    artistic = "artistic"                        # 文艺小资
    intensive = "intensive"                      # 特种兵式


class BudgetEnum(str, Enum):
    """预算档位枚举"""
    economy = "economy"                          # 经济型：人均 500-1000 元/天
    comfort = "comfort"                          # 舒适型：人均 1000-1500 元/天
    quality = "quality"                          # 品质型：人均 1500-2000 元/天


class AccommodationEnum(str, Enum):
    """住宿偏好枚举"""
    budget = "budget"                            # 经济连锁酒店
    comfort = "comfort"                          # 舒适三星级
    premium = "premium"                          # 高档四星级+


class TripStatusEnum(str, Enum):
    """行程状态枚举"""
    draft = "draft"                              # 草稿
    completed = "completed"                      # 已完成
    canceled = "canceled"                        # 已取消


# ========================================================================
# 第2层：表单输入 Schema
# ========================================================================
class TripFormData(BaseModel):
    """
    创建行程的表单数据（2步表单收集）
    
    字段别名说明：
    - alias="startDate": JSON 中是 startDate（前端驼峰命名），Python 中是 start_date（蛇形命名）
    - Pydantic 自动处理别名映射：接受 JSON 的 startDate → 存为 Python 的 start_date
    
    字段验证说明：
    - Field(default=2, ge=1, le=10): 默认值=2，范围 1~10
    - Field(..., min_length=1): ... 表示必填，min_length=1 表示至少1个字符
    - Field(default_factory=lambda: ...): 默认值通过工厂函数生成（避免可变默认值的陷阱）
    
    面试考点：default vs default_factory 的区别？为什么 list 默认值要用 default_factory？
    - default=["food"]: 所有实例共享同一个 list 对象（Python 经典陷阱）
    - default_factory=lambda: ["food"]: 每个实例创建新的 list 对象
    """
    origin: str | None = None                    # 出发城市（可选），如 "北京"
    destination: str = Field(..., min_length=1, max_length=50)  # 目的城市（必填），如 "杭州"
    start_date: date = Field(alias="startDate")  # 开始日期（必填），格式 "2025-06-01"
    end_date: date = Field(alias="endDate")      # 结束日期（必填）
    adults: int = Field(default=2, ge=1, le=10)  # 成人数量（1~10人，默认2人）
    children: int = Field(default=0, ge=0, le=5) # 儿童数量（0~5人，默认0人）
    style: StyleEnum = StyleEnum.leisure          # 旅行风格，默认轻松休闲
    interests: list[str] = Field(
        default_factory=lambda: ["food", "museum"],   # 默认兴趣：美食 + 博物馆
        description="food/museum/nature/family/shopping/red/nightlife/photo"  # 可选兴趣标签
    )
    budget: BudgetEnum = BudgetEnum.comfort       # 预算档位，默认舒适型
    accommodation: AccommodationEnum = AccommodationEnum.comfort  # 住宿偏好，默认舒适型
    special_needs: str | None = Field(default=None, max_length=500, alias="specialNeeds")  # 特殊需求，最多500字

    @field_validator("end_date")
    @classmethod                                 # classmethod: 验证器是类方法，不是实例方法
    def end_not_before_start(cls, v, info):
        """
        自定义字段验证器：结束日期 ≥ 开始日期
        
        参数说明：
        - cls: 类本身（@classmethod 的隐式参数）
        - v: 当前字段（end_date）的值
        - info: ValidationInfo 对象，包含所有已验证字段的数据
        
        info.data 可以访问之前验证过的字段值（注意：只有在该字段之前验证的字段才能访问）
        
        面试考点：为什么用 @classmethod 而不是 @staticmethod？
        - Pydantic v2 的 field_validator 要求使用 @classmethod
        - 可以访问类级别的配置
        - 在某些场景下可以被子类覆盖
        """
        if "start_date" in info.data and v < info.data["start_date"]:
            # 如果开始日期已设置且结束日期早于开始日期，抛出验证错误
            raise ValueError("结束日期不能早于开始日期")
        return v                                 # 验证通过，返回原值

    # ===== 计算属性 =====
    @property
    def days(self) -> int:
        """
        行程总天数（含首尾日）
        
        示例：6月1日 ~ 6月3日 = (3-1) + 1 = 3 天
        """
        return (self.end_date - self.start_date).days + 1

    @property
    def nights(self) -> int:
        """
        住宿晚数
        
        示例：6月1日 ~ 6月3日 = 3-1 = 2 晚
        """
        return (self.end_date - self.start_date).days

    @property
    def people(self) -> int:
        """出行总人数"""
        return self.adults + self.children


# ========================================================================
# 第3层：行程结果 Schema（嵌套结构，自底向上）
# ========================================================================

# --- 3.1 原子组件 ---
class FoodDish(BaseModel):
    """推荐菜品"""
    name: str                                    # 菜名，如 "东坡肉"
    image: str | None = None                     # 菜品图片 URL（可选）


class ScheduleItem(BaseModel):
    """时间安排项"""
    name: str                                    # 活动名
    times: str                                   # 时间范围，如 "09:00-11:30"


# --- 3.2 行程项 ---
class TimelineItem(BaseModel):
    """
    时间线上的单个行程点
    
    这是最核心的数据单元，代表一天中某个具体活动：
    如 "上午 9:00 游览西湖断桥残雪"
    
    字段设计说明：
    - tag/tagColor/tagBg: 用颜色标签区分活动类型（如 🏛️景点/🍜美食/🏨酒店）
    - dishes: 餐厅专属字段，该餐厅的推荐菜品
    - schedule: 景点专属字段，景点内的活动安排
    """
    time: str                                    # 时间点，如 "09:00"
    name: str                                    # 地点/活动名称，如 "断桥残雪"
    address: str = ""                            # 地址描述
    tag: str = ""                                # 类型标签，如 "景点"
    tagColor: str = "#3B82F6"                    # 标签文字颜色（十六进制）
    tagBg: str = "#DBEAFE"                       # 标签背景颜色
    description: str = ""                        # 简短描述（20字左右）
    image: str | None = None                     # 配图 URL（可选）
    tips: str = ""                               # 实用提示，如 "需提前预约"
    cost: float = 0.0                            # 预估费用（元）
    latitude: float | None = None                # 纬度（GCJ-02坐标系，_fix_coordinates填充）
    longitude: float | None = None               # 经度（GCJ-02坐标系，_fix_coordinates填充）
    dishes: list[FoodDish] | None = None         # 推荐菜品列表（仅餐厅有值）
    schedule: list[ScheduleItem] | None = None   # 子活动列表（仅景点有值）


# --- 3.3 时段 ---
class PeriodItem(BaseModel):
    """
    一天中的某个时段（上午/中午/下午/晚上）
    
    设计思路：
    - 将一天分为4个时段，每个时段独立展示
    - 每个时段有对应的 icon（表情符号）和颜色主题
    - 这与前端 result 页面的卡片式展示相对应
    """
    timeSlot: str                                # 时段名：上午/中午/下午/晚上
    icon: str                                    # 时段图标，如 "☀️"
    color: str                                   # 主色调，如 "#F59E0B"（琥珀色）
    bgColor: str                                 # 背景色，如 "#FEF3C7"（浅琥珀色）
    items: list[TimelineItem]                    # 该时段的活动列表


# --- 3.4 每日计划 ---
class DailyPlan(BaseModel):
    """
    单天完整行程
    
    一天的行程结构：
    - 上午（☀️）：1个核心景点
    - 中午（🍜）：1个推荐餐厅
    - 下午（🏛️）：1~2个次要景点
    - 晚上（🌃）：1个夜景/餐厅/购物（尽量靠近酒店）
    """
    day: int                                     # 第几天（从1开始）
    date: str                                    # 日期字符串，如 "2025-06-01"
    summary: str = ""                            # 每日摘要（一句话概括今天行程）
    periods: list[PeriodItem]                    # 该天的所有时段（通常4个）


# --- 3.5 预算 ---
class BudgetItem(BaseModel):
    """预算明细项"""
    name: str                                    # 项目名称
    type: str = ""                               # 项目类型描述
    amount: float                                # 费用金额（元）
    perNight: float | None = None                # 每晚价格（住宿专用）
    note: str | None = None                      # 备注说明


class BudgetCategory(BaseModel):
    """预算大类（住宿/餐饮/交通/门票）"""
    total: float                                 # 该分类总额
    icon: str                                    # 分类图标
    items: list[BudgetItem]                      # 明细列表
    tips: str = ""                               # 省钱提示


class BudgetDetail(BaseModel):
    """预算总览"""
    accommodation: BudgetCategory                # 住宿费用明细
    food: BudgetCategory                         # 餐饮费用明细
    transport: BudgetCategory                    # 交通费用明细
    tickets: BudgetCategory                      # 门票及其他费用明细


class BudgetPieItem(BaseModel):
    """
    饼图数据项
    
    用于前端 Canvas 绘制环形饼图
    面试考点：为什么后端返回饼图数据而不是让前端自己算？
    - 避免前后端计算不一致（单一数据源原则）
    - 后端可对数据进行统一精度处理
    - 前端只需要渲染，逻辑更简单
    """
    name: str                                    # 分类名称
    value: float                                 # 分类金额
    color: str                                   # 饼图颜色（后端预设配色方案）
    percent: int                                 # 占比百分比（整数）


# ========================================================================
# 第4层：完整行程结果（顶层）
# ========================================================================
class TripResult(BaseModel):
    """
    完整行程结果 — 前端 result 页面的完整数据
    
    这个 Schema 定义了从后端返回给前端的完整数据结构。
    它既是 API 响应体，也通过 CloudBase 存储到云数据库。
    
    面试考点：前端和后端共享 Schema 的利弊？
    - 利：类型安全、前后端一致、自动生成 API 文档
    - 弊：后端 Schema 变更可能影响前端（需向后兼容）
    - 最佳实践：后端 Schema 字段只增不删，废弃字段标记 deprecated
    """
    id: str                                      # 行程唯一 ID
    userId: str | None = None                    # 用户 ID（关联到用户系统）
    title: str                                   # 标题，如 "杭州3日文艺小资"
    origin: str | None = None                    # 出发城市
    destination: str                             # 目的地城市
    startDate: str                               # 开始日期
    endDate: str                                 # 结束日期
    days: int                                    # 总天数
    nights: int                                  # 总晚数
    people: int                                  # 出行总人数
    adults: int = 0                              # 成人数量
    children: int = 0                            # 儿童数量
    transport: str                               # 出行方式
    style: str                                   # 旅行风格
    interests: list[str]                         # 兴趣标签列表
    totalBudget: float                           # 总计预算（元）
    budgetPerPerson: float                       # 人均预算（元）
    budgetLevel: str                             # 预算档位
    status: TripStatusEnum = TripStatusEnum.completed  # 行程状态
    budgetDetail: BudgetDetail                   # 预算明细（嵌套结构）
    budgetPieData: list[BudgetPieItem]           # 饼图数据
    dailyPlan: list[DailyPlan]                   # 每日行程（嵌套结构）
    mapImage: str | None = None                  # 地图截图的图片 URL（可选）
    createdAt: datetime                          # 创建时间
    updatedAt: datetime | None = None            # 最后更新时间


# ========================================================================
# 第5层：列表项 + 目的地 + 进度 + 统计
# ========================================================================
class TripSummary(BaseModel):
    """首页/我的页面的行程摘要卡片"""
    id: str                                      # 行程 ID
    title: str                                   # 标题
    destination: str                             # 目的地
    startDate: str                               # 开始日期
    endDate: str                                 # 结束日期
    days: int                                    # 总天数
    people: int                                  # 出行人数
    tags: str = ""                               # 标签（用于前端徽章展示）
    status: TripStatusEnum                       # 行程状态
    statusText: str                              # 状态文本（中文）
    budget: float                                # 总预算
    month: str | None = None                     # 出行月份（用于分组显示）
    day: str | None = None                       # 出行日期（用于卡片展示）


class DestinationItem(BaseModel):
    """目的地推荐卡片"""
    id: str                                      # 目的地 ID
    name: str                                    # 目的地名称
    tags: str                                    # 标签（用逗号分隔）
    image: str                                   # 封面图片 URL
    description: str                             # 描述文字
    basePrice: float                             # 参考价格


class GenerateResponse(BaseModel):
    """
    行程生成响应（POST /generate 的返回值）
    
    异步模式关键：tripId 是后续轮询的唯一凭证
    """
    tripId: str                                  # 任务 ID（客户端用此 ID 轮询进度）
    status: str                                  # 状态：processing | completed | failed
    message: str = ""                            # 状态描述文字


class GenerateStatusResponse(BaseModel):
    """
    进度查询响应（GET /:id/status 的返回值）
    
    前端轮询逻辑：
    - status="processing" → 继续轮询（更新 progress + currentStep）
    - status="completed"  → 停止轮询，读取 result
    - status="failed"     → 停止轮询，显示错误
    """
    tripId: str                                  # 任务 ID
    status: str                                  # 当前状态
    progress: int = 0                            # 进度百分比（0~100）
    currentStep: str = ""                        # 当前步骤描述文字
    result: dict | None = None                   # 完成后的完整结果（TripResult 的 dict 形式）


class StatsResponse(BaseModel):
    """
    用户旅行统计（用于首页统计面板）
    
    这些数据从数据库聚合计算得出
    """
    totalTrips: int                              # 总行程数
    totalDays: int                               # 总旅行天数
    favoriteDestination: str                     # 最常去的目的地
    favoriteCount: int                           # 最常去的次数
    totalBudget: float                           # 累计预算总额
    avgBudgetPerTrip: float                      # 平均每次旅行预算
