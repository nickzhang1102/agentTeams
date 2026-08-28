import { test, expect } from '../fixtures/base'

// 回归探针：虚拟会诊嵌入页（快照式一次性挂载）下
// 1) 多个 MarkdownRenderer 同时挂载时 mermaid 是否卡在"正在渲染图表..."
// 2) 跨 Agent 的 scoped evidence 引用是否保持明文（当前行为记录）

const MERMAID_CASES = [
  '```mermaid\nflowchart TD\nA1[会诊资料聚合] --> B1[检验科分析]\n```',
  '```mermaid\nflowchart TD\nA2[影像资料] --> B2[影像科分析]\n```',
  '```mermaid\nflowchart TD\nA3[病理资料] --> B3[病理科分析]\n```',
]

test('multiple MarkdownRenderers mounting in the same tick render mermaid charts', async ({ page }, testInfo) => {
  const consoleErrors = []
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      consoleErrors.push(`[${message.type()}] ${message.text()}`)
    }
  })
  page.on('pageerror', (error) => consoleErrors.push(`[pageerror] ${error.message}`))

  await page.goto('/@vite/client')
  await page.evaluate(async (contents) => {
    document.body.innerHTML = '<main id="mermaid-test-host"></main>'
    document.body.style.margin = '0'

    const [{ createApp, h }, { default: ElementPlus }, { i18n }, { default: MarkdownRenderer }] =
      await Promise.all([
        import('/@id/vue'),
        import('/@id/element-plus'),
        import('/src/locales/index.js'),
        import('/src/components/MarkdownRenderer.vue'),
        import('/node_modules/element-plus/dist/index.css'),
        import('/src/styles/design-system.scss'),
      ])

    // 与嵌入页快照完全一致：单个父组件在一次 flush 中同时渲染全部实例
    // （同一 Date.now() → 跨实例 mermaid id 冲突）
    const host = document.getElementById('mermaid-test-host')
    const mountPoint = document.createElement('div')
    host.appendChild(mountPoint)
    const app = createApp({
      render: () => contents.map((content) => h(MarkdownRenderer, { content, evidenceMap: [] })),
    })
    app.use(i18n)
    app.use(ElementPlus)
    app.mount(mountPoint)
    window.__mermaidProbe = { count: contents.length }
  }, MERMAID_CASES)

  // mermaid 渲染是异步的，给足时间（真实浏览器环境）
  await page.waitForTimeout(8000)

  const state = await page.evaluate(() => {
    const containers = [...document.querySelectorAll('.mermaid-container')]
    return {
      mounted: !!window.__mermaidProbe,
      renderedBlocks: [...document.querySelectorAll('.markdown-renderer')].map(
        (node) => node.textContent.slice(0, 60),
      ),
      ids: containers.map((c) => c.dataset.mermaidId),
      results: containers.map((c) => ({
        hasSvg: !!c.querySelector('svg'),
        loading: !!c.querySelector('.mermaid-loading'),
        error: !!c.querySelector('.mermaid-error'),
      })),
    }
  })
  console.log('MERMAID_PROBE ' + JSON.stringify(state, null, 2))
  if (consoleErrors.length) {
    console.log('CONSOLE_ISSUES ' + JSON.stringify(consoleErrors.slice(0, 10), null, 2))
  }
  await page.screenshot({ path: testInfo.outputPath('mermaid-probe.png'), fullPage: true })

  expect(state.ids).toHaveLength(MERMAID_CASES.length)
  for (const result of state.results) {
    expect(result.loading, 'mermaid 不应停留在“正在渲染图表...”').toBe(false)
    expect(result.hasSvg, 'mermaid 应渲染出 svg').toBe(true)
  }
})

// ===== 探针 2：真实嵌入页（/embed/conversation/:token，快照数据）=====
const LAB_EVIDENCE_ID = 'laboratory-expert_ev_subtask_2_llm_analysis_1'
const ONCO_EVIDENCE_ID = 'medical-oncologist_ev_subtask_1_llm_analysis_1'

