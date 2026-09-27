"""
============================================================================
逆地理编码 API — 经纬度 → 城市/地址信息
============================================================================
功能说明：
  将 GPS 坐标（经纬度）转换为可读的地址文本（城市、区、街道等）。

  应用场景：
  1. ⭐ 用户在首页选择"附近热门目的地"时使用
  2. 行程地图模块展示时需要反向解析坐标所属城市
  3. 景点详情页显示完整地址

双 API 回退策略：
  1. 高德地图 REST API（WebService，高精度，需要 API Key）
  2. OpenStreetMap Nominatim（免费开源，备选）

面试考点：高德地图和 OpenStreetMap 的差异？
  - 高德：GCJ-02 坐标系（国家保密插件加密，中国标准）
  - OSM：WGS-84 坐标系（GPS 原始坐标）
  - OSM 在中国城市级精度不足（街道地址不完整）
  - 本项目倾向使用高德，OSM 仅作为兜底
============================================================================
"""
# ===== 标准库导入 =====
import logging                                  # 日志模块（记录 API 调用状态）

# ===== 第三方库导入 =====
import httpx                                    # 异步 HTTP 客户端（支持 async/await）
from fastapi import APIRouter, Query, HTTPException  # Query=URL查询参数, HTTPException=HTTP异常响应

# ===== 项目内部模块导入 =====
from config import settings                    # 全局配置（高德 Key）

# ===== 创建子路由 =====
router = APIRouter(prefix="/geo", tags=["地理编码"])
# 实际路径：/api/v1 + /geo + /reverse = /api/v1/geo/reverse
logger = logging.getLogger(__name__)            # 获取当前模块的日志实例


@router.get("/reverse")
async def reverse_geocode(
    lat: float = Query(..., description="纬度"),   # URL 参数: ?lat=39.9042
    lng: float = Query(..., description="经度"),   # URL 参数: &lng=116.4074
):
    """
    逆地理编码：经纬度 → 城市名/地址（GET /api/v1/geo/reverse）

    参数：
    - lat: 纬度（必填），如 39.9042（北京天安门）
    - lng: 经度（必填），如 116.4074

    返回：
    - {"city": "北京", "province": "北京市", "district": "东城区", "fullAddress": "..."}

    双 API 回退策略：
    1. 如果有高德 Key → 调用高德 REST API（精度更高、响应更快）
    2. 没有高德 Key → 回退到 OpenStreetMap（免费但精度较低）

    面试考点：为什么用双 API 策略？
    - 高德地图需要 API Key = 有调用成本
    - OSM 免费但可能需要代理（国内访问不稳定）
    - 双策略保证：有 Key 用最好的，没 Key 也能用
    - 这是一种"渐进增强"的设计思路
    """
    # === 主方案：高德地图 REST API ===
    if settings.amap_key:
        return await _amap_reverse(lat, lng)

    # === 备选方案：OpenStreetMap API ===
    return await _osm_reverse(lat, lng)


async def _amap_reverse(lat: float, lng: float) -> dict:
    """
    高德地图逆地理编码（异步 HTTP 调用）

    高德地图 REST API 说明：
    - 接口: https://restapi.amap.com/v3/geocode/regeo
    - 文档: https://lbs.amap.com/api/webservice/guide/api/georegeo
    - 限频: 个人开发者每日 5000 次（企业 50000 次）
    - 坐标系: GCJ-02（火星坐标系）

    解析逻辑：
    1. 调用高德逆地理编码 API
    2. 解析返回的 addressComponent 结构
    3. 提取 city/province/district 字段
    4. city 可能为空（直辖市的区没有 city 字段），此时用 province 代替

    参数：
    - lat: 纬度
    - lng: 经度
    返回：
    - dict: {city, province, district, fullAddress}
    异常：
    - HTTPException 503: 高德地图服务不可用
    """
    # 高德逆地理编码 REST API（非 MCP，MCP 目前无 regeo 工具）
    url = "https://restapi.amap.com/v3/geocode/regeo"

    # 使用 httpx.AsyncClient 发送异步 GET 请求
    # async with: 上下文管理器自动管理连接生命周期
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params={
            "output": "json",                        # 返回格式（支持 json/xml）
            "location": f"{lng},{lat}",              # 高德 REST API 坐标参数为"经度,纬度"格式
            "key": settings.amap_key,                 # 高德 WebService API Key
            "radius": 1000,                           # 搜索半径（米），默认 1000
        })
        data = resp.json()                            # 解析 JSON 响应

    # 检查返回状态：status="1" 表示成功（注意：字符串类型！）
    if data.get("status") == "1" and data.get("regeocode"):
        # 从 regeocode.addressComponent 提取地址组件
        # 结构：{"province":"北京市","city":"北京市","district":"东城区",...}
        addr = data["regeocode"]["addressComponent"]

        # 城市名处理：去掉"市"后缀
        # 高德返回的 city 可能为 "北京市"、"天津市"（直辖市）
        # 也可能为空（某些区级单位），此时用 province 代替
        city = (addr.get("city") or "").replace("市", "")

        if not city:
            # 直辖市的情况：city 为空但 province 是 "北京市"
            city = (addr.get("province") or "").replace("省", "").replace("市", "")

        return {
            "city": city,                              # 城市名（如 "北京"）
            "province": addr.get("province", ""),       # 省份名（如 "北京市"）
            "district": addr.get("district", ""),       # 区/县名（如 "东城区"）
            "fullAddress": data["regeocode"].get("formatted_address", ""),  # 完整地址
        }

    # 高德 API 返回失败 → 抛出 503 异常
    raise HTTPException(503, "高德地图逆地理编码失败")


