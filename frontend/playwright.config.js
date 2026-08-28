/**
 * Playwright E2E 测试配置
 *
 * 测试环境：
 * - 前端: localhost:5173 (Vite dev server)
 * - 后端: localhost:5000 (FastAPI server)
 * - 浏览器: Chromium (默认)
 */
import { defineConfig, devices } from '@playwright/test'

const frontendBaseURL = process.env.FRONT_BASE_URL || 'http://localhost:5173'

export default defineConfig({
  // 测试目录
  testDir: './e2e',

  // 并行执行
  fullyParallel: true,

  // CI 环境禁止 test.only
  forbidOnly: !!process.env.CI,

  // CI 环境重试 2 次
  retries: process.env.CI ? 2 : 0,

  // CI 环境单 worker，本地不限
  workers: process.env.CI ? 1 : undefined,

  // 报告器
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report' }]
  ],

  // 全局配置
  use: {
    baseURL: frontendBaseURL,
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 10000,
    navigationTimeout: 30000,
  },

  // 测试项目
  projects: [
    // Setup 项目：登录并保存状态
    {
      name: 'setup',
      testMatch: /auth\.setup\.js/,
    },

    // 登录失败测试（不依赖 setup，无登录状态）
    {
      name: 'login-fail',
      testMatch: /tests\/login-fail\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // 主页未认证测试（不依赖 setup，无登录状态）
    {
      name: 'home-noauth',
      testMatch: /tests\/(home-noauth|locale-switcher)\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // 认证完整流程测试（依赖 setup，保证账号存在）
    {
      name: 'auth-flow',
      testMatch: /tests\/auth\.spec\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // Chromium 已认证测试（依赖 setup）
    {
      name: 'chromium-auth',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
      testMatch: [
        /tests\/login\.spec\.js/,
        /tests\/home-auth\.spec\.js/,
        /tests\/password-change\.spec\.js/,
      ],
    },

    // 主页 Tab 切换测试（无需认证）
    {
      name: 'home-tabs',
      testMatch: /tests\/home-tabs\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // 主页 Tab 切换已认证测试（依赖 setup）
    {
      name: 'home-tabs-auth',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
      testMatch: /tests\/home-tabs\.spec\.js/,
    },

    // 精选案例测试（无需认证，公开访问）
    {
      name: 'featured-case',
      testMatch: /tests\/featured-case\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // Agent Teams embed 页面公开访问，不依赖登录或真实后端。
    {
      name: 'agentteams-embed',
      testMatch: /tests\/agentteams-embed\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // Evidence drawer layout states are self-contained and use mocked detail responses.
    {
      name: 'evidence-drawer-desktop',
      testMatch: /tests\/report-evidence-drawer\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // 嵌入会诊页渲染回归：快照式一次性挂载下 mermaid 图表必须完成渲染，
    // 跨 Agent 的 scoped 证据引用必须转成可点击引用而非明文。
    {
      name: 'embed-consultation-render',
      testMatch: /tests\/embed-consultation-render\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },
    {
      name: 'evidence-drawer-mobile',
      testMatch: /tests\/report-evidence-drawer\.spec\.js/,
      use: {
        ...devices['Pixel 7'],
      },
    },

    // 聊天核心流程测试（依赖 setup）
    {
      name: 'chat-core',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
      testMatch: /tests\/chat-core\.spec\.js/,
    },

    // Knowledge 页面测试（依赖 setup）
    {
      name: 'knowledge-auth',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
      testMatch: /tests\/knowledge\.spec\.js/,
    },

    // Knowledge 页面未认证测试（不依赖 setup）
    {
      name: 'knowledge-noauth',
      testMatch: /tests\/knowledge-noauth\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // 对话详情页测试（公开访问）
    {
      name: 'conversation-public',
      testMatch: /tests\/conversation\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // 对话详情页已认证测试
    {
      name: 'conversation-auth',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
      testMatch: /tests\/conversation\.spec\.js/,
    },

    // 注册页面测试（无需认证）
    {
      name: 'register-noauth',
      testMatch: /tests\/register\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // 注册页面已认证测试
    {
      name: 'register-auth',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
      testMatch: /tests\/register-auth\.spec\.js/,
    },

    // Admin Setup：管理员登录
    {
      name: 'admin-setup',
      testMatch: /admin\.setup\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // Admin 后台管理测试
    {
      name: 'admin-tests',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/admin.json',
      },
      dependencies: ['admin-setup'],
      testMatch: /tests\/admin(?:-localization)?\.spec\.js/,
    },

    // Admin 多语言移动端布局检查
    {
      name: 'admin-localization-mobile',
      use: {
        ...devices['Pixel 7'],
        storageState: '.auth/admin.json',
      },
      dependencies: ['admin-setup'],
      testMatch: /tests\/admin-localization\.spec\.js/,
    },

    // 实际聊天执行测试
    {
      name: 'chat-execution',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
      testMatch: /tests\/chat-execution\.spec\.js/,
    },

    // 文件上传完整流程测试
    {
      name: 'file-upload',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
      testMatch: /tests\/file-upload\.spec\.js/,
    },
  ],

  // 前端服务（本地自动启动，CI 不复用）
  webServer: {
    command: process.env.FRONT_DEV_COMMAND || 'npm run dev',
    url: frontendBaseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
})
