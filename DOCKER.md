# Agent Teams System - Docker 环境配置

## 📦 Docker 部署指南

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- 一个 OpenAI 兼容的 LLM 服务账号（启动后在后台配置）

### 🚀 快速启动

#### 1. 创建环境变量文件

```bash
# 后端环境变量
cp backend/.env.example backend/.env

# 前端环境变量
cp frontend/.env.example frontend/.env
```

#### 2. 编辑 `backend/.env` 文件

```bash
# 必填基础设施配置（LLM 与 Web Search 凭证在后台配置）
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here
FILE_STORAGE_PATH=/app/data/files
WORKSPACE_DIR=/app/data/workspace
AGENTS_DIR=/app/agents
```

#### 3. 启动服务

```bash
# 构建并启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f
```

#### 4. 数据库初始化说明

Docker 部署无需手动初始化数据库：backend 容器的启动脚本会自动执行 `alembic upgrade head`，并完成管理员账号与预设数据的初始化。以下为**非 Docker 环境**的手动迁移步骤：

```bash
cd backend
alembic upgrade head
```

从旧版本升级且 `.env` 中仍有 LLM/Exa/Tavily 配置时，在数据库迁移完成后执行一次：

```bash
docker compose run --rm --no-deps -v ./backend:/host-backend backend \
  python scripts/migrate_env_runtime_credentials.py \
  --cleanup-env --env-file /host-backend/.env
```

该一次性容器只为迁移过程挂载宿主 `backend` 目录，使脚本能够原子更新宿主 `.env`；长期运行的 backend 服务不会获得该挂载。脚本只会在数据库提交并复查成功后清理旧行。执行前请备份 `.env`，并确保当前用户可写该文件。数据库凭证由 `SECRET_KEY` 加密；轮换该根密钥前必须先完成凭证重新加密。

后台修改 LLM 模型和普通 Web Search Key 后，新请求会读取新配置。Exa MCP 连接在后端启动时建立；修改 Exa Key 或 MCP 服务配置后请执行 `docker compose restart backend`。

#### 5. 访问应用

- **前端**: http://localhost:8380
- **后端 API**: http://localhost:5000/api
- **管理员账号**:
  - 用户名: `admin`
  - 初始密码随机生成，见 `docker compose logs backend` 输出或宿主机 `backend/data/.admin_initial_password` 文件（仅本地开发 APP_ENV=development 时为 admin/admin123）
  - 请首次登录后立即修改密码

### 🛠️ 常用命令

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 停止并删除数据卷
docker compose down -v

# 重启服务
docker compose restart

# 查看日志
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres

# 进入容器
docker compose exec backend bash
docker compose exec frontend sh
docker compose exec postgres psql -U postgres -d agent_teams

# 重新构建镜像
docker compose build --no-cache
docker compose up -d

# 备份数据库
docker compose exec postgres pg_dump -U postgres agent_teams > backup.sql

# 恢复数据库
cat backup.sql | docker compose exec -T postgres psql -U postgres agent_teams
```

### 📊 服务架构

```
┌─────────────────┐
│   Frontend      │  Vue3 + Nginx (Port 8380)
│   (Nginx)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Backend       │  FastAPI API (Port 5000)
│   (Uvicorn)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   PostgreSQL    │  Database (容器 5432，宿主 127.0.0.1:5433 → 容器 5432)
│                 │
└─────────────────┘
```

### 🔧 配置说明

#### 环境变量

**后端 (backend/.env)**

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `SECRET_KEY` | ✅ | - | 应用密钥 |
| `JWT_SECRET_KEY` | ✅ | - | JWT 密钥 |
| `DATABASE_URL` | ❌ | 自动配置 | 数据库连接 |

**前端 (frontend/.env)**

前端默认通过 Nginx 代理转发 `/api` 请求，无需额外环境变量配置。

#### 数据卷

- `postgres_data`: PostgreSQL 数据持久化
- `./backend/data`: 文件存储
- `./.claude/agents`: Agent 配置文件

### 🔒 安全建议

**生产环境务必修改以下配置：**

1. **修改默认密码**
   ```bash
   # 登录后在界面上修改 admin 密码
   ```

2. **生成强密钥**
   ```bash
   # SECRET_KEY
   python -c "import secrets; print(secrets.token_hex(32))"

   # JWT_SECRET_KEY
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

