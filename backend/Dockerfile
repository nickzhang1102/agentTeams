# Agent Teams Backend - FastAPI + Uvicorn
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量（避免创建用户主目录）
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV HOME=/app
# pip 镜像源默认清华（国内加速），海外用户可构建时覆盖：
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.org/simple backend
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制 OpenHarness 源码（从项目根目录）
COPY OpenHarness /app/OpenHarness

# 安装 OpenHarness（可编辑模式）
RUN pip install --no-cache-dir -e /app/OpenHarness

# 复制依赖文件
COPY backend/requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY backend .

# 复制 Agent 配置文件（seed_admin_data.py 和 AgentContentReader 需要）
COPY agents /app/agents

# Agent 配置目录（覆盖 config.py 中基于 basedir 的默认路径）
ENV AGENTS_DIR=/app/agents

# 启动脚本（真实文件，勿用 RUN echo 内联生成——\n 转义在 dash/bash echo 中不生效）
COPY backend/start.sh /app/start.sh

# 创建数据目录、赋予运行权限并以非 root 用户运行（生产安全）
RUN chmod +x /app/start.sh \
    && mkdir -p /app/data/files /app/data/workspace /app/data/knowledge \
    && groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 5000

# 设置环境变量
ENV APP_ENV=production

# 使用启动脚本
CMD ["/app/start.sh"]
