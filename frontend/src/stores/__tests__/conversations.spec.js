import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useConversationsStore } from '@/stores/conversations'
import { useLeaderStore } from '@/stores/leader'

vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn()
  }
}))

import api from '@/utils/api'

describe('Conversations Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('fetchConversation', () => {
    it('为评审模式历史对话加载 Leader 历史，即使消息里没有 leader_session_id', async () => {
      api.get
        .mockResolvedValueOnce({
          data: {
            conversation: {
              id: 42,
              title: '评审历史',
              is_review_mode: true
            },
            messages: [
              {
                id: 1,
                role: 'user',
                content: '请帮我评审这个方案',
                created_at: '2026-03-08T10:00:00.000Z'
              }
            ]
          }
        })
        .mockResolvedValueOnce({
          data: {
            success: true,
            sessions: [
              {
                id: 9,
                state: 'completed',
                assessment_details: {},
                team_config: { agents: [] },
                agent_results: [],
                final_report: '最终报告'
              }
            ],
            messages: [
              {
                id: 2,
                role: 'assistant',
                type: 'leader_thinking',
                content: '需求分析中',
                created_at: '2026-03-08T10:01:00.000Z'
              }
            ]
          }
        })

      const store = useConversationsStore()
      const leaderStore = useLeaderStore()
      const loadHistoricalSessionSpy = vi.spyOn(leaderStore, 'loadHistoricalSession')

      const result = await store.fetchConversation(42)

      expect(result.success).toBe(true)
      expect(result.hasLeaderSession).toBe(true)
      expect(loadHistoricalSessionSpy).toHaveBeenCalledWith(42)
      expect(api.get).toHaveBeenNthCalledWith(1, '/api/conversations/42')
      expect(api.get).toHaveBeenNthCalledWith(2, '/api/leader/session/42')
      expect(store.currentConversation.is_review_mode).toBe(true)
      // messages 只包含从 conversations API 返回的消息
      // Leader 相关消息存储在 leaderStore 中
      expect(store.messages.map(message => message.id)).toEqual([1])
    })
  })

  describe('createConversation', () => {
    it('创建对话时透传会话级评审模式', async () => {
      api.post.mockResolvedValueOnce({
        data: {
          id: 7,
          title: '评审对话',
          is_review_mode: true
        }
      })

      const store = useConversationsStore()
      const result = await store.createConversation('评审对话', true)

      expect(result.success).toBe(true)
      expect(api.post).toHaveBeenCalledWith('/api/conversations', {
        title: '评审对话',
        is_review_mode: true
      })
      expect(store.currentConversation.is_review_mode).toBe(true)
      expect(store.messages).toEqual([])
    })
  })
})
