# 贡献指南

感谢关注 Agent Teams。本文档说明如何搭建开发环境、运行测试以及提交贡献。

## 开发环境搭建

前置要求：

- Node.js 20.19+（Vite 8 要求）
- Python 3.11+
- PostgreSQL 18（需支持 pgvector 扩展，推荐 `pgvector/pgvector:pg18` 镜像）
- 一个 OpenAI 兼容的 LLM 服务账号（启动后在后台配置，不参与单元测试）

完整安装步骤（虚拟环境、依赖安装、OpenHarness 内嵌框架、数据库初始化、管理员账号创建）请参阅 [README「方式二：本地开发」](./README.md#方式二本地开发)，此处不再重复。两点容易遗漏：

```bash
# OpenHarness 是仓库内嵌本地包，后端 services/harness、services/mcp 等模块直接导入，
# 本地开发必须以可编辑模式安装
pip install -e ../OpenHarness   # 在 backend/ 目录下执行

# 运行 pytest 前必须单独创建测试库并配置 TEST_DATABASE_URL
# 测试会清空目标库全部表，绝不指向主库；库名必须以 _test 结尾
CREATE DATABASE agent_teams_test;
```

## 本地开发流程

| 方式 | 启动命令 | 访问地址 | 适用场景 |
|------|----------|----------|----------|
| 后端 | `cd backend && python run.py`（uvicorn） | http://localhost:5000 | API 开发调试 |
| 前端 | `cd frontend && npm run dev`（Vite） | http://localhost:5173 | 页面开发调试 |
| Docker 一键部署 | `./scripts/docker-deploy.sh`（Windows: `.\scripts\docker-deploy.ps1`） | http://localhost:8380 | 完整联调 / 部署验证 |

Docker 部署细节见 [DOCKER.md](./DOCKER.md)。

## 测试要求

提交前请至少运行与改动相关的测试套件。三套测试的前置条件不同：

### 后端 pytest

前置：PostgreSQL 18 运行中 + 独立测试库 `agent_teams_test`（通过 `TEST_DATABASE_URL` 配置）。未正确配置时 conftest 会直接报错拒绝运行——这是防误删数据的保护机制，不是故障。

```bash
cd backend
pytest tests/ -v          # 全量
pytest tests/test_auth.py -v  # 单文件
```

### 前端 vitest

零外部依赖，无需数据库和后端服务。建议显式指定目录或文件：

```bash
cd frontend
npx vitest run src                          # 仅跑 src 下用例
npx vitest run src/stores/auth.spec.js      # 指定文件
```

> 注：当前 `vitest.config.js` 的 include 已限定为 `src/**`，全量 `npm run test:run` 不会误收 E2E 用例；显式指定路径是双保险。

### Playwright E2E

需要完整运行环境（后端 + 数据库 + 已配置的 LLM），适合在功能联调完成后手动执行：

```bash
cd frontend
npm run test:e2e
```

CI 只运行前两套（见 [.github/workflows/ci.yml](./.github/workflows/ci.yml)）。

## 提交规范

项目历史采用 Conventional Commits 风格、中文描述，请保持一致：

```
feat(leader): 实现Leader工作流全阶段可停止能力
fix(frontend,backend): 修复设置弹窗与分享页回归
chore(website): 新增 GitHub 展示网站
refactor(summarize_nodes): 重构最终汇总报告
```

- 类型：`feat` / `fix` / `chore` / `refactor` / `docs` / `test` 等
- scope 可选，使用模块名（backend、frontend、leader、agentteams 等），多模块逗号分隔
- 描述用中文一句话说清变更内容，避免只写"更新代码""修复 bug"

## Pull Request 指南

1. **小步提交**：一个 PR 聚焦一件事，便于审查与回滚。
2. **附带测试**：新增功能或修复缺陷应包含对应测试；改动行为时同步更新受影响的既有测试。
3. **医疗领域 Agent 内容须附来源**：新增或修改 `.claude/agents/` 下医疗类 Agent 配置（专科知识、诊疗流程等表述）时，请在 PR 描述中注明权威依据（指南、教科书、共识文件等）。本项目对 AI 医疗输出的定位见 [DISCLAIMER.md](./DISCLAIMER.md)。
4. **确保 CI 通过**：PR 会自动触发后端 pytest 与前端 vitest。
5. **描述清晰**：说明动机、改动范围、验证方式。

## 行为准则

参与本项目（包括 issue、讨论、代码审查）即表示同意遵守[行为准则](./CODE_OF_CONDUCT.md)。

## 许可证

提交的代码将以 [AGPL-3.0](./LICENSE) 授权发布，请确认你拥有所提交内容的版权。
