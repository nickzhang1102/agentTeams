[根目录](../CLAUDE.md) > **backend**

# Backend 模块

> FastAPI RESTful API 服务，提供用户认证、对话管理、SSE 流式聊天、文件管理、Leader 协调、知识图谱等功能。

## 变更记录 (Changelog)

### 2026-08-23
- **移除用户侧计费与卡密（开源化）**:
  - 删除 `CDKey`/`CdKeyRedeemAttempt`/`PurchaseOrder` 模型与三张表（迁移 `a5b6c7d8e9f0`）
  - 删除 `/api/billing/*`、`/api/cdkey/*` 路由与注册赠送 5 次
  - 删除 Leader 启动的余额检查/扣费/退费/SSE billing 事件（用户路径不再计量）
  - 前端删除 Billing.vue、CDKeys.vue、billing store、路由与菜单
- **移除集成路径计费残留（开源化收尾）**:
  - 删除 `UserBalance`/`UsageRecord` 模型与两张表、`billing_policy` 列（迁移 `b7c8d9e0f1a2`）
  - 删除 `services/billing.py` 与 `services/integration_billing.py`
  - Leader 入口去 usage_record_id/billing_policy 参数与确认/退费块；DecisionRunService 去 attach_usage/mark_usage_terminal
  - 服务账户容量（capacity）只返回 configured/enabled/user_id/username，管理端配置表单去初始余额

### 2026-06-25
- **优化报告质量（P0 全链路）**:
  - `LeaderAgentResult` 新增 `decomposition: JSONB` 字段（迁移 `94dcd0b602a2`），`to_dict()` 同步返回
  - `SubTask` 新增 `tool_results` 字段，`subtask_executor` 收集每个工具的原始返回值（5K 截断/条）
  - 失败工具有部分返回数据时一并传入 LLM 分析
  - `batch_executor._build_context` 移除 300 字符硬截断

### 2026-06-22
- **新增 AgentPack 功能**: Agent 组合包管理（models.py AgentPack + Alembic migration + agent_pack_service.py + agent_pack_api.py 6 端点 + seed_agent_packs.py 5 预设 + 19 测试）
  - 模型：`AgentPack`（agent_packs 表，JSONB agents 数组 + category/is_system/creator_id/tags/usage_count）
  - API：`GET/POST /api/agent-packs`、`GET/PUT/DELETE /api/agent-packs/{id}`、`POST /api/agent-packs/{id}/clone`
  - 权限：系统 Pack 只读、用户 Pack 仅 creator 可写、克隆仅限系统 Pack 或自己的 Pack
- **新增 WorkflowTemplate 功能**: 工作流模板管理（models.py WorkflowTemplate + Alembic migration + workflow_template_service.py + workflow_template_api.py 6 端点 + 21 测试）
  - 模型：`WorkflowTemplate`（workflow_templates 表，pack_id/agents 二选一 + skip_assessment/assessment_threshold/system_prompt_addition）
  - API：`GET/POST /api/workflow-templates`、`GET/PUT/DELETE /api/workflow-templates/{id}`、`POST /api/workflow-templates/{id}/apply`
  - apply 一键启动复用 `_start_leader_workflow()`（从 leader_api 提取），支持快速模式和自定义阈值

### 2026-06-18
- **移除自定义指令功能**: 删除 `GET/PUT /api/auth/custom-instructions` 端点、`UpdateCustomInstructionsRequest` 模型、`llm_service.py` 的 `user_instructions` 参数
  - `User` 模型 `custom_instructions` 字段已移除（迁移 489e09a8ebd5）
- **修复 Leader 动态子任务上限守卫**: `task_runtime.py:251` — `current_count` → `completed_count`
- **新增 knowledge_search 工具链过滤**: `batch_executor._filter_tools_for_user` + `subtask_executor._is_knowledge_available_for_user`
- **修复 summarize 节点异步问题**: `summarize_nodes.py` Memory 提取改用 `threading.Thread`

