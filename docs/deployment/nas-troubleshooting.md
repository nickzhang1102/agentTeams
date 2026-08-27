# NAS Docker 部署故障排查

> 飞牛 NAS / 群晖 / QNAP 等 NAS 设备的 Docker 部署常见问题与解决方案

---

## 问题 1：version 警告

### 错误信息

```
WARN[0000] /vol1/docker/agentTeams/docker-compose.yml: 
the attribute `version` is obsolete, it will be ignored
```

### 原因

Docker Compose V2 不再需要 `version` 字段。

### 解决方案

**已修复**：`docker-compose.yml` 已移除 `version: '3.8'`。

如果你使用的是旧版本，可以忽略此警告（不影响功能）。

---

## 问题 2：权限错误 (mkdir /home/znick: permission denied)

### 错误信息

```
[+] Building 0.0s (0/0)
mkdir /home/znick: permission denied
```

### 原因

Docker 构建时尝试在用户主目录创建文件，但 NAS 用户权限不足。

### 解决方案 A：使用 sudo（推荐）

```bash
cd /vol1/docker/agentTeams
sudo docker compose build --no-cache
```

### 解决方案 B：修改用户权限

```bash
# 将当前用户添加到 docker 组
sudo usermod -aG docker $USER

# 重新登录 SSH 使权限生效
exit
# 重新 ssh 登录
ssh admin@nas-ip

# 验证
docker ps
# 如无 permission denied 则成功
```

### 解决方案 C：修改 Dockerfile（已应用）

**已修复**：`backend/Dockerfile` 添加 `ENV HOME=/app`，避免访问用户主目录。

---

## 问题 3：构建超时或卡住

### 错误信息

```
[+] Building 300.5s (4/12)
=> [internal] load build context
```

### 原因

1. 网络慢，拉取基础镜像超时
2. 复制文件过多（如 node_modules, .git）

### 解决方案 A：配置 Docker 镜像加速

```bash
# 编辑 Docker 配置
sudo nano /etc/docker/daemon.json

# 添加以下内容
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.rainbond.cc",
    "https://dockerhub.icu"
  ]
}

# 重启 Docker
sudo systemctl restart docker
```

### 解决方案 B：检查 .dockerignore

确保 `.dockerignore` 包含：

```
node_modules/
.git/
venv/
__pycache__/
*.pyc
```

### 解决方案 C：手动拉取基础镜像

```bash
# 通过镜像加速器拉取
sudo docker pull registry.cn-hangzhou.aliyuncs.com/library/python:3.10-slim
sudo docker tag registry.cn-hangzhou.aliyuncs.com/library/python:3.10-slim python:3.10-slim

# 验证
sudo docker images | grep python
```

---

## 问题 4：OpenHarness 安装失败

### 错误信息

```
ERROR: Directory '/app/OpenHarness' is not installable. Neither 'setup.py' nor 'pyproject.toml' found.
```

### 原因

OpenHarness 目录不完整或不存在。

### 解决方案

```bash
# 检查目录结构
ls -la /vol1/docker/agentTeams/OpenHarness/src/openharness/

# 预期输出：
# -rw-r--r--  __init__.py
# -rw-r--r--  cli.py
# drwxr-xr-x  coordinator/

# 如不存在，重新上传
# 本地：
cd D:\dev
tar -czf OpenHarness.tar.gz OpenHarness
scp OpenHarness.tar.gz admin@nas-ip:/vol1/docker/agentTeams/

# NAS：
cd /vol1/docker/agentTeams
tar -xzf OpenHarness.tar.gz
rm OpenHarness.tar.gz
```

---

## 问题 5：前端构建失败（内存不足）

### 错误信息

```
Killed
npm ERR! code ELIFECYCLE
npm ERR! errno 137
```

### 原因

NAS 内存不足，npm 构建被 OOM Killer 杀死。

### 解决方案 A：限制 Node.js 内存

修改 `frontend/Dockerfile`：

```dockerfile
# 构建阶段限制内存
RUN NODE_OPTIONS="--max-old-space-size=2048" npm run build
```

### 解决方案 B：本地构建后上传

```bash
# Windows 本地构建
cd D:\dev\agentTeams\frontend
npm run build

# 打包 dist
tar -czf dist.tar.gz dist

# 上传到 NAS
scp dist.tar.gz admin@nas-ip:/vol1/docker/agentTeams/frontend/

# 修改 frontend/Dockerfile，跳过构建步骤
# FROM nginx:alpine
# COPY dist /usr/share/nginx/html
# ...
```

