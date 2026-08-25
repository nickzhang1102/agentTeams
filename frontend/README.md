# Agent Teams System

团队导向的 Claude Chat Web 应用，基于 Vue3+Vite 前端和 Flask 后端，支持 SSE 实时对话、文件管理、项目管理等功能。

## 技术栈

### 后端
- Flask 3.0
- SQLAlchemy
- Flask-JWT-Extended
- PostgreSQL
- Claude Code CLI

### 前端
- Vue 3.4
- Vite 5.0
- Pinia
- Vue Router 4
- Element Plus
- Axios
- Marked (Markdown 渲染)
- Highlight.js (代码高亮)

## 功能特性

### 核心功能
- ✅ JWT 用户认证
- ✅ SSE 流式对话
- ✅ Markdown + 代码高亮渲染
- ✅ Agent 选择 (Humanizer-zh, Codeknowledge)
- ✅ 项目关联

### 对话管理
- ✅ 创建/编辑/删除对话
- ✅ 对话共享设置 (只读/可写)
- ✅ 对话历史浏览
- ✅ 搜索功能

### 项目管理
- ✅ 创建/编辑/删除项目
- ✅ 项目类型分类 (前端/后端/全栈/其他)
- ✅ 技术栈管理
- ✅ 项目状态 (活跃/归档)
- ✅ 项目详情展示

### 文件管理
- ✅ 文件上传/下载
- ✅ 文件预览 (支持文本文件)
- ✅ 文件版本管理
- ✅ 按对话组织文件

## 快速开始

### 后端设置

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置必要的配置

# 初始化数据库
python init_db.py

# 运行服务器
python run.py
```

### 前端设置

```bash
cd frontend

# 安装依赖
npm install

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 开发模式运行
npm run dev

# 生产构建
npm run build
```

## API 端点

### 认证
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/me` - 获取当前用户信息

### 对话
- `GET /api/conversations` - 获取对话列表
- `POST /api/conversations` - 创建对话
- `GET /api/conversations/:id` - 获取对话详情
- `PUT /api/conversations/:id` - 更新对话
- `DELETE /api/conversations/:id` - 删除对话

### Leader 分析
- `POST /api/leader/start` - 启动 Leader 多 Agent 分析流

### 项目
- `GET /api/projects` - 获取项目列表
- `POST /api/projects` - 创建项目
- `GET /api/projects/:id` - 获取项目详情
- `PUT /api/projects/:id` - 更新项目
- `DELETE /api/projects/:id` - 删除项目

### 文件
- `GET /api/files` - 获取文件列表
- `POST /api/files/upload` - 上传文件
- `GET /api/files/:id/download` - 下载文件
- `GET /api/files/:id/preview` - 预览文件
- `GET /api/files/:id/versions` - 获取文件版本

## 项目结构

```
.
├── backend/              # 后端代码
│   ├── app.py           # FastAPI 应用
│   ├── models.py        # 数据模型
│   ├── api/leader_api.py # Leader 多 Agent 分析 API
│   ├── api/conversations.py # 对话管理
│   ├── api/files.py     # 文件管理
│   ├── config.py        # 配置
│   ├── run.py           # 运行脚本
│   └── tests/           # 测试
│
├── frontend/            # 前端代码
│   ├── src/
│   │   ├── main.js      # 入口文件
│   │   ├── App.vue      # 根组件
│   │   ├── router/      # 路由配置
│   │   ├── stores/      # Pinia 状态管理
│   │   ├── utils/       # 工具函数
│   │   ├── components/  # 组件
│   │   └── views/       # 页面
│   ├── public/          # 静态资源
│   ├── index.html       # HTML 模板
│   └── vite.config.js   # Vite 配置
│
└── docs/                # 文档
    └── plans/           # 计划文档
```

## 环境变量

### 后端 (.env)
```
APP_ENV=development
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
CLAUDE_API_KEY=your-claude-api-key
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/claude_chat
FILE_STORAGE_PATH=data/files
WORKSPACE_DIR=data/workspace
AGENTS_DIR=path/to/.claude/agents
```

### 前端 (.env)
```
VITE_API_BASE_URL=http://localhost:5000
VITE_APP_TITLE=Claude Chat
```

## 测试

### 后端测试
```bash
cd backend
python -m pytest tests/ -v
```

### 测试覆盖率
```bash
cd backend
python -m pytest tests/ --cov=. --cov-report=html
```

## 开发指南

### 代码风格
- 遵循 PEP 8 (Python)
- 遵循 Vue 3 Composition API 最佳实践
- 使用 ESLint 进行代码检查

### Git 提交规范
- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `style:` 代码格式调整
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建/工具相关

## 许可证

MIT

## 贡献指南

欢迎提交 Issue 和 Pull Request！

## 联系方式

项目维护者：Claude Chat Team
