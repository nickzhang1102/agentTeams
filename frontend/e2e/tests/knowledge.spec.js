/**
 * Knowledge 页面测试
 *
 * 测试知识库文档管理功能
 */
import { test, expect } from '../fixtures/base'

test.describe('Knowledge 页面', () => {
  test.use({ storageState: '.auth/user.json' })

  test.beforeEach(async ({ page }) => {
    await page.goto('/knowledge')
    // 等待页面加载
    await page.waitForSelector('.status-card', { timeout: 10000 })
  })

  test('应显示文档统计卡片', async ({ page }) => {
    // 检查统计卡片
    const statusCard = page.locator('.status-card')
    await expect(statusCard).toBeVisible()

    // 检查标题
    const statusTitle = statusCard.locator('.status-title')
    await expect(statusTitle).toHaveText('文档统计')
  })

  test('应显示统计数据', async ({ page }) => {
    // 检查统计项
    const statsSection = page.locator('.status-stats')
    await expect(statsSection).toBeVisible()

    // 检查总文档
    const totalDocs = statsSection.locator('.stat-item:has-text("总文档")')
    await expect(totalDocs).toBeVisible()

    // 检查已索引
    const indexedDocs = statsSection.locator('.stat-item:has-text("已索引")')
    await expect(indexedDocs).toBeVisible()

    // 检查待处理
    const pendingDocs = statsSection.locator('.stat-item:has-text("待处理")')
    await expect(pendingDocs).toBeVisible()
  })

  test('应显示 Tab 切换', async ({ page }) => {
    // 检查 Tab 组件
    const tabs = page.locator('.knowledge-tabs')
    await expect(tabs).toBeVisible()

    // 检查文档列表 Tab
    const documentsTab = tabs.locator('.el-tabs__item:has-text("文档列表")')
    await expect(documentsTab).toBeVisible()

    // 检查知识图谱 Tab
    const graphTab = tabs.locator('.el-tabs__item:has-text("知识图谱")')
    await expect(graphTab).toBeVisible()
  })

  test('默认应显示文档列表 Tab', async ({ page }) => {
    // 检查文档列表 Tab 是否激活
    const activeTab = page.locator('.el-tabs__item.is-active')
    await expect(activeTab).toHaveText('文档列表')
  })

  test('点击知识图谱 Tab 应切换内容', async ({ page }) => {
    // 点击知识图谱 Tab
    const graphTab = page.locator('.el-tabs__item:has-text("知识图谱")')
    await graphTab.click()

    // 等待切换
    await page.waitForTimeout(1000)

    // 检查知识图谱组件显示（实际组件类名）
    const graphViewer = page.locator('.graph-viewer')
    const graphEmpty = page.locator('.graph-empty')
    const graphLoading = page.locator('.graph-loading')
    const graphContainer = page.locator('.graph-container')

    // 知识图谱组件应该显示（即使为空状态）
    const hasGraphViewer = await graphViewer.count() > 0
    const hasGraphEmpty = await graphEmpty.count() > 0
    const hasGraphLoading = await graphLoading.count() > 0
    const hasGraphContainer = await graphContainer.count() > 0

    expect(hasGraphViewer || hasGraphEmpty || hasGraphLoading || hasGraphContainer).toBeTruthy()
  })

  test('应显示返回按钮', async ({ page }) => {
    const backButton = page.locator('.back-btn')
    await expect(backButton).toBeVisible()
  })

  test('点击返回按钮应跳转首页', async ({ page }) => {
    const backButton = page.locator('.back-btn')
    await backButton.click()

    // 等待跳转
    await page.waitForURL('/', { timeout: 10000 })
  })

  test('应显示用户菜单', async ({ page }) => {
    const userMenu = page.locator('.user-menu')
    await expect(userMenu).toBeVisible()
  })

  test('点击用户菜单应显示下拉选项', async ({ page }) => {
    // 点击用户菜单
    await page.click('.user-info')

    // 等待下拉菜单
    await page.waitForSelector('.el-dropdown-menu', { timeout: 3000 })

    // 检查下拉选项
    const dropdownMenu = page.locator('.el-dropdown-menu')
    await expect(dropdownMenu).toBeVisible()
  })
})

test.describe('Knowledge 页面文档列表', () => {
  test.use({ storageState: '.auth/user.json' })

  test.beforeEach(async ({ page }) => {
    await page.goto('/knowledge')
    await page.waitForSelector('.knowledge-tabs', { timeout: 10000 })
  })

  test('文档列表应显示搜索框或空状态', async ({ page }) => {
    // 检查搜索输入框
    const searchInput = page.locator('input[placeholder*="搜索"]')
    const hasSearchInput = await searchInput.count() > 0

    // 如果没有搜索框，可能文档列表为空显示空状态
    if (!hasSearchInput) {
      const emptyState = page.locator('.empty-state, .no-data')
      const hasEmptyState = await emptyState.count() > 0
      expect(hasEmptyState).toBeTruthy()
    } else {
      await expect(searchInput.first()).toBeVisible()
    }
  })

  test('文档列表应有分类筛选或文档卡片', async ({ page }) => {
    // 实际组件使用 .doc-list-card, .tabs, .doc-table
    const docListCard = page.locator('.doc-list-card')
    const tabs = page.locator('.tabs')
    const docTable = page.locator('.doc-table')

    const hasDocListCard = await docListCard.count() > 0
    const hasTabs = await tabs.count() > 0
    const hasDocTable = await docTable.count() > 0

    // 应有文档列表卡片或 Tab 分类筛选
    expect(hasDocListCard || hasTabs || hasDocTable).toBeTruthy()
  })
})