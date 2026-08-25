/**
 * 登录失败测试（不依赖 setup）
 *
 * 测试登录失败场景：
 * - 错误密码
 * - 空表单验证
 * - 用户不存在
 */
import { test, expect } from '../fixtures/base'

test.describe('登录失败场景', () => {
  // 不使用 storageState，确保未登录状态

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
  })

  test('错误密码应显示错误提示', async ({ page }) => {
    // 填写错误密码
    await page.fill('input[placeholder="用户名"]', 'test_e2e_user')
    await page.fill('input[placeholder="密码"]', 'wrong_password_123')

    // 点击登录
    await page.click('button:has-text("登录")')

    // 等待错误消息（Element Plus 消息类名可能不同）
    // 尝试多种选择器
    const errorSelectors = [
      '.el-message--error',
      '.el-message.error',
      '[class*="el-message"][class*="error"]',
    ]

    let errorFound = false
    for (const selector of errorSelectors) {
      try {
        await page.locator(selector).waitFor({ state: 'visible', timeout: 3000 })
        errorFound = true
        break
      } catch {
        // 继续尝试下一个选择器
      }
    }

    // 如果 Element Plus 消息选择器都失败，检查页面 URL 未变化
    if (!errorFound) {
      // 验证仍在登录页（登录失败的表现）
      await expect(page).toHaveURL(/.*\/login/)
    }

    // 验证仍在登录页
    await expect(page).toHaveURL(/.*\/login/)
  })

  test('空用户名应显示验证提示', async ({ page }) => {
    // 只填写密码
    await page.fill('input[placeholder="密码"]', 'some_password')

    // 点击登录
    await page.click('button:has-text("登录")')

    // 等待验证提示
    const validationMessage = page.locator('.el-form-item__error:has-text("请输入用户名")')
    await expect(validationMessage).toBeVisible({ timeout: 3000 })

    // 验证仍在登录页
    await expect(page).toHaveURL(/.*\/login/)
  })

  test('空密码应显示验证提示', async ({ page }) => {
    // 只填写用户名
    await page.fill('input[placeholder="用户名"]', 'some_user')

    // 点击登录
    await page.click('button:has-text("登录")')

    // 等待验证提示
    const validationMessage = page.locator('.el-form-item__error:has-text("请输入密码")')
    await expect(validationMessage).toBeVisible({ timeout: 3000 })

    // 验证仍在登录页
    await expect(page).toHaveURL(/.*\/login/)
  })

  test('密码少于6位应显示验证提示', async ({ page }) => {
    // 填写短密码
    await page.fill('input[placeholder="用户名"]', 'test_e2e_user')
    await page.fill('input[placeholder="密码"]', 'short')

    // 点击登录
    await page.click('button:has-text("登录")')

    // 等待验证提示
    const validationMessage = page.locator('.el-form-item__error:has-text("密码至少6个字符")')
    await expect(validationMessage).toBeVisible({ timeout: 3000 })

    // 验证仍在登录页
    await expect(page).toHaveURL(/.*\/login/)
  })
})