### 2026-06-14
- **项目初始化扫描**: 全面更新 CLAUDE.md
  - 确认从 Flask 迁移至 FastAPI（`app.py` 使用 FastAPI + lifespan）
  - 确认数据模型从 8 个扩至 21 个（新增 AgentConfig, SystemConfig, ToolCallLog, CDKey 等）
  - 确认 API 蓝图从 7 个扩至 18 个路由模块
  - 确认服务层从 3 个扩至 28+ 个模块
  - 确认新增知识图谱功能（graph_rag_service, graphify_extractor, gap_analysis_service）
  - 确认新增 LangGraph 编排层（workflow_nodes, langgraph_workflow, sse_streamer）
  - 确认新增商业化功能（billing_api, cdkey_api）

### 2026-06-08
- **安全加固**: 修复 P1 安全问题并收敛消息处理分层泄漏
- **路径安全**、**日志脱敏**、**密码策略**

### 2026-06-03
- **数据库迁移管理**: 引入 Alembic 迁移管理

### 2026-06-01
- **整体审核节点**: `overall_review_node` + 用户整体决策 API
- **Agent 执行节点**: `agent_execution_node` + BatchExecutor
- **团队组建 DAG 节点**: `team_form_dag_node` + Agent 优先级规则系统
- **需求完善循环节点**: `requirement_loop_node`
- **LangGraph 编排层骨架**: StateGraph + SSE 适配器
- **审核 Agent 配置**: ReviewerConfig 独立 LLM 配置
- **MCP Coordinator 集成**: McpClientManager 单例管理
- **MCP 工具注册**: AgentMcpPermission 权限配置

### 2026-04-08
- **OpenHarness Phase 4**: 记忆与治理（HarnessMemoryManager, HarnessPermissionManager）

### 2026-03-17
- **OpenHarness Phase 3**: Agent 实际执行与工具调用记录

---

## 模块职责

- 用户认证与授权（JWT, python-jose）
- 对话管理（CRUD、归档、共享）
- 实时聊天（SSE 流式响应）
- 文件上传/下载/预览/版本管理
- LLM API 集成（OpenAI 兼容 API）
- Leader Agent 协调机制（LangGraph 编排）
- 知识图谱（图提取、GraphRAG、Gap Analysis）
- Agent 管理（元数据、MCP 权限、优先级规则）
- 集成接入（Agent Teams 服务账户承载集成会话归属，无计费概念）
- 管理后台（Agent 编辑、工具配置、系统配置）

---

## 入口与启动

### 应用入口
- **主入口**: `app.py` - FastAPI 应用工厂（单例模式）
- **启动脚本**: `run.py` - uvicorn 开发服务器

### 启动方式
```bash
# 开发模式
uvicorn app:app --reload --host 0.0.0.0 --port 5000

# 生产模式
gunicorn -k uvicorn.workers.UvicornWorker -w 4 app:app
```

### 数据库迁移
```bash
# 使用 Alembic
alembic upgrade head                        # 升级到最新版本
alembic revision --autogenerate -m "描述"    # 生成新迁移脚本
alembic downgrade -1                        # 回滚
```

---

## API 路由

| 路由前缀 | 文件 | 职责 |
|----------|------|------|
| `/api/health` | `health_api.py` | 健康检查 |
| `/api/auth` | `auth.py` | 用户认证（JWT） |
| `/api/conversations` | `conversations.py` | 对话 CRUD |
| `/api/files` | `files.py` | 文件上传/下载 |
| `/api/agents` | `agents_api.py` | Agent 列表/详情/分类树/分类聚合 |
| `/api/agent-packs` | `agent_pack_api.py` | Agent 组合包 CRUD + 克隆 |
| `/api/workflow-templates` | `workflow_template_api.py` | 工作流模板 CRUD + 一键启动 apply |
| `/api/leader` | `leader_api.py` | Leader 会话管理 |
| `/api/admin` | `admin_api.py` | 管理后台 |
| `/api/admin/roles` | `admin_roles_api.py` | 角色管理 |
| `/api/knowledge` | `knowledge_api.py` | 知识图谱 |
| `/api/tools` | `tools_api.py` | 工具管理 |
| `/api/skills` | `skills_api.py` | 技能管理 |
| `/api/mcp` | `mcp_api.py` | MCP 配置 |
| `/api/user/agents` | `agent_api.py` | 用户端 Agent CRUD（创建/编辑/删除自建 Agent） |
| `/api/content-translations` | `content_translation_api.py` | 历史 AI 内容的多语言翻译（登录用户） |
| `/api/decision-runs` | `decision_run_api.py` | 决策运行记录的所有者只读查询投影 |
| `/api/llm-models` | `llm_models_api.py` | 可用 LLM 模型公开列表（仅启用项，不含密钥） |
| `/api/locales` | `locales.py` | 产品支持语言元数据的公开查询 |
| `/api/integrations/agentteams` | `agentteams_integration_api.py` | Agent Teams 外部集成启动/嵌入会话端点 |
| `/api/project` | `project_config_api.py` | 项目菜单运行时配置读取（凭证走加密真源） |

