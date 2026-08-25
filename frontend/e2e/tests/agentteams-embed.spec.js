import { test, expect } from '@playwright/test'

const runningSnapshot = {
  version: '20:monitoring:1:0:0',
  conversation: { id: 10, title: '虚拟会诊', status: 'analyzing' },
  sessions: [{
    id: 20,
    state: 'monitoring',
    started_at: '2026-07-27T03:00:00Z',
    selected_agents: ['medical-oncologist'],
    agent_results: [],
    final_report: null,
  }],
  messages: [],
  agent_progress: [{
    agent_id: 'medical-oncologist',
    agent_name: '肿瘤内科专家',
    status: 'running',
    currentSubtaskId: 'subtask-live',
    currentSubtaskGoal: '核对实时治疗方案',
    decomposition: {
      subtasks: [{
        id: 'subtask-live',
        goal: '核对实时治疗方案',
        status: 'running',
        tools: ['web_search'],
      }],
      completedCount: 0,
      totalCount: 1,
      currentSubtaskId: 'subtask-live',
      currentSubtaskGoal: '核对实时治疗方案',
    },
  }],
}

const fullRequirement = `完整医疗需求-${'病历资料'.repeat(1500)}-请保留末尾诊疗目标`

const questioningSnapshot = {
  version: '20:questioning:2:0:0',
  conversation: { id: 10, title: '虚拟会诊', status: 'analyzing' },
  sessions: [{
    id: 20,
    state: 'questioning',
    started_at: '2026-07-27T03:00:00Z',
    agent_results: [],
    final_report: null,
  }],
  messages: [
    {
      id: 1,
      type: 'user',
      content: { text: fullRequirement },
      leader_session_id: null,
      created_at: '2026-07-27T03:00:00Z',
    },
    {
      id: 2,
      type: 'question',
      content: {
        questions: [{ question: '当前治疗目标？', options: ['治愈', '控制', '缓解'] }],
      },
      leader_session_id: 20,
      created_at: '2026-07-27T03:00:02Z',
    },
    {
      id: 3,
      type: 'assessment',
      content: 'Leader 已完成需求评估',
      leader_session_id: 20,
      created_at: '2026-07-27T03:00:01Z',
    },
  ],
}

const completedSnapshot = {
  version: '20:completed:2:1:1',
  conversation: { id: 10, title: '虚拟会诊', status: 'completed' },
  sessions: [{
    id: 20,
    state: 'completed',
    started_at: '2026-07-27T03:00:00Z',
    agent_results: [{ id: 1, agent_name: '肿瘤内科', status: 'completed' }],
    final_report: { report: '浏览器轮询后出现的综合报告' },
  }],
  messages: [
    {
      id: 3,
      type: 'assessment',
      content: 'Leader 已完成需求评估',
      leader_session_id: 20,
      created_at: '2026-07-27T03:00:01Z',
    },
  ],
}

for (const viewport of [
  { name: 'desktop', width: 1366, height: 768 },
  { name: 'mobile', width: 390, height: 844 },
]) {
  test(`refreshes, answers questions, and continues in ${viewport.name} view`, async ({ page }) => {
    await page.setViewportSize(viewport)
    let detailRequestCount = 0
    let statusRequestCount = 0
    let submittedAnswer = null
    let authorizationHeader = null
    const ownerStatusRequests = []
    await page.route('**/api/leader/status/**', route => {
      ownerStatusRequests.push(route.request().url())
      route.fulfill({ status: 403, contentType: 'application/json', body: '{}' })
    })
    await page.route('**/api/integrations/agentteams/embed-sessions/e2e-token', route => {
      detailRequestCount += 1
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([
          runningSnapshot,
          questioningSnapshot,
          completedSnapshot,
        ][Math.min(detailRequestCount - 1, 2)]),
      })
    })
    await page.route('**/api/integrations/agentteams/embed-sessions/e2e-token/status', route => {
      statusRequestCount += 1
      const answered = submittedAnswer !== null
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          conversation_id: 10,
          status: answered ? 'completed' : 'questioning',
          terminal: answered,
          version: answered ? completedSnapshot.version : questioningSnapshot.version,
        }),
      })
    })
    await page.route('**/api/integrations/agentteams/embed-sessions/e2e-token/answers', async route => {
      submittedAnswer = route.request().postDataJSON()
      authorizationHeader = await route.request().headerValue('authorization')
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'data: {"type":"team_forming","phase":"analyzing","content":"正在继续分析","session_id":20}',
          '',
          'data: {"type":"done","session_id":20}',
          '',
        ].join('\n'),
      })
    })
    await page.route('**/api/integrations/agentteams/embed-sessions/e2e-token/events', route => {
      route.fulfill({
        status: 503,
        contentType: 'text/plain',
        body: 'event stream unavailable in polling fallback test',
      })
    })

    await page.goto('/embed/conversation/e2e-token')

    await expect(page.getByText('核对实时治疗方案')).toBeVisible()
    await expect(page.locator('.running-placeholder')).toHaveCount(0)
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5000 })
    await expect(page.getByRole('dialog').getByText('当前治疗目标？')).toBeVisible()
    await expect(page.locator('.info-header .question-text')).toHaveText(fullRequirement)
    await page.locator('.question-preview').evaluate(element => element.click())
    const expandedLayout = await page.evaluate(() => {
      const question = document.querySelector('.info-header .question-text')
      const main = document.querySelector('.main-content, .mobile-content')
      return {
        questionClientHeight: question?.clientHeight || 0,
        questionScrollHeight: question?.scrollHeight || 0,
        mainHeight: main?.getBoundingClientRect().height || 0,
      }
    })
    expect(expandedLayout.questionScrollHeight).toBeGreaterThan(expandedLayout.questionClientHeight)
    expect(expandedLayout.questionClientHeight).toBeLessThanOrEqual(Math.min(viewport.height * 0.36, 320) + 2)
    expect(expandedLayout.mainHeight).toBeGreaterThan(200)
    if (viewport.name === 'desktop') {
      await expect(page.getByText('Leader 已完成需求评估')).toBeVisible()
    } else {
      await expect(page.getByText('Leader 已完成需求评估')).toHaveCount(1)
    }

    await page.getByRole('dialog').getByText('控制', { exact: true }).click()
    await page.getByRole('button', { name: /^(提交回答|Submit answers)$/ }).click()

    await expect.poll(() => submittedAnswer).toEqual({ session_id: 20, answers: ['控制'] })
    expect(authorizationHeader).toBeNull()
    await expect(page.getByRole('dialog')).not.toBeVisible()
    await expect(page.locator('.status-text')).toHaveText(/^(已完成|Completed)$/, { timeout: 7000 })
    if (viewport.name === 'mobile') {
      await page.getByRole('button', { name: /^(消息|Messages)$/ }).click()
      await expect(page.getByText('Leader 已完成需求评估')).toBeVisible()
    }
    await page.getByRole('button', { name: /^(最终报告|Final report|报告|Reports)$/ }).click()
    await expect(page.getByText('浏览器轮询后出现的综合报告')).toBeVisible({ timeout: 7000 })
    expect(detailRequestCount).toBe(3)
    expect(statusRequestCount).toBeGreaterThanOrEqual(1)
    expect(ownerStatusRequests).toEqual([])

    const pageSize = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    expect(pageSize.scrollWidth).toBeLessThanOrEqual(pageSize.clientWidth + 1)
  })
}
