# ============================================================================
# Dockerfile — CloudBase CloudRun 容器构建文件
# ============================================================================
# 构建命令: docker build -t ai-travel-backend .
# 运行命令: docker run -p 8080:8080 --env-file .env ai-travel-backend
#
# 基础镜像选择: python:3.12-slim
#   - python:3.12: Python 3.12 解释器，包含 pip 等基础工具
#   - slim 版本: 精简版，去除编译工具链和文档，镜像大小约 150MB
#   - 对比 alpine 版本: slim 使用 Debian，glibc 兼容性好（飞猪 CLI 需要）
#
# 面试考点: Docker 镜像分层原理？
#   - 每条指令（FROM/COPY/RUN）创建一个镜像层
#   - 层是只读的，修改上层不会影响下层
#   - 层的复用: 如果两层的 hash 相同，Docker 会复用缓存
#   - 优化策略: 先 COPY requirements.txt（变化少），再 COPY .（变化多）
#     这样 pip install 层可以被缓存，加速后续构建
# ============================================================================

FROM python:3.12-slim
# FROM: 指定基础镜像，Docker 从 Docker Hub 拉取 python:3.12-slim
# 基础镜像已包含 Python 3.12 解释器和 pip

WORKDIR /app
# WORKDIR: 设置工作目录
# 后续的 COPY、RUN、CMD 都在此目录下执行
# 相当于 mkdir -p /app && cd /app

# ===== 安装 Python 依赖 =====
COPY requirements.txt .
# COPY: 将宿主机文件复制到容器中
# 先单独复制 requirements.txt（而不是 COPY . .）
# 原因: Docker 缓存机制——requirements.txt 不常变，pip install 层可复用
# 如果先 COPY . .，任何代码修改都会导致 pip install 重新执行（慢）

RUN pip install --no-cache-dir -r requirements.txt
# RUN: 在镜像构建时执行命令

# ===== 安装 Node.js 和飞猪 FlyAI CLI =====
# flyai_search() 通过 subprocess 调用 flyai CLI，需要 Node.js 运行时
# python:3.12-slim 不含 Node.js，需通过 apt-get 安装
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*
RUN npm i -g @fly-ai/flyai-cli
# 安装后 flyai 位于 /usr/local/bin/flyai（npm global bin 默认在 PATH 中）
# subprocess.run(["flyai", ...]) 无需指定完整路径即可找到
# --no-cache-dir: 不缓存 pip 下载包（减小镜像体积）
# 安装的包包括: fastapi, uvicorn, langgraph, langchain, httpx, pydantic 等
# 面试考点: pip --no-cache-dir 能省多少空间？
#   - pip 默认缓存下载的 .whl 文件，通常 50-200MB
#   - Docker 镜像中这些缓存文件永远不会被使用（容器是临时的）
#   - 加上 --no-cache-dir 可节省约 100MB 镜像空间

# ===== 复制应用代码 =====
COPY . .
# 复制所有源代码到容器的 /app 目录
# 包括: main.py, config.py, agents/, services/, schemas/, api/, .env
# .dockerignore 文件可排除不必要文件（如 __pycache__, .git, data/）

# ===== 暴露端口 =====
ENV PORT=8080
# ENV: 设置容器环境变量
# PORT=8080: CloudBase CloudRun 默认端口，按此端口进行健康检查
EXPOSE 8080
# EXPOSE: 声明容器运行时监听的端口
# 注意: 这只是文档性声明，不会实际开放端口
# 实际端口映射需要通过 -p 或 CloudRun 控制台配置

# ===== 启动命令 =====
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
# CMD: 容器启动时的默认命令（可被 docker run 后的参数覆盖）
# uvicorn: ASGI 服务器（FastAPI 官方推荐）
# main:app: main.py 文件中的 app 对象（FastAPI 实例）
# --host 0.0.0.0: 监听所有网络接口（容器内需要绑定 0.0.0.0 才能被外部访问）
# --port 8080: 监听端口（与 CloudRun 配置一致）
# 面试考点: CMD vs ENTRYPOINT 的区别？
#   - CMD: 提供默认命令，可被 docker run 后的参数覆盖
#   - ENTRYPOINT: 固定的入口命令，docker run 后的参数作为追加参数
#   - 本项目用 CMD 即可（CloudRun 不需要额外参数）
# 面试考点: 为什么用 uvicorn 而不是 gunicorn？
#   - uvicorn 是 ASGI 服务器（原生支持 async/await）
#   - gunicorn 是 WSGI 服务器（不支持异步），需要通过 uvicorn worker 桥接
#   - FastAPI 官方推荐直接用 uvicorn（简单、高效）
#   - 生产环境多 worker 可用 gunicorn + uvicorn workers
