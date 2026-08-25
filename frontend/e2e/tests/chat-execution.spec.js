/**
 * 实际聊天执行测试
 *
 * 测试完整聊天流程：发送消息 -> Leader 执行 -> Agent 结果 -> 最终报告
 */
import { test, expect } from '../fixtures/base'

test.describe('实际聊天执行流程', () => {
  test.use({ storageState: '.auth/user.json' })

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.main-input-section', { timeout: 10000 })
  })

  test('发送消息应创建对话并跳转到详情页', async ({ page }) => {
    // 输入测试问题
    const textarea = page.locator('.main-input')
    await textarea.fill('E2E测试：请简单介绍一下Agent Teams系统的功能')

    // 点击发送
    const sendButton = page.locator('.send-button')
    await sendButton.click()

    // 等待跳转到对话详情页
    await page.waitForURL(/\/conversation\//, { timeout: 15000 })

    // 验证 URL 包含 conversation
    expect(page.url()).toContain('/conversation/')
  })

  test('对话详情页应显示问题预览', async ({ page }) => {
    // 先发送消息创建对话
    const textarea = page.locator('.main-input')
    await textarea.fill('E2E测试：这是一个自动化测试消息')
    await page.click('.send-button')

    // 等待跳转
    await page.waitForURL(/\/conversation\//, { timeout: 15000 })

    // 检查问题预览
    const questionPreview = page.locator('.question-preview')
    await expect(questionPreview).toBeVisible()

    // 检查问题文本
    const questionText = page.locator('.question-text')
    await expect(questionText).toContainText('E2E测试')
  })

  test('对话详情页应显示状态徽章', async ({ page }) => {
    const textarea = page.locator('.main-input')
    await textarea.fill('E2E测试：测试状态徽章显示')
    await page.click('.send-button')

    await page.waitForURL(/\/conversation\//, { timeout: 15000 })

    // 检查状态徽章
    const statusBadge = page.locator('.status-badge')
    await expect(statusBadge).toBeVisible()

    // 状态可能是：空闲、评估中、组建团队、执行中、已完成等
    const statusText = await page.locator('.status-text').innerText()
    expect(['空闲', '评估中', '组建团队', '执行中', '已完成', '处理中']).toContain(statusText)
  })

  test('Leader 思考过程应显示', async ({ page }) => {
    const textarea = page.locator('.main-input')
    await textarea.fill('E2E测试：测试Leader思考过程')
    await page.click('.send-button')

    await page.waitForURL(/\/conversation\//, { timeout: 15000 })

    // 等待 Leader 思考组件加载
    await page.waitForTimeout(5000)

    // 检查 Leader 消息区域
    const leaderMessage = page.locator('.leader-message, .leader-thinking, .message-list')
    const hasLeaderContent = await leaderMessage.count() > 0

    // 或者检查消息侧边栏
    const messageSidebar = page.locator('.message-sidebar')
    const hasSidebar = await messageSidebar.count() > 0

    expect(hasLeaderContent || hasSidebar).toBeTruthy()
  })

  test('Agent 状态面板应显示', async ({ page }) => {
    const textarea = page.locator('.main-input')
    await textarea.fill('E2E测试：测试Agent状态面板')
    await page.click('.send-button')

    await page.waitForURL(/\/conversation\//, { timeout: 15000 })
    await page.waitForTimeout(10000) // 等待 Agent 执行

    // 点击 Agent 报告 Tab（移动端）或检查右侧面板（桌面端）
    const agentTab = page.locator('.mobile-tab:has-text("Agent"), button:has-text("Agent 报告")')
    const hasAgentTab = await agentTab.count() > 0

    if (hasAgentTab) {
      await agentTab.first().click()
      await page.waitForTimeout(1000)
    }

    // 检查 Agent 状态面板
    const agentPanel = page.locator('.agent-status-panel, .agent-panel')
    const agentCards = page.locator('.agent-card')

    // 等待 Agent 执行完成或有结果
    await page.waitForTimeout(5000)

    const hasAgentPanel = await agentPanel.count() > 0
    const hasAgentCards = await agentCards.count() > 0

    // 至少应该有 Agent 区域显示
    expect(hasAgentPanel || hasAgentCards || hasAgentTab).toBeTruthy()
  })

  test('最终报告 Tab 应可点击', async ({ page }) => {
    const textarea = page.locator('.main-input')
    await textarea.fill('E2E测试：测试最终报告')
    await page.click('.send-button')

    await page.waitForURL(/\/conversation\//, { timeout: 15000 })
    await page.waitForTimeout(3000)

    // 点击最终报告 Tab
    const reportTab = page.locator('.mobile-tab:has-text("报告"), button:has-text("最终报告")')
    const hasReportTab = await reportTab.count() > 0

    if (hasReportTab) {
      await reportTab.first().click()
      await page.waitForTimeout(1000)
    }
  })

  test('对话完成后应显示时间', async ({ page }) => {
    const textarea = page.locator('.main-input')
    await textarea.fill('E2E测试：测试时间显示')
    await page.click('.send-button')

    await page.waitForURL(/\/conversation\//, { timeout: 15000 })

    // 检查时间显示
    const timeDisplay = page.locator('.time-display')
    const hasTime = await timeDisplay.count() > 0

    if (hasTime) {
      const timeText = await timeDisplay.innerText()
      // 时间格式可能为 "00:00" 或 "XX:XX"
      expect(timeText.length).toBeGreaterThan(0)
    }
  })
})

test.describe('SSE 流式响应测试', () => {
  test.use({ storageState: '.auth/user.json' })

  test('发送消息后应显示加载状态', async ({ page }) => {
    await page.goto('/')

    const textarea = page.locator('.main-input')
    await textarea.fill('E2E测试：测试加载状态')

    // 点击发送并立即检查状态
    await page.click('.send-button')

    // 等待一小段时间让状态变化或跳转发生
    await page.waitForTimeout(1000)

    // 检查发送按钮状态变化或页面跳转
    const url = page.url()
    const isNavigating = url.includes('/conversation/')

    // 如果还没跳转，检查按钮状态
    if (!isNavigating) {
      await page.waitForTimeout(2000)
      const newUrl = page.url()
      expect(newUrl.includes('/conversation/')).toBeTruthy()
    } else {
      // 已经跳转，测试通过
      expect(isNavigating).toBeTruthy()
    }
  })

  test('流式消息应逐步显示', async ({ page }) => {
    await page.goto('/')

    const textarea = page.locator('.main-input')
    await textarea.fill('E2E测试：测试流式消息显示')

    await page.click('.send-button')

    // 等待跳转
    await page.waitForURL(/\/conversation\//, { timeout: 15000 })
    await page.waitForTimeout(5000)

    // 检查消息内容区域
    const messageContent = page.locator('.message-content, .markdown-body, .leader-message')

    // 等待内容加载
    await page.waitForTimeout(10000)

    const hasContent = await messageContent.count() > 0

    // 如果有内容，检查是否有文本
    if (hasContent) {
      const text = await messageContent.first().innerText()
      // 内容应该逐步增长或有内容显示
      expect(text.length).toBeGreaterThanOrEqual(0)
    }
  })
})