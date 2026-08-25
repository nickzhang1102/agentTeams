/**
 * 登录流程测试（成功场景）
 *
 * 依赖 auth.setup，继承已登录状态
 * 测试登录成功后的页面行为
 */
import { test, expect } from '../fixtures/base'

test.describe('登录成功场景', () => {
  // 使用 setup 保存的登录状态
  test.use({ storageState: '.auth/user.json' })

  test('登录成功后应跳转到主页', async ({ page }) => {
    // 已登录状态访问登录页，应自动跳转到主页
    await page.goto('/login')

    // 等待跳转
    await expect(page).toHaveURL(/.*\/$/, { timeout: 5000 })
  })

  test('主页应显示用户信息', async ({ page }) => {
    await page.goto('/')

    // 检查用户菜单存在（已认证状态）
    const userMenu = page.locator('.user-menu')
    await expect(userMenu).toBeVisible()

    // 检查用户名显示
    const username = page.locator('.username')
    await expect(username).toBeVisible()
  })

  test('主页应显示退出按钮', async ({ page }) => {
    await page.goto('/')

    // 点击用户菜单展开
    await page.click('.user-info')

    // 检查退出登录选项
    const logoutItem = page.locator('.el-dropdown-menu__item:has-text("退出登录")')
    await expect(logoutItem).toBeVisible()
  })
})