> 注：`/api/feedback` 反馈管理路由已移除（FeedbackStats/ReportFeedback 组件已归档）。

> 注：`/static/knowledge` 静态路由已删除（2026-06-17 知识库个人化改造），图谱改由 `/api/knowledge/graph-data` 返回 JSON。

---

## 服务层

### 核心服务
| 文件 | 职责 |
|------|------|
| `llm_service.py` | LLM API 适配（OpenAI 兼容） |
| `tools_registry.py` | 工具注册表 |

### Agent 编排（harness/）
| 文件 | 职责 |
|------|------|
| `harness_coordinator.py` | Agent 协调器 |
| `harness_adapter.py` | 适配器层 |
| `openharness_llm_client.py` | LLM 客户端适配 |
| `openharness_permission_checker.py` | 权限检查 |
| `harness_memory_manager.py` | 记忆管理 |
| `harness_permission_manager.py` | 权限治理 |

### LangGraph 编排（leader/，27 模块）
| 文件 | 职责 |
|------|------|
| `workflow_nodes.py` | 工作流节点函数 |
| `langgraph_workflow.py` | StateGraph 定义 |
| `workflow_state.py` | 工作流状态 TypedDict |
| `sse_streamer.py` | LangGraph→SSE 适配 |
| `dag_planner.py` | DAG 执行计划 |
| `batch_executor.py` | 批次并行执行器 |
| `execution_result.py` | 执行结果 TypedDict |
| `execution_nodes.py` | 执行节点（Agent 实际调用） |
| `node_services.py` | 节点共享服务容器 |
| `requirement_assessor.py` | 需求评估 |
| `requirement_nodes.py` | 需求循环节点 |
| `team_former.py` | 团队组建 |
| `team_form_nodes.py` | 团队组建节点 |
| `leader_events.py` | SSE 事件推送 |
| `leader_persistence.py` | 持久化工具 |
| `agent_report_synthesizer.py` | Agent 报告合成 |
| `subtask_executor.py` | 子任务执行器 |
| `summarize_nodes.py` | 汇总节点 |
| `task_planner.py` | 任务规划器 |
| `task_runtime.py` | 任务运行时 |
| `task_types.py` | 任务类型定义 |
| `langgraph_entry.py` | LangGraph 入口 |
| `locale_generation.py` | Leader 生成内容的语言策略 |
| `node_utils.py` | Leader 节点公共工具函数 |
| `question_answers.py` | 需求答案的共享持久化与续跑流程 |
| `report_structures.py` | Leader 报告结构化辅助 |
| `terminal_state.py` | Leader 会话终态兜底保护 |

### 知识库
| 文件 | 职责 |
|------|------|
| `graph_rag_service.py` | GraphRAG 查询 |
| `graphify_extractor.py` | 图提取 |
| `gap_analysis_service.py` | 知识缺口分析 |

