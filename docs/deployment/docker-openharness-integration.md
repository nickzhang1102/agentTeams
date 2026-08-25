# Docker 环境集成 OpenHarness

> **创建时间**: 2026-06-14  
> **状态**: ✅ 已完成  
> **作者**: Claude Code

---

## 问题背景

`backend/requirements.txt` 中 OpenHarness 曾使用可编辑安装：

```txt
pip install -e /path/to/OpenHarness
```

此方式依赖宿主机路径，Docker 容器内无法访问 `D:\dev\OpenHarness`，导致镜像构建失败。

**当前状态**：
- OpenHarness **未发布到 PyPI**，无法通过 `pip install openharness-ai` 安装
- 项目已将 OpenHarness 源码纳入根目录 `OpenHarness/`
- Docker 构建时从项目根目录复制源码并安装

---

## 解决方案

采用**源码复制方案**：将 OpenHarness 源码纳入项目，构建时复制到容器内安装。

---

## 实施步骤

### 1. 项目结构调整

将 OpenHarness 复制到项目根目录：

```bash
cd D:\dev\agentTeams
xcopy /E /I D:\dev\OpenHarness OpenHarness
```

**目标结构**：
```
agentTeams/
├── backend/
├── frontend/
├── OpenHarness/         # ← 新增
│   ├── src/
│   │   └── openharness/  # ← 核心源码
│   ├── pyproject.toml
│   └── setup.py
├── docker-compose.yml
└── .dockerignore
```

### 2. 修改 `backend/Dockerfile`

```dockerfile
# Agent Teams Backend - FastAPI + Uvicorn
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

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

# 创建数据目录
RUN mkdir -p /app/data/files /app/data/workspace

# 暴露端口
EXPOSE 5000

# 设置环境变量
ENV APP_ENV=production
ENV PYTHONUNBUFFERED=1

# 启动脚本已包含在 COPY . . 中，仅需赋予执行权限
RUN chmod +x /app/docker-entrypoint.sh

# 启动命令（先执行 Alembic 迁移，再启动 uvicorn）
ENTRYPOINT ["/app/docker-entrypoint.sh"]
```

**关键变更**：
- **第 14-17 行**：在安装依赖前先复制并安装 OpenHarness
- **第 20 行**：修改 COPY 路径为 `backend/` 相对路径

### 3. 修改 `docker-compose.yml`

```yaml
services:
  backend:
    build:
      context: .              # ← 改为根目录
      dockerfile: backend/Dockerfile
```

**关键变更**：
- `context` 从 `./backend` 改为 `.`（根目录），使 Dockerfile 能访问 `OpenHarness/`

### 4. 修改 `backend/requirements.txt`

```diff
- openharness-ai==0.1.9  # 本地可编辑安装覆盖此版本：pip install -e /path/to/OpenHarness
+ # openharness-ai==0.1.9  # Docker 中从项目根目录复制源码安装（见 Dockerfile）
```

**原因**：避免 pip 尝试从 PyPI 安装，与 Dockerfile 中的可编辑安装冲突。

### 5. 更新 `.dockerignore`

```diff
  # 其他
  .claude/
  design-system/
+ 
+ # 但不要忽略 OpenHarness 源码（需要复制到容器）
+ !OpenHarness/
```

**原因**：确保 `OpenHarness/` 目录不被忽略，能正确复制到构建上下文。

---

## 验证步骤

### 1. 构建镜像

```bash
cd D:\dev\agentTeams
docker compose build backend
```

**预期输出**：
```
[+] Building 45.2s (15/15) FINISHED
 => CACHED [1/9] FROM python:3.10-slim
 => [2/9] COPY OpenHarness /app/OpenHarness
 => [3/9] RUN pip install --no-cache-dir -e /app/OpenHarness
 => [4/9] COPY backend/requirements.txt .
 ...
```

### 2. 验证安装

```bash
docker compose up -d backend
docker compose exec backend python -c "import openharness; print(openharness.__version__)"
```

