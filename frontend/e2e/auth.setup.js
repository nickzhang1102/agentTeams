/**
 * 认证 Setup
 *
 * 登录测试账号并保存状态到 .auth/user.json
 * 其他测试项目依赖此 setup，继承登录状态
 *
 * 策略：
 * 1. 尝试通过页面登录
 * 2. 如果失败（账号不存在），通过注册页面注册
 * 3. 重新登录并保存状态
 */
import { test as setup } from '@playwright/test'

// 测试账号配置（与 fixtures/base.js 保持一致）
const TEST_USER = {
  username: process.env.E2E_TEST_USER || 'test_e2e_user',
  password: process.env.E2E_TEST_PASSWORD || 'test_e2e_password',
  email: process.env.E2E_TEST_EMAIL || 'test_e2e_user@test.local',
}

// Setup：通过页面登录并保存状态
setup('authenticate', async ({ page }) => {
  // 尝试登录
  await page.goto('/login')
  await page.fill('input[placeholder="用户名"]', TEST_USER.username)
  await page.fill('input[placeholder="密码"]', TEST_USER.password)
  await page.click('button:has-text("登录")')

  // 等待 3 秒观察结果
  await page.waitForTimeout(3000)

  // 检查是否成功登录（URL 不在登录页）
  const isLoggedIn = !page.url().includes('/login')

  if (!isLoggedIn) {
    // 登录失败，通过注册页面注册
    console.log('Login failed, attempting to register test user via register page...')

    // 访问注册页面
    await page.goto('/register')

    // 填写注册表单
    await page.fill('input[placeholder="用户名"]', TEST_USER.username)
    await page.fill('input[placeholder="邮箱"]', TEST_USER.email)
    await page.fill('input[placeholder="密码"]', TEST_USER.password)
    await page.fill('input[placeholder="确认密码"]', TEST_USER.password)

    // 点击注册按钮
    await page.click('button:has-text("注册")')

    // 等待注册成功（跳转到登录页）
    await page.waitForURL('/login', { timeout: 15000 })

    // 等待成功消息
    await page.waitForTimeout(2000)

    // 重新登录
    await page.fill('input[placeholder="用户名"]', TEST_USER.username)
    await page.fill('input[placeholder="密码"]', TEST_USER.password)
    await page.click('button:has-text("登录")')

    // 等待登录成功
    await page.waitForURL('/', { timeout: 15000 })
  }

  // 验证登录状态（检查 localStorage 是否有 token）
  const token = await page.evaluate(() => localStorage.getItem('token'))
  if (!token) {
    throw new Error('Login failed: no token in localStorage')
  }

  // 保存存储状态（含 localStorage 和 cookies）
  await page.context().storageState({ path: '.auth/user.json' })
})