### 其他服务
| 文件 | 职责 |
|------|------|
| `agent_metadata.py` | Agent 元数据解析 |
| `agent_content_reader.py` | Agent 统一读取层（DB 优先，fallback 文件），替代 AgentMetadataParser |
| `agent_categories.py` | Agent 分类映射（已废弃，仅 migration 回填脚本引用） |
| `agent_category_service.py` | Agent 动态分类服务（DB 聚合 + CATEGORY_META 兜底，替代 agent_categories.py） |
| `agent_pack_service.py` | Agent 组合包 CRUD + 克隆 + validate_agents |
| `workflow_template_service.py` | 工作流模板 CRUD + agents 解析（pack_id 优先） |
| `agent_file_manager.py` | Agent 文件管理 |
| `file_storage.py` | 文件存储服务 |
| `document_processor.py` | 文档解析（PDF, DOCX, XLSX, PPTX） |
| `ocr_processor.py` | OCR 处理 |
| `mcp/mcp_manager.py` | MCP 连接池管理 |
| `mcp/mcp_client.py` | MCP 客户端 |
| `mcp/mcp_config.py` | MCP 配置 |
| `skills_manager.py` | 技能管理 |
| `memory_service.py` | 记忆服务 |

---

## 数据模型（35 个）

| 类别 | 模型 | 表名 | 说明 |
|------|------|------|------|
| 系统配置 | `AgentConfig` | `agent_configs` | Agent 配置与统计 |
| 系统配置 | `AgentCategory` | `agent_categories` | Agent 分类（DB 动态聚合） |
| 系统配置 | `SystemConfig` | `system_configs` | 系统动态配置 |
| 系统配置 | `ToolCallLog` | `tool_call_logs` | 工具调用日志 |
| 系统配置 | `BackfillTask` | `backfill_tasks` | 能力补全后台任务 |
| 用户 | `User` | `users` | 用户（含密码安全、账户锁定） |
| 对话 | `Conversation` | `conversations` | 对话（分享、分类、状态） |
| 对话 | `Message` | `messages` | 统一消息表 |
| 对话 | `File` | `files` | 文件 |
| 对话 | `ContentTranslation` | `content_translations` | 历史 AI 内容翻译缓存 |
| Integration 集成 | `IntegrationClient` | `integration_clients` | 外部系统身份与能力注册 |
| Integration 集成 | `AgentTeamsLaunch` | `agent_teams_launches` | 启动幂等记录 |
| Integration 集成 | `AgentTeamsEmbedToken` | `agent_teams_embed_tokens` | Agent Teams 短期嵌入访问令牌 |
| Integration 集成 | `IntegrationAccessOperation` | `integration_access_operations` | 本地访问撤销操作状态 |
| Leader | `LeaderSession` | `leader_sessions` | Leader 会话 |
| Leader | `LeaderWorkflowCancellation` | `leader_workflow_cancellations` | 跨 worker 取消墓碑 |
| Leader | `LeaderAgentResult` | `leader_agent_results` | Agent 执行结果 |
| Leader | `LeaderFinalReport` | `leader_final_reports` | 最终报告 |
| Leader | `LeaderReportRating` | `leader_report_ratings` | Leader 报告评分 |
| 决策运行 | `DecisionRun` | `decision_runs` | 决策运行生命周期 |
| 决策运行 | `DecisionEvidence` | `decision_evidences` | 决策证据条目 |
| 决策运行 | `DecisionClaim` | `decision_claims` | 证据支撑的结论声明 |
| 决策运行 | `DecisionClaimEvidence` | `decision_claim_evidence` | 声明与证据多对多绑定 |
| 决策运行 | `DecisionEvidenceMetrics` | `decision_evidence_metrics` | 证据质量指标 |
| 审计 | `SecurityLog` | `security_logs` | 安全日志（登录安全、集成审计） |
| 权限 | `AgentMcpPermission` | `agent_mcp_permissions` | MCP 工具权限 |
| 权限 | `AgentPriorityRule` | `agent_priority_rules` | 优先级规则 |
| 映射 | `HarnessSessionMapping` | `harness_session_mappings` | OpenHarness 会话映射 |
| 组合包 | `AgentPack` | `agent_packs` | Agent 组合包（系统预设 + 用户自建） |
| 模板 | `WorkflowTemplate` | `workflow_templates` | 工作流模板（引用 pack 或直接 agents，支持 skip_assessment） |
| 知识库 | `KnowledgeDocument` | `knowledge_documents` | 知识库文档 |
| 知识库 | `KnowledgeCategory` | `knowledge_categories` | 知识库分类（含 user_id 按用户隔离） |
| 记忆与向量 | `AgentMemory` | `agent_memories` | 用户长期记忆 |
| 记忆与向量 | `NodeEmbedding` | `node_embeddings` | 知识图谱节点向量 |
| 记忆与向量 | `LLMModel` | `llm_models` | LLM 模型配置 |