---

## 问题 6：PostgreSQL 容器启动失败

### 错误信息 A（数据目录非空）

```
postgres  | initdb: error: directory "/var/lib/postgresql/data" exists but is not empty
```

### 原因 A

数据卷已存在旧数据，且格式不兼容。

### 解决方案 A

```bash
# 停止所有服务
sudo docker compose down

# 删除数据卷（⚠️ 数据会丢失）
sudo docker volume rm agentteams_postgres_data

# 重新启动
sudo docker compose up -d postgres

# 查看日志确认启动成功
sudo docker compose logs postgres
```

### 错误信息 B：PostgreSQL 18+ 数据目录布局变更（unused mount/volume）

```
agent-teams-postgres  | Error: in 18+, these Docker images are configured to store database data in a
agent-teams-postgres  |        format which is compatible with "pg_ctlcluster" ...
agent-teams-postgres  |        Counter to that, there appears to be PostgreSQL data in:
agent-teams-postgres  |          /var/lib/postgresql/data (unused mount/volume)
```

### 原因 B

PostgreSQL 18 起官方镜像将默认数据目录改为 `/var/lib/postgresql/<主版本>/docker`
（[PR #1259](https://github.com/docker-library/postgres/pull/1259)），compose 应把数据卷挂载到
`/var/lib/postgresql` 而不是旧的 `/var/lib/postgresql/data`。若数据库此前按旧布局初始化在卷根目录、
compose 又仍挂在 `/var/lib/postgresql/data`，entrypoint 检测到这份数据「未被使用」就会拒绝启动，
防止你以为在用旧库实际却在空库上运行。

### 解决方案 B-1：无需保留数据（测试环境推荐）

1. 将 `docker-compose.yml` 中 postgres 的挂载改为：
   ```yaml
   volumes:
     - postgres_data:/var/lib/postgresql
   ```
2. 清掉旧布局的数据卷后重建：
   ```bash
   sudo docker compose down
   # postgres_data 是本栈唯一的 named volume；卷名前缀随部署目录变化，可先 docker volume ls 核对
   sudo docker volume rm agentteams_postgres_data
   sudo docker compose up -d
   ```
   首次启动会重新执行 `docker/init-db.sql` 完成初始化。

### 解决方案 B-2：需要保留数据

先确认卷内数据的 PostgreSQL 主版本：

```bash
docker run --rm -v agentteams_postgres_data:/d:ro pgvector/pgvector:pg18 cat /d/PG_VERSION
```

**输出为 `18`**（本仓库一直使用 pg18 镜像，多数属于这种情况）——数据本身无需升级，
只是目录布局是旧的，把它整体搬进新布局的版本化子目录即可：

```bash
sudo docker compose down

# mv 原样保留文件属主与权限，不要 chown
docker run --rm -v agentteams_postgres_data:/d alpine sh -c '
  set -e
  mkdir -p /d/18/docker
  cd /d
  for f in .* * ; do
    case "$f" in .|..|18) continue ;; esac
    mv "$f" /d/18/docker/
  done
'

# 核对：卷根下只剩 18/，集群文件都在 18/docker/
docker run --rm -v agentteams_postgres_data:/d alpine ls -la /d /d/18/docker
```

然后把 `docker-compose.yml` 挂载点改为 `/var/lib/postgresql` 并重启：

```bash
sudo docker compose up -d
sudo docker compose logs postgres
# 出现 “database system is ready to accept connections” 即迁移成功，原数据原样可用
```

**输出不是 `18`**（例如 17 或更早的主版本）：仅移动目录无法解决，需走 dump/restore——
用对应旧版本镜像临时起容器 `pg_dumpall` 导出 SQL，再导入全新初始化的新布局库；
跨大版本升级的完整讨论见 [docker-library/postgres#37](https://github.com/docker-library/postgres/issues/37)。

---

## 问题 7：后端容器无法连接数据库

### 错误信息

```
sqlalchemy.exc.OperationalError: connection to server at "localhost" (127.0.0.1), port 5432 failed
```

### 原因

`backend/.env` 中 `DATABASE_URL` 使用了 `localhost`，容器内无法访问。

### 解决方案

确认 `backend/.env` 配置：

```bash
# ❌ 错误（本地开发用）
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agent_teams

# ✅ 正确（Docker 环境用服务名）
# 注意：docker-compose.yml 会自动覆盖此项，无需手动修改
```

验证 `docker-compose.yml`：

```yaml
services:
  backend:
    environment:
      - DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/agent_teams
      #                                                       ^^^^^^^^ 使用服务名
```

---

## 问题 8：端口冲突

### 错误信息

```
Error starting userland proxy: listen tcp 0.0.0.0:5432: bind: address already in use
```

### 原因

NAS 上已有服务占用端口（如 PostgreSQL、其他容器）。

### 解决方案

```bash
# 查看端口占用
sudo netstat -tuln | grep -E '5432|5000|8380'

# 修改 docker-compose.yml 端口映射
services:
  postgres:
    ports:
      - "5433:5432"  # 修改为 5433
  backend:
    ports:
      - "5001:5000"  # 修改为 5001
  frontend:
    ports:
      - "8081:80"    # 修改为 8081
```

---

## 问题 9：访问前端显示 502 Bad Gateway

### 原因

后端容器未启动或启动失败。

### 排查步骤

```bash
# 1. 检查容器状态
sudo docker compose ps

# 预期：backend 显示 Up (healthy)
# 如显示 Restarting 或 Exited，查看日志

# 2. 查看后端日志
sudo docker compose logs backend | tail -50

# 常见错误：
# - SECRET_KEY 未设置
# - LLM_API_KEY 未配置
# - 数据库连接失败

# 3. 手动测试后端
sudo docker compose exec backend curl http://localhost:5000/health
# 预期：{"status":"healthy"}
```

---

## 问题 10：登录后白屏或 CORS 错误

### 错误信息（浏览器控制台）

```
Access to XMLHttpRequest at 'http://192.168.1.100:5000/api/auth/login' 
from origin 'http://192.168.1.100:8380' has been blocked by CORS policy
```

### 原因

后端 CORS 配置未包含 NAS 局域网 IP。

### 解决方案

编辑 `backend/.env`：

```bash
CORS_ORIGINS=http://localhost:5173,http://192.168.1.100:8380,http://your-nas-ip:8380
```

重启后端：

```bash
sudo docker compose restart backend
```

详见：`docs/deployment/cors-configuration.md`

---

## 通用排查流程

### 1. 检查容器状态

```bash
sudo docker compose ps
```

### 2. 查看所有日志

```bash
sudo docker compose logs --tail=100
```

### 3. 查看单个服务日志

```bash
sudo docker compose logs backend -f
```

### 4. 进入容器调试

```bash
# 进入后端容器
sudo docker compose exec backend bash

# 检查环境变量
env | grep -E 'SECRET|DATABASE|LLM'

# 检查 Python 包
pip list | grep openharness

# 测试数据库连接
python -c "from sqlalchemy import create_engine; engine = create_engine('postgresql+psycopg://postgres:postgres@postgres:5432/agent_teams'); conn = engine.connect(); print('Connected')"
```

### 5. 重新构建（清除缓存）

```bash
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
```

---

## 群晖 NAS 特定问题

### 问题：Container Station 无法使用 sudo

**解决**：通过 SSH 使用管理员账户登录后才有 sudo 权限。

```bash
# 启用 SSH
# 控制面板 → 终端机和 SNMP → 启用 SSH 服务

# 使用管理员账户登录
ssh admin@synology-ip
```

### 问题：Docker 命令找不到

**解决**：手动添加到 PATH。

```bash
export PATH=$PATH:/usr/local/bin
docker --version
```

---

## QNAP NAS 特定问题

### 问题：opkg 包管理器缺失

**解决**：安装 Entware。

```bash
# QNAP 官方指南
# https://wiki.qnap.com/wiki/Install_Entware

# 或通过 App Center 安装 "Entware"
```

---

## 完整部署检查清单

- [ ] OpenHarness 目录完整（`ls -la OpenHarness/src/openharness/`）
- [ ] `.env` 文件已创建并填写必填项
- [ ] SECRET_KEY 和 JWT_SECRET_KEY 已生成
- [ ] LLM_API_KEY 已配置
- [ ] Docker 镜像加速已配置（国内网络）
- [ ] 端口无冲突（5432, 5000, 8380）
- [ ] 用户在 docker 组或使用 sudo
- [ ] CORS_ORIGINS 包含 NAS IP
- [ ] 数据目录有写权限（`/vol1/docker/agentTeams/backend/data`）

---

**更新时间**: 2026-06-15  
**适用版本**: Agent Teams v2.0 (FastAPI + Docker)
