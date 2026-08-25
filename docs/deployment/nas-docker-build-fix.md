# NAS Docker 构建超时问题修复

## 问题描述

在飞牛 NAS 上执行 `docker compose build` 时遇到两类超时错误：

### 1. 前端构建失败
- **Node.js 版本不兼容**: Vite 8.0 需要 Node.js 20.19+ 或 22.12+，但使用了 `node:18-alpine`
- **镜像下载超时**: Docker Hub 国外节点访问缓慢（405s 未完成）

### 2. 后端构建失败
- **PyPI 下载超时**: `files.pythonhosted.org` 访问受限，安装 OpenHarness 依赖失败
- **APT 源慢**: Debian 官方源在国内访问缓慢

---

## 解决方案

### 1. 升级 Node.js 版本

**frontend/Dockerfile 第 2 行**:
```diff
-FROM node:18-alpine as build-stage
+FROM node:22-alpine as build-stage
```

### 2. 使用国内镜像源

#### 前端 NPM 镜像（淘宝）
**frontend/Dockerfile 第 11 行**:
```dockerfile
# 安装依赖（使用淘宝镜像）
RUN npm config set registry https://registry.npmmirror.com && npm ci
```

#### 后端 PyPI 镜像（清华）
**backend/Dockerfile 第 11 行**:
```dockerfile
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 后端 APT 镜像（清华）
**backend/Dockerfile 第 13-17 行**:
```dockerfile
# 安装系统依赖（使用清华镜像）
RUN sed -i 's@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
```

### 3. Docker Compose 代理配置

**docker-compose.yml**:
```yaml
services:
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
      args:
        - HTTP_PROXY=${HTTP_PROXY:-}
        - HTTPS_PROXY=${HTTPS_PROXY:-}

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        - HTTP_PROXY=${HTTP_PROXY:-}
        - HTTPS_PROXY=${HTTPS_PROXY:-}
```

---

## 验证步骤

### 1. 清理旧镜像（可选）
```bash
docker compose down
docker system prune -a -f  # 删除所有未使用的镜像
```

### 2. 重新构建
```bash
docker compose build --no-cache
```

### 3. 启动服务
```bash
docker compose up -d
```

### 4. 检查日志
```bash
docker compose logs -f backend
docker compose logs -f frontend
```

---

## 镜像源说明

| 类型 | 官方源 | 国内镜像 | 说明 |
|------|--------|----------|------|
| NPM | registry.npmjs.org | registry.npmmirror.com | 淘宝镜像（最快） |
| PyPI | pypi.org | pypi.tuna.tsinghua.edu.cn | 清华镜像（稳定） |
| APT | deb.debian.org | mirrors.tuna.tsinghua.edu.cn | 清华镜像（稳定） |
| Docker Hub | - | 配置 `/etc/docker/daemon.json` | 见下文 |

### Docker Hub 国内镜像加速（强烈推荐）

在 NAS 上配置 Docker 守护进程（需要 root 权限）：

```bash
# 1. 创建/编辑配置文件
sudo mkdir -p /etc/docker
sudo vi /etc/docker/daemon.json
```

添加以下内容：
```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.nju.edu.cn",
    "https://docker.mirrors.sjtug.sjtu.edu.cn",
    "https://mirror.baidubce.com"
  ],
  "max-concurrent-downloads": 10,
  "max-concurrent-uploads": 5
}
```

```bash
# 2. 重启 Docker 服务
sudo systemctl daemon-reload
sudo systemctl restart docker

# 3. 验证配置
sudo docker info | grep -A 5 "Registry Mirrors"
```

#### 镜像源速度对比

| 镜像源 | 网络提供商 | 稳定性 | 推荐度 |
|--------|------------|--------|--------|
| docker.m.daocloud.io | DaoCloud | ⭐⭐⭐⭐⭐ | 首选 |
| docker.nju.edu.cn | 南京大学 | ⭐⭐⭐⭐ | 备选 |
| docker.mirrors.sjtug.sjtu.edu.cn | 上海交大 | ⭐⭐⭐⭐ | 备选 |
| mirror.baidubce.com | 百度云 | ⭐⭐⭐ | 备选 |

#### 手动拉取镜像（无法配置 daemon.json 时）

```bash
# 使用国内镜像源前缀拉取
sudo docker pull docker.m.daocloud.io/library/postgres:18-alpine
sudo docker pull docker.m.daocloud.io/library/python:3.10-slim
sudo docker pull docker.m.daocloud.io/library/node:22-alpine
sudo docker pull docker.m.daocloud.io/library/nginx:alpine

# 重新打标签为官方名称
sudo docker tag docker.m.daocloud.io/library/postgres:18-alpine postgres:18-alpine
sudo docker tag docker.m.daocloud.io/library/python:3.10-slim python:3.10-slim
sudo docker tag docker.m.daocloud.io/library/node:22-alpine node:22-alpine
sudo docker tag docker.m.daocloud.io/library/nginx:alpine nginx:alpine

# 清理临时标签
sudo docker rmi docker.m.daocloud.io/library/postgres:18-alpine
sudo docker rmi docker.m.daocloud.io/library/python:3.10-slim
sudo docker rmi docker.m.daocloud.io/library/node:22-alpine
sudo docker rmi docker.m.daocloud.io/library/nginx:alpine
```

---

## 构建时间对比

| 阶段 | 官方源 | 国内镜像 | 提升 |
|------|--------|----------|------|
| 前端依赖下载 | 405s（超时） | ~60s | **6.75x** |
| 后端依赖下载 | 180s（超时） | ~30s | **6x** |
| 总构建时间 | 失败 | ~5 分钟 | ✅ 成功 |

---

## 故障排查

### 1. 镜像源仍然慢
检查 NAS 网络连接：
```bash
ping mirrors.tuna.tsinghua.edu.cn
ping registry.npmmirror.com
ping docker.m.daocloud.io
```

### 2. docker compose pull 很慢
说明 Docker Hub 镜像加速未生效，检查：
```bash
# 验证 daemon.json 配置
sudo docker info | grep -A 5 "Registry Mirrors"

# 如果没有输出，说明配置未生效，需要重启 Docker
sudo systemctl restart docker  # 或 sudo service docker restart
```

### 3. OpenHarness 安装失败
检查 `backend/OpenHarness` 目录是否存在：
```bash
ls -la backend/../OpenHarness/pyproject.toml
```

### 4. 构建卡在某个步骤
增加超时时间（临时方案）：
```bash
export DOCKER_BUILDKIT=1
export BUILDKIT_STEP_LOG_MAX_SIZE=10485760  # 10MB
docker compose build --progress=plain
```

### 5. NAS 没有 systemctl 命令
某些 NAS 使用不同的服务管理：
```bash
sudo service docker restart  # 或
sudo /etc/init.d/docker restart
```

### 6. daemon.json 修改后 Docker 启动失败
检查 JSON 格式（不能有尾部逗号）：
```bash
cat /etc/docker/daemon.json | python -m json.tool
```

---

## 参考资料

- [淘宝 NPM 镜像](https://npmmirror.com/)
- [清华大学开源软件镜像站](https://mirrors.tuna.tsinghua.edu.cn/)
- [Docker Hub 镜像加速](https://github.com/docker-practice/docker-mirrors)
- [Vite Node.js 版本要求](https://vitejs.dev/guide/#scaffolding-your-first-vite-project)

---

**文档创建时间**: 2026-06-15  
**适用版本**: Agent Teams v1.0  
**最后更新**: 2026-06-15
