/**
 * 注册页面已认证测试
 *
 * 测试已登录用户访问注册页的行为
 */
import { test, expect } from '../fixtures/base'

test.describe('已登录用户访问注册页', () => {
  test.use({ storageState: '.auth/user.json' })

  test('已登录访问注册页应跳转首页', async ({ page }) => {
    await page.goto('/register')

    // 等待跳转到首页
    await page.waitForURL('/', { timeout: 10000 })

    expect(page.url()).not.toContain('/register')
  })
})