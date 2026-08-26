[根目录](../CLAUDE.md) > **frontend**

# Frontend 模块

> Vue3 + Vite 前端应用，提供用户界面、状态管理、路由管理、知识图谱、管理后台、Leader 协调界面等功能。

## 变更记录 (Changelog)

### 2026-08-26
- **新增全局底部状态栏（对齐 OncoPath）**: 新增 `components/AppFooter.vue`（fixed 底栏：品牌版本/GitHub/赞助/协议/署名，移动端细条）与 `components/SponsorDialog.vue`（赞助弹窗：5 档金额卡 → 各档专属微信收款码 + 支付宝通用码入口，图片自 OncoPath 拷入）；新增 `composables/useAppVersion.js`（`/api/health` 版本号）与 `composables/useResponsive.js`（768 断点）；`utils/constants.js` 增 `REPO_URL`；`design-system.scss` 增 `--footer-height: 32px`；ChatLayout/ConversationDisplay/admin 布局高度改 `calc(100vh - var(--footer-height))`，ThemeToggle/beginner-help 抬升；embed 路由不展示；i18n 双语文案（common.footer/common.sponsor）

### 2026-08-23
- **移除计费与卡密界面（开源化）**: 删除 `Billing.vue`、`admin/CDKeys.vue`、`stores/billing.js`、billing i18n 与路由（`/billing`、`/admin/cdkeys`）；Home/Login 移除余额检查跳转；e2e 计费用例删除

### 2026-06-18
- **移除自定义指令功能**: 删除 `UserSettings.vue` 组件，移除 `auth.js` 中 `customInstructions` 状态及 `fetchCustomInstructions`/`updateCustomInstructions` 方法，移除 `Home.vue` 菜单入口

### 2026-06-14
- **项目初始化扫描**: 全面更新 CLAUDE.md
  - 确认前端组件从 10+ 扩至 50+ 个 Vue 组件
  - 确认新增知识图谱功能（KnowledgeGraphExplorer, KnowledgeUpload, KnowledgeDocList 等）
  - 确认新增管理后台页面（Dashboard, AgentEditor, CDKeys, OpenHarness 等）
  - 确认新增商业化页面（Billing）
  - 确认新增暗色主题（dark-mode.scss, ThemeToggle）
  - 确认新增 D3 知识图谱可视化（KnowledgeGraphViewer）
  - 确认新增 Mermaid 支持
  - 确认新增 Leader 审核评审组件（LeaderReviewDialog, LeaderOverallReviewDialog）
  - 确认新增 Playwright E2E 测试

### 2026-03-17
- 确认聊天界面增强功能稳定运行
- 导出 PDF/图片功能正常
- 建议问题功能正常
- Leader 相关组件完善

### 2026-03-06
- 新增聊天界面增强功能（ScrollToTopButton, ChatActionBar, SuggestedQuestions）

---

## 模块职责

- 用户界面渲染
- 用户认证流程
- 实时聊天交互（SSE）
- 对话管理界面
- 文件管理界面
- Agent 团队选择
- Leader 协调界面（含审核评审）
- 知识图谱可视化与交互
- 管理后台
- 暗色主题
- 状态管理（Pinia）
- 路由管理（Vue Router）

---

## 入口与启动

### 应用入口
- **主入口**: `src/main.js` - Vue 应用初始化
- **HTML 模板**: `index.html`

### 启动方式

```bash
# 开发模式
npm run dev        # 访问 http://localhost:5173

# 生产构建
npm run build
npm run preview
```

---

## 页面路由

```
/                        # Home（公开）
/login                   # 登录（公开）
/register                # 注册（公开）
/knowledge               # 知识图谱（需认证）
/agents                  # 用户端 Agent 管理（需认证）
/conversation/:token     # 分享对话（公开）

/chat                    # 聊天布局（需认证，带侧边栏）
  /chat                  # ChatHome
  /chat/:token           # ChatConversation

/admin                   # 管理后台（需认证 + 管理员）
  /admin/dashboard       # 仪表盘
  /admin/agents          # Agent 列表
  /admin/agents/:id      # Agent 详情
  /admin/agents/create   # 新建 Agent
  /admin/agents/:id/edit # 编辑 Agent
  /admin/performance     # 性能监控
  /admin/leader-sessions # Leader 会话
  /admin/tools           # 工具管理
  /admin/openharness     # OpenHarness 配置
  /admin/settings        # 系统设置
```

---

## 组件清单（50+）

### 核心组件
| 组件 | 路径 | 职责 |
|------|------|------|
| `ChatLayout.vue` | `views/` | 主聊天布局（含侧边栏） |
| `Home.vue` | `views/` | 首页/欢迎页 |
| `ConversationDisplay.vue` | `views/` | 会话聊天显示器 |
| `MarkdownRenderer.vue` | `components/` | Markdown 渲染（代码高亮） |
| `ThemeToggle.vue` | `components/` | 暗色主题切换 |

### Leader 协调组件
| 组件 | 路径 | 职责 |
|------|------|------|
| `LeaderThinking.vue` | `components/` | Leader 思考过程 |
| `LeaderQuestionDialog.vue` | `components/` | Leader 提问对话框 |
| `LeaderFinalReport.vue` | `components/` | 最终报告 |
| `AgentStatusPanel.vue` | `components/` | Agent 状态面板 |

