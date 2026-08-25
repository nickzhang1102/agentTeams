# Agent Teams System

> 团队导向的多智能体协作平台，基于 Vue3+Vite 前端和 FastAPI 后端，支持 SSE 实时流式对话、Agent 团队协作与 Leader 智能编排（LangGraph）。
>
> 🌐 **在线展示站**：[https://nickzhang1102.github.io/agentTeams/](https://nickzhang1102.github.io/agentTeams/)

简体中文 | [English](./README.en.md)

[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-20.19+-green.svg)](https://nodejs.org/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-18-blue.svg)](https://www.postgresql.org/)

## 🎯 项目特性

### 核心功能
- ✅ **JWT 用户认证** - 安全的用户注册登录系统
- ✅ **SSE 流式对话** - 实时 AI 对话体验
- ✅ **Markdown 渲染** - 支持代码高亮的富文本显示
- ✅ **文件管理** - 上传/下载/预览/版本管理
- ✅ **对话管理** - CRUD、归档、共享设置
- ✅ **知识图谱** - D3 可视化、GraphRAG 检索、知识缺口分析

### Agent 系统
- ✅ **100+ 内置专家 Agent** - 覆盖医疗专科、商业角色、金融期货等领域
- ✅ **Agent 团队协作** - 并行执行，智能聚合
- ✅ **Leader Agent** - 需求评估、团队组建（DAG 编排）、结果汇总
- ✅ **AgentPack / 工作流模板** - Agent 组合包管理与一键启动模板

### 界面增强
- ✅ **暗色主题** - 一键切换深浅色
- ✅ **导出功能** - PDF/图片导出
- ✅ **多语言** - 中文 / English 界面切换
- ✅ **管理后台** - Agent 编辑、工具配置、性能监控

## 🔒 安全

- 认证采用 JWT + httpOnly Cookie（SameSite=Strict）
- 密码 pbkdf2 哈希存储 + RSA 加密传输
- 密钥启动强制校验（`SECRET_KEY` / `JWT_SECRET_KEY` 缺失或强度不足时拒绝启动）
- 自托管公网部署务必设置 `APP_ENV=production` 并修改默认凭证

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/nickzhang1102/agentTeams.git
cd agentTeams

# 2. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env 设置数据库与应用根密钥；启动后在后台添加 LLM 模型

# 3. 一键部署
# Linux/macOS:
./scripts/docker-deploy.sh

# Windows (PowerShell):
.\scripts\docker-deploy.ps1

# 4. 访问应用
# 前端: http://localhost:8380
# 管理员账号: admin，初始密码随机生成，见 docker compose logs backend 输出
#            或宿主机 backend/data/.admin_initial_password 文件
#           （仅本地开发 APP_ENV=development 时为 admin/admin123），
#            首次登录后请立即修改密码
```

详见: [Docker 部署文档](./DOCKER.md)

### 方式二：本地开发

#### 前置要求
- Node.js 20.19+（Vite 8 要求）
- Python 3.11+
- PostgreSQL 18
- 一个 OpenAI 兼容的 LLM 服务账号（启动后在后台配置）

#### 后端启动

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装内嵌的 OpenHarness 框架（本地开发必需，Docker 镜像已自动处理）
pip install -e ../OpenHarness

# 配置环境变量
cp .env.example .env
# 编辑 .env 设置 DATABASE_URL、SECRET_KEY 和 JWT_SECRET_KEY

# 初始化数据库
alembic upgrade head

# 创建默认管理员账号（默认密码 admin123，首次登录后请立即修改）
python init_admin.py

# 启动服务
python run.py
```

LLM 模型在后台“LLM 模型”配置，Exa/Tavily Key 在后台“系统设置”配置。数据库凭证使用 `SECRET_KEY` 加密；轮换该根密钥前必须先用旧密钥解密并重新加密数据库凭证，否则服务将拒绝读取。

#### 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 配置环境变量
cp .env.example .env

# 启动开发服务器
npm run dev
```

访问 http://localhost:5173

详见: [快速入门指南](./QUICKSTART.md)

## 📁 项目结构

```
agentTeams/
├── backend/              # FastAPI 后端
│   ├── app.py           # 应用工厂
│   ├── models.py        # 数据模型
│   ├── api/             # RESTful 路由
│   ├── services/        # 领域服务层
│   ├── leader/          # LangGraph 编排层
│   └── tests/           # 测试
│
├── frontend/            # Vue3 前端
│   ├── src/
│   │   ├── views/      # 页面组件
│   │   ├── components/ # UI 组件
│   │   ├── stores/     # Pinia 状态管理
│   │   └── locales/    # 多语言文案
│   └── e2e/             # Playwright E2E 测试
│
├── OpenHarness/          # 内嵌 Agent 执行框架（MIT）
│
├── .claude/              # Agent 配置
│   └── agents/         # 内置专家 Agent 定义
│
├── docker/              # Docker 配置
│   └── init-db.sql     # 数据库初始化
│
├── scripts/             # 部署脚本
│   ├── docker-deploy.sh
│   └── docker-deploy.ps1
│
├── website/             # GitHub Pages 展示站
│   ├── index.html      # 单页站点（浅色科技蓝主题）
│   └── sponsor/        # 赞赏码图片
│
├── docker-compose.yml   # Docker Compose 配置
├── DOCKER.md           # Docker 文档
└── QUICKSTART.md       # 快速入门
```

> `OpenHarness/` 为内嵌的 MIT 许可第三方子项目（上游 OpenHarness 项目），经 `pip install -e` 安装使用。

## 🛠️ 技术栈

### 后端
- **FastAPI** - Web 框架
- **SQLAlchemy 2.0** - ORM
- **PostgreSQL 18** - 数据库（pgvector 向量索引）
- **LangGraph** - 多智能体编排
- **psycopg 3.3** - PostgreSQL 适配器
- **python-jose** - JWT 认证
- **OpenAI SDK** - LLM API 集成（OpenAI 兼容接口）

### 前端
- **Vue 3.4** - 前端框架
- **Vite 8** - 构建工具
- **Pinia** - 状态管理
- **Element Plus** - UI 组件库
- **D3.js** - 知识图谱可视化
- **Marked** - Markdown 解析

### 部署
- **Docker** - 容器化
- **Docker Compose** - 服务编排
- **Nginx** - 前端服务器
- **Uvicorn / Gunicorn** - ASGI 服务器

## 🔌 API 端点（节选）

### 认证
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/me` - 获取当前用户

### 对话
- `GET /api/conversations` - 对话列表
- `POST /api/conversations` - 创建对话
- `GET /api/conversations/:id` - 对话详情
- `PUT /api/conversations/:id` - 更新对话
- `DELETE /api/conversations/:id` - 删除对话

### Agent & 团队
- `GET /api/agents` - Agent 列表

### Leader & 工作流
- `POST /api/leader/start` - 启动 Leader 会话
- `GET /api/agent-packs` - Agent 组合包列表
- `POST /api/workflow-templates/{id}/apply` - 应用工作流模板一键启动

## 🧪 测试

### 后端测试

> **前置条件**：需要本机 PostgreSQL 18 处于运行状态，且先创建测试专用数据库 `agent_teams_test`：
>
> ```sql
> CREATE DATABASE agent_teams_test;
> ```
>
> 该要求的完整说明见 `backend/.env.example` 顶部注释（`TEST_DATABASE_URL` 相关条目）。

```bash
cd backend

# 运行所有测试
python -m pytest tests/ -v
```

### 前端测试

```bash
cd frontend

# 单元测试（Vitest）
npm run test

# E2E 测试（Playwright）
npm run test:e2e

# 构建验证
npm run build
```

> **E2E 前置条件**：
> - 需先启动完整后端服务（后端 API 可访问）；
> - 首次运行前执行 `npx playwright install chromium` 安装浏览器；
> - admin 系列用例需要一个已手工提权为管理员且未被锁定的账号，通过环境变量 `E2E_ADMIN_USER` / `E2E_ADMIN_PASSWORD` 提供（默认值仅适用于本地 E2E 环境）。

## 📝 环境变量

### 后端 (`.env`)

```bash
# 必填基础设施配置
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agent_teams

# LLM 与 Exa/Tavily 凭证在后台管理中配置并加密保存。
# 可选
FILE_STORAGE_PATH=data/files
WORKSPACE_DIR=data/workspace
AGENTS_DIR=../.claude/agents
```

密钥生成方式：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 前端 (`.env`)

前端默认通过 Vite 代理 / Nginx 代理转发 `/api` 请求，无需额外配置。

## 🐳 Docker 命令

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 查看日志
docker compose logs -f

# 进入容器
docker compose exec backend bash
docker compose exec postgres psql -U postgres -d agent_teams

# 备份数据库
docker compose exec postgres pg_dump -U postgres agent_teams > backup.sql

# 恢复数据库
cat backup.sql | docker compose exec -T postgres psql -U postgres agent_teams
```

## 📚 文档

- [快速入门指南](./QUICKSTART.md) - 本地开发和 Docker 部署
- [Docker 部署文档](./DOCKER.md) - Docker 详细配置
- [医疗 AI 免责声明](./DISCLAIMER.md) - 使用边界与风险提示

## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'feat: add some feature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 提交规范
- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `style:` 代码格式
- `refactor:` 重构
- `test:` 测试
- `chore:` 构建/工具

## 📄 许可证

本项目基于 [AGPL-3.0](./LICENSE) 协议开源。内嵌的 [OpenHarness](./OpenHarness/) 框架采用 MIT 协议。

## ⚕️ 医疗免责声明

本项目内置的医疗领域 Agent 仅用于**健康信息的整理与辅助理解**，其输出不构成医疗诊断、治疗建议或处方意见，也不属于医疗器械用途。任何诊疗决策必须由具备执业资质的医师作出。详见 [DISCLAIMER.md](./DISCLAIMER.md)。

## 👥 联系方式

- GitHub: [@nickzhang1102](https://github.com/nickzhang1102)

---

## ☕ 赞助支持

如果 Agent Teams 对你有所帮助，欢迎请作者喝一杯咖啡 ☕

**每一份支持都是作者持续维护的动力，真的很重要！**

| 💚 微信 | 💙 支付宝 |
| :---: | :---: |
| ![微信赞赏码](website/sponsor/wechat.jpg) | ![支付宝收款码](website/sponsor/alipay.jpg) |

也欢迎点一个 ⭐ Star，让更多有需要的人看到这个项目。
