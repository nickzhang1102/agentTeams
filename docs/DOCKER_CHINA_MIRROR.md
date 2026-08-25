# Docker 国内镜像加速配置指南

## 🚀 快速解决 Docker Hub 访问问题

在国内网络环境下，访问 Docker Hub 可能会很慢或失败。本指南提供多种解决方案。

---

## 方案一：配置 Docker Desktop 镜像加速器（推荐）

### Windows/macOS Docker Desktop 配置

#### 1. 打开 Docker Desktop 设置

1. 右键点击系统托盘中的 Docker Desktop 图标
2. 选择 **Settings**（设置）
3. 点击 **Docker Engine**

#### 2. 添加国内镜像源

在 JSON 配置中添加 `registry-mirrors`：

```json
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false,
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.rainbond.cc",
    "https://dockerhub.icu",
    "https://docker.udayun.com",
    "https://docker.211678.top"
  ]
}
```

**完整的配置示例：**

```json
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false,
  "features": {
    "buildkit": true
  },
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.rainbond.cc",
    "https://dockerhub.icu",
    "https://docker.udayun.com",
    "https://docker.211678.top"
  ]
}
```

#### 3. 应用并重启

1. 点击 **Apply & Restart**
2. 等待 Docker 重启完成

#### 4. 验证配置

```powershell
# 查看配置是否生效
docker info | Select-String "Registry Mirrors"

# 应该看到类似输出：
# Registry Mirrors:
#  https://docker.m.daocloud.io/
#  https://docker.rainbond.cc/
```

---

## 方案二：使用修改后的 Dockerfile（国内镜像源）

### 已为您准备好了使用国内镜像源的 Dockerfile

**文件：`backend/Dockerfile.china`**
**文件：`frontend/Dockerfile.china`**

使用方法：

```powershell
# 使用国内镜像构建
docker-compose -f docker-compose.yml -f docker-compose.china.yml build
```

---

## 方案三：手动拉取镜像并重新标记

如果镜像加速器仍然无法使用，可以手动拉取镜像：

```powershell
# 拉取 Python 镜像
docker pull python:3.10-slim

# 如果拉取失败，使用阿里云镜像
docker pull registry.cn-hangzhou.aliyuncs.com/library/python:3.10-slim
docker tag registry.cn-hangzhou.aliyuncs.com/library/python:3.10-slim python:3.10-slim

# 拉取 Node 镜像
docker pull node:18-alpine

# 拉取 Nginx 镜像
docker pull nginx:alpine

# 拉取 PostgreSQL 镜像
docker pull postgres:18-alpine
```

---

## 方案四：使用代理（如果有）

### 配置 Docker Desktop 使用代理

#### 1. 打开代理设置

1. Docker Desktop → Settings → Resources → Proxies
2. 启用 **Manual proxy configuration**

#### 2. 配置代理

```
HTTP Proxy:  http://your-proxy:port
HTTPS Proxy: https://your-proxy:port
```

#### 3. 应用并重启

点击 **Apply & Restart**

---

## 常见国内镜像源

### Docker Hub 镜像加速器

| 镜像源 | 地址 | 状态 |
|--------|------|------|
| DaoCloud | `https://docker.m.daocloud.io` | ✅ 推荐 |
| Rainbond | `https://docker.rainbond.cc` | ✅ 推荐 |
| DockerHub ICU | `https://dockerhub.icu` | ✅ 可用 |
| Udayun | `https://docker.udayun.com` | ✅ 可用 |
| 211678 | `https://docker.211678.top` | ✅ 可用 |

### NPM 镜像源

```bash
# 临时使用
npm install --registry=https://registry.npmmirror.com

# 永久设置
npm config set registry https://registry.npmmirror.com

# 或使用 cnpm
npm install -g cnpm --registry=https://registry.npmmirror.com
```

### PIP 镜像源

```bash
# 临时使用
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 永久设置
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 验证镜像加速是否生效

### 测试拉取镜像

```powershell
# 清理现有镜像
docker system prune -a

# 重新拉取测试
docker pull python:3.10-slim
docker pull node:18-alpine
docker pull nginx:alpine
docker pull postgres:18-alpine
```

### 查看镜像拉取速度

```powershell
# 查看镜像来源
docker images
docker inspect python:3.10-slim | Select-String "RepoTags"
```

---

## 故障排查

### 问题1: 镜像加速器配置后仍然很慢

**解决方法：**
```powershell
# 1. 重启 Docker Desktop
# 2. 清理 Docker 缓存
docker system prune -a

# 3. 重试拉取镜像
docker pull python:3.10-slim
```

### 问题2: 镜像加速器无法访问

**解决方法：**
```powershell
# 尝试不同的镜像源
# 在 Docker Desktop 设置中更换镜像源
# 或使用方案三手动拉取
```

### 问题3: 构建时仍然访问 Docker Hub

**解决方法：**
```powershell
# 使用国内镜像 Dockerfile
docker-compose -f docker-compose.yml -f docker-compose.china.yml build --no-cache
```

---

## 完整部署流程（国内环境）

### 步骤 1: 配置镜像加速器

按照**方案一**配置 Docker Desktop

### 步骤 2: 预拉取基础镜像

```powershell
# 拉取所有需要的基础镜像
docker pull python:3.10-slim
docker pull node:18-alpine
docker pull nginx:alpine
docker pull postgres:18-alpine
```

### 步骤 3: 构建并启动

```powershell
# 使用国内镜像配置构建
docker-compose -f docker-compose.yml -f docker-compose.china.yml build

# 启动服务
docker-compose up -d
```

### 步骤 4: 初始化数据库

```powershell
docker-compose exec backend python init_db.py
```

---

## 自动化脚本（国内环境）

已为您创建了专门针对国内环境的部署脚本：

**文件：`scripts/docker-deploy-china.ps1`**

使用方法：
```powershell
.\scripts\docker-deploy-china.ps1
```

---

## 附录：各云服务商镜像源

### 阿里云镜像加速

1. 登录 [阿里云容器镜像服务](https://cr.console.aliyun.com/)
2. 获取您的专属加速器地址：`https://xxxxxx.mirror.aliyuncs.com`
3. 添加到 Docker Desktop 配置中

### 腾讯云镜像加速

```
https://mirror.ccs.tencentyun.com
```

### 网易云镜像加速

```
https://hub-mirror.c.163.com
```

### 中科大镜像加速

```
https://docker.mirrors.ustc.edu.cn
```

---

**文档版本**: 1.0
**更新时间**: 2026-03-12
