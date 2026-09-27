"""
============================================================================
LangChain Tools — 搜索 + 高德 MCP + 飞猪 + 往年天气
============================================================================
工具层设计说明：
  - 高德 MCP：统一的地理信息服务（天气、地理编码、POI搜索、驾车路线）
  - 飞猪 FlyAI：酒店/机票/景区价格查询
  - 飞猪 FlyAI：酒店/机票/景区价格查询
  - 往年天气：不足天数时用城市+季节的往年平均数据补全

MCP 协议说明（Model Context Protocol）：
  - MCP 是 Anthropic 提出的 AI-工具通信标准协议
  - 基于 JSON-RPC 2.0，支持工具发现和调用
  - 本项目通过 HTTP POST 直接调用高德 MCP 服务器
  - 协议流程：initialize → initialized notification → tools/call

面试考点：MCP vs Function Calling 的区别？
  - Function Calling：LLM 服务商的功能（如 OpenAI 的 function_call），耦合于服务商
  - MCP：独立于 LLM 的通用协议，任何 MCP 客户端可以调用任何 MCP 服务器
  - 优势：工具定义和服务解耦，可独立开发、测试、部署
============================================================================
"""
# ===== 标准库导入 =====
import hashlib
import json                                     # JSON 序列化/反序列化
import subprocess                               # 子进程调用（用于飞猪 CLI 工具）
import os                                       # 操作系统接口（环境变量）

# ===== 第三方库导入 =====
import httpx                                    # 现代 HTTP 客户端（支持 HTTP/2 + 异步）
from langchain_core.tools import tool           # LangChain @tool 装饰器
from config import settings                             # 全局配置单例


# ========================================================================
# 第1部分：高德 MCP 统一客户端
# ========================================================================

# MCP 会话缓存：key = amap_key 的 MD5，value = {"headers": {...}}
# 避免每次调用都走 3 步握手（initialize + initialized + tools/call）
_mcp_sessions: dict[str, dict] = {}


def _amap_mcp(tool_name: str, **kwargs) -> str:
    """
    高德 MCP 统一调用客户端（含自动会话初始化）
    
    这是整个工具层最核心的函数，所有高德相关的操作（天气、地理编码、搜索、路线）
    都通过这个统一入口调用高德 MCP 服务器。
    
    参数：
    - tool_name: MCP 工具名称（maps_weather / maps_geo / maps_text_search / maps_direction_driving）
    - **kwargs: 工具的调用参数（如 city="北京", address="天安门"）
    
    返回值：
    - str: MCP 返回的 JSON 字符串（如果出错则返回 {"error":"..."} 格式的 JSON）
    
    MCP 协议调用流程（3步）：
    1. initialize: 发送初始化请求，获取 session ID
    2. notifications/initialized: 发送初始化完成通知
    3. tools/call: 调用实际的工具
    
    面试考点：为什么需要 session？
    - HTTP 是无状态协议，每次请求都是独立的
    - MCP 服务端需要 session 来维持连接上下文
    - session ID 通过 HTTP 响应头的 mcp-session-id 返回
    - 后续请求在请求头中带上 Mcp-Session-Id 标识会话
    """
    # 检查高德 Key 是否配置（未配置则无法使用 MCP）
    if not settings.amap_key:
        return json.dumps({"error": "高德 Key 未配置"}, ensure_ascii=False)

    base_url = f"https://mcp.amap.com/mcp?key={settings.amap_key}"

    # 尝试从缓存获取已初始化的会话
    key_hash = hashlib.md5(settings.amap_key.encode()).hexdigest()
    cached = _mcp_sessions.get(key_hash)

    try:
        if cached:
            # === 有缓存：直接 tools/call（省掉 initialize + initialized） ===
            headers = cached["headers"]
        else:
            # === 无缓存：完整 3 步握手 ===
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
            # 第1步：initialize
            init_resp = httpx.post(
                base_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "ai-travel", "version": "1.0"}
                    },
                    "id": 0
                },
                headers=headers,
                timeout=15,
            )
            mcp_id = init_resp.headers.get(
                "mcp-session-id",
                init_resp.headers.get("Mcp-Session-Id", "")
            )
            if mcp_id:
                headers["Mcp-Session-Id"] = mcp_id
                # 第2步：initialized notification
                try:
                    httpx.post(
                        base_url,
                        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                        headers=headers,
                        timeout=5
                    )
                except:
                    pass
                # 缓存会话（只缓存成功初始化的）
                _mcp_sessions[key_hash] = {"headers": dict(headers)}

        # 第3步：调用实际工具
        resp = httpx.post(
            base_url,
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": kwargs
                },
                "id": 1
            },
            headers=headers,
            timeout=15,
        )
        data = resp.json()

        # MCP 返回格式：{"result":{"content":[{"type":"text","text":"..."}]}}
        content = data.get("result", {}).get("content", [])
        if content and isinstance(content, list):
            return "\n".join(
                c.get("text", "") for c in content if c.get("type") == "text"
            )

        if "error" in data:
            return json.dumps({"error": str(data["error"])}, ensure_ascii=False)

        return json.dumps(data, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e)[:200]}, ensure_ascii=False)