const embedSnapshot = {
  version: '20:completed:9:2:2',
  locale: 'zh-CN',
  conversation: { id: 10, title: '肿瘤 MDT 虚拟会诊', status: 'completed' },
  sessions: [{
    id: 20,
    state: 'completed',
    locale: 'zh-CN',
    started_at: '2026-08-29T03:00:00Z',
    completed_at: '2026-08-29T03:20:00Z',
    selected_agents: ['laboratory-expert', 'medical-oncologist'],
    agent_results: [
      {
        id: 1,
        agent_id: 'laboratory-expert',
        agent_name: '检验科专家',
        leader_session_id: 20,
        status: 'success',
        content: [
          '## 检验科分析',
          '',
          '血小板计数持续偏低，建议关注化疗后骨髓抑制 [evidence_id:' + LAB_EVIDENCE_ID + ']。',
          '',
          '```mermaid',
          'flowchart TD',
          'L1[血常规] --> L2[血小板减低]',
          '```',
        ].join('\n'),
        evidence_map: [{
          evidence_id: LAB_EVIDENCE_ID,
          source_type: 'tool_result',
          title: '检验科证据一',
          excerpt: '血小板 62×10^9/L，低于正常参考区间。',
          completeness: 'passage',
        }],
        tool_calls: [],
      },
      {
        id: 2,
        agent_id: 'medical-oncologist',
        agent_name: '肿瘤内科专家',
        leader_session_id: 20,
        status: 'success',
        content: [
          '## 肿瘤内科综合意见',
          '',
          '结合检验科提示的骨髓抑制风险，建议延期一周化疗 [evidence_id:' + LAB_EVIDENCE_ID + ']，并复查肝功能 [evidence_id:' + ONCO_EVIDENCE_ID + ']。',
          '',
          '```mermaid',
          'flowchart TD',
          'O1[会诊意见汇总] --> O2[延期化疗]',
          '```',
        ].join('\n'),
        evidence_map: [{
          evidence_id: ONCO_EVIDENCE_ID,
          source_type: 'web',
          title: '肿瘤内科证据一',
          excerpt: 'NCCN 指南建议粒细胞缺乏时推迟化疗。',
          completeness: 'snippet',
        }],
        tool_calls: [],
      },
    ],
    final_report: {
      id: 5,
      leader_session_id: 20,
      report: [
        '# 虚拟会诊综合报告',
        '',
        '**一句话总结：** 建议延期化疗一周并复查血象。',
        '',
        '综合两位专家意见，骨髓抑制为主要风险 [evidence_id:' + LAB_EVIDENCE_ID + ']。',
        '',
        '```mermaid',
        'flowchart TD',
        'R1[综合评估] --> R2[延期化疗]',
        '```',
      ].join('\n'),
      content_locale: 'zh-CN',
      summary: {
        title: '虚拟会诊综合报告',
        executive_summary: '建议延期化疗一周并复查血象。',
        key_findings: ['血小板减低'],
        recommendations: ['延期一周'],
        risks: ['骨髓抑制'],
        next_steps: ['复查血常规'],
      },
      structured_report: {
        evidence_refs: [LAB_EVIDENCE_ID],
        visual_blocks: [{
          block_id: 'vb_1',
          type: 'risk_matrix',
          title: '风险矩阵',
          data: { risks: [{ name: '骨髓抑制', likelihood: '中', impact: '高', mitigation: '延期化疗', source_id: LAB_EVIDENCE_ID }] },
          evidence_refs: [LAB_EVIDENCE_ID],
        }],
      },
      evidence_map: [
        { evidence_id: LAB_EVIDENCE_ID, source_type: 'tool_result', title: '检验科证据一', excerpt: '血小板 62×10^9/L。', completeness: 'passage' },
        { evidence_id: ONCO_EVIDENCE_ID, source_type: 'web', title: '肿瘤内科证据一', excerpt: 'NCCN 建议。', completeness: 'snippet' },
      ],
      created_at: '2026-08-29T03:20:00Z',
    },
  }],
  messages: [{
    id: 1,
    type: 'user',
    content: { text: '患者确诊肺癌，白细胞低，下一步化疗方案？' },
    leader_session_id: null,
    created_at: '2026-08-29T03:00:00Z',
  }],
  tool_calls: [],
  agent_progress: [],
}

