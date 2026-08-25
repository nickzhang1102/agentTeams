import { test, expect } from '../fixtures/base'

const longPassage = `${'相关证据段落用于验证长文本滚动与换行。'.repeat(120)}关键限定条件位于旧300字截断之后。`

const evidenceMap = [
  {
    evidence_id: 'ev_long_passage',
    source_type: 'web',
    title: 'A very long evidence title that must wrap without widening the drawer or covering the source action',
    excerpt: '列表摘要保持可见，详情加载失败或展开时都不应消失。',
    url: 'https://example.com/research/source',
    completeness: 'passage',
    locator: { page: 4, source_file: 'reports/2026/a-very-long-source-file-name-that-must-wrap.md' },
  },
  {
    evidence_id: 'ev_snippet',
    source_type: 'web',
    title: 'Snippet-only provider result',
    excerpt: 'Provider only returned a snippet.',
    completeness: 'snippet',
  },
  {
    evidence_id: 'ev_legacy',
    source_type: 'tool_result',
    title: 'Legacy aggregate evidence',
    excerpt: '历史聚合证据仍可读，但不能伪装成精确段落。',
    completeness: 'legacy',
  },
  {
    evidence_id: 'ev_retry',
    source_type: 'knowledge',
    title: 'Retryable evidence detail',
    excerpt: '首次请求失败后可以在当前证据内重试。',
    completeness: 'passage',
    url: 'javascript:alert(1)',
  },
]

async function mountDrawer(page) {
  await page.goto('/@vite/client')
  await page.evaluate(async ({ evidence }) => {
    document.body.innerHTML = '<main id="evidence-test-host"><div id="app"></div></main>'
    document.body.style.margin = '0'

    const [{ createApp }, { default: ElementPlus }, { i18n }, { default: Drawer }] = await Promise.all([
      import('/@id/vue'),
      import('/@id/element-plus'),
      import('/src/locales/index.js'),
      import('/src/components/ReportEvidenceDrawer.vue'),
      import('/node_modules/element-plus/dist/index.css'),
      import('/src/styles/design-system.scss'),
    ])

    const app = createApp(Drawer, {
      modelValue: true,
      evidenceMap: evidence,
      sessionId: 42,
      title: '最终报告证据',
      highlightId: 'ev_long_passage',
    })
    app.use(i18n)
    app.use(ElementPlus)
    app.mount('#app')
    window.__evidenceDrawerTestApp = app
  }, { evidence: evidenceMap })
}

async function assertNoHorizontalOverflow(page) {
  const layout = await page.evaluate(() => {
    const drawer = document.querySelector('.el-drawer')
    const items = [...document.querySelectorAll('.evidence-item')]
    const drawerBox = drawer?.getBoundingClientRect()
    return {
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      drawer: drawerBox && { left: drawerBox.left, right: drawerBox.right, width: drawerBox.width },
      items: items.map((item) => {
        const box = item.getBoundingClientRect()
        return { left: box.left, right: box.right, width: box.width }
      }),
    }
  })

  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth)
  expect(layout.drawer.left).toBeGreaterThanOrEqual(0)
  expect(layout.drawer.right).toBeLessThanOrEqual(layout.viewportWidth + 1)
  expect(layout.drawer.width).toBeLessThanOrEqual(Math.min(421, layout.viewportWidth * 0.93))
  for (const item of layout.items) {
    expect(item.left).toBeGreaterThanOrEqual(layout.drawer.left)
    expect(item.right).toBeLessThanOrEqual(layout.drawer.right)
  }
}

test('证据详情各动态状态在桌面和移动视口均保持可核验且不溢出', async ({ page }, testInfo) => {
  let retryCalls = 0
  await page.route('**/api/leader/sessions/42/evidence/*', async (route) => {
    const evidenceId = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop())
    if (evidenceId === 'ev_long_passage') {
      await new Promise(resolve => setTimeout(resolve, 250))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...evidenceMap[0],
          passage: longPassage,
          content_hash: 'stable-content-hash',
        }),
      })
      return
    }
    if (evidenceId === 'ev_snippet') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...evidenceMap[1], passage: 'Provider snippet detail.' }),
      })
      return
    }
    if (evidenceId === 'ev_legacy') {
      await route.fulfill({ status: 422, contentType: 'application/json', body: '{}' })
      return
    }
    retryCalls += 1
    await route.fulfill({
      status: retryCalls === 1 ? 503 : 200,
      contentType: 'application/json',
      body: JSON.stringify(retryCalls === 1 ? {} : { ...evidenceMap[3], passage: '重试后加载成功。' }),
    })
  })

  await mountDrawer(page)

  await expect(page.locator('[data-ev-id="ev_long_passage"] .evidence-detail-loading')).toBeVisible()
  const longItem = page.locator('[data-ev-id="ev_long_passage"]')
  await expect(longItem.locator('.evidence-passage')).toContainText('关键限定条件位于旧300字截断之后')
  const passageLayout = await longItem.locator('.evidence-passage').evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
    overflowY: getComputedStyle(element).overflowY,
  }))
  expect(passageLayout.scrollHeight).toBeGreaterThan(passageLayout.clientHeight)
  expect(['auto', 'scroll']).toContain(passageLayout.overflowY)
  await page.waitForTimeout(400)
  await assertNoHorizontalOverflow(page)

  const snippetItem = page.locator('[data-ev-id="ev_snippet"]')
  await snippetItem.locator('.evidence-detail-toggle').click()
  await expect(snippetItem.locator('.evidence-detail-notice')).toBeVisible()

  const legacyItem = page.locator('[data-ev-id="ev_legacy"]')
  await legacyItem.locator('.evidence-detail-toggle').click()
  await expect(legacyItem.locator('.evidence-detail-error')).toContainText('旧版证据无法精确解析')

  const retryItem = page.locator('[data-ev-id="ev_retry"]')
  await retryItem.locator('.evidence-detail-toggle').click()
  await expect(retryItem.locator('.evidence-detail-error')).toContainText('证据详情加载失败')
  await retryItem.locator('.evidence-detail-error button').click()
  await expect(retryItem.locator('.evidence-passage')).toContainText('重试后加载成功')
  await expect(retryItem.locator('.evidence-item-actions button')).toHaveCount(0)

  await assertNoHorizontalOverflow(page)
  await page.screenshot({ path: testInfo.outputPath('evidence-drawer.png'), fullPage: true })
})
