import { describe, expect, it } from 'vitest'
import { i18n } from '@/locales'
import { formatMessageContent } from './messageContentFormatter'

describe('formatMessageContent localized SSE descriptor', () => {
  it('uses message_key and params with the active UI locale', () => {
    const event = {
      message_key: 'leader.phase.execution_starting',
      message_params: { agent_count: 3, batch_count: 2 },
      message: 'legacy fallback',
    }

    i18n.global.locale.value = 'zh-CN'
    expect(formatMessageContent(event, 'progress')).toBe('启动 3 个 Agent 执行，共 2 个批次...')

    i18n.global.locale.value = 'en-US'
    expect(formatMessageContent(event, 'progress')).toBe('Starting 3 agents across 2 batches...')
  })

  it('falls back to the compatible message when the key is unknown', () => {
    expect(formatMessageContent({
      message_key: 'leader.phase.unknown',
      message: 'Compatible fallback',
    }, 'progress')).toBe('Compatible fallback')
  })
})