test('embed page renders mermaid charts and links scoped evidence citations', async ({ page }, testInfo) => {
  const consoleErrors = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(`[console] ${message.text()}`)
  })
  page.on('pageerror', (error) => consoleErrors.push(`[pageerror] ${error.message}`))

  await page.setViewportSize({ width: 1366, height: 900 })
  await page.route('**/api/integrations/agentteams/embed-sessions/probe-token', route => {
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(embedSnapshot) })
  })
  await page.route('**/api/integrations/agentteams/embed-sessions/probe-token/status', route => {
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ conversation_id: 10, status: 'completed', terminal: true, version: embedSnapshot.version }),
    })
  })
  await page.route('**/api/integrations/agentteams/embed-sessions/probe-token/events', route => {
    route.fulfill({ status: 503, contentType: 'text/plain', body: 'no events in probe' })
  })

  await page.goto('/embed/conversation/probe-token')
  await page.waitForTimeout(1500)

  // 展开两位 Agent 的报告（手风琴单开：先检验科）
  const agentHeaders = page.locator('.agent-title')
  await agentHeaders.first().click()
  await page.waitForTimeout(4000)

  const probeAgents = await page.evaluate(() => {
    const items = [...document.querySelectorAll('.agent-content')]
    return items.map((item) => {
      const containers = [...item.querySelectorAll('.mermaid-container')]
      return {
        hasContent: item.textContent.includes('检验科分析') || item.textContent.includes('肿瘤内科'),
        charts: containers.map((c) => ({
          hasSvg: !!c.querySelector('svg'),
          loading: !!c.querySelector('.mermaid-loading'),
          error: !!c.querySelector('.mermaid-error'),
          hidden: c.offsetParent === null,
        })),
        evidenceButtons: item.querySelectorAll('.evidence-ref, .evidence-linked-content').length,
        rawEvidenceIds: (item.textContent.match(/\[evidence_id:[^\]]+\]/g) || []),
        linkedIds: [...item.querySelectorAll('.evidence-ref, .evidence-linked-content')]
          .map((el) => el.dataset.evidenceId),
      }
    })
  })
  console.log('EMBED_AGENTS_PROBE ' + JSON.stringify(probeAgents, null, 2))

  // 最终报告 tab：完整报告折叠面板展开
  await page.getByRole('button', { name: /最终报告|Final report/ }).first().click()
  const fullReportHeader = page.locator('.report-detail-collapse .el-collapse-item__header')
  if (await fullReportHeader.count()) {
    await fullReportHeader.first().click()
  }
  await page.waitForTimeout(4000)

  const probeReport = await page.evaluate(() => {
    const report = document.querySelector('.final-report')
    if (!report) return { exists: false }
    const containers = [...report.querySelectorAll('.mermaid-container')]
    return {
      exists: true,
      charts: containers.map((c) => ({
        hasSvg: !!c.querySelector('svg'),
        loading: !!c.querySelector('.mermaid-loading'),
        error: !!c.querySelector('.mermaid-error'),
        hidden: c.offsetParent === null,
      })),
      visualBlocks: report.querySelectorAll('.report-visual-block, [class*="visual-block"]').length,
      evidenceButtons: report.querySelectorAll('.evidence-ref, .evidence-linked-content').length,
      rawEvidenceIds: (report.textContent.match(/\[evidence_id:[^\]]+\]/g) || []),
      linkedIds: [...report.querySelectorAll('.evidence-ref, .evidence-linked-content')]
        .map((el) => el.dataset.evidenceId),
    }
  })
  console.log('EMBED_REPORT_PROBE ' + JSON.stringify(probeReport, null, 2))
  if (consoleErrors.length) {
    console.log('CONSOLE_ISSUES ' + JSON.stringify(consoleErrors.slice(0, 12), null, 2))
  }
  await page.screenshot({ path: testInfo.outputPath('embed-probe.png'), fullPage: true })

  // === 修复验收 ===
  // 1) Agent 报告中所有图表都渲染出 svg（不允许停留在“正在渲染图表...”）
  for (const agent of probeAgents) {
    for (const chart of agent.charts) {
      expect(chart.loading, 'Agent 报告图表不应停留在加载占位').toBe(false)
      expect(chart.hasSvg, 'Agent 报告图表应渲染出 svg').toBe(true)
    }
  }
  // 2) 跨 Agent 的 scoped 证据引用必须转成可点击引用，不能保留明文
  for (const agent of probeAgents) {
    expect(agent.rawEvidenceIds, 'Agent 报告不得出现明文证据 ID').toEqual([])
  }
  const allLinkedIds = probeAgents.flatMap((agent) => agent.linkedIds)
  expect(allLinkedIds).toContain(LAB_EVIDENCE_ID)
  expect(allLinkedIds).toContain(ONCO_EVIDENCE_ID)
  // 3) 最终报告图表渲染 + 无明文证据 ID + 可见信息图块
  for (const chart of probeReport.charts) {
    expect(chart.loading, '最终报告图表不应停留在加载占位').toBe(false)
    expect(chart.hasSvg, '最终报告图表应渲染出 svg').toBe(true)
  }
  expect(probeReport.rawEvidenceIds).toEqual([])
  expect(probeReport.linkedIds).toContain(LAB_EVIDENCE_ID)
  expect(probeReport.visualBlocks).toBeGreaterThan(0)
})
