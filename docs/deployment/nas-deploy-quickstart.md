# 飞牛 NAS 部署快速指引

> 适用于 Synology、QNAP、TrueNAS 等 NAS 设备的快速部署流程

---

## 前置准备

**两种部署方式任选其一**：

### 方式 A：完整打包上传（推荐）

```bash
# 1. 本地打包整个项目（已包含 OpenHarness）
cd D:\dev\agentTeams
tar -czf agentTeams-full.tar.gz --exclude=node_modules --exclude=venv --exclude=.git .

# 2. 上传到 NAS
scp agentTeams-full.tar.gz admin@<NAS-IP>:/volume1/docker/
```

### 方式 B：Git 克隆 + OpenHarness 补充

```bash
# 1. 仅打包 OpenHarness（如 Git 仓库不包含完整源码）
cd D:\dev
tar -czf OpenHarness.tar.gz OpenHarness

# 2. 上传到 NAS
scp OpenHarness.tar.gz admin@<NAS-IP>:/volume1/docker/

# 注：项目主体通过 Git 克隆
```

---

## NAS 上操作

### 如使用方式 A（完整打包）

```bash
# 3. SSH 登录 NAS
ssh admin@<NAS-IP>

# 4. 解压项目（已包含 OpenHarness）
cd /volume1/docker  # TrueNAS 改为 /mnt/pool1/docker
mkdir agentTeams && cd agentTeams
tar -xzf ../agentTeams-full.tar.gz
rm ../agentTeams-full.tar.gz

# 5. 验证 OpenHarness 已包含
ls -la OpenHarness/src/openharness/
# 预期输出：显示 __init__.py, cli.py, coordinator/ 等文件
```

### 如使用方式 B（Git + OpenHarness）

```bash
# 3. SSH 登录 NAS
ssh admin@<NAS-IP>

# 4. 克隆项目
cd /volume1/docker
git clone https://github.com/your-org/agentTeams.git
cd agentTeams

# 5. 检查 OpenHarness 是否完整
ls -la OpenHarness/src/openharness/
# 如为空或不存在，解压之前上传的 OpenHarness.tar.gz：
tar -xzf ../OpenHarness.tar.gz
rm ../OpenHarness.tar.gz
```

### 通用步骤（两种方式都需要）

```bash
# 6. 配置环境变量（⚠️ 必须在构建前完成）
cp backend/.env.example backend/.env
nano backend/.env  # 填写必填项（见下方）
```

---

## 环境变量填写（nano 编辑器中）

**必填项清单**：

```bash
# ==================== 安全密钥（必须） ====================
# 运行下面命令生成，然后粘贴到这里：
# python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<粘贴生成的 64 字符十六进制串>
JWT_SECRET_KEY=<粘贴另一个生成的 64 字符十六进制串>

# ==================== LLM API（必须） ====================
LLM_API_KEY=<你的 API Key>
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_MODEL=ep-xxxxxxxx  # 你的模型端点 ID

# ==================== 其他（可选） ====================
LOG_LEVEL=info
```

**生成密钥命令**（在 NAS 终端运行）：

```bash
# 生成 SECRET_KEY（复制输出）
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"

# 生成 JWT_SECRET_KEY（复制输出）
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_hex(32))"

# 注意：
# - Linux/NAS 系统：使用 python3 命令
# - Windows 系统：使用 python 命令
# - 如命令不存在，先安装 Python 3.8+
```

**保存并退出 nano**：
- `Ctrl + O` → 确认保存
- `Enter` → 确认文件名
- `Ctrl + X` → 退出编辑器

---

## 构建与启动

```bash
# 7. 构建镜像
sudo docker compose build --no-cache

# 8. 启动服务
sudo docker compose up -d

# 9. 验证部署
sudo docker compose ps
curl http://localhost:5000/health
curl http://localhost:8380
```

**预期输出**：

```
NAME                     STATUS         PORTS
agent-teams-postgres     Up (healthy)   0.0.0.0:5432->5432/tcp
agent-teams-backend      Up (healthy)   0.0.0.0:5000->5000/tcp
agent-teams-frontend     Up (healthy)   0.0.0.0:8380->80/tcp
```

---

## 浏览器访问

```
http://<NAS-IP>:8380
```

**管理员账号**（首次访问）：
- 用户名：`admin`
- 密码：推荐部署前在 `backend/.env` 设置 `ADMIN_INITIAL_PASSWORD`，首次创建时直接作为初始密码；未设置则随机生成——见 `docker compose logs backend` 最近一次"管理员已创建"的输出，或 `backend/data/.admin_initial_password` 文件（仅 APP_ENV=development 时为 `admin/admin123`）

⚠️ **忘记密码或被锁**：`docker compose exec -e ADMIN_INITIAL_PASSWORD='新密码' backend python reset_admin.py`

---

## 常见问题

### 1. 找不到 Python 命令

```bash
# 检查 Python 安装
which python3 || which python

# 如未安装（QNAP）
opkg install python3

# 如未安装（Synology）
# 套件中心 → 搜索 "Python3" → 安装
```

### 2. 端口被占用

```bash
# 检查端口占用
netstat -tuln | grep -E '5432|5000|8380'

# 修改 docker-compose.yml 端口映射
# 例如将前端改为 8081：
#   ports:
#     - "8081:80"
```

### 3. 构建失败：找不到 OpenHarness

```bash
# 检查目录结构
ls -la OpenHarness/src/openharness/

# 预期输出：
# -rw-r--r--  __init__.py
# -rw-r--r--  cli.py
# drwxr-xr-x  coordinator/
# drwxr-xr-x  commands/
```

### 4. 后端启动失败：SECRET_KEY 未设置

```bash
# 检查 .env 文件是否存在
cat backend/.env | grep -E 'SECRET_KEY|JWT_SECRET_KEY'

# 如为空，重新编辑填写
nano backend/.env
```

### 5. 访问 8380 显示 502 Bad Gateway

```bash
# 查看后端日志
docker compose logs backend

# 常见原因：LLM_API_KEY 配置错误或网络不通
# 解决：检查 backend/.env 中 LLM_API_KEY / LLM_BASE_URL
```

---

## 后续维护

### 查看日志

```bash
docker compose logs -f           # 所有服务
docker compose logs -f backend   # 仅后端
```

### 重启服务

```bash
docker compose restart           # 全部重启
docker compose restart backend   # 仅重启后端
```

### 停止服务

```bash
docker compose down              # 停止（保留数据）
docker compose down -v           # 停止并删除数据卷（⚠️ 数据丢失）
```

### 更新代码

```bash
# 本地重新打包上传，然后：
cd /volume1/docker/agentTeams
docker compose down
docker compose build --no-cache
docker compose up -d
```

### 数据备份

```bash
# 备份数据库
docker compose exec postgres pg_dump -U postgres agent_teams > backup_$(date +%Y%m%d).sql

# 备份文件存储
tar -czf files_backup_$(date +%Y%m%d).tar.gz backend/data/files
```

---

## 相关文档

- [完整部署文档](./docker-deploy.md)
- [OpenHarness 集成文档](./docker-openharness-integration.md)
- [Docker 国内镜像加速](../DOCKER_CHINA_MIRROR.md)

---

**更新时间**: 2026-06-14  
**适用版本**: Agent Teams v2.0 + FastAPI + PostgreSQL 18
