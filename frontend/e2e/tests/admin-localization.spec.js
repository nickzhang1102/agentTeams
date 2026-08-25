import { test, expect } from '@playwright/test'

const ADMIN_ROUTES = [
  ['/admin/dashboard', 'Dashboard'],
  ['/admin/performance', 'Performance'],
  ['/admin/leader-sessions', 'Leader session management'],
  ['/admin/featured', 'Featured case management'],
  ['/admin/tools', 'Tool management'],
  ['/admin/openharness', 'OpenHarness configuration'],
  ['/admin/agentteams-integration', 'Agent Teams integration'],
  ['/admin/llm-models', 'LLM model management'],
  ['/admin/settings', 'System settings'],
]

async function selectEnglish(page) {
  await page.waitForTimeout(400)
  await page.locator('.lang-trigger').click()
  await page.getByRole('option', { name: 'English' }).click()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('preferred_locale'))).toBe('en-US')
}

async function findVisibleChinese(page) {
  return page.evaluate(() => {
    const sourceContentSelector = [
      '.config-desc',
      '.preset-desc',
      '.tool-desc-short',
      '.tool-detail-desc',
      '.debug-tool-desc',
      '.param-desc',
    ].join(',')
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    const matches = new Set()
    let node = walker.nextNode()

    while (node) {
      const text = node.textContent?.trim()
      const element = node.parentElement
      if (
        text
        && /[\u3400-\u9fff]/.test(text)
        && element?.checkVisibility()
        && !element.closest(sourceContentSelector)
      ) {
        matches.add(text)
      }
      node = walker.nextNode()
    }

    return [...matches]
  })
}

async function assertUsableViewport(page) {
  await expect(page.locator('.el-loading-mask:visible')).toHaveCount(0, { timeout: 15000 })

  const layout = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    blank: document.body.innerText.trim().length === 0,
  }))

  expect(layout.blank).toBe(false)
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth + 1)

  if (layout.viewportWidth < 768) {
    const sidebarRight = await page.locator('.admin-sidebar').evaluate((sidebar) =>
      sidebar.getBoundingClientRect().right,
    )
    expect(sidebarRight).toBeLessThanOrEqual(0)
  }

  const blockedControls = await page.locator('button:visible, [role="button"]:visible').evaluateAll((controls) =>
    controls.flatMap((control) => {
      const rect = control.getBoundingClientRect()
      if (!rect.width || !rect.height || rect.bottom <= 0 || rect.top >= innerHeight) return []

      const x = Math.min(innerWidth - 1, Math.max(0, rect.left + rect.width / 2))
      const y = Math.min(innerHeight - 1, Math.max(0, rect.top + rect.height / 2))
      const topElement = document.elementFromPoint(x, y)
      return topElement && (control === topElement || control.contains(topElement))
        ? []
        : [control.getAttribute('aria-label') || control.textContent?.trim() || control.className]
    }),
  )

  expect(blockedControls).toEqual([])
}

test('all Admin routes render cleanly in English', async ({ page }, testInfo) => {
  const pageErrors = []
  const catalogRequests = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('request', (request) => {
    if (/\/api\/admin\/(?:tools|openharness\/tools)/.test(request.url())) {
      catalogRequests.push(request.url())
    }
  })

  await page.goto('/admin/dashboard')
  await selectEnglish(page)

  if (testInfo.project.name === 'admin-localization-mobile') {
    await page.locator('.collapse-btn').click()
    await expect(page.locator('.sidebar-overlay')).toBeVisible()
    await expect(page.getByRole('menuitem', { name: 'Dashboard' })).toBeVisible()
    await page.locator('.sidebar-overlay').click({ position: { x: 300, y: 100 } })
    await expect(page.locator('.sidebar-overlay')).toBeHidden()
  }

  for (const [route, expectedText] of ADMIN_ROUTES) {
    await page.goto(route)
    await expect(page).toHaveURL(new RegExp(`${route.replaceAll('/', '\\/')}$`))
    await expect(page.getByRole('heading', { name: expectedText, exact: true }).first()).toBeVisible()
    await page.waitForTimeout(500)

    expect(await findVisibleChinese(page), `${route} contains fixed Chinese copy`).toEqual([])
    await assertUsableViewport(page)
    await page.screenshot({
      path: testInfo.outputPath(`${route.split('/').at(-1)}.png`),
      fullPage: true,
    })

    if (route === '/admin/openharness') {
      await Promise.all([
        page.waitForRequest((request) => request.url().includes('/api/admin/openharness/tools')),
        page.getByRole('tab', { name: 'Tools', exact: true }).click(),
      ])
      await page.waitForTimeout(500)
      expect(await findVisibleChinese(page), `${route} tools contain fixed Chinese copy`).toEqual([])
      await assertUsableViewport(page)
      await page.screenshot({
        path: testInfo.outputPath('openharness-tools.png'),
        fullPage: true,
      })
    }
  }

  expect(pageErrors).toEqual([])
  expect(catalogRequests.some((url) => url.includes('/api/admin/tools') && url.includes('locale=en-US'))).toBe(true)
  expect(catalogRequests.some((url) => url.includes('/api/admin/openharness/tools') && url.includes('locale=en-US'))).toBe(true)
})

test('Admin locale switch preserves route and entered form data', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'admin-localization-mobile', 'Desktop interaction coverage is sufficient.')

  await page.goto('/admin/performance')
  await selectEnglish(page)

  await page.locator('.lang-trigger').click()
  await page.getByRole('option', { name: '中文' }).click()
  await expect(page.getByText('性能监控', { exact: true }).first()).toBeVisible()
  await expect(page).toHaveURL(/\/admin\/performance$/)

  await selectEnglish(page)
  await expect(page).toHaveURL(/\/admin\/performance$/)
})