# ========================================================================
# 第2部分：LangChain @tool 装饰器
# ========================================================================
@tool
def amap(method: str, **kwargs) -> str:
    """
    高德统一工具（LangChain Tool 接口）
    
    @tool 装饰器的作用：
    - 自动生成工具的 name 和 description（从函数签名和 docstring）
    - LLM（LangChain Agent）可以自动发现和调用此工具
    - 支持流式调用和错误处理
    
    参数：
    - method: 操作类型（weather/search/route/geocode）
    - **kwargs: 具体操作的参数
    
    面试考点：@tool 装饰器做了什么？
    - 将普通 Python 函数包装为 BaseTool 的子类实例
    - 自动生成 JSON Schema（用于 LLM 的 function calling 参数描述）
    - 提供 args_schema 属性（Pydantic 模型，描述工具参数）
    - 支持 return_direct（工具调用后是否直接返回结果）
    """
    # method → MCP 工具名的映射表
    method_map = {
        "weather": "maps_weather",               # 天气查询
        "search": "maps_text_search",             # POI 文本搜索
        "route": "maps_direction_driving",        # 驾车路线规划
        "geocode": "maps_geo",                    # 地理编码（地址→经纬度）
    }
    # 如果 method 不在映射表中，直接使用传入的 method（兼容直接传 MCP 工具名）
    actual_tool = method_map.get(method, method)
    return _amap_mcp(actual_tool, **kwargs)


# ========================================================================
# 第3部分：天气查询（便捷函数）
# ========================================================================
def get_weather(city: str, days: int = 3, start_date: str = "") -> dict:
    """
    获取城市天气信息（结构化 dict 返回）
    
    智能天气策略：
    1. 调用高德天气 API 获取最近 3 天预报
    2. 如果行程超过 3 天，超出部分用往年同期平均气温补全
    3. 往年数据基于城市+月份的硬编码气候数据
    
    参数：
    - city: 城市名称（如 "北京"、"杭州"）
    - days: 需要的预报天数（= 行程天数）
    - start_date: 出发日期（用于确定季节，计算往年平均）
    
    返回结构：
    {
        "city": "北京",
        "live": {"weather":"晴", "temperature":"25°C", "wind":"南风 4级", "humidity":"45%"},
        "forecast": [
            {"date":"2025-06-01", "dayWeather":"晴", "nightTemp":"18", "dayTemp":"32", ...},
            ...
        ]
    }
    
    面试考点：外部 API 调用的容错设计？
    1. 检查空返回（if not raw）
    2. try/except JSON 解析失败
    3. 兼容多种返回格式（lives/live、forecasts/forecast、list/dict）
    4. 不足的数据用兜底策略补全（往年平均）
    5. 所有异常返回空结构而非 None（调用方不用判空）
    """
    raw = _amap_mcp("maps_weather", city=city)   # 调用高德天气 API
    if not raw:
        return {"city": city, "live": {}, "forecast": []}  # 空返回：返回空结构
    
    # JSON 解析（兼容非 JSON 返回）
    try:
        data = json.loads(raw)
    except:
        return {"city": city, "live": {}, "forecast": [], "raw": raw}
    
    # === 解析实时天气（lives 字段） ===
    # 高德 API 可能返回 lives（数组）或 live（单对象）
    lives = data.get("lives", data.get("live", {}))
    if isinstance(lives, list) and lives:
        lives = lives[0]                          # 取数组第一个元素
    if isinstance(lives, str):
        lives = {}                                # 字符串当空处理
    
    # === 解析天气预报（forecasts 字段） ===
    # 高德 API 格式: {"forecasts":[{"casts":[{"date":"2025-06-01","dayweather":"晴",...},...]}]}
    forecasts = data.get("forecasts", [])
    if isinstance(forecasts, list) and forecasts:
        # 取第一个城市（forecasts[0]）的 casts 列表
        casts = forecasts[0].get("casts", []) if isinstance(forecasts[0], dict) else []
    elif isinstance(forecasts, dict):
        casts = forecasts.get("casts", [])
    else:
        casts = forecasts if isinstance(forecasts, list) else []
    
    # === 格式化预报数据 ===
    # 将高德原始字段转为前端友好的字段名
    formatted = []
    for f in (casts or []):
        formatted.append({
            "date": str(f.get("date", "")),         # 日期
            "dayWeather": str(f.get("dayweather", "")),  # 白天天气
            "nightWeather": str(f.get("nightweather", "")),  # 夜间天气
            "dayTemp": str(f.get("daytemp", "")),       # 白天温度
            "nightTemp": str(f.get("nighttemp", "")),   # 夜间温度
            "wind": str(f.get("daywind", "")) + " " + str(f.get("daypower", "")),  # 风力
        })
    
    # === 不足天数补往年平均 ===
    need = days - len(formatted)                 # 还差几天
    if need > 0:
        # 调用 _seasonal_avg 获取往年同期平均数据
        formatted.extend(_seasonal_avg(city, len(formatted) + 1, days, start_date))
    
    # === 返回结构化结果 ===
    return {
        "city": str(lives.get("city", city)),    # 城市名
        "live": {                                # 实时天气
            "weather": str(lives.get("weather", "")),         # 天气状况
            "temperature": str(lives.get("temperature", "")) + "°C",  # 温度
            "wind": str(lives.get("winddirection", "")) + " " + str(lives.get("windpower", "")) + "级",  # 风力
            "humidity": str(lives.get("humidity", "")) + "%",  # 湿度
        },
        "forecast": formatted[:days],            # 预报数据（截取需要的天数）
    }


