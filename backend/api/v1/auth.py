"""
============================================================================
用户认证 API — 微信小程序 code2session 登录 + JWT Token
============================================================================
微信小程序登录流程（OAuth 2.0 授权码模式简化版）：
  1. 小程序端调用 wx.login() → 获取临时 code（5分钟有效期）
  2. 前端将 code 通过 POST /api/v1/auth/login 发给后端
  3. 后端用 code + appid + secret 调微信服务器换取 openid
  4. 后端根据 openid 生成 JWT Token 返回给前端
  5. 前端后续请求在 Authorization 头携带 Bearer token

面试考点：为什么不用 session/cookie 而用 JWT？
  - 微信小程序没有 cookie 机制（WebView 限制）
  - JWT 无状态，服务器不需要存储 session（水平扩展友好）
  - JWT 可以携带自定义 payload（user_id, openid）
  - 缺点：无法主动失效（被盗后直到过期都有效）
  - 解决：Token 有效期设 7 天，敏感操作需二次验证
============================================================================
"""
# ===== 标准库导入 =====
import uuid                                     # 生成唯一 user_id（"通用唯一识别码"）
import logging                                  # 日志记录模块
from datetime import datetime, timedelta, timezone  # datetime=日期时间, timedelta=时间段, timezone=时区

# ===== 第三方库导入 =====
import httpx                                    # 现代 HTTP 客户端（支持 HTTP/2 和 async/await）
import jwt                                      # PyJWT: JSON Web Token 编码/解码库
from fastapi import APIRouter, HTTPException     # HTTPException: 抛出标准 HTTP 错误响应（登录失败时使用）
from pydantic import BaseModel                  # Pydantic 数据模型基类（请求/响应 Schema）

# ===== 项目内部模块导入 =====
import db                                        # 本地 SQLite 数据层（登录时写 users 表）
from config import settings                    # 全局配置（微信 appid/secret 等）

# ===== 创建子路由 =====
router = APIRouter(prefix="/auth", tags=["认证"])
# 所有路由自动带 /auth 前缀 → 实际路径 /api/v1/auth/login
logger = logging.getLogger(__name__)            # 获取当前模块的日志实例

# ===== 稳定 user_id 的 UUIDv5 命名空间 =====
# 为什么需要：原先每次登录都 uuid4() 生成新 ID，同一微信用户每次登录身份都变，
#             导致「我的行程」按 userId 过滤时查不到历史数据。
# 做法：用固定命名空间 + openid 做 UUIDv5（确定性哈希），同一 openid 永远得到同一 user_id。
#       这是零存储、零依赖的最小修复；后续若要存昵称/头像，再把 (openid → user_id) 落库即可。
_USER_ID_NAMESPACE = uuid.UUID("6f1b8a2c-3d4e-5f60-8a7b-9c0d1e2f3a4b")


class LoginRequest(BaseModel):
    """
    登录请求体 Schema

    微信小程序 wx.login() 返回的临时 code，有效期 5 分钟
    """
    code: str                                    # 微信临时登录凭证


class LoginResponse(BaseModel):
    """
    登录响应体 Schema

    返回给前端的认证信息，前端需要：
    1. 将 token 存入 localStorage（小程序存到 storage）
    2. 后续请求在 Authorization 头带上 "Bearer <token>"
    3. 将 user_id 作为用户标识
    """
    token: str                                   # JWT Token（后续请求认证凭证）
    user_id: str                                 # 用户唯一 ID
    openid: str                                  # 微信 OpenID（用户微信身份标识）
    nickname: str = ""                           # 用户昵称（小程序登录后从用户信息获取）
    avatar_url: str = ""                         # 用户头像 URL


def create_jwt_token(user_id: str, openid: str) -> str:
    """
    生成 JWT Token

    JWT 结构：header.payload.signature
    - header: {"alg": "HS256", "typ": "JWT"}（自动生成）
    - payload: {"user_id": "...", "openid": "...", "exp": ..., "iat": ...}
    - signature: HMAC-SHA256(header + "." + payload, secret)

    参数：
    - user_id: 用户唯一标识
    - openid: 微信 OpenID

    返回：
    - 编码后的 JWT 字符串（如 "eyJhbGciOiJIUzI1NiIs..."）

    面试考点：JWT 的安全注意事项？
    - secret 必须足够强（至少 32 字节随机字符串），写在 .env 中
    - exp（过期时间）不可过长（本项目 7 天）
    - payload 不存敏感信息（Base64 编码不是加密！）
    - 必须用 HTTPS 传输（防止中间人窃取 token）
    """
    # 构建 JWT payload（载荷）
    payload = {
        "user_id": user_id,                      # 自定义声明：用户 ID
        "openid": openid,                        # 自定义声明：微信 OpenID
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days),  # 过期时间（UTC）
        "iat": datetime.now(timezone.utc),       # 签发时间（Issued At，UTC 时间）
    }
    # jwt.encode: 使用 HS256 算法 + secret 密钥签名
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


