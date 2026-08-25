/**
 * 注册流程测试
 *
 * 测试用户注册功能
 */
import { test, expect } from '../fixtures/base'

// 生成随机用户名避免冲突
function generateRandomUsername() {
  return `test_user_${Date.now()}_${Math.floor(Math.random() * 1000)}`
}

test.describe('注册页面', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/register')
    await page.waitForSelector('.register-container, form', { timeout: 10000 })
  })

  test('应显示注册表单', async ({ page }) => {
    // 检查表单存在
    const form = page.locator('form, .register-form')
    await expect(form).toBeVisible()
  })

  test('应显示用户名输入框', async ({ page }) => {
    const usernameInput = page.locator('input[placeholder*="用户名"]')
    await expect(usernameInput).toBeVisible()
  })

  test('应显示邮箱输入框', async ({ page }) => {
    const emailInput = page.locator('input[placeholder*="邮箱"]')
    await expect(emailInput).toBeVisible()
  })

  test('应显示密码输入框', async ({ page }) => {
    const passwordInput = page.locator('input[type="password"]').first()
    await expect(passwordInput).toBeVisible()
  })

  test('应显示确认密码输入框', async ({ page }) => {
    const confirmInput = page.locator('input[placeholder*="确认"]')
    await expect(confirmInput).toBeVisible()
  })

  test('应显示注册按钮', async ({ page }) => {
    const registerButton = page.locator('button:has-text("注册")')
    await expect(registerButton).toBeVisible()
  })

  test('应显示返回登录链接', async ({ page }) => {
    const loginLink = page.locator('a:has-text("登录"), button:has-text("登录")')
    const hasLoginLink = await loginLink.count() > 0

    // 如果有登录链接或按钮
    if (hasLoginLink) {
      await expect(loginLink.first()).toBeVisible()
    }
  })
})

test.describe('注册验证', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/register')
    await page.waitForSelector('form', { timeout: 10000 })
  })

  test('空用户名应显示验证提示', async ({ page }) => {
    // 直接点击注册按钮
    await page.click('button:has-text("注册")')

    // 等待验证触发
    await page.waitForTimeout(1000)

    // 检查验证错误
    const errorItems = page.locator('.el-form-item.is-error, .error-message')
    const hasError = await errorItems.count() > 0

    expect(hasError).toBeTruthy()
  })

  test('空邮箱应显示验证提示', async ({ page }) => {
    await page.click('button:has-text("注册")')
    await page.waitForTimeout(1000)

    const errorItems = page.locator('.el-form-item.is-error')
    const hasError = await errorItems.count() > 0

    expect(hasError).toBeTruthy()
  })

  test('密码少于6位应显示验证提示', async ({ page }) => {
    // 填写表单
    await page.fill('input[placeholder*="用户名"]', 'testuser')
    await page.fill('input[placeholder*="邮箱"]', 'test@test.com')
    await page.fill('input[placeholder*="密码"]', '12345')  // 5位
    await page.fill('input[placeholder*="确认"]', '12345')

    await page.click('button:has-text("注册")')
    await page.waitForTimeout(1000)

    const errorItems = page.locator('.el-form-item.is-error')
    const hasError = await errorItems.count() > 0

    expect(hasError).toBeTruthy()
  })

  test('两次密码不一致应显示验证提示', async ({ page }) => {
    await page.fill('input[placeholder*="用户名"]', 'testuser')
    await page.fill('input[placeholder*="邮箱"]', 'test@test.com')
    await page.fill('input[placeholder*="密码"]', 'password123')
    await page.fill('input[placeholder*="确认"]', 'different123')

    await page.click('button:has-text("注册")')
    await page.waitForTimeout(1000)

    const errorItems = page.locator('.el-form-item.is-error')
    const hasError = await errorItems.count() > 0

    expect(hasError).toBeTruthy()
  })

  test('无效邮箱格式应显示验证提示', async ({ page }) => {
    await page.fill('input[placeholder*="用户名"]', 'testuser')
    await page.fill('input[placeholder*="邮箱"]', 'invalid-email')
    await page.fill('input[placeholder*="密码"]', 'password123')
    await page.fill('input[placeholder*="确认"]', 'password123')

    await page.click('button:has-text("注册")')
    await page.waitForTimeout(1000)

    const errorItems = page.locator('.el-form-item.is-error')
    const hasError = await errorItems.count() > 0

    expect(hasError).toBeTruthy()
  })
})

test.describe('注册成功流程', () => {
  test('注册成功应跳转登录页', async ({ page }) => {
    const randomUsername = generateRandomUsername()

    // 填写完整表单
    await page.goto('/register')
    await page.waitForSelector('form', { timeout: 10000 })

    await page.fill('input[placeholder*="用户名"]', randomUsername)
    await page.fill('input[placeholder*="邮箱"]', `${randomUsername}@test.local`)
    await page.fill('input[placeholder*="密码"]', 'password123')
    await page.fill('input[placeholder*="确认"]', 'password123')

    // 点击注册
    await page.click('button:has-text("注册")')

    // 等待跳转到登录页
    await page.waitForURL('/login', { timeout: 15000 })

    // 验证跳转成功
    expect(page.url()).toContain('/login')
  })
})

test.describe('已登录用户访问注册页', () => {
  test.use({ storageState: '.auth/user.json' })

  test('已登录访问注册页应跳转首页', async ({ page }) => {
    await page.goto('/register')

    // 等待跳转到首页
    await page.waitForURL('/', { timeout: 10000 })

    expect(page.url()).not.toContain('/register')
  })
})