# ========================================================================
# 第4部分：地理编码
# ========================================================================
def geocode(address: str) -> dict:
    """
    地理编码：将地址文本转为经纬度坐标
    
    这是高德地图的核心能力之一，用于：
    1. format Agent 中修正 LLM 生成的虚假坐标
    2. 将景点名称转为真实 GPS 坐标
    3. 前端地图显示时需要准确的经纬度
    
    参数：
    - address: 地址字符串，如 "杭州市西湖区断桥残雪"
    
    返回：
    - {"longitude": 120.15, "latitude": 30.25} 成功时
    - {} 失败时（返回空字典而非 None）
    
    面试考点：地理编码的精度问题？
    - 地址越详细，结果越精确（"断桥残雪" vs "杭州市西湖区断桥残雪"）
    - 本项目在 _fix_coordinates 中拼接城市名：f"{city}{name}"
    - 返回的坐标是 GCJ-02 坐标系（国测局，中国标准），与前端高德地图坐标系一致
    - 如果用 GPS 原始坐标（WGS-84），在中国会有 300~500 米偏移
    """
    raw = _amap_mcp("maps_geo", address=address)  # 调用高德地理编码
    
    try:
        data = json.loads(raw)
        loc = ""
        
        # 兼容多种返回格式（MCP 不同版本的返回格式不同）
        # 格式1: MCP 返回 {"results":[{"location":"lng,lat"}]}
        if data.get("results"):
            loc = data["results"][0].get("location", "")
        # 格式2: 直接返回 {"geocodes":[{"location":"lng,lat"}]}
        elif data.get("geocodes"):
            loc = data["geocodes"][0].get("location", "")
        # 格式3: {"location":"lng,lat"}
        elif data.get("location"):
            loc = data["location"]
        
        # 解析 "120.15,30.25" 格式的坐标字符串
        if loc and "," in str(loc):
            lng, lat = str(loc).split(",")[:2]    # 拆分为经度和纬度
            return {"longitude": float(lng), "latitude": float(lat)}
            
    except:
        pass                                    # 解析失败返回空字典
    
    return {}                                   # 兜底：返回空字典


