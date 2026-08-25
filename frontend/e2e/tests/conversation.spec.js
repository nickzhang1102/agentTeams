/**
 * 对话详情页测试
 *
 * 测试公开对话访问、Leader 执行流程、Agent 结果展示等
 */
import { test, expect } from '../fixtures/base'

// 使用合成分享 token + 全量 route mock（参照 locale-switcher.spec.js），
// 不再依赖真实后端数据库中的分享对话数据
const PUBLIC_TOKEN = 'e2e-public-conversation'

test.describe('对话详情页（公开访问）', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/**', async (route) => {
      const url = route.request().url()
      if (url.includes(`/api/conversations/share/${PUBLIC_TOKEN}`)) {
        await route.fulfill({
          json: {
            conversation: { id: 101, title: '这是 e2e 合成的公开对话问题' },
            files: [],
            messages: [{ id: 1, role: 'user', content: '这是 e2e 合成的公开对话问题' }],
          },
        })
        return
      }
      if (url.includes(`/api/leader/session/share/${PUBLIC_TOKEN}`)) {
        await route.fulfill({
          json: {
            success: true,
            sessions: [{
              id: 202,
              state: 'completed',
              total_time: 12,
              selected_agents: ['analysis-agent'],
              agent_results: [{
                agent_id: 'analysis-agent',
                agent_name: '分析 Agent',
                status: 'success',
                content: '这是 e2e 合成的 Agent 报告',
              }],
              final_report: '这是 e2e 合成的最终报告',
            }],
            messages: [{
              message_type: 'thinking',
              content: '这是 e2e 合成的思考内容',
              leader_session_id: 202,
              created_at: '2026-08-01T08:00:00Z',
            }],
          },
        })
        return
      }
      if (url.includes('/api/content-translations/')) {
        await route.fulfill({ json: { items: [], missing_sources: [] } })
        return
      }
      await route.fulfill({ json: [] })
    })
  })

  test('公开对话页面应可访问', async ({ page }) => {
    await page.goto(`/conversation/${PUBLIC_TOKEN}`)

    // 等待页面加载
    await page.waitForTimeout(3000)

    // 检查页面主要内容存在
    const pageContent = page.locator('.conversation-display')
    await expect(pageContent).toBeVisible()
  })

  test('应显示问题预览', async ({ page }) => {
    await page.goto(`/conversation/${PUBLIC_TOKEN}`)
    await page.waitForSelector('.info-header', { timeout: 10000 })

    // 检查问题预览区域
    const questionPreview = page.locator('.question-preview')
    await expect(questionPreview).toBeVisible()

    // 检查问题标签
    const questionLabel = page.locator('.question-label')
    await expect(questionLabel).toHaveText('问题：')
  })

  test('应显示状态徽章', async ({ page }) => {
    await page.goto(`/conversation/${PUBLIC_TOKEN}`)
    await page.waitForSelector('.info-header', { timeout: 10000 })

    // 检查状态徽章
    const statusBadge = page.locator('.status-badge')
    await expect(statusBadge).toBeVisible()

    // 检查状态文本
    const statusText = page.locator('.status-text')
    const text = await statusText.innerText()
    // 可能是"已完成"、"进行中"等
    expect(text.length).toBeGreaterThan(0)
  })

  test('应显示返回按钮', async ({ page }) => {
    await page.goto(`/conversation/${PUBLIC_TOKEN}`)
    await page.waitForSelector('.info-header', { timeout: 10000 })

    const backButton = page.locator('.back-button')
    await expect(backButton).toBeVisible()
  })

  test('点击返回按钮应跳转首页', async ({ page }) => {
    await page.goto(`/conversation/${PUBLIC_TOKEN}`)
    await page.waitForSelector('.back-button', { timeout: 10000 })

    await page.click('.back-button')

    // 等待跳转
    await page.waitForURL('/', { timeout: 10000 })
  })

  test('应显示主内容区域', async ({ page }) => {
    await page.goto(`/conversation/${PUBLIC_TOKEN}`)
    await page.waitForSelector('.main-content', { timeout: 10000 })

    const mainContent = page.locator('.main-content')
    await expect(mainContent).toBeVisible()
  })

  test('移动端应显示 Tab 切换栏', async ({ page }) => {
    // 设置移动端视口
    await page.setViewportSize({ width: 375, height: 667 })

    await page.goto(`/conversation/${PUBLIC_TOKEN}`)
    await page.waitForTimeout(3000)

    // 检查移动端 Tab 切换栏
    const mobileTabBar = page.locator('.mobile-tab-bar')
    const hasTabBar = await mobileTabBar.count() > 0

    if (hasTabBar) {
      // 检查三个 Tab
      const messagesTab = page.locator('.mobile-tab:has-text("对话")')
      const agentsTab = page.locator('.mobile-tab:has-text("Agent")')
      const reportTab = page.locator('.mobile-tab:has-text("报告")')

      await expect(messagesTab).toBeVisible()
      await expect(agentsTab).toBeVisible()
      await expect(reportTab).toBeVisible()
    } else {
      // 桌面端布局
      const desktopLayout = page.locator('.splitpanes, .default-theme')
      const hasDesktopLayout = await desktopLayout.count() > 0
      expect(hasDesktopLayout).toBeTruthy()
    }
  })

  test('Leader 会话页面应显示思考过程组件', async ({ page }) => {
    await page.goto(`/conversation/${PUBLIC_TOKEN}`)
    await page.waitForTimeout(5000)

    // 检查 LeaderThinking 组件或消息列表
    const leaderThinking = page.locator('.leader-thinking, [class*="leader"]')
    const messageList = page.locator('.message-list, .message-item')

    const hasLeaderContent = await leaderThinking.count() > 0
    const hasMessages = await messageList.count() > 0

    // 至少应该有某种内容显示
    expect(hasLeaderContent || hasMessages).toBeTruthy()
  })

  test('Agent 结果面板应可展开查看', async ({ page }) => {
    await page.goto(`/conversation/${PUBLIC_TOKEN}`)
    await page.waitForTimeout(5000)

    // 检查 Agent 结果卡片
    const agentCards = page.locator('.agent-card, .agent-result-card')
    const hasAgentCards = await agentCards.count() > 0

    if (hasAgentCards) {
      // 点击第一个卡片展开
      await agentCards.first().click()
      await page.waitForTimeout(1000)

      // 检查展开内容
      const expandedContent = page.locator('.agent-detail, .expanded-content')
      const hasExpanded = await expandedContent.count() > 0

      // 如果有展开内容，验证可见
      if (hasExpanded) {
        await expect(expandedContent.first()).toBeVisible()
      }
    }
  })
})