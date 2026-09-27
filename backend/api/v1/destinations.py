"""
============================================================================
目的地推荐 API — 热门目的地 + 随机推荐
============================================================================
设计说明：
  - 硬编码 20 个中国热门旅游城市的目的地数据
  - 提供 GET /hot（全部列表）和 GET /random（随机一个）两个端点
  - 数据中包含 Pydantic 验证通过的目的地 Schema

为什么硬编码而不是从数据库读取？
  1. 首页加载需要极快的响应速度（硬编码 = 零数据库查询）
  2. 热门目的地数据变化频率极低（按季度/年度更新）
  3. 减少数据库和网络 IO 的开销
  4. 这是缓存策略的一种简化实现（"冷启动兜底数据"）

面试考点：后端硬编码数据的最佳实践？
  - 适合低频变化、启动必需的数据（热门目的地、配置项、枚举值）
  - 不适合用户个性化、实时变化的数据（价格、库存、评论）
  - 硬编码数据应有明确的 Schema 类型约束（Pydantic BaseModel）
  - 大型硬编码数据应考虑拆分为 JSON 配置文件
============================================================================
"""
# ===== 标准库导入 =====
import random                                   # 随机选择（用于随机推荐功能）

# ===== FastAPI 导入 =====
from fastapi import APIRouter                   # APIRouter: 子路由注册器

# ===== 项目内部模块导入 =====
from schemas.trip import DestinationItem        # 目的地数据 Schema

# ===== 创建子路由 =====
router = APIRouter(prefix="/destinations", tags=["目的地"])
# 实际路径：/api/v1 + /destinations + /hot = /api/v1/destinations/hot

# ===== 热门目的地数据（硬编码，共 20 个城市） =====
# 设计为一个列表，每个元素是 Pydantic 验证通过的 DestinationItem 实例
# 数据结构：id(唯一标识) / name(名称) / tags(标签) / image(封面图) / description(描述) / basePrice(参考价格)
# tags 格式：用 " | " 分隔多个标签，前端用 split(" | ") 拆分为数组
# image 使用 placeholder 图片服务（dummyimage），生产环境应替换为 CDN 图片
HOT_DESTINATIONS = [
    # ---- 一线/新一线城市 ----
    DestinationItem(id="beijing", name="北京", tags="历史名城 | 文化之都",
                    image="https://dummyimage.com/600x400/0891B2/fff&text=北京",
                    description="故宫、长城、颐和园、胡同文化", basePrice=2200),
    DestinationItem(id="shanghai", name="上海", tags="魔都 | 时尚前沿",
                    image="https://dummyimage.com/600x400/E11D48/fff&text=上海",
                    description="外滩、迪士尼、南京路、新天地", basePrice=2500),
    DestinationItem(id="guangzhou", name="广州", tags="美食之都 | 千年商都",
                    image="https://dummyimage.com/600x400/22C55E/fff&text=广州",
                    description="广州塔、长隆、陈家祠、早茶", basePrice=1800),
    DestinationItem(id="shenzhen", name="深圳", tags="创新之城 | 海滨城市",
                    image="https://dummyimage.com/600x400/3B82F6/fff&text=深圳",
                    description="世界之窗、欢乐谷、大鹏所城", basePrice=2000),
    # ---- 旅游热门城市 ----
    DestinationItem(id="chengdu", name="成都", tags="美食之都 | 亲子友好",
                    image="https://dummyimage.com/600x400/F59E0B/fff&text=成都",
                    description="熊猫基地、宽窄巷子、火锅美食", basePrice=1800),
    DestinationItem(id="hangzhou", name="杭州", tags="人间天堂 | 浪漫之都",
                    image="https://dummyimage.com/600x400/8B5CF6/fff&text=杭州",
                    description="西湖、灵隐寺、西溪湿地", basePrice=2000),
    DestinationItem(id="chongqing", name="重庆", tags="8D魔幻 | 火锅之都",
                    image="https://dummyimage.com/600x400/EF4444/fff&text=重庆",
                    description="洪崖洞、解放碑、长江索道", basePrice=1600),
    DestinationItem(id="wuhan", name="武汉", tags="九省通衢 | 樱花之城",
                    image="https://dummyimage.com/600x400/14B8A6/fff&text=武汉",
                    description="黄鹤楼、东湖、户部巷", basePrice=1500),
    DestinationItem(id="xian", name="西安", tags="历史名城 | 红色基地",
                    image="https://dummyimage.com/600x400/D97706/fff&text=西安",
                    description="兵马俑、大雁塔、回民街", basePrice=2200),
    DestinationItem(id="nanjing", name="南京", tags="六朝古都 | 历史名城",
                    image="https://dummyimage.com/600x400/EC4899/fff&text=南京",
                    description="中山陵、夫子庙、明孝陵", basePrice=1700),
    DestinationItem(id="changsha", name="长沙", tags="网红城市 | 美食天堂",
                    image="https://dummyimage.com/600x400/06B6D4/fff&text=长沙",
                    description="橘子洲、岳麓山、茶颜悦色", basePrice=1500),
    DestinationItem(id="xiamen", name="厦门", tags="文艺小资 | 海岛风情",
                    image="https://dummyimage.com/600x400/10B981/fff&text=厦门",
                    description="鼓浪屿、环岛路、曾厝垵", basePrice=1900),
    # ---- 度假/特色城市 ----
    DestinationItem(id="sanya", name="三亚", tags="热带天堂 | 度假胜地",
                    image="https://dummyimage.com/600x400/0EA5E9/fff&text=三亚",
                    description="亚龙湾、蜈支洲岛、天涯海角", basePrice=3000),
    DestinationItem(id="lijiang", name="丽江", tags="古城风韵 | 慢生活",
                    image="https://dummyimage.com/600x400/A855F7/fff&text=丽江",
                    description="古城、玉龙雪山、束河古镇", basePrice=2200),
    DestinationItem(id="guilin", name="桂林", tags="山水甲天下 | 摄影圣地",
                    image="https://dummyimage.com/600x400/65A30D/fff&text=桂林",
                    description="漓江、阳朔、龙脊梯田", basePrice=1800),
    DestinationItem(id="dalian", name="大连", tags="浪漫之都 | 海滨城市",
                    image="https://dummyimage.com/600x400/0284C7/fff&text=大连",
                    description="星海广场、老虎滩、棒棰岛", basePrice=1700),
    DestinationItem(id="qingdao", name="青岛", tags="啤酒之都 | 欧式风情",
                    image="https://dummyimage.com/600x400/059669/fff&text=青岛",
                    description="栈桥、崂山、八大关", basePrice=1600),
    DestinationItem(id="suzhou", name="苏州", tags="园林之城 | 水乡古镇",
                    image="https://dummyimage.com/600x400/7C3AED/fff&text=苏州",
                    description="拙政园、周庄、虎丘", basePrice=1900),
    DestinationItem(id="kunming", name="昆明", tags="春城 | 花都",
                    image="https://dummyimage.com/600x400/DC2626/fff&text=昆明",
                    description="石林、滇池、西山", basePrice=1600),
    DestinationItem(id="dali", name="大理", tags="风花雪月 | 文艺圣地",
                    image="https://dummyimage.com/600x400/2563EB/fff&text=大理",
                    description="洱海、苍山、双廊古镇", basePrice=2000),
]