### 知识图谱组件
| 组件 | 路径 | 职责 |
|------|------|------|
| `KnowledgePage.vue` | `views/` | 知识图谱主页面 |
| `KnowledgeGraphExplorer.vue` | `components/knowledge/` | D3 图谱可视化与浏览器 |
| `KnowledgeUpload.vue` | `components/knowledge/` | 知识库上传 |
| `KnowledgeDocList.vue` | `components/knowledge/` | 文档列表 |
| `KnowledgeCategoryManage.vue` | `components/knowledge/` | 分类管理 |
| `KnowledgeGapPanel.vue` | `components/knowledge/` | 知识缺口面板 |
| `NodeDetailPanel.vue` | `components/knowledge/` | 节点详情面板 |
| `CommunityFilter.vue` | `components/knowledge/` | 社区筛选 |

### 管理后台组件
| 组件 | 路径 | 职责 |
|------|------|------|
| `admin/Layout.vue` | `components/` | 后台布局（含侧边栏 + 管理员验证） |
| `admin/Header.vue` | `components/` | 后台头部导航 |
| `admin/Sidebar.vue` | `components/` | 后台侧边栏 |
| `admin/StatsCard.vue` | `components/` | 统计卡片 |
| `admin/PerformanceChart.vue` | `components/` | 性能图表 |

### Agent 生态组件
| 组件 | 路径 | 职责 |
|------|------|------|
| `AgentCard.vue` | `components/agent/` | Agent 员工卡组件（响应式：桌面纵向/移动横向） |
| `AgentPortrait.vue` | `components/agent/` | Agent 头像组件（三级降级：portrait_url → DiceBear → 首字） |
| `AgentsPage.vue` | `views/` | 用户端 Agent 管理页（卡片网格 + 分类 Tab） |
| `AgentCreateDialog.vue` | `views/` | 用户 Agent 创建/编辑弹窗 |

### 页面组件
| 页面 | 路径 | 职责 |
|------|------|------|
| `Dashboard.vue` | `views/admin/` | 管理员仪表盘 |
| `Agents.vue` | `views/admin/` | Agent 管理列表 |
| `AgentDetail.vue` | `views/admin/` | Agent 详情 |
| `AgentEditor.vue` | `views/admin/` | Agent 编辑器 |
| `OpenHarness.vue` | `views/admin/` | OpenHarness 配置 |
| `Tools.vue` | `views/admin/` | 工具管理 |
| `Settings.vue` | `views/admin/` | 系统设置 |
| `Performance.vue` | `views/admin/` | 性能监控 |
| `LeaderSessions.vue` | `views/admin/` | Leader 会话管理 |

### 增强组件
| 组件 | 路径 | 职责 |
|------|------|------|
| `ScrollToTopButton.vue` | `components/` | 返回顶部浮动按钮 |
| `ChatActionBar.vue` | `components/` | 对话操作工具条（复制、PDF、图片） |
| `ToolCallVisualization.vue` | `components/` | 工具调用可视化 |
| `EditIndicator.vue` | `components/` | 编辑指示器 |
| `ConversationSidebar.vue` | `components/` | 对话侧边栏 |

> 注：SuggestedQuestions、FileManager、TeamSelector、ModelSelector、FeedbackStats、ReportFeedback 已归档至 `components/__archive__/`。

---

## 状态管理（Pinia Stores）

| Store | 文件 | 状态 |
|------|------|------|
| `auth` | `stores/auth.js` | 认证 Token、用户信息、管理员状态 |
| `conversations` | `stores/conversations.js` | 对话列表、当前对话、消息 |
| `agents` | `stores/agents.js` | Agent 列表、当前 Agent |
| `leader` | `stores/leader.js` | Leader 会话、执行状态、审核 |
| `admin` | `stores/admin.js` | 管理后台状态 |
| `knowledge` | `stores/knowledge.js` | 知识图谱文档、节点 |
| `draft` | `stores/draft.js` | 草稿编辑 |

---

## 关键依赖

```json
{
  "vue": "^3.4.0",
  "vue-router": "^4.2.0",
  "pinia": "^2.1.0",
  "element-plus": "^2.5.0",
  "axios": "^1.6.0",
  "marked": "^11.0.0",
  "highlight.js": "^11.9.0",
  "d3": "^7.9.0",
  "mermaid": "^11.13.0",
  "dompurify": "^3.4.7",
  "dayjs": "^1.11.0",
  "html2pdf.js": "^0.14.0",
  "html2canvas": "^1.4.1",
  "jsencrypt": "^3.3.2",
  "splitpanes": "^4.0.4"
}
```

## 测试

```bash
# 单元测试（Vitest + happy-dom）
npm run test

# E2E 测试（Playwright）
npm run test:e2e
npm run test:e2e:ui  # UI 模式

# 构建验证
npm run build
```

---

## 关键功能实现

### SSE 流式聊天
ChatLayout.vue / ConversationDisplay.vue 通过 EventSource 或 fetch 流式接收 chat API 响应，实时渲染 Markdown。

### 知识图谱可视化
使用 D3.js 力导向图渲染知识节点与关系，支持社区筛选、节点跳转、桥接高亮。

### 暗色主题
通过 ThemeToggle.vue 切换，CSS 变量体系定义在 dark-mode.scss，Element Plus 通过 CSS 变量覆盖。

### 管理后台
/admin 路由受 `requiresAdmin` 守卫保护，侧边栏 Layout 组件验证用户权限。

---

**文档生成时间**: 2026-08-25
