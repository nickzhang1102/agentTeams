# CORS 跨域配置指南

> 配置后端允许的前端访问来源

---

## 问题场景

### 场景 1：局域网访问被拒绝

**现象**：
```
浏览器控制台错误：
Access to XMLHttpRequest at 'http://192.168.1.100:5000/api/auth/login' 
from origin 'http://192.168.1.100:8380' has been blocked by CORS policy
```

**原因**：后端默认仅允许 `localhost:5173`，局域网 IP 未在白名单中。

### 场景 2：域名访问被拒绝

**现象**：
```
浏览器控制台错误：
Access to XMLHttpRequest at 'https://api.yourdomain.com/api/health' 
from origin 'https://yourdomain.com' has been blocked by CORS policy
```

**原因**：后端默认仅允许本地开发地址，生产域名未在白名单中。

---

## 配置方法

### 1. 编辑 `backend/.env`

添加或修改 `CORS_ORIGINS` 配置项：

```bash
# 开发环境（默认）
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# 开发 + 局域网访问
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.100:8380

# 开发 + 局域网 + 公网域名
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.100:8380,https://yourdomain.com

# 生产环境（仅域名）
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

**格式说明**：
- 多个来源用**英文逗号**分隔，不要有空格
- 必须包含**完整协议**（`http://` 或 `https://`）
- 必须包含**端口号**（如果非默认端口）
- 不要在末尾加斜杠 `/`

### 2. 重启后端服务

**Docker 部署**：
```bash
docker compose restart backend
```

**本地开发**：
```bash
# Ctrl+C 停止，然后重新运行
python run.py
```

---

## 常见配置示例

### 示例 1：本地开发

```bash
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### 示例 2：NAS 局域网部署

```bash
# NAS IP: 192.168.1.100，前端端口: 8380
CORS_ORIGINS=http://192.168.1.100:8380,http://localhost:8380
```

### 示例 3：多设备局域网访问

```bash
# 开发机 + 测试机 + NAS
CORS_ORIGINS=http://localhost:5173,http://192.168.1.100:8380,http://192.168.1.200:8380
```

### 示例 4：内网穿透 + 本地开发

```bash
# 花生壳/cpolar 等内网穿透
CORS_ORIGINS=http://localhost:5173,https://abc123.cpolar.cn
```

### 示例 5：生产环境多域名

```bash
# 主域名 + www 子域名 + API 子域名
CORS_ORIGINS=https://example.com,https://www.example.com,https://app.example.com
```

### 示例 6：开发 + 预发布 + 生产

```bash
CORS_ORIGINS=http://localhost:5173,https://dev.example.com,https://staging.example.com,https://example.com
```

---

## 安全建议

### ❌ 不推荐：允许所有来源

```python
# 不要这样配置！
allow_origins=["*"]
```

**风险**：
- 任何网站都可调用你的 API
- 容易被 CSRF 攻击
- 用户凭证可能泄露

### ✅ 推荐：明确指定白名单

```bash
# 只允许已知的可信来源
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### ✅ 推荐：生产环境仅 HTTPS

```bash
# 生产环境禁用 HTTP
CORS_ORIGINS=https://yourdomain.com
```

### ✅ 推荐：定期审计白名单

```bash
# 移除不再使用的旧域名
# 检查测试域名是否误配置到生产环境
```

---

## 验证配置

### 方法 1：浏览器控制台

1. 打开前端页面（如 `http://192.168.1.100:8380`）
2. 按 `F12` 打开开发者工具
3. 切换到 **Network** 标签
4. 发送一个 API 请求（如登录）
5. 检查响应头：

```http
Access-Control-Allow-Origin: http://192.168.1.100:8380
Access-Control-Allow-Credentials: true
```

### 方法 2：curl 测试

```bash
curl -I \
  -H "Origin: http://192.168.1.100:8380" \
  -H "Access-Control-Request-Method: POST" \
  -X OPTIONS \
  http://192.168.1.100:5000/api/auth/login

# 预期输出包含：
# Access-Control-Allow-Origin: http://192.168.1.100:8380
# Access-Control-Allow-Methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
```

### 方法 3：检查后端日志

```bash
# Docker 部署
docker compose logs backend | grep CORS

# 本地开发
# 查看终端输出，应显示：
# INFO: CORS enabled for origins: ['http://localhost:5173', 'http://192.168.1.100:8380']
```

---

## 故障排查

### 问题 1：配置后仍然 CORS 错误

**检查清单**：
1. 确认 `.env` 文件已保存
2. 确认后端服务已重启
3. 确认浏览器缓存已清除（`Ctrl+Shift+Delete`）
4. 确认 `CORS_ORIGINS` 格式正确（无多余空格、无末尾斜杠）
5. 确认协议匹配（HTTP vs HTTPS）
6. 确认端口号正确

### 问题 2：配置了但仍显示 localhost

**原因**：Docker Compose 可能覆盖了 `.env` 配置。

**解决**：
```bash
# 检查 docker-compose.yml 是否硬编码了环境变量
grep -A 10 "environment:" docker-compose.yml

# 如有 CORS_ORIGINS 硬编码，删除该行，改为从 .env 读取
```

### 问题 3：配置了 HTTPS 但报错

**错误**：
```
Mixed Content: The page at 'https://example.com' was loaded over HTTPS, 
but requested an insecure XMLHttpRequest endpoint 'http://api.example.com/api/...'
```

**原因**：HTTPS 前端无法请求 HTTP 后端（浏览器安全限制）。

**解决**：
- 后端也配置 HTTPS（通过 Nginx 反向代理 + SSL 证书）
- 或前端改用 HTTP（不推荐生产环境）

---

## Docker 部署特殊说明

### Nginx 代理模式（推荐）

**架构**：
```
浏览器 → Nginx (8380) → 
           ├─ /      → 前端静态文件
           └─ /api/  → 后端 (5000)
```

**CORS 配置**：
```bash
# 前后端同域，无需配置 CORS
# Nginx 统一处理所有请求
CORS_ORIGINS=
```

**优势**：
- 无跨域问题
- 统一入口，易于管理
- 支持 HTTPS 配置

### 分离部署模式

**架构**：
```
浏览器 → 前端 (8380)
      ↘ 后端 (5000)
```

**CORS 配置**：
```bash
# 必须配置跨域
CORS_ORIGINS=http://nas-ip:8380
```

---

## 相关配置文件

- **后端配置**：`backend/config.py:41`
- **CORS 中间件注册**：`backend/app.py:197-210`
- **环境变量模板**：`backend/.env.example`
- **Docker Compose**：`docker-compose.yml`

---

**更新时间**: 2026-06-15  
**适用版本**: Agent Teams v2.0 (FastAPI)
