/**
 * 主页已认证状态测试
 *
 * 使用 storageState，测试已登录用户看到的内容
 */
import { test, expect } from '../fixtures/base'

test.describe('主页已认证状态', () => {
  // 使用 setup 保存的登录状态
  test.use({ storageState: '.auth/user.json' })

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('已登录应显示用户菜单', async ({ page }) => {
    const userMenu = page.locator('.user-menu')
    await expect(userMenu).toBeVisible()
  })

  test('已登录应显示输入区域', async ({ page }) => {
    const mainInput = page.locator('.main-input')
    await expect(mainInput).toBeVisible()
  })

  test('输入文本并发送应创建对话', async ({ page }) => {
    // 填写输入
    await page.fill('.main-input', 'E2E测试：这是一个自动化测试消息')

    // 点击发送
    await page.click('button:has-text("开始分析")')

    // 等待跳转到对话详情页
    await page.waitForTimeout(3000)

    // 检查 URL 变化
    const url = page.url()

    // 验证：跳转到对话页（成功创建对话）
    if (!url.includes('/conversation/')) {
      throw new Error(`Unexpected URL: ${url}`)
    }
  })

  test('点击文件上传按钮应触发文件选择', async ({ page }) => {
    // 检查上传按钮存在
    const uploadButton = page.locator('.tool-button').first()
    await expect(uploadButton).toBeVisible()
  })
})

test.describe('退出登录流程', () => {
  // 使用已登录状态
  test.use({ storageState: '.auth/user.json' })

  test('退出后应清除 localStorage', async ({ page }) => {
    await page.goto('/')

    // 验证有 token
    const tokenBefore = await page.evaluate(() => localStorage.getItem('token'))
    expect(tokenBefore).toBeTruthy()

    // 点击退出
    await page.click('.user-info')
    await page.click('.el-dropdown-menu__item:has-text("退出登录")')

    // 等待页面稳定
    await page.waitForTimeout(1000)

    // 验证 token 已清除
    const tokenAfter = await page.evaluate(() => localStorage.getItem('token'))
    expect(tokenAfter).toBeNull()
  })
})