3. **修改数据库密码**

   注意：`POSTGRES_PASSWORD` 是 Compose 层变量（`${POSTGRES_PASSWORD:-postgres}` 插值），
   **写在 `backend/.env` 中不生效**。两种正确改法任选其一：

   ```yaml
   # 方法一：直接修改 docker-compose.yml 中 postgres 服务的 environment
   postgres:
     environment:
       POSTGRES_PASSWORD: your-strong-password-here

   # 并同步修改 backend 服务的 DATABASE_URL
   backend:
     environment:
       - DATABASE_URL=postgresql+psycopg://postgres:your-strong-password-here@postgres:5432/agent_teams
   ```

   ```bash
   # 方法二：在仓库根目录创建 .env 文件（与 docker-compose.yml 同级），写入：
   # POSTGRES_PASSWORD=your-strong-password-here
   # backend 的 DATABASE_URL 由 compose 拼接，自动使用新密码
   ```

   改完后必须重置数据卷才会以新密码重新初始化（首启后修改环境变量不会变更已建库的密码）：

   ```bash
   docker compose down -v   # ⚠️ 会删除数据库数据，请先备份
   docker compose up -d
   ```

4. **配置 HTTPS**
   - 使用 Nginx 反向代理
   - 配置 SSL 证书
   - 修改前端 API 地址为 HTTPS

5. **了解工具执行边界**

   Leader 编排的 Agent 可按其工具白名单调用文件读写、命令执行等 OpenHarness 工具。这些工具与后端服务同用户运行，不具备容器级隔离。生产环境若无需此类能力，在 `backend/.env` 中设置：

   ```bash
   OPENHARNESS_TOOLS_ENABLED=false
   ```

   启用时建议将服务部署在独立容器/主机中，并限制其文件系统与网络可见范围（详见 SECURITY.md「工具执行边界」）。

### 📝 开发模式

```bash
# 仅启动数据库
docker compose up -d postgres

# 本地运行后端
cd backend
alembic upgrade head
python run.py

# 本地运行前端
cd frontend
npm run dev
```

### 🐛 故障排查

#### 数据库连接失败

```bash
# 检查 PostgreSQL 是否运行
docker compose ps postgres

# 查看数据库日志
docker compose logs postgres

# 手动连接数据库测试
docker compose exec postgres psql -U postgres -d agent_teams
```

#### 后端服务无法启动

```bash
# 查看后端日志
docker compose logs backend

# 检查环境变量
docker compose exec backend env | grep -E 'DATABASE_URL|SECRET_KEY|JWT_SECRET_KEY'

# 手动测试数据库连接
docker compose exec backend python -c "from database import SessionLocal; from sqlalchemy import text; s = SessionLocal(); print(s.execute(text('SELECT 1')).scalar()); s.close()"
```

#### 前端无法访问后端

```bash
# 检查网络
docker network ls
docker network inspect agent-teams-network

# 测试后端健康状态
curl http://localhost:5000/api/auth/me

# 查看前端日志
docker compose logs frontend
```

### 📦 数据迁移

#### 导出数据

```bash
# 导出数据库
docker compose exec postgres pg_dump -U postgres agent_teams > backup_$(date +%Y%m%d).sql

# 导出文件存储
tar -czf files_backup_$(date +%Y%m%d).tar.gz backend/data/files
```

#### 导入数据

```bash
# 导入数据库
cat backup_20260312.sql | docker compose exec -T postgres psql -U postgres agent_teams

# 导入文件存储
tar -xzf files_backup_20260312.tar.gz
```

### 🔄 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker compose down
docker compose build --no-cache
docker compose up -d
```

> 注：数据库结构变更由容器启动脚本在每次启动时自动执行 `alembic upgrade head` 完成，无需手动运行迁移命令。

### 📧 支持

如有问题，请查看：
- 项目文档: `docs/`
- GitHub Issues: https://github.com/nickzhang1102/agentTeams
- 后端日志: `docker compose logs backend`
- 前端日志: `docker compose logs frontend`

---

**Docker 部署文档版本**: 2.0
**更新时间**: 2026-08-25