# ========================================================================
# 第5部分：往年平均天气
# ========================================================================
def _seasonal_avg(city: str, start: int, end: int, start_date: str = "") -> list:
    """
    根据城市和季节返回往年同期平均天气
    
    当前实现：基于硬编码的中国主要城市季节气候数据
    未来可改进：接入气象历史数据 API
    
    季节划分：
    - 12月、1月、2月 → 冬季
    - 3月、4月、5月 → 春季
    - 6月、7月、8月 → 夏季
    - 9月、10月、11月 → 秋季
    
    参数：
    - city: 城市名
    - start: 开始天数（从第几天开始补）
    - end: 结束天数
    - start_date: 出发日期（用于确定季节）
    """
    # 从日期提取月份，确定季节
    m = _get_month(start_date) if start_date else _get_month("")
    season = (
        "winter" if m in (12,1,2) else
        "spring" if m in (3,4,5) else
        "summer" if m in (6,7,8) else
        "autumn"                                  # 9~11 月 = 秋季
    )
    
    # 获取该城市的季节气候数据，不存在则用默认数据
    defaults = _city_season.get(city, _city_season["默认"])
    d = defaults.get(season, defaults.get("summer", {
        "dayWeather":"多云", "nightWeather":"晴",
        "dayTemp":"25", "nightTemp":"18"
    }))
    
    month_name = f"{m}月"                        # 中文月份名
    results = []
    for i in range(start, end + 1):
        results.append({
            "date": f"Day{i}",                    # 伪日期（如 Day4）
            "dayWeather": d.get("dayWeather", ""),
            "nightWeather": d.get("nightWeather", ""),
            "dayTemp": d.get("dayTemp", ""),
            "nightTemp": d.get("nightTemp", ""),
            "wind": d.get("wind", ""),
            "isHistorical": True,                 # 标记为往年数据（前端显示不同图标）
            "note": f"{city}{month_name}往年同期平均气温{d.get('nightTemp','?')}°C~{d.get('dayTemp','?')}°C",
        })
    return results


def _get_month(date_str: str) -> int:
    """
    从日期字符串中提取月份
    
    支持多种日期格式：
    - "2025-06-01" → 6
    - "2025.06.01" → 6
    - "" (空字符串) → 当前月份
    """
    if not date_str:
        from datetime import datetime
        return datetime.now().month              # 空日期：返回当前月份
    
    # 尝试 - 和 . 两种分隔符
    for ch in ('-', '.'):
        if ch in date_str:
            try:
                return int(date_str.split(ch)[1]) # 取中间部分 = 月份
            except:
                pass
    
    from datetime import datetime
    return datetime.now().month                  # 解析失败兜底


# 主要城市按季节的往年平均气候数据
# 数据结构：{ 城市名: { 季节: { 白天天气, 夜间天气, 白天温度, 夜间温度, 风力 } } }
_city_season = {
    "北京":{"spring":{"dayWeather":"晴","nightWeather":"晴","dayTemp":"18","nightTemp":"8"},"summer":{"dayWeather":"多云","nightWeather":"雷阵雨","dayTemp":"32","nightTemp":"23"},"autumn":{"dayWeather":"晴","nightWeather":"晴","dayTemp":"18","nightTemp":"9"},"winter":{"dayWeather":"晴","nightWeather":"多云","dayTemp":"3","nightTemp":"-6"}},
    "西安":{"spring":{"dayWeather":"多云","nightWeather":"阴","dayTemp":"20","nightTemp":"10"},"summer":{"dayWeather":"晴","nightWeather":"多云","dayTemp":"33","nightTemp":"24"},"autumn":{"dayWeather":"阴","nightWeather":"小雨","dayTemp":"17","nightTemp":"9"},"winter":{"dayWeather":"阴","nightWeather":"多云","dayTemp":"6","nightTemp":"-3"}},
    "成都":{"spring":{"dayWeather":"阴","nightWeather":"小雨","dayTemp":"22","nightTemp":"14"},"summer":{"dayWeather":"多云","nightWeather":"雷阵雨","dayTemp":"31","nightTemp":"24"},"autumn":{"dayWeather":"阴","nightWeather":"小雨","dayTemp":"20","nightTemp":"15"},"winter":{"dayWeather":"阴","nightWeather":"小雨","dayTemp":"10","nightTemp":"4"}},
    "上海":{"spring":{"dayWeather":"多云","nightWeather":"小雨","dayTemp":"18","nightTemp":"11"},"summer":{"dayWeather":"多云","nightWeather":"雷阵雨","dayTemp":"32","nightTemp":"26"},"autumn":{"dayWeather":"晴","nightWeather":"多云","dayTemp":"22","nightTemp":"16"},"winter":{"dayWeather":"阴","nightWeather":"小雨","dayTemp":"8","nightTemp":"2"}},
    "三亚":{"spring":{"dayWeather":"晴","nightWeather":"多云","dayTemp":"30","nightTemp":"24"},"summer":{"dayWeather":"晴","nightWeather":"雷阵雨","dayTemp":"33","nightTemp":"27"},"autumn":{"dayWeather":"晴","nightWeather":"多云","dayTemp":"30","nightTemp":"24"},"winter":{"dayWeather":"晴","nightWeather":"多云","dayTemp":"26","nightTemp":"20"}},
    "广州":{"spring":{"dayWeather":"阴","nightWeather":"小雨","dayTemp":"24","nightTemp":"18"},"summer":{"dayWeather":"多云","nightWeather":"雷阵雨","dayTemp":"33","nightTemp":"26"},"autumn":{"dayWeather":"晴","nightWeather":"多云","dayTemp":"28","nightTemp":"20"},"winter":{"dayWeather":"多云","nightWeather":"阴","dayTemp":"18","nightTemp":"11"}},
    "杭州":{"spring":{"dayWeather":"多云","nightWeather":"小雨","dayTemp":"20","nightTemp":"12"},"summer":{"dayWeather":"多云","nightWeather":"雷阵雨","dayTemp":"34","nightTemp":"26"},"autumn":{"dayWeather":"晴","nightWeather":"多云","dayTemp":"22","nightTemp":"15"},"winter":{"dayWeather":"阴","nightWeather":"小雨","dayTemp":"8","nightTemp":"2"}},
    "默认":{"spring":{"dayWeather":"多云","nightWeather":"晴","dayTemp":"20","nightTemp":"12"},"summer":{"dayWeather":"晴","nightWeather":"多云","dayTemp":"32","nightTemp":"24"},"autumn":{"dayWeather":"晴","nightWeather":"多云","dayTemp":"20","nightTemp":"13"},"winter":{"dayWeather":"多云","nightWeather":"阴","dayTemp":"8","nightTemp":"0"}},
}