**预期输出**：
```
0.1.9
```

### 3. 检查 API 健康状态

```bash
curl http://localhost:5000/health
```

**预期输出**：
```json
{"status": "healthy"}
```

---

## 注意事项

### 1. 开发同步

**问题**：`D:\dev\OpenHarness` 修改后，需手动同步到 `agentTeams/OpenHarness/`。

**解决方案**：

**选项 A**：Git 子模块（推荐）
```bash
cd D:\dev\agentTeams
git submodule add file:///D:/dev/OpenHarness OpenHarness
git submodule update --remote  # 更新到最新版本
```

**选项 B**：符号链接（Windows 需管理员权限）
```powershell
cd D:\dev\agentTeams
New-Item -ItemType SymbolicLink -Path OpenHarness -Target D:\dev\OpenHarness
```

**选项 C**：手动同步脚本
```bash
# sync-openharness.sh
rsync -av --delete D:/dev/OpenHarness/ OpenHarness/
```

### 2. `.dockerignore` 陷阱

Docker 的 `!` 规则（排除忽略）仅在父目录未被忽略时生效。如果 `.dockerignore` 中有：

```
*
!OpenHarness/
```

`OpenHarness/` 仍会被忽略，因为 `*` 已匹配所有。**正确做法**：明确列出需忽略的目录，而非使用通配符。

### 3. 本地开发热重载

**问题**：容器内 OpenHarness 为静态副本，修改不生效。

**解决方案**：`docker-compose.yml` 中添加 volume 挂载（仅用于本地开发）：

```yaml
services:
  backend:
    volumes:
      - D:/dev/OpenHarness:/app/OpenHarness  # ← 开发环境热重载
```

**注意**：生产环境移除此挂载，避免依赖宿主机路径。

### 4. 生产环境优化

**当前方案**适用于开发与私有部署。生产环境可考虑：

**选项 A**：私有 PyPI 服务器
```bash
# 打包 OpenHarness
cd D:\dev\OpenHarness
python -m build
twine upload --repository-url https://pypi.your-company.com dist/*

# requirements.txt
openharness-ai==0.1.9 --index-url https://pypi.your-company.com/simple
```

**选项 B**：私有 Git 仓库 + SSH 密钥
```dockerfile
# Dockerfile
RUN --mount=type=ssh \
    pip install git+ssh://git@github.com/your-org/OpenHarness.git@main
```

---

## 故障排查

### 问题 1：`COPY OpenHarness /app/OpenHarness` 失败

**错误信息**：
```
ERROR [2/9] COPY OpenHarness /app/OpenHarness
failed to compute cache key: "/OpenHarness" not found
```

**原因**：
1. `OpenHarness/` 目录不存在于项目根目录
2. `.dockerignore` 忽略了 `OpenHarness/`

**解决**：
```bash
# 检查目录是否存在
ls -la D:/dev/agentTeams/OpenHarness

# 检查 .dockerignore
grep -i openharness D:/dev/agentTeams/.dockerignore
```

### 问题 2：容器内 `import openharness` 失败

**错误信息**：
```
ModuleNotFoundError: No module named 'openharness'
```

**原因**：
1. OpenHarness 未正确安装
2. 包名不匹配（源码包名为 `openharness_ai`）

**解决**：
```bash
# 进入容器检查
docker compose exec backend bash
pip list | grep -i harness
python -c "import sys; print('\n'.join(sys.path))"
```

### 问题 3：构建缓存导致修改未生效

**解决**：
```bash
# 强制重新构建
docker compose build --no-cache backend
```

---

## 相关文档

- [Backend Dockerfile](../../backend/Dockerfile)
- [Docker Compose 配置](../../docker-compose.yml)
- [Backend CLAUDE.md](../../backend/CLAUDE.md)

---

## 变更历史

| 日期 | 版本 | 变更说明 |
|------|------|----------|
| 2026-06-14 | 1.0 | 初始版本，完成 Docker 集成 OpenHarness |
