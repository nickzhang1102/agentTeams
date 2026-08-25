import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ConversationDisplay from './ConversationDisplay.vue'
import { useLeaderStore } from '@/stores/leader'

const { consumeSSEStreamMock } = vi.hoisted(() => ({
  consumeSSEStreamMock: vi.fn(),
}))

vi.mock('@/utils/sseConsumer', () => ({
  consumeSSEStream: consumeSSEStreamMock,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({
    path: '/embed/conversation/embed-token',
    params: {
      token: 'embed-token'
    }
  })
}))

// 三个展示子组件很重（依赖 i18n/翻译 store/Element Plus），stub 之，
// 专注验证 embed 快照 → leaderStore 的灌入与组件装配。
const leaderThinkingStub = {
  props: ['sessionId', 'allowStop'],
  template: '<div data-test="leader-thinking" :data-session-id="sessionId" :data-allow-stop="allowStop ? \'true\' : \'false\'"></div>'
}
const agentStatusPanelStub = {
  props: ['conversationId', 'evidenceDetailEnabled'],
  template: '<div data-test="agent-status-panel" :data-conversation-id="conversationId" :data-evidence-detail-enabled="evidenceDetailEnabled ? \'true\' : \'false\'"></div>'
}
const leaderFinalReportStub = {
  props: ['conversationId', 'sessionId', 'evidenceDetailEnabled'],
  template: '<div data-test="leader-final-report" :data-conversation-id="conversationId" :data-session-id="sessionId" :data-evidence-detail-enabled="evidenceDetailEnabled ? \'true\' : \'false\'"></div>'
}
const leaderQuestionDialogStub = {
  props: ['answerEndpoint', 'includeAuthorization', 'reconcileOnDone'],
  template: '<div data-test="leader-question-dialog" :data-answer-endpoint="answerEndpoint" :data-include-authorization="includeAuthorization ? \'true\' : \'false\'" :data-reconcile-on-done="reconcileOnDone ? \'true\' : \'false\'"></div>'
}

function makeCompletedSnapshot() {
  return {
    version: '20:completed:1:1:1',
    conversation: {
      id: 10,
      title: '虚拟会诊',
      status: 'completed'
    },
    sessions: [{
      id: 20,
      state: 'completed',
      risk_level: 'medium',
      started_at: '2026-07-08T08:00:00Z',
      completed_at: '2026-07-08T08:05:00Z',
      selected_agents: ['oncology', 'pathology'],
      final_report: {
        id: 5,
        leader_session_id: 20,
        report: '综合报告内容',
        summary: { title: '摘要', key_findings: ['发现1'] }
      },
      agent_results: [{
        id: 1,
        agent_id: 'oncology',
        agent_name: '肿瘤内科',
        status: 'success',
        content: '肿瘤内科分析',
        decomposition: { subtasks: [] },
        tool_calls: [],
        tokens_used: 100,
        execution_time: 12.3,
        sequence_number: 1
      }, {
        id: 2,
        agent_id: 'pathology',
        agent_name: '病理科',
        status: 'failed',
        error: '超时',
        sequence_number: 2
      }]
    }],
    messages: [{
      id: 30,
      type: 'user',
      content: '请基于病历生成多学科会诊意见。',
      sequence_number: 1,
      created_at: '2026-07-08T08:00:00Z',
      leader_session_id: 20
    }]
  }
}

function mountComponent(props = { token: 'embed-token', accessMode: 'embed' }) {
  return mount(ConversationDisplay, {
    props,
    global: {
      stubs: {
        LeaderThinking: leaderThinkingStub,
        AgentStatusPanel: agentStatusPanelStub,
        LeaderFinalReport: leaderFinalReportStub,
        LeaderQuestionDialog: leaderQuestionDialogStub,
        ScrollToTopButton: true,
        EditIndicator: true,
        Splitpanes: { template: '<div><slot /></div>' },
        Pane: { template: '<div><slot /></div>' }
      }
    }
  })
}

