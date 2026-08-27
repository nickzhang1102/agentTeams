# Agent Teams 本地服务器 Docker 部署指南

> 面向本地/内网服务器的完整 Docker 部署文档。
> 覆盖环境准备、配置、构建、启动、运维全流程。

---

## 目录

1. [架构概览](#1-架构概览)
2. [环境要求](#2-环境要求)
3. [部署前准备](#3-部署前准备)
4. [环境变量配置](#4-环境变量配置)
5. [构建与启动](#5-构建与启动)
6. [验证部署](#6-验证部署)
7. [国内网络加速](#7-国内网络加速)
8. [日常运维](#8-日常运维)
9. [故障排查](#9-故障排查)
10. [安全加固](#10-安全加固)
11. [附录：手动部署（不用脚本）](#附录手动部署不用脚本)

集成客户端生命周期、通用 launch/status/reconcile 以及本地 embed access 撤销的运维流程，见[集成客户端与会诊对账运维指南](./integration-clients.md)。

---

## 1. 架构概览

```
┌──────────────────┐    :8380
│  Nginx (前端)     │  Vue3 SPA 静态文件
└────────┬─────────┘
         │ proxy_pass /api/
         ▼
┌──────────────────┐    :5000
│  Uvicorn (后端)   │  FastAPI + 多 worker
└────────┬─────────┘
         │ psycopg
         ▼
┌──────────────────┐    :5432
│  PostgreSQL 18   │  数据持久化 + pgvector 向量索引（Docker volume）
│  (pgvector)      │
└──────────────────┘
```

**容器列表：**

| 容器名 | 镜像 | 端口映射 | 职责 |
|--------|------|----------|------|
| `agent-teams-postgres` | `pgvector/pgvector:pg18` | 127.0.0.1:5433->5432 | 数据库（含 pgvector 向量扩展） |
| `agent-teams-backend` | 自构建 | 127.0.0.1:5000->5000 | FastAPI API |
| `agent-teams-frontend` | 自构建 | 8380:80 | Nginx + Vue3 SPA |

---

## 2. 环境要求

### 服务器

| 项目 | 最低要求 | 推荐配置 |
|------|----------|----------|
| OS | Linux（Ubuntu 20.04+ / CentOS 7+）| Ubuntu 22.04 LTS |
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 20 GB 可用 | 50 GB（含数据库增长） |
| 网络 | 能访问 Docker Hub 或配置镜像加速 | |

### 软件

| 软件 | 版本要求 | 安装方式 |
|------|----------|----------|
| Docker | 20.10+ | `curl -fsSL https://get.docker.com \| sh` |
| Docker Compose | V2（`docker compose` 子命令） | Docker 自带；或 `apt install docker-compose-plugin` |
| Git | 任意 | `apt install git` |

验证：

```bash
docker --version       # Docker version 24.x+
docker compose version # Docker Compose version v2.x+
```

---

## 3. 部署前准备

### 3.1 克隆项目

```bash
cd /opt  # 或你选择的部署目录
git clone <repository-url> agentTeams
cd agentTeams

# ⚠️ 克隆后立即配置环境变量（.env 文件未提交到 Git）
cp backend/.env.example backend/.env
# 编辑 backend/.env 填写必填项（见下方章节 4）
```

**为什么 .env 不在 Git 中？**

`.env` 包含数据库连接和应用根密钥，已添加到 `.gitignore`。每次部署时必须从 `.env.example` 模板手动创建并填写。

### 3.2 创建数据目录

```bash
mkdir -p backend/data/files
mkdir -p backend/data/workspace
mkdir -p logs
```

### 3.3 准备 LLM 服务账号

基础服务可以先启动；首次分析前需在后台“LLM 模型”中添加并启用一个 OpenAI 兼容模型：

| 提供商 | LLM_BASE_URL | 获取方式 |
|--------|--------------|----------|
| 豆包（火山引擎）| `https://ark.cn-beijing.volces.com/api/v3` | [控制台](https://www.volcengine.com/docs/82379) |
| 天翼云 WishHub | 按实际分配 | 联系服务商 |
| OpenAI 兼容 | `https://api.openai.com/v1` | [platform.openai.com](https://platform.openai.com) |

---

## 4. 环境变量配置

### 4.1 后端 `.env`

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，**必须填写以下项**：

```bash
# ==================== 安全（必须） ====================
# 生成方式: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<随机 32+ 字符>
JWT_SECRET_KEY=<随机 32+ 字符>

# ==================== 数据库（Docker 内自动覆盖） ====================
# Docker 环境中此项被 docker-compose.yml 的 environment 覆盖，
# 本地开发时才需要手动设置
# DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agent_teams

# ==================== 可选 ====================
# 文件存储（容器内路径，已通过 volume 映射）
FILE_STORAGE_PATH=/app/data/files
WORKSPACE_DIR=/app/data/workspace

# Agent 配置目录（容器内路径，已通过 volume 映射）
AGENTS_DIR=/app/agents

# 日志级别
LOG_LEVEL=info

# Agent Teams iframe 来源策略
# 同站 /agentteams 反代只需 'self'；独立域名部署必须列出 Agent Teams 前端 origin。
AGENTTEAMS_EMBED_FRAME_ANCESTORS="'self' https://agentteams.example.com"

# ==================== 可选：LLM 并发上限 ====================
# 进程级信号量，限制同一 uvicorn worker 内并行发起的 LLM API 调用数。
# 默认 3；Docker 以 --workers 4 启动时全实例上限为 4 × 3 = 12。
# 该上限跨所有模型/账号共享：多用户并发时超出的调用会静默排队，
# 表现为聊天/分析首字延迟上升。压测后可按账号 tpm 配额调高。
# LLM_MAX_CONCURRENT_CALLS=3
```

`frame-ancestors` 必须使用浏览器访问 Agent Teams 时的 origin，不是容器内部地址。
例如 Agent Teams 页面为 `https://agentteams.example.com`，就必须包含该完整 origin；
漏配时浏览器会在加载 AgentTeams iframe HTML 前直接拦截页面。

### 4.2 前端 `.env`（通常不需要修改）

```bash
# 前端在 Docker 中通过 nginx proxy_pass 访问后端，
# 不需要配置 VITE_API_BASE_URL（nginx.conf 已代理 /api/）
```

### 4.3 数据库密码（可选修改）

默认 `postgres/postgres`。如需修改，同步改 `docker-compose.yml` 中两处：

```yaml
# postgres 服务
POSTGRES_PASSWORD: your-strong-password

# backend 服务的 DATABASE_URL
DATABASE_URL: postgresql+psycopg://postgres:your-strong-password@postgres:5432/agent_teams
```

---

## 5. OpenHarness 依赖

后端依赖 [OpenHarness](https://github.com/novix-science/OpenHarness)（Agent 工具生态框架）。

### 5.1 源码集成方式（唯一方式）

**项目已包含 OpenHarness 源码**（位于根目录 `OpenHarness/`），容器构建时自动安装。

**验证目录结构**：
```
agentTeams/
├── backend/
├── frontend/
├── OpenHarness/         # ← 必须存在
│   ├── src/
│   │   └── openharness/  # ← 核心源码
│   ├── pyproject.toml
│   └── setup.py
└── docker-compose.yml
```

**工作原理**：
- `backend/Dockerfile` 在安装依赖前，先 `COPY OpenHarness /app/OpenHarness`
- 然后执行 `pip install -e /app/OpenHarness`（可编辑模式）
- 后续修改 `OpenHarness/` 源码后，重新构建镜像即可生效

### 5.2 首次部署准备

**如果你的项目是通过 Git 克隆的**，OpenHarness 源码可能不完整（需要单独复制）：

```bash
# 检查 OpenHarness 是否存在
ls -la OpenHarness/openharness/

# 如不存在或不完整，从开发机复制
# Windows 开发机：
cd D:\dev
tar -czf OpenHarness.tar.gz OpenHarness
scp OpenHarness.tar.gz user@server:/path/to/agentTeams/
# 服务器端：
cd /path/to/agentTeams
tar -xzf OpenHarness.tar.gz
rm OpenHarness.tar.gz
```

**如果项目是完整打包的**（已包含 OpenHarness），无需额外操作。

### 5.3 飞牛 NAS 部署指南

飞牛 NAS（基于 TrueNAS/OpenMediaVault）通常通过 Portainer 或 Docker Compose 管理容器。

**前置要求**：
- NAS 已安装 Docker + Docker Compose
- 可通过 SSH 或 Web 终端访问
- 已挂载至少 20GB 存储池

**部署步骤**：

1. **上传项目到 NAS**：
   ```bash
   # 方式 A：通过 Git（NAS 已安装 Git）
   ssh admin@nas-ip
   cd /volume1/docker  # TrueNAS 替换为 /mnt/pool1/docker
   git clone https://github.com/your-org/agentTeams.git
   cd agentTeams
   
   # ⚠️ 重要步骤 1：配置环境变量（.env 不在 Git 中）
   cp backend/.env.example backend/.env
   nano backend/.env  # 编辑填写必填项（见下方第 3 步）
   
   # ⚠️ 重要步骤 2：检查 OpenHarness 是否完整
   ls -la OpenHarness/src/openharness/
   # 预期输出：显示 __init__.py, cli.py, coordinator/ 等文件
   # 如目录为空或不存在，需从开发机复制（见下方"方式 C"）
   
   # 方式 B：本地打包上传（推荐，包含完整 OpenHarness）
   # Windows 本地打包（包含 OpenHarness）：
   cd D:\dev\agentTeams
   tar -czf agentTeams-full.tar.gz --exclude=node_modules --exclude=venv --exclude=.git .
   scp agentTeams-full.tar.gz admin@nas-ip:/volume1/docker/
   
   # NAS 上解压：
   ssh admin@nas-ip
   cd /volume1/docker
   mkdir agentTeams && cd agentTeams
   tar -xzf ../agentTeams-full.tar.gz
   rm ../agentTeams-full.tar.gz
   
   # 配置环境变量
   cp backend/.env.example backend/.env
   nano backend/.env  # 编辑填写必填项（见下方第 3 步）
   
   # 方式 C：仅上传 OpenHarness（Git 克隆方式的补充）
   # 适用于通过 Git 克隆但 OpenHarness 不完整的情况
   # Windows 本地：
   cd D:\dev
   tar -czf OpenHarness.tar.gz OpenHarness
   scp OpenHarness.tar.gz admin@nas-ip:/volume1/docker/agentTeams/
   
   # NAS 上解压：
   ssh admin@nas-ip
   cd /volume1/docker/agentTeams
   tar -xzf OpenHarness.tar.gz
   rm OpenHarness.tar.gz
   ```

2. **复制 OpenHarness 源码**（⚠️ 仅当步骤 1 方式 A 使用 Git 克隆且 OpenHarness 不完整时）：
   
   **检查是否需要此步骤**：
   ```bash
   ssh admin@nas-ip
   cd /volume1/docker/agentTeams
   ls -la OpenHarness/src/openharness/
   # 预期输出：显示 __init__.py, cli.py, coordinator/ 等文件
   # 如输出显示目录不存在或为空，则需要执行下面的操作
   ```
   
   **上传 OpenHarness**：
   ```bash
   # 本地 Windows 打包
   cd D:\dev
   tar -czf OpenHarness.tar.gz OpenHarness
   
   # 上传到 NAS
   scp OpenHarness.tar.gz admin@nas-ip:/volume1/docker/agentTeams/
   
   # NAS 上解压
   ssh admin@nas-ip
   cd /volume1/docker/agentTeams
   tar -xzf OpenHarness.tar.gz
   rm OpenHarness.tar.gz
   ```
   
   **注意**：
   - 如使用步骤 1 的**方式 B**（本地打包上传），OpenHarness 已包含，**跳过此步骤**
   - 如 Git 仓库已包含完整 OpenHarness 源码（作为子模块或直接提交），**跳过此步骤**

3. **配置环境变量**：
   ```bash
   cd /volume1/docker/agentTeams
   cp backend/.env.example backend/.env
   vi backend/.env  # 或用 nano 编辑器
   
   # 必填项：
   # SECRET_KEY=<生成：python -c "import secrets; print(secrets.token_hex(32))">
   # JWT_SECRET_KEY=<生成：python -c "import secrets; print(secrets.token_hex(32))">
   # LLM 与 Exa/Tavily 凭证不写入 .env，启动后在后台配置
   ```

4. **调整数据卷路径**（可选）：
   
   编辑 `docker-compose.yml`，将数据目录映射到 NAS 存储池：
   ```yaml
   services:
     backend:
       volumes:
         - /volume1/docker/agentTeams/backend/data:/app/data
         - /volume1/docker/agentTeams/agents:/app/agents:ro
     
     postgres:
       volumes:
         - /volume1/docker/agentTeams/postgres_data:/var/lib/postgresql/data
   ```

5. **构建并启动**：
   ```bash
   # 构建镜像
   docker compose build --no-cache
   
   # 启动服务
   docker compose up -d
   
   # 查看日志
   docker compose logs -f
   ```

6. **验证部署**：
   ```bash
   # NAS 终端测试
   curl http://localhost:5000/health
   curl http://localhost:8380
   
   # 本地浏览器访问
   # http://nas-ip:8380
   ```

7. **通过 Portainer 管理**（如已安装）：
   - 访问 `http://nas-ip:9000`
   - 进入 Stacks → Add stack
   - 选择 "Upload from computer"，上传 `docker-compose.yml`
   - 或选择 "Repository"，输入 Git URL
   - 点击 "Deploy the stack"

**NAS 特定注意事项**：

- **持久化路径**：确保数据目录在 `/volume1`（群晖/威联通）或 `/mnt/pool1`（TrueNAS）下，避免系统重启丢失
- **端口冲突**：检查 5433/5000/8380 是否被占用（PostgreSQL 宿主侧映射为 `127.0.0.1:5433`），如冲突修改 `docker-compose.yml` 端口映射
- **内存限制**：部分 NAS 内存有限（如 4GB），可修改 `docker-compose.yml` 添加资源限制：
  ```yaml
  services:
    backend:
      deploy:
        resources:
          limits:
            memory: 1G
          reservations:
            memory: 512M
  ```
- **国内镜像**：NAS 通常网络不稳定，必须配置 Docker 镜像加速器（见 7.1 节）
- **定时备份**：使用 NAS 自带备份任务定期备份 `postgres_data` 卷和 `backend/data/`

**Synology 群晖特定配置**：

1. **安装 Docker 和 Git**：
   - 套件中心 → 搜索 "Docker" → 安装
   - 套件中心 → 搜索 "Git Server" → 安装

2. **SSH 访问**：
   - 控制面板 → 终端机和 SNMP → 启用 SSH 服务（端口 22）
   - 本地连接：`ssh admin@nas-ip`

3. **权限问题**：
   ```bash
   # 如遇权限错误，修改目录所有者
   sudo chown -R $(id -u):$(id -g) /volume1/docker/agentTeams
   ```

**QNAP 威联通特定配置**：

1. **安装 Container Station**：
   - App Center → 搜索 "Container Station" → 安装

2. **通过 UI 创建 Stack**：
   - Container Station → Create → Create Application
   - 粘贴 `docker-compose.yml` 内容
   - 编辑环境变量后创建

---

### 5.4 更新 OpenHarness

**本地开发环境**：
```bash
# 更新本地 OpenHarness
cd D:\dev\OpenHarness
git pull

# 同步到项目
cd D:\dev\agentTeams
xcopy /E /I /Y D:\dev\OpenHarness OpenHarness

# 重新构建容器
docker compose build backend
docker compose restart backend
```

**NAS 生产环境**：
```bash
# 在 NAS 上更新
ssh admin@nas-ip
cd /volume1/docker/agentTeams/OpenHarness
git pull  # 如 OpenHarness 也是 Git 子模块

# 或本地重新打包上传
# 然后重新构建
cd /volume1/docker/agentTeams
docker compose build --no-cache backend
docker compose restart backend
```

> **详细排查指南**：参见 [OpenHarness Docker 集成文档](./docker-openharness-integration.md)

---

## 6. 构建与启动

### 方式一：使用部署脚本（推荐）

**Linux / macOS：**

```bash
chmod +x scripts/docker-deploy.sh
./scripts/docker-deploy.sh
```

**Windows PowerShell：**

```powershell
.\scripts\docker-deploy.ps1
```

脚本自动完成：检查环境 → 创建 `.env` → 构建镜像 → 启动服务 → 初始化数据库。

### 方式二：手动执行

```bash
# 1. 构建镜像
docker compose build --no-cache

# 2. 启动服务（后台）
docker compose up -d

# 3. 等待 PostgreSQL 就绪（healthcheck 自动处理）
docker compose ps   # 确认 postgres 状态为 healthy

# 4. 初始化数据库（仅首次）
docker compose exec backend alembic upgrade head

# 从旧版升级且 backend/.env 仍有 LLM/Exa/Tavily 配置时，先备份 .env，
# 再用一次性容器导入数据库并原子清理宿主文件：
docker compose run --rm --no-deps -v ./backend:/host-backend backend \
  python scripts/migrate_env_runtime_credentials.py \
  --cleanup-env --env-file /host-backend/.env

# 5. 查看日志确认启动成功
docker compose logs -f --tail=50
```

---

## 7. 验证部署

### 6.1 容器状态

```bash
docker compose ps
```

预期输出：

```
NAME                     STATUS                  PORTS
agent-teams-postgres     Up (healthy)            127.0.0.1:5433->5432/tcp
agent-teams-backend      Up (healthy)            127.0.0.1:5000->5000/tcp
agent-teams-frontend     Up (healthy)            0.0.0.0:8380->80/tcp
```

### 6.2 健康检查

```bash
# 后端存活检查
curl http://localhost:5000/health
# {"status":"ok","uptime":12.3}

# 后端就绪检查（含数据库 + LLM 配置）
curl http://localhost:5000/ready
# {"status":"ready","checks":{"database":{"status":"ok"},"llm_config":{"status":"ok"}}}

# 前端页面
curl -I http://localhost:8380
# HTTP/1.1 200 OK
```

### 6.3 功能验证

1. 浏览器访问 `http://<服务器IP>:8380`
2. 注册账号登录；若部署时保留 `APP_ENV=development` 则默认账号为 `admin / admin123`（生产环境首次启动会生成随机密码，写入容器内 data/.admin_initial_password），首次登录后请立即修改
3. 创建对话，发送消息，验证 SSE 流式响应正常
4. 选择 Agent（如"全科专家"），验证 Agent 响应

---

## 8. 国内网络加速

### 7.1 Docker 镜像加速器（拉取基础镜像）

编辑 `/etc/docker/daemon.json`：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.rainbond.cc",
    "https://dockerhub.icu"
  ]
}
```

```bash
sudo systemctl restart docker
```

### 7.2 使用国内镜像加速器

配置 `/etc/docker/daemon.json` 后，所有 `docker compose build` 命令自动通过加速器拉取基础镜像，
无需额外 Dockerfile 或 compose override 文件。

```bash
# 直接构建即可，加速器会自动生效
docker compose build --no-cache
```

### 7.3 预拉取基础镜像

如果加速器仍慢，手动拉取后标记：

```bash
# 阿里云镜像
docker pull registry.cn-hangzhou.aliyuncs.com/library/python:3.10-slim
docker tag registry.cn-hangzhou.aliyuncs.com/library/python:3.10-slim python:3.10-slim

docker pull registry.cn-hangzhou.aliyuncs.com/library/node:18-alpine
docker tag registry.cn-hangzhou.aliyuncs.com/library/node:18-alpine node:18-alpine

docker pull registry.cn-hangzhou.aliyuncs.com/library/nginx:alpine
docker tag registry.cn-hangzhou.aliyuncs.com/library/nginx:alpine nginx:alpine

docker pull registry.cn-hangzhou.aliyuncs.com/library/postgres:18-alpine
docker tag registry.cn-hangzhou.aliyuncs.com/library/postgres:18-alpine postgres:18-alpine
```

> 详见 [Docker 国内镜像加速配置](../DOCKER_CHINA_MIRROR.md)

---

## 9. 日常运维

### 8.1 常用命令

```bash
# 查看服务状态
docker compose ps

# 查看实时日志
docker compose logs -f                # 所有服务
docker compose logs -f backend        # 仅后端
docker compose logs -f --tail=100     # 最近 100 行

# 重启服务
docker compose restart                # 全部重启
docker compose restart backend        # 仅重启后端

# 停止服务
docker compose down

# 停止并删除数据卷（⚠️ 数据库数据会丢失）
docker compose down -v
```

### 8.2 进入容器调试

```bash
# 后端容器
docker compose exec backend bash

# 数据库容器
docker compose exec postgres psql -U postgres -d agent_teams

# 前端容器
docker compose exec frontend sh
```

### 8.3 数据库迁移

```bash
# 查看当前迁移版本
docker compose exec backend alembic current

# 应用迁移（拉取新代码后）
docker compose exec backend alembic upgrade head

# 回滚一个版本
docker compose exec backend alembic downgrade -1

# 查看迁移历史
docker compose exec backend alembic history
```

### 8.4 数据备份与恢复

```bash
# 备份数据库
docker compose exec postgres pg_dump -U postgres agent_teams > backup_$(date +%Y%m%d_%H%M%S).sql

# 恢复数据库
cat backup_20260614_120000.sql | docker compose exec -T postgres psql -U postgres agent_teams

# 备份文件存储
tar -czf files_backup_$(date +%Y%m%d).tar.gz backend/data/files

# 备份 Agent 配置
tar -czf agents_backup_$(date +%Y%m%d).tar.gz agents/
```

### 8.5 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker compose down
docker compose build --no-cache
docker compose up -d

# 应用数据库迁移
docker compose exec backend alembic upgrade head
```

### 8.6 日志管理

后端日志同时输出到容器 stdout 和容器内文件 `/app/logs/backend.log`。

```bash
# 导出后端日志
docker compose exec backend cat /app/logs/backend.log > backend.log

# 查看日志文件大小
docker compose exec backend ls -lh /app/logs/
```

---

## 10. 故障排查

### 9.1 PostgreSQL 连接失败

```bash
# 检查 postgres 容器状态
docker compose ps postgres

# 查看 postgres 日志
docker compose logs postgres

# 手动连接测试
docker compose exec postgres psql -U postgres -d agent_teams -c "SELECT 1;"
```

常见原因：
- `postgres` 容器未启动完成 → healthcheck 会自动等待，backend 的 `depends_on` 已配置 `condition: service_healthy`
- 密码不匹配 → 检查 `docker-compose.yml` 中 `POSTGRES_PASSWORD` 和 `DATABASE_URL` 是否一致

### 9.2 后端启动失败

```bash
# 查看后端日志
docker compose logs backend

# 常见错误：SECRET_KEY / JWT_SECRET_KEY 未设置
# 解决：编辑 backend/.env 确保两个 key 都已填写

# 常见错误：DATABASE_URL 连接失败
# 解决：确认 postgres 已 healthy，DATABASE_URL 格式正确
```

### 9.3 前端无法访问后端

```bash
# 检查 nginx 代理配置
docker compose exec frontend cat /etc/nginx/conf.d/default.conf

# 从 nginx 容器内测试后端连通性
docker compose exec frontend curl -s http://backend:5000/health

# 检查 Docker 网络
docker network inspect agentteams_agent-teams-network
```

### 9.4 SSE 流式响应中断

nginx 已配置 `proxy_buffering off` 和 `proxy_read_timeout 300s`。如仍中断：

```bash
# 检查后端日志是否有超时
docker compose logs backend | grep -i timeout

# 进入容器测试直接 SSE
docker compose exec backend curl -N http://localhost:5000/api/leader/start \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":1,"message":"test","file_ids":[]}'
```

### 9.5 磁盘空间不足

```bash
# 查看 Docker 磁盘使用
docker system df

# 清理未使用的镜像和构建缓存
docker system prune

# 查看 postgres 数据卷大小
docker volume inspect agentteams_postgres_data
```

---

## 11. 安全加固

### 10.1 必做项

1. **修改默认密码** — 登录后立即修改 `admin` 账号密码
2. **生成强密钥** — `python -c "import secrets; print(secrets.token_hex(32))"`
3. **修改数据库密码** — 不在生产环境使用默认 `postgres/postgres`
4. **限制端口暴露** — 如无需外部直连数据库，移除 `docker-compose.yml` 中 postgres 的 `ports` 映射：

```yaml
postgres:
  # ports:          # 注释掉此项，仅容器内部网络可访问
  #   - "5432:5432"
```

### 10.2 推荐项

5. **配置 HTTPS** — 在服务器前置 Nginx 反向代理 + Let's Encrypt 证书
6. **限制 CORS** — 修改 `backend/.env` 中 `CORS_ORIGINS` 为实际域名
7. **定期备份** — 配置 crontab 定期执行数据库备份脚本
8. **日志轮转** — Docker 日志已通过 `json-file` driver 自动轮转（默认 10MB × 5）

---

## 附录：手动部署（不用脚本）

适用于需要精细控制每一步的场景。

```bash
# 0. 进入项目根目录
cd /opt/agentTeams

# 1. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env 填写 SECRET_KEY / JWT_SECRET_KEY

# 2. 创建数据目录
mkdir -p backend/data/files backend/data/workspace logs

# 3. 构建镜像（国内用 Dockerfile.china）
docker compose build

# 4. 启动数据库
docker compose up -d postgres
# 等待 healthy
until docker compose ps postgres | grep -q healthy; do sleep 2; done

# 5. 运行数据库迁移
docker compose run --rm backend alembic upgrade head

# 旧版升级可在数据库迁移后执行一次凭据导入/清理（执行前备份 backend/.env）
docker compose run --rm --no-deps -v ./backend:/host-backend backend \
  python scripts/migrate_env_runtime_credentials.py \
  --cleanup-env --env-file /host-backend/.env

# 6. 启动全部服务
docker compose up -d

# 7. 验证
curl -s http://localhost:5000/health
curl -sI http://localhost:8380

# 8. 查看日志
docker compose logs -f --tail=50
```

---

**文档版本**: 2.0
**更新时间**: 2026-06-14
**适用版本**: FastAPI 后端 + Vue3 前端 + PostgreSQL 18