# ========================================================================
# 第6部分：飞猪 FlyAI（旅游比价）
# ========================================================================
@tool
def flyai_search(query: str, category: str = "poi", destination: str = "") -> str:
    """
    飞猪 FlyAI 搜索工具

    用途：搜索酒店价格、景区门票、机票信息
    调用方式：通过 subprocess 运行飞猪 CLI 工具

    category 选项：
    - "poi": 景点/地标（配合 destination 参数使用 search-poi 命令）
    - "hotel": 酒店（配合 destination 参数使用 search-hotels 命令）
    - "flight": 机票（使用 ai-search 命令）

    面试考点：为什么用 subprocess 而不是 Python SDK？
    - 飞猪 FlyAI 只提供 CLI 工具，没有 Python SDK
    - subprocess 是调用外部程序的通用方式
    - 设置 env 参数注入 API Key 到子进程环境变量
    - text=False + UTF-8 手动解码：解决 Windows GBK 编码问题
    - timeout=20: 子进程超时保护
    """
    if not settings.flyai_api_key:
        return json.dumps({"note":"飞猪未配置"}, ensure_ascii=False)

    try:
        # 将 FLYAI_API_KEY 注入子进程环境变量
        env = {
            "FLYAI_API_KEY": settings.flyai_api_key,
            "PATH": os.environ.get("PATH", "")    # 保留系统 PATH
        }

        # 构建 CLI 命令（使用正确的飞猪命令）
        if category == "poi" and destination:
            cmd = ["flyai", "search-poi", "--city-name", destination, "--keyword", query]
        elif category == "hotel" and destination:
            cmd = ["flyai", "search-hotels", "--dest-name", destination]
        elif category == "flight":
            cmd = ["flyai", "ai-search", "--query", query]  # 机票用 ai-search
        else:
            cmd = ["flyai", "keyword-search", "--query", query]  # 通用搜索，无 --type

        # 执行子进程
        # text=False 避免 Windows GBK 解码崩溃，手动 UTF-8 解码
        r = subprocess.run(
            cmd,
            capture_output=True,                  # 捕获标准输出和标准错误
            text=False,                           # 返回 bytes 而非 str（避免 GBK 问题）
            timeout=20,                           # 超时 20 秒
            env=env                               # 注入 API Key
        )

        out = r.stdout.decode("utf-8", errors="replace")
        return out[:3000] if r.returncode == 0 else json.dumps(
            {"error": "飞猪失败"}, ensure_ascii=False
        )

    except FileNotFoundError:
        # flyai 命令不存在（未安装 或 Docker 镜像中没有）
        return json.dumps({"note": "飞猪不可用"}, ensure_ascii=False)
    except:
        # 其他异常（超时、权限等）
        return json.dumps({"note": "飞猪异常"}, ensure_ascii=False)