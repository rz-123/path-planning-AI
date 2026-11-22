"""
============================================================================
本地数据层 — SQLite（替代 CloudBase 云数据库）
============================================================================
为什么新增这个模块：
  - 云托管服务到期后，小程序的 users / trips 仍写在 CloudBase 云数据库，
    云环境不可用会导致「保存失败、历史列表为空」。
  - 改为后端本地 SQLite 持久化，小程序只通过后端接口读写。

设计说明：
  - 用标准库 sqlite3（异步框架里做这种毫秒级单表操作足够，不引入新依赖）
  - 每次操作独立连接，避免多线程共享连接的问题（uvicorn 多线程处理请求）
  - 数据库文件位置复用 config.database_url，不重复硬编码路径
  - 行程完整数据以 JSON 存在 payload 列，同时把列表页需要的字段拆成独立列，
    这样列表查询不用解析 JSON，也方便按 user_id 过滤
============================================================================
"""
import json                                      # 完整行程转成 JSON 字符串存库
import sqlite3                                   # Python 标准库 SQLite 驱动
import uuid                                      # 行程缺少 id 时兜底生成
from contextlib import contextmanager            # 管理连接的创建/提交/关闭
from datetime import datetime, timezone          # 统一用 UTC 时间字符串排序
from pathlib import Path                         # 解析数据库文件所在目录

from config import settings                      # 复用已有的数据库路径配置


# 从 SQLAlchemy 风格的连接串里取出真实文件路径，避免再定义一个硬编码路径
# 例：sqlite+aiosqlite:///E:\...\backend\data\travel.db → E:\...\backend\data\travel.db
_DB_FILE = settings.database_url.replace("sqlite+aiosqlite:///", "")


def _now() -> str:
    """统一时间格式（UTC ISO 字符串），保证按字符串排序 = 按时间排序"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@contextmanager
def _db():
    """每次操作创建一个连接，用完提交并关闭（简单可靠的并发策略）"""
    # 数据库目录可能被删除，操作前确保存在，否则 sqlite3 会报 unable to open database file
    Path(_DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_FILE, timeout=5)
    conn.row_factory = sqlite3.Row             # 让查询结果支持按列名访问
    try:
        yield conn
        conn.commit()                          # 成功则提交事务
    finally:
        conn.close()                           # 无论成功失败都关闭连接


def init_db() -> None:
    """
    建表（应用启动时调用一次，IF NOT EXISTS 保证幂等）

    users：登录时按 openid upsert，记录最近登录时间
    trips：一个用户可保存多条行程，payload 存完整 TripResult
    """
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                openid     TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                nickname   TEXT DEFAULT '',
                avatar_url TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                last_login TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                id             TEXT PRIMARY KEY,
                user_id        TEXT NOT NULL,
                title          TEXT DEFAULT '',
                destination    TEXT DEFAULT '',
                start_date     TEXT DEFAULT '',
                end_date       TEXT DEFAULT '',
                days           INTEGER DEFAULT 0,
                nights         INTEGER DEFAULT 0,
                people         INTEGER DEFAULT 0,
                total_budget   REAL DEFAULT 0,
                interests      TEXT DEFAULT '[]',
                payload        TEXT NOT NULL,
                created_at     TEXT NOT NULL
            )
        """)
        # 列表查询固定是「某用户的行程按时间倒序」，加复合索引避免全表扫描
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trips_user_created
            ON trips (user_id, created_at DESC)
        """)


def upsert_user(openid: str, user_id: str, nickname: str = "", avatar_url: str = "") -> None:
    """登录时写入/更新用户；同一 openid 只保留一条记录"""
    now = _now()
    with _db() as conn:
        conn.execute("""
            INSERT INTO users (openid, user_id, nickname, avatar_url, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(openid) DO UPDATE SET
                user_id    = excluded.user_id,
                last_login = excluded.last_login
        """, (openid, user_id, nickname, avatar_url, now, now))


def save_trip(user_id: str, trip: dict) -> str:
    """
    保存一条行程（同一 id 重复保存则覆盖，避免用户连点造成重复记录）

    返回：行程 id
    """
    # 优先用行程自带的 id；没有则生成，保证主键非空
    trip_id = str(trip.get("id") or uuid.uuid4().hex)
    # 完整数据原样保留，详情页需要 dailyPlan / budgetDetail / weather 等全部字段
    payload = json.dumps(trip, ensure_ascii=False)
    # 兴趣是数组，SQLite 没有数组类型，统一存 JSON 字符串
    interests = json.dumps(trip.get("interests") or [], ensure_ascii=False)

    with _db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO trips
                (id, user_id, title, destination, start_date, end_date,
                 days, nights, people, total_budget, interests, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trip_id,
            user_id,
            str(trip.get("title") or ""),
            str(trip.get("destination") or ""),
            str(trip.get("startDate") or ""),
            str(trip.get("endDate") or ""),
            int(trip.get("days") or 0),
            int(trip.get("nights") or 0),
            int(trip.get("people") or 0),
            float(trip.get("totalBudget") or 0),
            interests,
            payload,
            str(trip.get("createdAt") or _now()),
        ))
    return trip_id


def list_trips(user_id: str, limit: int = 20) -> list[dict]:
    """
    查询某用户的行程列表（按创建时间倒序）

    返回结构与前端原来的云数据库文档保持兼容：
      - _id：行程 id（前端现有代码用 item._id）
      - fullData：完整行程对象（点击卡片进详情页用）
      - 其余为列表卡片需要用的摘要字段
    """
    # limit 限制在 1~100，防止前端传入异常值把整库拉出来
    limit = max(1, min(int(limit or 20), 100))
    with _db() as conn:
        rows = conn.execute("""
            SELECT id, title, destination, start_date, end_date,
                   days, nights, people, total_budget, interests, payload, created_at
            FROM trips
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()

    result = []
    for row in rows:
        try:
            full = json.loads(row["payload"])   # 完整行程
        except (json.JSONDecodeError, TypeError):
            # 历史脏数据：不因为一条坏数据让整个列表失败
            full = {}
        result.append({
            "_id": row["id"],
            "id": row["id"],
            "title": row["title"] or (row["destination"] or "") + "之旅",
            "destination": row["destination"],
            "startDate": row["start_date"],
            "endDate": row["end_date"],
            "days": row["days"],
            "nights": row["nights"],
            "people": row["people"],
            "totalBudget": row["total_budget"],
            "budgetPerPerson": full.get("budgetPerPerson", 0),
            "interests": json.loads(row["interests"] or "[]"),
            "createdAt": row["created_at"],
            "fullData": full or None,           # 为空时前端会退化成最小摘要展示
        })
    return result
