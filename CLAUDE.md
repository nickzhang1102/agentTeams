# Agent Teams System

> 团队导向的 Agent Teams Web 应用，基于 Vue3+Vite 前端和 FastAPI 后端，支持 SSE 实时对话、Agent 团队协作、知识图谱、Leader 智能编排等功能。

## 变更记录 (Changelog)

### 2026-08-26
- **前端新增全局底部状态栏（对齐 OncoPath）**: 移植姊妹项目 OncoPath 的 AppFooter 模式——fixed 底栏展示品牌版本（`/api/health` 下发 APP_VERSION）| GitHub | 赞助弹窗 | © 2026 AGPL-3.0 | 署名，移动端收窄为细条；新增 `AppFooter.vue`/`SponsorDialog.vue`（赞助弹窗对齐 OncoPath：5 档金额卡 ¥5/¥10/¥20/¥50/¥99 → 各档专属微信收款码，另留支付宝通用码入口，图片自 OncoPath 拷入 `assets/sponsor/`）与 `useAppVersion`/`useResponsive` composables；embed 嵌入路由不展示；`design-system.scss` 新增 `--footer-height: 32px`，固定视口页（ChatLayout/ConversationDisplay/admin 布局）高度改 `calc(100vh - var(--footer-height))`，ThemeToggle/新手帮助等浮动件抬升至状态栏上方；文案走 i18n 双语。

### 2026-08-26
- **website 官网全面改版（对齐 OncoPath 官网）**: 布局骨架全面参考姊妹项目 OncoPath——Hero 改左右分栏（超大渐变字 + 深色窗框内嵌真实截图 + 浮动徽章），删除原 CSS 动画模拟的 session-demo 会话演示与 flow-anim 点阵动画；新增 `#showcase` 界面预览区（桌面 7 屏 + 移动 4 屏逐屏滚动叙事 + noscript 回退画廊）；赞助区补微信/支付宝收款码卡片（复用作者 OncoPath 同款码）；`website/screenshots/` 新增 11 张真实界面截图（桌面 1600×1000 七张 + 移动 390×844 四张），由本地起后端+造演示数据后 Playwright 实拍。

### 2026-08-25
- **开源前复审整改（P1 修复 + OncoPath 更名 + 文档双语）**: 复审发现的 6 项 P1 全部闭环——`config.py` default 改为 ProductionConfig 且 `APP_ENV` 判定全链路 fail-closed（未设置即生产姿态）；上传改为流式分块校验修复 OOM DoS；删除伪沙箱 `execute_code` 工具并在 SECURITY/DOCKER 文档警示工具执行边界；修正 Docker 初始密码文档矛盾；清理内部过程文档与死测试。**OncoPath 代号全局更名 Agent Teams**：代码标识 `agentteams`、表名 `agent_teams_launches/embed_tokens`（迁移 `a8b9c0d1e2f3`）、env 前缀 `AGENTTEAMS_`，历史迁移文件保持原名。新增 README.en.md 中英双语；提交元数据去除个人邮箱。

### 2026-08-25
- **开源前整改（安全修复 + 文档收尾）**: 修复安全问题并完成文档批次清理——删除过期/误导文档（teams-api、REFACTOR_STATUS、2026-03 测试分析报告等），修正 backend/CLAUDE.md 与 DOCKER.md 中的过时配置与计数，README 补测试前置条件；git 历史已于开源前重写为单一初始提交（2f836b5）。

### 2026-08-23
- **移除计费与卡密（开源化）**: 删除 CDKey/CdKeyRedeemAttempt/PurchaseOrder 模型与表（迁移 `a5b6c7d8e9f0`）、`/api/billing` 与 `/api/cdkey` 路由、注册赠送、Leader 启动余额检查；随后删除 Agent Teams/通用集成路径的 `UserBalance`、`UsageRecord` 与 `billing_policy`（迁移 `b7c8d9e0f1a2`）。

### 2026-06-25
- **优化报告质量（P0 全链路）**:
  - **子任务分解 + 原始工具结果存 DB**：`LeaderAgentResult` 新增 `decomposition: JSONB` 字段（迁移 `94dcd0b602a2`），`SubTask` 新增 `tool_results` 字段保存每个工具的原始返回值（截断 5K/条）
  - **API 返回 decomposition**：`LeaderAgentResult.to_dict()` 补上 `decomposition` 字段，历史会话可查看子任务详情
  - **失败工具结果传入 LLM**：`subtask_executor.py` 失败工具有部分返回数据时一并传入
  - **批次间上下文去掉截断**：`batch_executor._build_context` 移除 300 字符硬截断

### 2026-06-22
- **新增 AgentPack 功能**: Agent 组合包管理（AgentPack 模型 + CRUD API + 系统预设 + 克隆 + 19 测试）
- **新增 WorkflowTemplate 功能**: 工作流模板管理（WorkflowTemplate 模型 + CRUD API + 一键启动 apply + 21 测试）
  - apply 复用 `_start_leader_workflow()`，支持 `skip_assessment` 快速模式和自定义评估阈值
  - Leader workflow_state 新增 `assessment_threshold` / `system_prompt_addition` 两字段
  - 后端模型 27→28，API 路由 18→19

