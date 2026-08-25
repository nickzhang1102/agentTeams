/**
 * 认证完整流程测试
 *
 * 测试完整的用户认证流程：
 * - 登录 → 主页 → 操作 → 退出
 *
 * 注意：这些测试不使用已登录状态，而是从登录页开始
 */
import { test, expect } from '../fixtures/base'
import { TEST_USER } from '../fixtures/base'

// 不使用 storageState，从头开始测试完整流程
test.describe('认证完整流程', () => {
  test('完整流程：登录 → 主页 → 退出', async ({ page }) => {
    // 先导航到页面，再清除登录状态
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())

    // Step 1: 访问登录页
    await page.goto('/login')

    // Step 2: 登录
    await page.fill('input[placeholder="用户名"]', TEST_USER.username)
    await page.fill('input[placeholder="密码"]', TEST_USER.password)
    await page.click('button:has-text("登录")')

    // Step 3: 等待跳转到主页
    await expect(page).toHaveURL(/.*\/$/, { timeout: 10000 })

    // Step 4: 验证主页显示用户信息
    const userMenu = page.locator('.user-menu')
    await expect(userMenu).toBeVisible()

    // Step 5: 点击用户菜单展开
    await page.click('.user-info')

    // Step 6: 点击退出登录
    await page.click('.el-dropdown-menu__item:has-text("退出登录")')

    // Step 7: 验证跳转到主页（未认证状态）
    await expect(page).toHaveURL(/.*\/$/, { timeout: 5000 })

    // Step 8: 验证显示登录/注册按钮
    const loginButton = page.locator('button:has-text("登录")')
    await expect(loginButton).toBeVisible()
  })

  test('登录后访问登录页应跳转主页', async ({ page }) => {
    // 先导航到页面，再清除登录状态
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())

    // 先登录
    await page.goto('/login')
    await page.fill('input[placeholder="用户名"]', TEST_USER.username)
    await page.fill('input[placeholder="密码"]', TEST_USER.password)
    await page.click('button:has-text("登录")')
    await expect(page).toHaveURL(/.*\/$/, { timeout: 10000 })

    // 再次访问登录页
    await page.goto('/login')

    // 应自动跳转到主页
    await expect(page).toHaveURL(/.*\/$/, { timeout: 5000 })
  })
})