@router.get("/hot", response_model=dict)
async def get_hot():
    """
    获取全部热门目的地列表（GET /api/v1/destinations/hot）

    返回前端首页的「热门目的地」横向滚动列表

    面试考点：为什么返回 dict 包裹的 items 而非直接返回 list？
    - 直接返回 list 不是合法的 JSON 顶层结构（有安全风险，如 JSON 劫持）
    - dict 包裹可以扩展附加字段（如 total, page, pageSize）
    - 前端解构更方便：const { items } = await response.json()
    """
    # model_dump(): Pydantic v2 的序列化方法（替代 v1 的 .dict()）
    # 将每个 DestinationItem 转为普通 dict，确保 JSON 序列化兼容
    return {"items": [d.model_dump() for d in HOT_DESTINATIONS]}


@router.get("/random", response_model=dict)
async def get_random():
    """
    随机推荐一个目的地（GET /api/v1/destinations/random）

    用于首页的「随机推荐」模块，每次刷新展示不同的目的地

    实现方式：random.choice() 从 20 个热门目的地中随机选一个

    面试考点：random.choice 的随机性足够吗？
    - 对于旅游推荐场景足够了（不需要密码学级别的随机性）
    - 如果希望同一用户多次刷新看到不同推荐，可以加"上次排除"逻辑
    """
    # random.choice: 从列表中随机选取一个元素
    d = random.choice(HOT_DESTINATIONS)

    # 返回精选字段（比 /hot 接口更精简）
    return {
        "name": d.name,                           # 城市名
        "id": d.id,                               # 唯一标识
        "tags": d.tags,                           # 标签字符串
        "description": d.description,              # 描述文字
    }