> 注：完整清单以 `models.py` 文件头注释为准。

> 注：2026-08-23 开源化移除用户侧商业化，`CDKey`/`CdKeyRedeemAttempt`/`PurchaseOrder` 三模型与表已删除（迁移 `a5b6c7d8e9f0`）。
> 注：2026-08-23 移除集成路径计费残留，`UserBalance`/`UsageRecord` 两模型与表及 `billing_policy` 列已删除（迁移 `b7c8d9e0f1a2`）。

## Alembic 迁移

> 注：版本数量与增量迁移一律以 `migrations/versions/` 目录为准（当前 51 个版本）；下表仅为节选。

| 版本 | 说明 |
|------|------|
| `98736f6635e8` | 初始 schema |
| `0d15800c46b1` | Leader 增加 requirement_loop_count |
| `600a5369112d` | Leader 报告评分表 |
| `a1b2c3d4e5f6` | 增加 original_filename |
| `b3c4d5e6f7a8` | 增加 token_version |
| `c4d5e6f7a8b9` | 增加 custom_instructions |
| `d5e6f7a8b9c0` | 增加 role/model_override/edit_fields |
| `e6f7a8b9c0d1` | 增加 pg_trgm 搜索索引 |
| `f7a8b9c0d1e2` | Agent memories 表 |
| `d48a6f9187c2` | Conversation 增加 featured 字段 |
| `5159c8bf2d21` | KnowledgeDocument 增加 shared_with + category user_id |
| `b1c2d3e4f5a6` | 回填默认个人分类 |
| `d3cfb9455122` | 合并多 head |
| `489e09a8ebd5` | 移除死字段 custom_instructions |
| `2ba1c3410b4a` | 移除死字段 shared_with |
| `e4b7526dbb09` | 创建 agent_packs 表（AgentPack） |
| `f1a2b3c4d5e6` | 创建 workflow_templates 表（WorkflowTemplate） |
| `94dcd0b602a2` | LeaderAgentResult 新增 decomposition JSONB 字段 |
| `a5b6c7d8e9f0` | 移除用户侧商业化表（cdkeys/cdkey_redeem_attempts/purchase_orders） |
| `b7c8d9e0f1a2` | 移除集成路径计费残留（user_balances/usage_records 及 billing_policy 列） |

## 手工迁移脚本（`migrations/scripts/`）
- 数据表迁移：`create_db`, `init_db`, `merge_message_tables`, `add_leader_tables`, `add_graphify_fields`, `add_ocr_fields`
- 字段迁移：`add_is_archived`, `add_is_review_mode`, `add_share_token` 等（数量以目录为准）
- 清理/修复：`remove_teams_and_projects`, `fix_review_mode_messages`

> 注：2026-08-23 移除 `migrate_add_billing`、`migrate_add_cdkey_security`、`fix_money_precision`（引用已删表，Alembic 已接管）。

---

## LangGraph 工作流

```
user_input → requirement_loop → team_form_dag → agent_execution → summarize → end
                        ↻
```

节点：
- `requirement_loop_node` - 需求评估与完善（含循环计数上限）
- `team_form_dag_node` - DAG 团队组建（按优先级分批）
- `agent_execution_node` - Agent 并行执行（批次内并行、批次间顺序）
- `summarize_node` - 结果汇总

---

## 关键配置

```bash
# LLM 模型、Base URL、API Key 和 token 规格通过后台 LLM 模型管理配置。
# 知识图谱提取复用后台默认 LLM；Exa/Tavily Key 通过后台系统设置配置。

# 数据库
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agent_teams

# OpenHarness
OPENHARNESS_ENABLED=true
OPENHARNESS_COORDINATOR_ENABLED=true
MAX_AGENT_PARALLEL=5
MAX_AGENT_ITERATIONS=10
OPENHARNESS_TOOLS_TIMEOUT=300

# 密码策略
PASSWORD_MIN_LENGTH=8
PASSWORD_REQUIRE_LETTER=true
PASSWORD_REQUIRE_DIGIT=true

# 记忆与治理
OPENHARNESS_MEMORY_ENABLED=true
OPENHARNESS_MEMORY_MAX_MESSAGES=50
OPENHARNESS_PERMISSION_ENABLED=true
OPENHARNESS_HOOKS_ENABLED=true
OPENHARNESS_HOOKS_TIMEOUT=10

```