async def _osm_reverse(lat: float, lng: float) -> dict:
    """
    OpenStreetMap 逆地理编码（备选方案）

    OSM API 说明：
    - 接口: https://nominatim.openstreetmap.org/reverse
    - 文档: https://nominatim.org/release-docs/develop/api/Reverse/
    - 限频: 每秒 1 次（匿名使用）
    - 坐标系: WGS-84（GPS 原始坐标）
    - 需要设置 User-Agent 请求头（OSM 要求标识调用方）

    解析逻辑比高德更复杂，因为 OSM 的地址格式因国家/地区而异：
    - 城市级行政单位可能是 city/state/county/town 等不同字段
    - 中国城市需特殊处理（直辖市、地级市、县、镇）

    参数：
    - lat: 纬度
    - lng: 经度
    返回：
    - dict: {city, province, district, fullAddress}
    异常：
    - HTTPException 503: OSM 服务不可用
    """
    # OSM Nominatim 逆地理编码 API
    url = "https://nominatim.openstreetmap.org/reverse"

    # OSM 要求设置 User-Agent（标识调用方，方便联系）
    headers = {"User-Agent": "AITravelAPI/2.0"}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params={
            "lat": lat,                            # 纬度
            "lon": lng,                            # 经度
            "format": "json",                      # 返回格式（支持 json/xml/html）
            "accept-language": "zh",               # 返回中文地址（默认英文）
            "zoom": 8,                             # 详细程度（1=国家, 18=建筑, 8=城市级）
        }, headers=headers)
        data = resp.json()                         # 解析 JSON 响应

    # 检查 HTTP 状态码和 address 字段是否存在
    if resp.status_code == 200 and data.get("address"):
        addr = data["address"]                     # 地址组件
        city = ""

        # === 城市名提取逻辑（兼容 OSM 各种地址格式） ===
        # OSM 的地址格式因国家/地区而异：
        # 1. 大多数城市：addr.city 存在（如 "北京市"）
        # 2. 直辖市：city 不存在，state 是 "北京市"
        # 3. 县级市：county 可能是 "某某县" 或 "某某区"
        # 4. 镇：town 可能是 "某某镇"
        if addr.get("city"):
            # 普通城市（去掉"市"后缀）
            city = addr["city"].replace("市", "")
        elif addr.get("state") in ("北京市", "上海市", "天津市", "重庆市"):
            # 四个直辖市：state 字段就是城市名
            city = addr["state"].replace("市", "")
        elif addr.get("county"):
            # 县级/区级：去掉"县"或"区"后缀
            city = addr["county"].replace("县", "").replace("区", "")
        elif addr.get("town"):
            # 镇级：去掉"镇"或"乡"后缀
            city = addr["town"].replace("镇", "").replace("乡", "")

        return {
            "city": city,                          # 提取后的城市名
            "province": addr.get("province", addr.get("state", "")),  # 省份
            "district": addr.get("county", ""),     # 区/县
            "fullAddress": data.get("display_name", ""),  # OSM 完整地址
        }

    # OSM 返回失败 → 抛出 503 异常
    raise HTTPException(503, "逆地理编码服务不可用")
