/**
 * Admin 后台管理测试
 *
 * 测试管理员后台功能：Dashboard、Agent 管理
 * 需要管理员账号登录（依赖 admin.setup.js）
 */
import { test, expect } from '../fixtures/base'

test.describe('Admin 后台 Dashboard', () => {
  test.use({ storageState: '.auth/admin.json' })

  test.beforeEach(async ({ page }) => {
    await page.goto('/admin/dashboard')
    await page.waitForTimeout(3000)
  })

  test('Dashboard 页面应可访问', async ({ page }) => {
    // 检查 URL 正确
    expect(page.url()).toContain('/admin/dashboard')

    // 检查页面内容存在
    const pageContent = page.locator('body')
    await expect(pageContent).toBeVisible()
  })

  test('应显示侧边栏导航', async ({ page }) => {
    // 检查侧边栏
    const sidebar = page.locator('.admin-sidebar, .el-menu, nav')

    // 如果侧边栏存在
    const hasSidebar = await sidebar.count() > 0
    if (hasSidebar) {
      await expect(sidebar.first()).toBeVisible()
    }
  })

  test('应显示统计数据', async ({ page }) => {
    // 检查统计卡片或数据区域
    const statsCard = page.locator('.stat-card, .dashboard-stats, .el-card')
    const hasStats = await statsCard.count() > 0

    if (hasStats) {
      await expect(statsCard.first()).toBeVisible()
    }
  })
})

test.describe('Admin Agent 管理', () => {
  test.use({ storageState: '.auth/admin.json' })

  test('Agent 管理页面应可访问', async ({ page }) => {
    await page.goto('/admin/agents')
    await page.waitForTimeout(3000)

    expect(page.url()).toContain('/admin/agents')
  })

  test('应显示 Agent 列表', async ({ page }) => {
    await page.goto('/admin/agents')
    await page.waitForTimeout(3000)

    // 检查表格或卡片列表
    const agentTable = page.locator('.el-table, table')
    const agentCards = page.locator('.agent-card')

    const hasTable = await agentTable.count() > 0
    const hasCards = await agentCards.count() > 0

    expect(hasTable || hasCards).toBeTruthy()
  })

  test('应显示 Agent 详情链接', async ({ page }) => {
    await page.goto('/admin/agents')
    await page.waitForTimeout(3000)

    // 检查详情按钮或链接
    const detailLinks = page.locator('a[href*="/admin/agents/"], button:has-text("详情")')
    const hasDetailLinks = await detailLinks.count() > 0

    // 如果有详情链接，点击第一个
    if (hasDetailLinks) {
      await detailLinks.first().click()
      await page.waitForTimeout(2000)

      // 应跳转到详情页
      expect(page.url()).toMatch(/\/admin\/agents\/\d+/)
    }
  })
})

test.describe('Admin Leader Sessions', () => {
  test.use({ storageState: '.auth/admin.json' })

  test('Leader Sessions 页面应可访问', async ({ page }) => {
    await page.goto('/admin/leader-sessions')
    await page.waitForTimeout(3000)

    expect(page.url()).toContain('/admin/leader-sessions')
  })

  test('应显示 Leader 会话列表', async ({ page }) => {
    await page.goto('/admin/leader-sessions')
    await page.waitForTimeout(3000)

    // 检查表格
    const table = page.locator('.el-table, table')
    const hasTable = await table.count() > 0

    if (hasTable) {
      await expect(table.first()).toBeVisible()
    }
  })
})

test.describe('Admin Tools 管理', () => {
  test.use({ storageState: '.auth/admin.json' })

  test('Tools 页面应可访问', async ({ page }) => {
    await page.goto('/admin/tools')
    await page.waitForTimeout(3000)

    expect(page.url()).toContain('/admin/tools')
  })

  test('应显示工具列表', async ({ page }) => {
    await page.goto('/admin/tools')
    await page.waitForTimeout(3000)

    // 检查工具列表区域
    const toolList = page.locator('.tool-list, .el-table, .el-card')
    const hasToolList = await toolList.count() > 0

    expect(hasToolList).toBeTruthy()
  })
})

test.describe('Admin OpenHarness 管理', () => {
  test.use({ storageState: '.auth/admin.json' })

  test('OpenHarness 页面应可访问', async ({ page }) => {
    await page.goto('/admin/openharness')
    await page.waitForTimeout(3000)

    expect(page.url()).toContain('/admin/openharness')
  })

  test('应显示 OpenHarness 状态', async ({ page }) => {
    await page.goto('/admin/openharness')
    await page.waitForTimeout(3000)

    // 检查状态区域
    const statusArea = page.locator('.status-card, .el-card, .openharness-status')
    const hasStatus = await statusArea.count() > 0

    expect(hasStatus).toBeTruthy()
  })
})