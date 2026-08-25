/**
 * Knowledge 页面未认证测试
 *
 * 测试未登录用户访问 /knowledge 的行为
 */
import { test, expect } from '../fixtures/base'

test.describe('Knowledge 页面未认证', () => {
  test('未登录访问 /knowledge 应跳转登录页', async ({ page }) => {
    // 清除登录状态
    await page.context().clearCookies()

    await page.goto('/knowledge')

    // 等待跳转
    await page.waitForURL(/\/login/, { timeout: 15000 })

    expect(page.url()).toContain('/login')
  })
})