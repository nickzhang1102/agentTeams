# Agent Teams System - 快速入门指南

## 📋 目录

1. [环境要求](#环境要求)
2. [本地开发](#本地开发)
3. [Docker 部署](#docker-部署)
4. [配置说明](#配置说明)
5. [常见问题](#常见问题)

---

## 环境要求

### 本地开发

- **Node.js**: 20.19+（Vite 8 要求）
- **Python**: 3.11+
- **PostgreSQL**: 18+
- **LLM 服务账号**: 一个 OpenAI 兼容的 LLM 服务（启动后在后台“LLM 模型”中配置）

### Docker 部署

- **Docker**: 20.10+
- **Docker Compose**: 2.0+

---

## 本地开发

### 1. 安装 PostgreSQL

**Windows**
```bash
# 下载安装: https://www.postgresql.org/download/windows/
# 或使用 Chocolatey
choco install postgresql18
```

**macOS**
```bash
# 使用 Homebrew
brew install postgresql@18
brew services start postgresql@18
```

**Linux (Ubuntu/Debian)**
```bash
sudo apt update
sudo apt install postgresql-18
sudo systemctl start postgresql
```

### 2. 创建数据库

```bash
# Linux/macOS
sudo -u postgres psql -c "CREATE DATABASE agent_teams;"

# Windows
psql -U postgres -c "CREATE DATABASE agent_teams;"
```

### 3. 配置后端

```bash
# 进入后端目录
cd backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装内嵌的 OpenHarness 框架（本地开发必需，Docker 镜像已自动处理）
pip install -e ../OpenHarness

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置：
# - SECRET_KEY（应用根密钥，数据库凭证将用它加密）
# - JWT_SECRET_KEY
# - DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agent_teams

# 初始化数据库结构
alembic upgrade head

# 创建默认管理员账号（默认密码 admin123，首次登录后请立即修改）
python init_admin.py

# 启动后端
python run.py
```

> LLM 模型、Base URL 与 API Key 在启动后的后台「LLM 模型」页面配置并加密保存，无需写入 .env。

### 4. 配置前端

```bash
# 新终端窗口，进入前端目录
cd frontend

# 安装依赖
npm install

# 启动前端
npm run dev
```

### 5. 访问应用

- **前端**: http://localhost:5173
- **后端 API**: http://localhost:5000/api
- **默认账号**: admin / admin123（仅本地开发 APP_ENV=development 时为固定初始口令，首次登录后请立即修改）

---

## Docker 部署

### 方式一：一键部署（推荐）

**Linux/macOS**
```bash
# 赋予执行权限
chmod +x scripts/docker-deploy.sh

# 执行部署脚本
./scripts/docker-deploy.sh
```

**Windows (PowerShell)**
```powershell
# 执行部署脚本
.\scripts\docker-deploy.ps1
```

### 方式二：手动部署

#### 1. 配置环境变量

```bash
# 复制环境变量模板
cp backend/.env.example backend/.env

# 编辑 backend/.env
# 必须设置：
# - SECRET_KEY=your-secret-key
# - JWT_SECRET_KEY=your-jwt-secret
# - DATABASE_URL 无需手动设置，由 docker compose 自动注入
```

#### 2. 启动服务

```bash
# 构建并启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f
```

#### 3. 访问应用

- **前端**: http://localhost:8380
- **后端 API**: http://localhost:5000/api
- **管理员账号**: 用户名 `admin`。推荐：启动前在 `backend/.env` 设置 `ADMIN_INITIAL_PASSWORD`（至少 8 位、含字母和数字），首次创建 admin 时直接作为初始密码，无需翻查日志；未设置时回退随机生成——见 `docker compose logs backend`（认准最近一次"管理员已创建"的记录）或宿主机 `backend/data/.admin_initial_password`（仅本地开发 APP_ENV=development 时为 admin/admin123）。忘密/被锁重置：`docker compose exec -e ADMIN_INITIAL_PASSWORD='新密码' backend python reset_admin.py`

---

## 配置说明

### 后端环境变量 (`backend/.env`)

| 变量名 | 必填 | 说明 | 示例值 |
|--------|------|------|--------|
| `SECRET_KEY` | ✅ | 应用根密钥（用于加密数据库凭证） | 随机字符串 |
| `JWT_SECRET_KEY` | ✅ | JWT 密钥 | 随机字符串 |
| `ADMIN_INITIAL_PASSWORD` | ❌（推荐） | 首次创建 admin 的初始密码；未设置则随机生成，忘密/被锁用 `reset_admin.py` 重置 | `MyPass2026` |
| `DATABASE_URL` | ✅ | 数据库连接 | `postgresql+psycopg://...` |
| `FILE_STORAGE_PATH` | ❌ | 文件存储路径 | `data/files` |
| `WORKSPACE_DIR` | ❌ | 工作目录 | `data/workspace` |
| `AGENTS_DIR` | ❌ | Agent 目录 | `../agents` |

> LLM 模型与 Exa/Tavily Key 不在 .env 中配置：登录后台 → 「LLM 模型」/「系统设置」，保存后加密入库。

### 生成安全密钥

```bash
# SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
```

### 前端环境变量 (`frontend/.env`)

前端通过 Vite 代理（开发）/ Nginx 代理（生产）转发 `/api` 请求，通常无需额外配置。

---

## 常见问题

### Q1: 数据库连接失败？

**检查项：**
1. PostgreSQL 服务是否启动
2. 数据库 `agent_teams` 是否存在
3. `DATABASE_URL` 配置是否正确
4. 用户名和密码是否正确

**解决方法：**
```bash
# 测试数据库连接
psql -U postgres -d agent_teams -c "SELECT 1;"

# 重新创建数据库
psql -U postgres -c "DROP DATABASE IF EXISTS agent_teams;"
psql -U postgres -c "CREATE DATABASE agent_teams;"

# 重新初始化表结构
cd backend
alembic upgrade head
```

### Q2: Docker 服务无法启动？

**检查项：**
1. Docker 服务是否运行
2. 端口是否被占用（8380, 5000, 5433）
3. 环境变量是否配置

**解决方法：**
```bash
# 查看日志
docker compose logs backend
docker compose logs postgres

# 重启服务
docker compose restart

# 重新构建
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Q3: 前端无法访问后端？

**检查项：**
1. 后端服务是否运行
2. CORS 配置是否正确
3. API 地址是否正确

**解决方法：**
```bash
# 测试后端健康状态
curl http://localhost:5000/health

# 检查前端代理配置
cat frontend/vite.config.js
```

### Q4: 文件上传失败？

**检查项：**
1. 文件大小（限制 10MB）
2. 文件类型是否在支持列表内
3. 存储目录权限

**解决方法：**
```bash
# 创建存储目录
mkdir -p backend/data/files

# 修改权限（Linux/macOS）
chmod -R 755 backend/data
```

支持的文件类型以后端 `backend/utils/upload_validator.py` 中的白名单为准。

### Q5: LLM 调用失败？

**检查项：**
1. 后台「LLM 模型」中是否已添加并启用模型
2. API Key 与 Base URL 是否有效
3. LLM 服务商侧余额/限流是否充足
4. 网络连接是否正常（Exa MCP 配置变更后需重启后端）

### Q6: 如何修改默认密码？

**解决方法：**
1. 登录应用
2. 进入用户设置
3. 修改密码

**或通过数据库修改：**
```bash
# 进入后端容器
docker compose exec backend bash

# 修改密码
python -c "
from database import SessionLocal
from models import User
session = SessionLocal()
try:
    admin = session.query(User).filter_by(username='admin').first()
    admin.set_password('new-password')
    session.commit()
    print('密码已修改')
finally:
    session.close()
"
```

### Q7: 如何备份数据？

**Docker 环境：**
```bash
# 备份数据库
docker compose exec postgres pg_dump -U postgres agent_teams > backup_$(date +%Y%m%d).sql

# 备份文件
tar -czf files_backup_$(date +%Y%m%d).tar.gz backend/data/files
```

**本地环境：**
```bash
# 备份数据库
pg_dump -U postgres agent_teams > backup_$(date +%Y%m%d).sql

# 备份文件
tar -czf files_backup_$(date +%Y%m%d).tar.gz backend/data/files
```

### Q8: 如何恢复数据？

**Docker 环境：**
```bash
# 恢复数据库
cat backup_20260312.sql | docker compose exec -T postgres psql -U postgres agent_teams

# 恢复文件
tar -xzf files_backup_20260312.tar.gz
```

**本地环境：**
```bash
# 恢复数据库
psql -U postgres agent_teams < backup_20260312.sql

# 恢复文件
tar -xzf files_backup_20260312.tar.gz
```

---

## 📚 相关文档

- [Docker 部署文档](./DOCKER.md)
- [医疗 AI 免责声明](./DISCLAIMER.md)
- [Backend 模块文档](./backend/CLAUDE.md)
- [Frontend 模块文档](./frontend/CLAUDE.md)

---

## 🆘 获取帮助

- **项目文档**: `docs/` 目录
- **GitHub Issues**: https://github.com/nickzhang1102/agentTeams/issues
- **查看日志**: `docker compose logs -f`

---

**文档版本**: 1.1
**更新时间**: 2026-08-24