### 2026-06-18
- **移除自定义指令功能**: 删除用户自定义指令（Custom Instructions）全链路
  - 后端：移除 `GET/PUT /api/auth/custom-instructions` 端点及 `UpdateCustomInstructionsRequest` 模型
  - 后端：移除 `llm_service.py` 的 `user_instructions` 参数及系统提示注入逻辑
  - 前端：删除 `UserSettings.vue` 组件，移除 `auth.js` 中 `customInstructions` 状态及相关方法
  - 前端：移除 `Home.vue` 用户菜单中的"自定义指令"入口
  - 注：`User` 模型 `custom_instructions` 字段已移除（迁移 489e09a8ebd5）
- **修复 Leader 动态子任务未执行**: `task_runtime.py` 上限守卫 `current_count` → `completed_count`
- **优化 knowledge_search 工具链**: 规划层+执行层双层过滤，医疗类工具链补充 `web_search`
- **修复 summarize 节点异步问题**: Memory 提取改用 `threading.Thread` 替代同步上下文中的 `asyncio.create_task`

### 2026-06-14
- **项目初始化扫描**: 全面更新 CLAUDE.md
  - 确认后端已从 Flask 迁移至 FastAPI（`app.py` 使用 FastAPI + lifespan）
  - 确认后端模型扩至 21 个（新增 AgentConfig, SystemConfig, ToolCallLog, CDKey, KnowledgeDocument 等）
  - 确认后端 API 蓝图从 7 个扩至 18 个路由模块
  - 确认后端服务层从 3 个扩至 29 个服务模块（含 leader/ 下 22 个 LangGraph 模块）
  - 确认前端组件从 10+ 扩至 55 个 Vue 组件
  - 确认测试文件从 17 个扩至 67 个
  - 确认 Agent 配置从 68 个扩至 74 个（新增 6 金融期货，移除审核 Agent）
  - 确认新增知识图谱功能（D3 可视化, GraphRAG, Gap Analysis）
  - 确认新增知识图谱功能（D3 图谱可视化, GraphRAG, Gap Analysis）
  - 确认新增管理后台（Dashboard, AgentEditor, OpenHarness 配置, 性能监控）
  - 确认新增商业化功能（Billing, CDKey, UsageRecord）
  - 确认新增 LangGraph 编排层（workflow_nodes, langgraph_workflow, sse_streamer）
  - 确认新增 DAG 执行计划（dag_planner, priority_rules）
  - 确认新增 MCP 工具注册与管理
  - 确认新增暗色主题切换功能
  - 确认新增 Playwright E2E 测试
  - 确认新增文档解析服务（PDF, DOCX, XLSX, PPTX）
  - 确认新增 OCR 处理服务

### 2026-03-17
- 增量扫描更新

### 2026-03-15
- 移除 Humanizer 功能

### 2026-03-12
- 新增风险评估功能

### 2026-03-06
- 前端界面增强

### 2026-03-04
- 从 SQLite 迁移到 PostgreSQL 18

---

## 项目愿景

构建一个团队协作的 AI Agent 系统，支持：
- 多用户认证与权限管理
- 实时流式对话（SSE）
- 文件上传与版本管理
- Agent 自动选择与角色切换
- Agent 团队协作（Team）
- Leader Agent 协调机制（LangGraph 编排）
- 知识图谱与 GraphRAG
- 管理后台（Agent、工具、配置、监控）
- 暗色主题
- 聊天界面增强（导出、建议问题）

---

## 架构总览

```mermaid
graph TD
    A["Agent Teams System"] --> B["backend/<br/>FastAPI 服务"]
    A --> C["frontend/<br/>Vue3 应用"]
    A --> D["docs/<br/>文档"]
    A --> E[".claude/<br/>配置与技能"]
    A --> F["scripts/<br/>运维脚本"]

    B --> B1["api/<br/>FastAPI 路由"]
    B --> B2["services/<br/>领域服务"]
    B --> B3["leader/<br/>LangGraph 编排层"]
    B --> B4["models.py<br/>35 数据模型"]

    C --> C1["views/<br/>页面组件"]
    C --> C2["components/<br/>50+ 可复用组件"]
    C --> C3["stores/<br/>Pinia 状态"]

    B1 --> B1a["auth / conversations"]
    B1 --> B1b["leader_api / admin_api / admin_roles"]
    B1 --> B1c["knowledge_api / files"]
    B1 --> B1d["tools / skills / mcp"]

    B2 --> B2a["llm_service"]
    B2 --> B2b["harness/ 协调器"]
    B2 --> B2c["memory_service"]
    B2 --> B2d["graph_rag_service / graphify_extractor"]
    B2 --> B2e["mcp/ MCP 管理"]

    B3 --> B3a["workflow_nodes"]
    B3 --> B3b["langgraph_workflow"]
    B3 --> B3c["dag_planner / batch_executor"]
    B3 --> B3d["sse_streamer"]

    click B "./backend/CLAUDE.md"
    click C "./frontend/CLAUDE.md"
```

