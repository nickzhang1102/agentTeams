import { describe, expect, it } from 'vitest'
import { collectLeaderTranslationSources } from './contentTranslationSources'

describe('collectLeaderTranslationSources', () => {
  it('collects only persisted mismatched translatable Leader content', () => {
    const sources = collectLeaderTranslationSources({
      targetLocale: 'en-US',
      messages: [
        { id: 1, type: 'progress', content_locale: 'zh-CN', rawContent: { text: '分析中' } },
        { id: 2, type: 'answer', content_locale: 'zh-CN', rawContent: { text: '用户回答' } },
        { id: 3, type: 'assessment', content_locale: 'zh-CN', rawContent: { score: 80 } },
        { id: 4, type: 'progress', content_locale: 'en-US', rawContent: { text: 'Running' } },
        { id: 'sse-1', type: 'progress', content_locale: 'zh-CN', rawContent: { text: '临时' } },
      ],
      agentResults: [
        { id: 10, content_locale: 'zh-CN', content: '中文报告' },
        { id: 11, content_locale: 'en-US', content: 'English report' },
      ],
      finalReport: { id: 20, content_locale: 'zh-CN', report: '中文最终报告' },
    })

    expect(sources).toEqual([
      { type: 'message', id: 1 },
      { type: 'leader_agent_result', id: 10 },
      { type: 'leader_final_report', id: 20 },
    ])
  })

  it('returns no sources for an unsupported target locale', () => {
    expect(collectLeaderTranslationSources({
      targetLocale: 'fr-FR',
      agentResults: [{ id: 10, content_locale: 'zh-CN', content: '中文报告' }],
    })).toEqual([])
  })
})