@router.post("/login", response_model=LoginResponse)
async def wx_login(body: LoginRequest):
    """
    微信小程序登录接口（POST /api/v1/auth/login）

    完整登录流程：
    1. 接收前端发来的临时 code
    2. 检查微信配置是否存在（不存在时走开发模式，返回模拟数据）
    3. 调用微信 jscode2session 接口换取 openid
    4. 生成 JWT Token 返回前端

    面试考点：为什么要有"开发模式"（没配置微信时也能登录）？
    - 开发阶段不需要真实的微信 AppID（审核流程慢）
    - 方便前后端联调和本地测试
    - 自动化测试不需要依赖微信服务（Mock 微信 API）
    - 生产环境配置后自动启用真实登录流程

    面试考点：httpx.AsyncClient 和 requests 库的区别？
    - httpx 支持 async/await（不阻塞事件循环）
    - httpx 支持 HTTP/2（多路复用，减少连接数）
    - requests 是同步库，在 asyncio 中会阻塞事件循环
    """
    openid = ""                                  # 初始化 openid 为空

    # === 开发模式：未配置微信时返回模拟数据 ===
    if not settings.wx_appid or not settings.wx_secret:
        # 日志记录：提醒开发者配置微信密钥
        logger.warning("WX_APPID/WX_SECRET 未配置，返回模拟 openid")
        # 用 code 的前 6 位作为 dev 模式下的模拟 openid
        openid = f"dev_user_{body.code[:6]}"

    # === 生产模式：调用微信服务器换取真实 openid ===
    else:
        # 微信 jscode2session 接口 URL（官方文档）
        url = "https://api.weixin.qq.com/sns/jscode2session"

        # 请求参数（微信接口要求）
        params = {
            "appid": settings.wx_appid,           # 小程序 AppID（在微信公众平台获取）
            "secret": settings.wx_secret,          # 小程序 AppSecret
            "js_code": body.code,                 # 前端 wx.login() 获取的临时 code
            "grant_type": "authorization_code",    # 授权类型（固定值）
        }

        try:
            # 使用 httpx.AsyncClient 发起异步 HTTP 请求（不阻塞事件循环）
            # async with: 自动管理 HTTP 连接的生命周期（创建 → 使用 → 关闭）
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                data = resp.json()                 # 解析微信返回的 JSON

        except Exception as e:
            # 网络异常处理：微信服务不可用时明确报错，不再签发"假"token
            logger.error(f"wx.login 网络异常: {e}")
            # 为什么抛 502：这是上游（微信）不可用，不是客户端参数错误，502 Bad Gateway 语义更准确
            raise HTTPException(status_code=502, detail="微信登录服务暂不可用，请稍后重试")

        # 检查微信返回是否有错误（errcode != 0 表示失败）
        if data.get("errcode", 0) != 0:
            errcode = data.get("errcode")           # 错误码（如 40029 = code 无效）
            errmsg = data.get("errmsg", "未知错误")  # 错误描述
            logger.error(f"wx.login 失败: errcode={errcode} errmsg={errmsg}")
            # 为什么抛 502：登录失败必须让前端知道，否则用户会拿着无效身份继续请求
            raise HTTPException(status_code=502, detail=f"微信登录失败: {errcode} {errmsg}")

        # 成功获取 openid（微信用户的唯一标识）
        openid = data.get("openid", "")
        if not openid:
            # 微信返回 200 但没有 openid（极少见），按登录失败处理
            logger.error("wx.login 未返回 openid")
            raise HTTPException(status_code=502, detail="微信登录失败: 未返回 openid")
        logger.info(f"用户登录成功: openid={openid[:10]}...")

    # === 生成 JWT Token ===
    # 为什么用 UUIDv5(openid) 而不是 uuid4()：openid 是稳定标识，
    # 同一用户每次登录必须拿到同一 user_id，否则历史行程全部"丢失"。
    user_id = "u_" + uuid.uuid5(_USER_ID_NAMESPACE, openid).hex[:16]

    # === 写入本地用户表（替代 CloudBase users 集合） ===
    try:
        db.upsert_user(openid, user_id)
    except Exception as e:
        # 为什么不让它失败：用户表只是登录附属数据，写失败不应该导致用户登不进来
        logger.warning(f"users 表写入失败（不影响登录）: {e}")

    token = create_jwt_token(user_id, openid)

    # === 返回登录响应 ===
    return LoginResponse(
        token=token,                               # JWT Token（前端后续请求用）
        user_id=user_id,                           # 用户 ID
        openid=openid,                             # 微信 OpenID
    )