describe('ConversationDisplay embed access mode', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    consumeSSEStreamMock.mockReset()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(makeCompletedSnapshot())
    })))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('loads the embed snapshot and hydrates the leader store for full detail rendering', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      '/api/integrations/agentteams/embed-sessions/embed-token',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )

    // 三个完整明细子组件被装配，且拿到正确 props
    expect(wrapper.find('[data-test="leader-thinking"]').attributes('data-session-id')).toBe('20')
    expect(wrapper.find('[data-test="leader-thinking"]').attributes('data-allow-stop')).toBe('false')
    expect(wrapper.find('[data-test="agent-status-panel"]').attributes('data-conversation-id')).toBe('10')
    expect(wrapper.find('[data-test="agent-status-panel"]').attributes('data-evidence-detail-enabled')).toBe('false')
    expect(wrapper.find('[data-test="leader-final-report"]').attributes('data-session-id')).toBe('20')
    expect(wrapper.find('[data-test="leader-final-report"]').attributes('data-evidence-detail-enabled')).toBe('false')
    expect(wrapper.find('.back-button').exists()).toBe(false)
    expect(wrapper.find('.edit-question-btn').exists()).toBe(false)
    expect(wrapper.find('.regenerate-btn').exists()).toBe(false)

    // store 被正确灌入
    const store = useLeaderStore()
    expect(store.leaderState).toBe('completed')
    expect(store.resultsReconciled).toBe(true)
    expect(store.totalTime).toBe(5 * 60 * 1000)
    expect(store.currentSession).toEqual({ id: 20 })

    // 团队
    expect(store.selectedAgents.map(a => a.agent_id)).toEqual(['oncology', 'pathology'])

    // Agent 结果与状态
    expect(store.agentResults).toHaveLength(2)
    expect(store.agentResults[0].success).toBe(true)
    expect(store.agentResults[1].success).toBe(false)
    expect(store.agentStatuses[0].status).toBe('completed')
    expect(store.agentStatuses[1].status).toBe('failed')
    expect(store.agentStatuses[1].message).toBe('超时')
    expect(store.agentStatuses[0].decomposition).toEqual({ subtasks: [] })

    // 执行顺序
    expect(store.agentExecutionOrder.oncology.sequence).toBe(0)
    expect(store.agentExecutionOrder.pathology.sequence).toBe(1)

    // 最终报告挂到 sessions 上，供按 sessionId 取报告
    expect(store.finalReport.report).toBe('综合报告内容')
    const session = store.sessions.find(s => s.id === 20)
    expect(session.final_report.report).toBe('综合报告内容')

    // 历史消息时间线
    expect(store.historicalMessages).toHaveLength(1)
    expect(store.historicalMessages[0].type).toBe('user')

    wrapper.unmount()
  })

  it('subscribes to embed SSE and refreshes when the durable snapshot changes', async () => {
    fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          version: '20:monitoring:1:0:0',
          conversation: { id: 10, title: '虚拟会诊', status: 'analyzing' },
          sessions: [{ id: 20, state: 'monitoring', agent_results: [] }],
          messages: []
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        body: {},
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(makeCompletedSnapshot())
      })

    consumeSSEStreamMock.mockImplementation(async (_response, onMessage) => {
      onMessage({
        type: 'embed_snapshot',
        version: '20:completed:2:0:1',
        terminal: true,
      })
    })

    const wrapper = mountComponent()
    await flushPromises()
    await flushPromises()
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(fetch.mock.calls[1][0]).toBe(
      '/api/integrations/agentteams/embed-sessions/embed-token/events'
    )
    expect(consumeSSEStreamMock).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[2][0]).toBe(
      '/api/integrations/agentteams/embed-sessions/embed-token'
    )

    const store = useLeaderStore()
    expect(store.leaderState).toBe('completed')
    expect(store.finalReport.report).toBe('综合报告内容')

    // 终态后停止事件流和轮询
    await vi.advanceTimersByTimeAsync(10000)
    expect(fetch).toHaveBeenCalledTimes(3)
    wrapper.unmount()
  })

  it('falls back to bounded polling when the embed SSE connection fails', async () => {
    fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          version: '20:monitoring:1:0:0',
          conversation: { id: 10, title: '虚拟会诊', status: 'analyzing' },
          sessions: [{ id: 20, state: 'monitoring', agent_results: [] }],
          messages: []
        })
      })
      .mockResolvedValueOnce({ ok: false, status: 503, text: () => Promise.resolve('offline') })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          conversation_id: 10,
          status: 'completed',
          terminal: true,
          version: '20:completed:2:0:1'
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(makeCompletedSnapshot())
      })
    consumeSSEStreamMock.mockRejectedValue(new Error('SSE unavailable'))

    const wrapper = mountComponent()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(fetch.mock.calls[2][0]).toBe(
      '/api/integrations/agentteams/embed-sessions/embed-token/status'
    )
    await flushPromises()
    expect(fetch.mock.calls[3][0]).toBe(
      '/api/integrations/agentteams/embed-sessions/embed-token'
    )
    expect(useLeaderStore().leaderState).toBe('completed')
    wrapper.unmount()
  })

  it('restores pending questions and wires the shared dialog to the bound embed endpoint', async () => {
    const fullRequirement = `完整医疗需求-${'病历'.repeat(200)}`
    fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        version: '20:questioning:2:0:0',
        conversation: { id: 10, title: '虚拟会诊', status: 'analyzing' },
        sessions: [{ id: 20, state: 'questioning', agent_results: [] }],
        messages: [
          {
            id: 30,
            type: 'user',
            content: fullRequirement,
            created_at: '2026-07-08T08:00:00Z',
            leader_session_id: 20
          },
          {
            id: 31,
            type: 'question',
            content: {
              questions: [{ question: '当前治疗目标？', options: ['治愈', '控制', '缓解'] }]
            },
            created_at: '2026-07-08T08:01:00Z',
            leader_session_id: 20
          }
        ]
      })
    })

    const wrapper = mountComponent()
    await flushPromises()

    const store = useLeaderStore()
    expect(store.leaderState).toBe('questioning')
    expect(store.currentQuestions).toEqual([
      { question: '当前治疗目标？', options: ['治愈', '控制', '缓解'] }
    ])
    expect(wrapper.text()).toContain(fullRequirement)
    expect(wrapper.find('[data-test="leader-question-dialog"]').attributes()).toMatchObject({
      'data-answer-endpoint': '/api/integrations/agentteams/embed-sessions/embed-token/answers',
      'data-include-authorization': 'false',
      'data-reconcile-on-done': 'false'
    })

    wrapper.unmount()
  })

  it('cancels the event stream and does not start fallback polling after unmount', async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        version: '20:monitoring:1:0:0',
        conversation: { id: 10, status: 'analyzing' },
        sessions: [{ id: 20, state: 'monitoring', agent_results: [] }],
        messages: []
      })
    })

    const wrapper = mountComponent()
    await flushPromises()
    expect(fetch.mock.calls[1][0]).toBe(
      '/api/integrations/agentteams/embed-sessions/embed-token/events'
    )
    wrapper.unmount()

    await vi.advanceTimersByTimeAsync(10000)
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('shows an error view when the embed link is invalid', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: { message: 'Invalid embed token' } })
    })

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.text()).toContain('Invalid embed token')
    expect(wrapper.find('[data-test="agent-status-panel"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps the standard share access path on the same analysis component', async () => {
    const store = useLeaderStore()
    store.currentSession = { id: 999 }
    store.agentResults = [{ agent_id: 'stale-agent' }]
    store.finalReport = { report: 'Stale embed report' }
    store.thinkingContent = 'Stale embed thinking'
    fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          conversation: { id: 11, title: 'Standard analysis' },
          messages: [],
          files: []
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, sessions: [], messages: [] })
      })

    const wrapper = mountComponent({ token: 'share-token', accessMode: 'standard' })
    await flushPromises()

    expect(fetch.mock.calls[0][0]).toBe('/api/conversations/share/share-token')
    expect(fetch.mock.calls[1][0]).toBe('/api/leader/session/share/share-token')
    expect(wrapper.find('.back-button').exists()).toBe(true)
    expect(wrapper.find('[data-test="leader-question-dialog"]').attributes()).toMatchObject({
      'data-answer-endpoint': '/api/leader/answer-questions',
      'data-include-authorization': 'true',
      'data-reconcile-on-done': 'true'
    })
    expect(store.currentSession).toBeNull()
    expect(store.agentResults).toEqual([])
    expect(store.finalReport).toBe('')
    expect(store.thinkingContent).toBe('')

    wrapper.unmount()
  })

  it('reloads standard access and clears the previous session when the route token changes', async () => {
    fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          conversation: { id: 11, title: 'Conversation A' },
          messages: [],
          files: []
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          sessions: [{
            id: 21,
            state: 'completed',
            agent_results: [{
              agent_id: 'agent-a',
              agent_name: 'Agent A',
              status: 'success'
            }],
            final_report: { report: 'Report A' }
          }],
          messages: []
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          conversation: { id: 12, title: 'Conversation B' },
          messages: [],
          files: []
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, sessions: [], messages: [] })
      })

    const wrapper = mountComponent({ token: 'token-a', accessMode: 'standard' })
    await flushPromises()
    expect(useLeaderStore().finalReport).toMatchObject({ report: 'Report A' })

    await wrapper.setProps({ token: 'token-b' })
    await flushPromises()

    expect(fetch.mock.calls.map(call => call[0])).toEqual([
      '/api/conversations/share/token-a',
      '/api/leader/session/share/token-a',
      '/api/conversations/share/token-b',
      '/api/leader/session/share/token-b'
    ])
    expect(wrapper.find('[data-test="agent-status-panel"]').attributes('data-conversation-id')).toBe('12')
    expect(useLeaderStore().currentSession).toBeNull()
    expect(useLeaderStore().agentResults).toEqual([])
    expect(useLeaderStore().finalReport).toBe('')

    wrapper.unmount()
  })
})