---

## 模块索引

| 模块 | 路径 | 语言/框架 | 职责 | 入口文件 |
|------|------|----------|------|----------|
| Backend | `backend/` | Python/FastAPI | RESTful API 服务 | `app.py` |
| Frontend | `frontend/` | Vue3/Vite | Web 前端应用 | `src/main.js` |
| Docs | `docs/` | Markdown | 项目文档与计划 | - |
| Claude Config | `.claude/` | Markdown/YAML | Agent 配置与技能 | - |
| Scripts | `scripts/` | Python/Shell | 运维与部署脚本 | - |

---

## 运行与开发

### 环境要求
- Node.js 20.19+（Vite 8 要求）
- Python 3.11+
- PostgreSQL 18
- 一个 OpenAI 兼容的 LLM 服务账号（启动后在后台配置）

### Docker 部署
```bash
cp backend/.env.example backend/.env
# 编辑 .env 设置必要变量
docker compose up -d
# 访问 http://localhost:8380
```

**服务清单**：
- `postgres`（pgvector/pgvector:pg18，宿主 127.0.0.1:5433 → 容器 5432，仅回环绑定）
- `backend`（FastAPI + gunicorn/UvicornWorker，容器端口 5000，宿主仅回环绑定）
- `frontend`（Nginx + Vue dist，端口 8380）

**注意**：
- **无 Redis**：当前配置未使用 Redis
- **数据库连接**：Docker 内使用服务名 `postgres`，非 `localhost`
  - 容器内：`postgresql+psycopg://postgres:postgres@postgres:5432/agent_teams`
  - 本地开发：`postgresql+psycopg://postgres:postgres@localhost:5432/agent_teams`
- **密钥生成**：
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  # 生成 64 字符十六进制串，分别用于 SECRET_KEY 和 JWT_SECRET_KEY
  ```

### 后端
```bash
cd backend
python -m venv venv && venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 设置 DATABASE_URL、SECRET_KEY 和 JWT_SECRET_KEY
uvicorn app:app --reload --host 0.0.0.0 --port 5000
```

启动后在后台“LLM 模型”中添加并启用模型；Exa/Tavily Key 在后台“系统设置”中配置。

### 前端
```bash
cd frontend
npm install
npm run dev
```
访问 http://localhost:5173

---

## 技术栈

**后端**: FastAPI · SQLAlchemy 2.0 · PostgreSQL · python-jose (JWT) · OpenAI SDK · LangGraph · OpenHarness

**前端**: Vue 3.4 · Vite 8 · Pinia · Vue Router 4 · Element Plus · D3.js · Mermaid · Marked · html2canvas

**工具**: Alembic · Pytest · Vitest · Playwright · Gunicorn · Uvicorn

---

## Agent 系统

共 **107 个 Agent** 配置文件位于 `.claude/agents/`，覆盖以下领域：
- **医疗专家**: 内科、外科、专科、医技科室（心内、呼内、消化、神内、普外、肝胆、骨科、儿科、眼科…）
- **商业角色**: CEO(Bezos), CTO(Vogels), CFO(Campbell), 产品(Norman), UI(Duarte), 交互(Cooper)…
- **金融期货**: CIO(Dalio), CRO(Taleb), 合规(Gensler), 量化(Simons), 分析师（宏观/黑色/有色/农产品等）…

> 注：各 Agent 的 `category` 分类由 `AgentCategoryService` 从 DB 动态聚合，前端 Tab 通过 `GET /api/agents/categories` 获取分类列表含数量，支持 category 参数筛选。

---

## 测试

```bash
# 后端
cd backend && pytest tests/ -v

# 前端
cd frontend && npm run test

# E2E
cd frontend && npm run test:e2e
```

---

## 相关链接

- [Backend 模块文档](./backend/CLAUDE.md)
- [Frontend 模块文档](./frontend/CLAUDE.md)
- [项目 README](./README.md)

---

**文档生成时间**: 2026-08-25

## 项目碎片知识

<!-- cs-note managed: 用 cs-note 维护，新条目按下面分节追加 -->

### 编译与构建

### 运行与本地起服务

### 测试
- Vitest 的 `include` 已限定 `src/**`（vitest.config.js），不会再误收 `e2e/tests` 下 Playwright 用例，可放心使用全量 `npm run test:run` 做验收。
- 后端 pytest 需 PostgreSQL 18 运行中且先创建 `agent_teams_test` 库（详见 `backend/.env.example` 注释）。

### 命令与脚本陷阱

### 路径与目录约定

### 环境变量与凭证

### 其他