## Docker 部署

**docker-compose.yml 定义 3 个服务**：
```yaml
services:
  postgres:   # pgvector/pgvector:pg18（含向量索引支持），端口 5432
  backend:    # FastAPI + uvicorn, 端口 5000
  frontend:   # Nginx + Vue dist, 端口 8380
```

**注意事项**：
- **无 Redis**：当前架构未使用 Redis
- **数据库连接**：
  - Docker 容器内：`DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/agent_teams`
  - 本地开发：`DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agent_teams`
  - Docker Compose 会自动覆盖 .env 中的 DATABASE_URL 为容器服务名 `postgres`
- **密钥生成**：
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  # 输出 64 字符十六进制串，复制到 .env 的 SECRET_KEY 和 JWT_SECRET_KEY
  ```
- **健康检查**：postgres（pg_isready），backend（/health），frontend（wget /）
- **数据持久化**：postgres_data 卷挂载到 `/var/lib/postgresql/data`

## 数据库迁移

```bash
# Alembic 版本化管理（以 migrations/versions/ 目录为准，当前 51 个版本）
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic downgrade -1

# 手工迁移脚本（migrations/scripts/，当前 28 个脚本，以目录为准）
python -m migrations.scripts.migrate_add_xxx
```

---

## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 覆盖率
pytest tests/ --cov=. --cov-report=html
```

测试文件清单（`tests/` 目录）：
- 核心模块：`test_models`, `test_auth`, `test_conversations`, `test_leader_only_api`, `test_files`, `test_file_storage`
- Agent：`test_agent_metadata`, `test_agent_tree_api`, `test_team_forming_message`, `test_agent_file_manager`, `test_agent_category_service`, `test_agent_categories_api`, `test_backfill_capabilities`, `test_agent_pack_api`, `test_workflow_template_api`
- Leader：`test_leader_models`, `test_leader_api`, `test_leader_agent_result`, `test_leader_final_report`, `test_leader_messages`, `test_risk_level`, `test_quick_mode`
- LangGraph：`test_langgraph_workflow`, `test_requirement_loop_node`, `test_requirement_assessor_scores`, `test_dag_planner`, `test_batch_executor`, `test_sse_streamer_integration`, `test_summarize_node`, `test_sse_async`
- OpenHarness：`test_harness_coordinator`, `test_harness_adapter`, `test_harness_standalone`, `test_harness_integration`, `test_harness_session_mapping`, `test_harness_memory_manager`, `test_harness_permission_manager`, `test_openharness_llm_client`, `test_openharness_permission_checker`, `test_openharness_config`
- MCP：`test_mcp_manager`, `test_mcp_tool_registration`, `test_mcp_client_async`
- 知识图谱：`test_graphify_mcp_registration`, `test_knowledge_api`, `test_knowledge_retriever`, `test_graph_rag_service`, `test_knowledge_isolation`
- 管理与监控：`test_admin_api`, `test_admin_models`, `test_admin_agent_api`, `test_admin_monitoring_api`, `test_priority_rules_api`
- 集成：`test_phase3_task3_execution`, `test_agentteams_launch_contract`, `test_agentteams_service_account`, `test_agentteams_integration_admin_api`, `test_integration_client_admin_api`, `test_integration_architecture_boundaries`
- 安全：`test_llm_service_security`, `test_upload_validator`
- 其他：`test_new_cases`, `test_tool_execution`, `test_context_builder`, `test_context_memory`, `test_context_pack`, `test_memory_service`, `test_migration_safe_ops`, `test_migration_scripts_are_safe`, `test_structured_output`, `test_featured_in_my_conversations`

---

**文档生成时间**: 2026-08-25
