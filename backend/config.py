"""
============================================================================
LLM 配置中心 + 模型工厂
============================================================================
技术选型说明：
  - pydantic-settings: 基于 Pydantic 的配置管理库，自动从 .env 和环境变量加载配置
  - ChatOpenAI: LangChain 的 OpenAI 兼容客户端，支持任何 OpenAI API 格式的 LLM
  - SQLite + aiosqlite: 轻量级异步数据库，适合单机部署和开发环境

设计模式：单例模式（Settings 类只实例化一次，全局共享）
============================================================================
"""
# ===== 标准库导入 =====
import os                                       # 操作系统接口，用于读取环境变量
from functools import lru_cache                 # 缓存装饰器
from pathlib import Path                        # 面向对象的文件系统路径处理

# ===== 第三方库导入 =====
from pydantic_settings import BaseSettings      # Pydantic Settings 基类，支持从 .env 自动加载配置


class Settings(BaseSettings):
    """
    全局配置类（单例模式）
    
    继承 BaseSettings 的好处：
    1. 自动从 .env 文件加载配置（按 Config.env_file 指定）
    2. 自动从环境变量读取（环境变量优先级高于 .env 文件）
    3. 类型安全：每个字段都有明确的 Python 类型注解
    4. 支持默认值：字段可直接赋默认值
    
    面试考点：BaseSettings vs os.environ 的区别？
    - BaseSettings 提供类型验证和转换（自动将字符串 "8080" 转为 int 8080）
    - 支持嵌套模型和复杂类型
    - 与 FastAPI 依赖注入深度集成
    """
    
    # ===== 应用配置 =====
    app_name: str = "AI旅行规划 API"             # 应用名称，用于 Swagger 文档标题和日志
    debug: bool = True                            # 调试模式开关，开发阶段保持 True
    
    # ===== 数据库配置 =====
    # Path(__file__).parent: 获取 config.py 所在的目录（backend/）
    # mkdir(parents=True, exist_ok=True): 递归创建目录，目录已存在时不报错
    _db_dir = Path(__file__).parent / "data"      # 数据库文件存放目录
    _db_dir.mkdir(parents=True, exist_ok=True)    # 确保目录存在
    database_url: str = f"sqlite+aiosqlite:///{_db_dir / 'travel.db'}"
    # database_url 说明：
    #   - sqlite+aiosqlite: 使用 aiosqlite 驱动，支持异步操作
    #   - SQLite 是嵌入式数据库，无需额外安装服务，数据存储在单个文件中
    #   - 面试考点：为什么选 SQLite 而不是 MySQL/PostgreSQL？
    #     答：本项目是 MVP 原型，SQLite 零配置、轻量级，适合单机和开发环境。
    #     生产环境可切换为 PostgreSQL（只需改连接字符串）
    
    # ===== LLM 大语言模型配置 =====
    # LLM Provider 选项说明：
    #   - deepseek: DeepSeek（推荐：性价比最高，中文理解好，价格仅 OpenAI 的 1/10）
    #   - openai: OpenAI GPT 系列
    #   - hunyuan: 腾讯混元（企业微信生态兼容好）
    #   - zhipu: 智谱 GLM（国内合规首选）
    llm_provider: str = "deepseek"                # LLM 服务提供商标识
    llm_model: str = "deepseek-flash"           # 模型名称，具体型号
    llm_api_key: str = ""                         # API 密钥（必填，从 .env 加载）
    llm_base_url: str = "https://api.deepseek.com"  # API 基础 URL，兼容 OpenAI 格式
    llm_temperature: float = 0.7                  # 生成温度 (0~2)
                                                   # 温度说明：值越高输出越随机/有创意，越低越确定/保守
                                                   # 0.7 适合需要创造性的任务（如旅行推荐）
                                                   # 0.3 适合结构化输出（如 JSON 格式化）
    llm_max_tokens: int = 16384                   # 单次生成最大 Token 数
                                                   # 16384 Token ≈ 1.2万中文字，足够生成多天完整行程
    
    # ===== 外部 API 配置 =====
    amap_key: str = ""                            # 高德地图 WebService API Key（每日免费5000次）
                                                   # 天气/搜索/路线走 MCP，逆地理编码走 REST API（geo.py）
    flyai_api_key: str = ""                       # 飞猪 FlyAI API Key（酒店/机票/景点价格查询）
    # ===== 微信小程序登录 =====
    wx_appid: str = ""                            # 微信小程序 AppID
    wx_secret: str = ""                           # 微信小程序 AppSecret（用于 code2session）
    jwt_secret: str = "change-this-to-a-random-secret-in-production"
    jwt_expire_days: int = 7


    # ===== Pydantic Settings 内部配置 =====
    class Config:
        """
        Pydantic Settings 专用配置类
        
        注意：这是嵌套类 Config，不是全局的 config 模块
        env_file = ".env": 指定从哪个文件加载环境变量
        env_file_encoding = "utf-8": 文件编码（支持中文值）
        
        面试考点：.env 文件的管理原则？
        - .env 包含敏感信息（API Key），绝不能提交到 Git
        - 使用 .env.example 作为模板提交到仓库
        - 部署时通过 CloudRun 环境变量注入（更安全）
        """
        env_file = ".env"                         # 环境变量文件路径（相对于运行目录）
        env_file_encoding = "utf-8"               # 文件编码


# ===== 全局配置单例 =====
# 在模块级别实例化 Settings，整个应用共享同一个配置对象
# Python 模块只加载一次，所以这天然实现单例模式
settings = Settings()


# ===== LLM 工厂函数 =====
@lru_cache(maxsize=8)
def _get_llm_cached(provider: str, model: str, temperature: float):
    """
    按参数缓存的 LLM 工厂（内部函数）

    lru_cache 保证同参数组合只创建一次 ChatOpenAI 实例
    """
    from langchain_openai import ChatOpenAI

    base_kwargs = dict(
        model=model,
        api_key=settings.llm_api_key,
        temperature=temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=120,
    )

    if provider == "deepseek":
        return ChatOpenAI(
            **base_kwargs,
            base_url="https://api.deepseek.com/v1",
            extra_body={"thinking": {"type": "disabled"}},
        )
    elif provider == "openai":
        return ChatOpenAI(
            **base_kwargs,
            base_url=settings.llm_base_url or None,
        )
    elif provider in ("hunyuan", "zhipu"):
        return ChatOpenAI(
            **base_kwargs,
            base_url=settings.llm_base_url or "https://api.hunyuan.cloud.tencent.com/v1",
        )
    else:
        raise ValueError(f"不支持的 LLM provider: {provider}")


def get_llm():
    """获取标准 LLM 实例（已缓存）"""
    return _get_llm_cached(
        settings.llm_provider,
        settings.llm_model,
        settings.llm_temperature,
    )


def get_llm_structured():
    """获取结构化输出 LLM（temperature=0.3，已缓存）"""
    return _get_llm_cached(
        settings.llm_provider,
        settings.llm_model,
        0.3,
    )
