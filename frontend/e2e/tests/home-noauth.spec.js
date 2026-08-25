/**
 * 主页未认证状态测试
 *
 * 不使用 storageState，测试未登录用户看到的内容
 */
import { test, expect } from '../fixtures/base'

test.describe('主页未认证状态', () => {
  test.beforeEach(async ({ page }) => {
    // 确保未登录状态
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())
    await page.reload()
  })

  test('未登录应显示登录/注册按钮', async ({ page }) => {
    await page.goto('/')

    // 检查登录按钮
    const loginButton = page.locator('button:has-text("登录")')
    await expect(loginButton).toBeVisible()

    // 检查注册按钮
    const registerButton = page.locator('button:has-text("注册")')
    await expect(registerButton).toBeVisible()
  })

  test('未登录点击发送应跳转登录页', async ({ page }) => {
    await page.goto('/')

    // 填写输入
    await page.fill('.main-input', '测试消息内容')

    // 点击发送
    await page.click('button:has-text("开始分析")')

    // 等待跳转到登录页
    await expect(page).toHaveURL(/.*\/login/, { timeout: 5000 })
  })
})