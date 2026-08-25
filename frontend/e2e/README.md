# E2E 测试（Playwright）运行指南

## 运行方式

```bash
cd frontend
npx playwright install chromium        # 首次运行前安装浏览器
npm run test:e2e                       # 全量运行（等价于 npx playwright test）
npm run test:e2e:ui                    # UI 调试模式
npx playwright test --project=home-noauth   # 只跑某个 project
```

- `baseURL` 默认 `http://localhost:5173`，可通过 `FRONT_BASE_URL` 覆盖。
- 配置了 `webServer`：本地运行会自动执行 `npm run dev` 启动 Vite（CI 下不复用已有服务）。

## 测试分档

按前置条件分为三档，跑之前先确认目标 project 属于哪一档。

### 第一档：免登录态，可直跑

无 `dependencies`、无 `storageState` 的 project，不需要任何账号：

| project | spec |
|---------|------|
| `login-fail` | tests/login-fail.spec.js |
| `home-noauth` | tests/home-noauth.spec.js, tests/locale-switcher.spec.js |
| `home-tabs` | tests/home-tabs.spec.js（未认证变体） |
| `featured-case` | tests/featured-case.spec.js |
| `agentteams-embed` | tests/agentteams-embed.spec.js（公开页，自包含） |
| `evidence-drawer-desktop` / `evidence-drawer-mobile` | tests/report-evidence-drawer.spec.js（mock 数据，自包含） |
| `knowledge-noauth` | tests/knowledge-noauth.spec.js |
| `register-noauth` | tests/register.spec.js |
| `conversation-public` | tests/conversation.spec.js（公开分享页变体） |

> 多数用例只依赖前端页面渲染，但个别断言可能发起后端请求；本地获得与线上一致的
> 结果建议同时启动后端（FastAPI :5000）与数据库。

### 第二档：需要普通用户登录态（`.auth/user.json`）

依赖 `setup` project（`e2e/auth.setup.js`）：自动注册/登录普通测试用户，
并把会话写入 `.auth/user.json`。需要完整后端 + PostgreSQL 可达：

| project | 备注 |
|---------|------|
| `auth-flow` | 认证全流程 |
| `chromium-auth` | login / home-auth / password-change |
| `home-tabs-auth` | 已认证 Tab 变体 |
| `knowledge-auth` | 知识库页面 |
| `conversation-auth` | 对话详情 |
| `register-auth` | 已认证注册页变体 |
| `chat-core` | 聊天核心流程 |
| `file-upload` | 文件上传全流程 |
| `chat-execution` | **额外要求后台已配置可用的 LLM 模型**（触发真实 Agent 执行） |

### 第三档：admin 系列（`.auth/admin.json`）

涉及 project：`admin-setup` -> `admin-tests`、`admin-localization-mobile`
（spec：tests/admin.spec.js、tests/admin-localization.spec.js）。

**前置条件：必须先在系统里手工创建管理员账号。**

原因：注册接口创建的用户默认 `is_admin=False`，而 `admin.setup.js` 在登录失败时
的兜底逻辑是"走注册页新造一个账号"——那只会得到普通用户，无法通过 `/admin`
路由守卫，setup 必然失败。

操作步骤：

1. 注册（或 SQL 直建）一个专用账号，例如用户名 `admin_e2e`；
2. 将其提权为管理员（需已有管理员在界面上操作，或直接执行 SQL）：

   ```sql
   UPDATE users SET is_admin = true WHERE username = 'admin_e2e';
   ```

3. 在**运行 Playwright 的同一 shell** 中设置环境变量（配置文件不会自动加载 .env 文件，
   未设置时回退默认值 `admin_e2e` / `admin_e2e_password`）：

   ```bash
   # bash
   export E2E_ADMIN_USER=admin_e2e
   export E2E_ADMIN_PASSWORD='你的密码'
   # PowerShell
   $env:E2E_ADMIN_USER='admin_e2e'; $env:E2E_ADMIN_PASSWORD='你的密码'
   ```

4. 正常运行即可，`admin-setup` 会登录并把会话写入 `.auth/admin.json`：

   ```bash
   npx playwright test --project=admin-setup --project=admin-tests
   ```

### `.auth/` 状态文件说明

- `.auth/user.json` 由 `setup` project（auth.setup.js）生成；
- `.auth/admin.json` 由 `admin-setup` project（admin.setup.js）生成；
- 两者均为有效登录凭据缓存（含 token），**不要提交到 git**，请确认 `.gitignore`
  已忽略 `.auth/` 目录；凭据过期或账号变更后删除对应文件重跑 setup 即可再生。
