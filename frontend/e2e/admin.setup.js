/**
 * Admin 认证 Setup
 *
 * 登录管理员账号并保存状态到 .auth/admin.json
 * 其他 Admin 测试项目依赖此 setup
 */
import { test as setup } from '@playwright/test'

const ADMIN_USER = {
  username: process.env.E2E_ADMIN_USER || 'admin_e2e',
  password: process.env.E2E_ADMIN_PASSWORD || 'admin_e2e_password',
}

setup('authenticate admin', async ({ page }) => {
  // 尝试登录
  await page.goto('/login')
  await page.locator('.login-form input').first().fill(ADMIN_USER.username)
  await page.locator('.login-form input[type="password"]').fill(ADMIN_USER.password)
  await page.locator('.login-button').click()

  // 等待 3 秒观察结果
  await page.waitForTimeout(3000)

  // 检查是否成功登录（URL 不在登录页）
  const isLoggedIn = !page.url().includes('/login')

  if (!isLoggedIn) {
    // 登录失败，可能账号不存在
    console.log('Admin login failed, attempting to register admin account via register page...')

    // 访问注册页面
    await page.goto('/register')

    // 填写注册表单
    await page.locator('.register-form input').nth(0).fill(ADMIN_USER.username)
    await page.locator('.register-form input[type="email"]').fill(`${ADMIN_USER.username}@test.local`)
    await page.locator('.register-form input[type="password"]').nth(0).fill(ADMIN_USER.password)
    await page.locator('.register-form input[type="password"]').nth(1).fill(ADMIN_USER.password)

    // 点击注册按钮
    await page.locator('.register-button').click()

    // 等待注册成功（跳转到登录页）
    await page.waitForURL('/login', { timeout: 15000 })

    // 重新登录
    await page.locator('.login-form input').first().fill(ADMIN_USER.username)
    await page.locator('.login-form input[type="password"]').fill(ADMIN_USER.password)
    await page.locator('.login-button').click()

    // 等待登录成功
    await page.waitForURL('/', { timeout: 15000 })
  }

  // 验证登录状态（检查 localStorage 是否有 token）
  const token = await page.evaluate(() => localStorage.getItem('token'))
  if (!token) {
    throw new Error('Admin login failed: no token in localStorage')
  }

  // 保存存储状态
  await page.context().storageState({ path: '.auth/admin.json' })
})
