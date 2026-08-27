/**
 * 主页 Tab 切换测试
 *
 * 测试精选会话和我的会话 Tab 切换功能
 */
import { test, expect } from '../fixtures/base'

test.describe('主页 Tab 切换', () => {
  test('默认应显示精选会话 Tab', async ({ page }) => {
    await page.goto('/')

    // 检查精选会话 Tab 是否激活
    const featuredTab = page.locator('.tab:has-text("精选会话")')
    await expect(featuredTab).toHaveClass(/active/)

    // 检查精选会话内容显示
    const casesGrid = page.locator('.cases-grid')
    await expect(casesGrid).toBeVisible()

    // 检查至少有一个案例卡片
    const caseCards = page.locator('.case-card')
    const count = await caseCards.count()
    expect(count).toBeGreaterThan(0)
  })

  test('点击我的会话 Tab 应切换到我的会话', async ({ page }) => {
    await page.goto('/')

    // 点击我的会话 Tab
    await page.click('.tab:has-text("我的会话")')

    // 检查我的会话 Tab 是否激活
    const mineTab = page.locator('.tab:has-text("我的会话")')
    await expect(mineTab).toHaveClass(/active/)

    // 精选会话 Tab 不应激活
    const featuredTab = page.locator('.tab:has-text("精选会话")')
    await expect(featuredTab).not.toHaveClass(/active/)
  })

  test('未登录时我的会话应显示空状态', async ({ page }) => {
    await page.goto('/')

    // 点击我的会话 Tab
    await page.click('.tab:has-text("我的会话")')

    // 等待内容加载
    await page.waitForTimeout(1000)

    // 检查空状态显示（未登录用户看到空状态）
    const emptyState = page.locator('.empty-state')

    // 检查空状态是否可见
    const isVisible = await emptyState.isVisible()

    // 如果空状态不可见，检查是否有案例卡片（可能已登录）
    if (!isVisible) {
      const caseCards = page.locator('.cases-grid .case-card')
      const cardCount = await caseCards.count()
      // 如果有案例卡片，说明已登录，跳过此测试
      if (cardCount > 0) {
        test.skip('User appears to be logged in')
        return
      }
    }

    // 检查空状态提示文本
    await expect(emptyState.locator('p:has-text("还没有对话记录")')).toBeVisible()
  })
})

test.describe('主页 Tab 切换（已认证）', () => {
  test.use({ storageState: '.auth/user.json' })

  test('已登录我的会话应显示对话列表或空状态', async ({ page }) => {
    await page.goto('/')

    // 点击我的会话 Tab
    await page.click('.tab:has-text("我的会话")')

    // 等待 API 响应
    await page.waitForTimeout(2000)

    // 检查是否显示对话列表或空状态
    const casesGrid = page.locator('.cases-grid')
    const emptyState = page.locator('.empty-state')

    // 两种情况都是正常的
    const hasCards = await casesGrid.locator('.case-card').count() > 0
    const hasEmpty = await emptyState.isVisible()

    expect(hasCards || hasEmpty).toBeTruthy()
  })
})