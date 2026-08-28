import { describe, it, expect } from 'vitest'
import { renderInlineMd } from '../markdown'

describe('renderInlineMd evidence refs', () => {
  const evidenceMap = [
    { evidence_id: 'lab_ev_subtask_1_llm_analysis_1', title: '来源一' },
    { evidence_id: 'lab_ev_subtask_2_web_search_1', title: '来源二' }
  ]

  it('命中证据表时把 [evidence_id:xxx] 渲染为可点击短标签', () => {
    const html = renderInlineMd('结论见 [evidence_id:lab_ev_subtask_1_llm_analysis_1]。', {
      evidenceMap,
      evidenceLabel: '证据'
    })
    expect(html).toContain('data-evidence-id="lab_ev_subtask_1_llm_analysis_1"')
    expect(html).toContain('证据1')
    expect(html).toContain('class="evidence-ref"')
    expect(html).not.toContain('[evidence_id:')
    expect(html).not.toContain('lab_ev_subtask_1_llm_analysis_1</')
  })

  it('未命中证据表时直接移除标记，不回显原始 ID', () => {
    const html = renderInlineMd('结论见 [evidence_id:unknown_ev_99]。', {
      evidenceMap,
      evidenceLabel: '证据'
    })
    expect(html).not.toContain('[evidence_id:')
    expect(html).not.toContain('unknown_ev_99')
    expect(html).not.toContain('evidence-ref-unknown')
  })

  it('无证据表时同样直接移除标记', () => {
    const html = renderInlineMd('结论见 [evidence_id:unknown_ev_99]。')
    expect(html).not.toContain('[evidence_id:')
    expect(html).not.toContain('unknown_ev_99')
    expect(html).not.toContain('evidence-ref-unknown')
  })

  it('保留行内 Markdown 基础语法', () => {
    const html = renderInlineMd('**加粗** 与 *斜体* 和 `code`')
    // 注：happy-dom 下 DOMPurify 会剥离 <strong>（浏览器正常），故不直接断言 strong 标签
    expect(html).toContain('加粗')
    expect(html).not.toContain('**')
    expect(html).toContain('<em>斜体</em>')
    expect(html).toContain('<code>code</code>')
  })

  it('转义原始 HTML 防止标签注入', () => {
    const html = renderInlineMd('<script>alert(1)</script>')
    expect(html).not.toContain('<script>')
  })
})
