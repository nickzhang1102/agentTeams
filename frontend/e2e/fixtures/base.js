/**
 * 测试 Fixtures
 *
 * 共享测试配置和工具函数
 */
import { test as base, expect } from '@playwright/test'

// 导出 test 和 expect 供其他文件使用
export { expect }

// 扩展基础 test，可添加自定义 fixtures
export const test = base.extend({
  // 可在此添加自定义 fixtures
})

// 测试账号配置
export const TEST_USER = {
  username: process.env.E2E_TEST_USER || 'test_e2e_user',
  password: process.env.E2E_TEST_PASSWORD || 'test_e2e_password',
}

// 辅助函数：等待 Element Plus 消息提示
export async function waitForMessage(page, text, timeout = 5000) {
  await page.waitForSelector(`.el-message:has-text("${text}")`, { timeout })
}

// 辅助函数：等待路由变化
export async function waitForRoute(page, path, timeout = 10000) {
  await page.waitForURL(`**${path}`, { timeout })
}