import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useLeaderStore } from '../leader'
import { i18n } from '@/locales'

vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn()
  }
}))

import api from '@/utils/api'

function createEmptySSE() {
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: vi.fn().mockResolvedValue({ done: true }),
        cancel: vi.fn()
      })
    }
  }
}

function createSSE(...events) {
  const chunks = events.map(event => new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`))
  const read = vi.fn()
  for (const chunk of chunks) {
    read.mockResolvedValueOnce({ done: false, value: chunk })
  }
  read.mockResolvedValueOnce({ done: true })
  return {
    ok: true,
    body: {
      getReader: () => ({ read, cancel: vi.fn() })
    }
  }
}

function createControllableSSE() {
  let resolveRead
  const read = vi.fn(() => new Promise(resolve => {
    resolveRead = resolve
  }))
  const cancel = vi.fn()
  return {
    response: {
      ok: true,
      body: {
        getReader: () => ({ read, cancel })
      }
    },
    emit(event) {
      resolveRead({
        done: false,
        value: new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`)
      })
    },
    read,
    cancel
  }
}

describe('Leader Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    i18n.global.locale.value = 'zh-CN'
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('应该正确初始化状态', () => {
    const store = useLeaderStore()

    expect(store.sessions).toEqual([])
    expect(store.messages).toEqual([])
    expect(store.currentSession).toBeNull()
    expect(store.isLoading).toBe(false)
  })

  it('应该正确按类型筛选消息', () => {
    const store = useLeaderStore()

    // 模拟消息数据
    store.messages = [
      { id: 1, type: 'assessment', content: { score: 85 } },
      { id: 2, type: 'team_config', content: { agents: ['a1'] } },
      { id: 3, type: 'assessment', content: { score: 90 } }
    ]

    const assessmentMsgs = store.getMessagesByType('assessment')
    expect(assessmentMsgs).toHaveLength(2)
    expect(assessmentMsgs[0].content.score).toBe(85)
  })

  it('应该正确按会话 ID 筛选消息', () => {
    const store = useLeaderStore()

    // 模拟消息数据
    store.messages = [
      { id: 1, leader_session_id: 'session-1', type: 'assessment' },
      { id: 2, leader_session_id: 'session-2', type: 'team_config' },
      { id: 3, leader_session_id: 'session-1', type: 'final_report' }
    ]

    const session1Msgs = store.getMessagesBySession('session-1')
    expect(session1Msgs).toHaveLength(2)
    expect(session1Msgs[0].type).toBe('assessment')
    expect(session1Msgs[1].type).toBe('final_report')
  })

  it('停止请求失败后恢复按钮状态并允许重试', async () => {
    api.post.mockRejectedValueOnce(new Error('temporary failure'))
    const store = useLeaderStore()
    store.currentSession = { id: 77 }

    await expect(store.stopExecution()).rejects.toThrow('temporary failure')

    expect(store.stopRequested).toBe(false)
    api.post.mockResolvedValueOnce({ data: { success: true } })
    await store.stopExecution()
    expect(api.post).toHaveBeenLastCalledWith('/api/leader/stop', { session_id: 77 })
  })

  it('实时消息不应覆盖快照中的 Leader 历史消息', () => {
    const store = useLeaderStore()

    store.historicalMessages = [
      { id: 1, leader_session_id: 7, type: 'assessment', content: '评估完成' },
      { id: 2, leader_session_id: 7, type: 'team_config', content: '团队已组建' },
    ]
    store.messages = [
      { id: 3, leader_session_id: '7', type: 'answer', content: '用户回答' },
      { id: 2, leader_session_id: '7', type: 'team_config', content: '团队已更新' },
    ]

    expect(store.getMessagesBySession('7')).toEqual([
      { id: 1, leader_session_id: 7, type: 'assessment', content: '评估完成' },
      { id: 2, leader_session_id: '7', type: 'team_config', content: '团队已更新' },
      { id: 3, leader_session_id: '7', type: 'answer', content: '用户回答' },
    ])
  })

  it('应该正确清空数据', () => {
    const store = useLeaderStore()

    // 模拟数据
    store.sessions = [{ id: 'session-1' }]
    store.messages = [{ id: 1, type: 'assessment' }]
    store.currentSession = { id: 'session-1' }
    store.error = 'Some error'

    // 清空数据
    store.clearData()

    expect(store.sessions).toEqual([])
    expect(store.messages).toEqual([])
    expect(store.currentSession).toBeNull()
    expect(store.error).toBeNull()
  })

  it('应该正确处理空消息列表', () => {
    const store = useLeaderStore()

    const assessmentMsgs = store.getMessagesByType('assessment')
    expect(assessmentMsgs).toHaveLength(0)

    const sessionMsgs = store.getMessagesBySession('session-1')
    expect(sessionMsgs).toHaveLength(0)
  })

  it('子任务全部结束后应等待 Agent 报告事件再标记完成', () => {
    const store = useLeaderStore()
    store.agentStatuses = [{
      agent_id: 'medical-oncologist',
      status: 'running',
      decomposition: {
        subtasks: [{ id: 'subtask-1', status: 'running', goal: '分析病历' }]
      }
    }]

    store.handleSubtaskCompleted({
      agent_id: 'medical-oncologist',
      subtask_id: 'subtask-1',
      status: 'completed'
    })

    expect(store.agentStatuses[0].status).toBe('running')

    store.handleAgentResult({
      agent_id: 'medical-oncologist',
      agent_name: '肿瘤内科专家',
      status: 'success',
      content: '完整 Agent 报告'
    })

    expect(store.agentStatuses[0].status).toBe('completed')
    expect(store.agentStatuses[0].content).toBe('完整 Agent 报告')
  })

  it('loadHistoricalSession 应为旧历史会话补齐执行顺序', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        success: true,
        sessions: [
          {
            id: 12,
            state: 'completed',
            total_time: 18,
            team_config: {
              agent_details: [
                { agent_id: 'researcher', agent_name: '研究专家' },
                { agent_id: 'writer', agent_name: '写作专家' }
              ]
            },
            agent_results: [],
            final_report: 'ok'
          }
        ],
        messages: []
      }
    })

    const store = useLeaderStore()
    const result = await store.loadHistoricalSession(99)

    expect(result.latestSession.id).toBe(12)
    expect(store.selectedAgents).toHaveLength(2)
    expect(store.agentExecutionOrder.researcher).toMatchObject({
      batchIndex: 0,
      agentIndex: 0,
      sequence: 0
    })
    expect(store.agentExecutionOrder.writer).toMatchObject({
      batchIndex: 1,
      agentIndex: 0,
      sequence: 1
    })
  })

  it('loadHistoricalSession 应恢复 questioning 会话的待回答问题', async () => {
    const questions = [{ question: '需要部署到哪里？', options: ['云端', '本地'] }]
    api.get.mockResolvedValueOnce({
      data: {
        success: true,
        sessions: [{
          id: 13,
          state: 'questioning',
          total_time: 5,
          team_config: {},
          agent_results: []
        }],
        messages: [{
          id: 31,
          type: 'question',
          leader_session_id: 13,
          content: { questions }
        }]
      }
    })

    const store = useLeaderStore()
    await store.loadHistoricalSession(99)

    expect(store.leaderState).toBe('questioning')
    expect(store.currentQuestions).toEqual(questions)
  })

  it('不为非 questioning 会话恢复历史问题', () => {
    const store = useLeaderStore()
    store.currentQuestions = [{ question: '旧问题', options: [] }]

    const restored = store.restorePendingQuestions(
      { id: 13, state: 'completed' },
      [{
        type: 'question',
        leader_session_id: 13,
        content: { questions: [{ question: '旧问题', options: [] }] }
      }]
    )

    expect(restored).toEqual([])
    expect(store.currentQuestions).toEqual([])
  })

  it('网络错误最多重试三次并保留最终重试计数', async () => {
    vi.useFakeTimers()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const store = useLeaderStore()

    const result = expect(
      store.startLeaderSessionWithRetry(99, '分析病例')
    ).rejects.toThrow('Failed to fetch')
    await vi.runAllTimersAsync()

    await result
    expect(fetch).toHaveBeenCalledTimes(4)
    expect(store.retryCount).toBe(3)
    store.clearData()
  })

  it('英文 UI 直接启动时发送 locale 快照', async () => {
    i18n.global.locale.value = 'en-US'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(createEmptySSE()))
    const store = useLeaderStore()

    await store.startLeaderSession(99, 'Analyze this request', [7], { source: 'chat' })

    const body = JSON.parse(fetch.mock.calls[0][1].body)
    expect(body).toEqual({
      conversation_id: 99,
      message: 'Analyze this request',
      file_ids: [7],
      context: { source: 'chat' },
      locale: 'en-US'
    })
    store.clearData()
  })

  it('重置后旧执行流的晚到事件不会污染新会话且新会话可以启动', async () => {
    const oldStream = createControllableSSE()
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(oldStream.response)
      .mockResolvedValueOnce(createEmptySSE()))
    const store = useLeaderStore()

    const oldRequest = store.startLeaderSession(1, 'Old request')
    await vi.waitFor(() => expect(oldStream.read).toHaveBeenCalledOnce())

    store.resetState()
    expect(oldStream.cancel).toHaveBeenCalledOnce()
    const newRequest = store.startLeaderSession(2, 'New request')
    await newRequest

    oldStream.emit({
      type: 'assessment_result',
      session_id: 1,
      analysis: 'Stale assessment'
    })
    await oldRequest

    expect(fetch).toHaveBeenCalledTimes(2)
    expect(store.currentSession).toBeNull()
    expect(store.thinkingContent).not.toContain('Stale assessment')
  })

  it('重置后旧 done 对账响应不会覆盖当前 store', async () => {
    let resolvePersisted
    const persistedResponse = new Promise(resolve => {
      resolvePersisted = resolve
    })
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(createSSE(
        { type: 'assessment_result', session_id: 11, analysis: 'Old' },
        { type: 'done', session_id: 11 }
      ))
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn(() => persistedResponse)
      }))
    const store = useLeaderStore()

    await store.startLeaderSession(1, 'Old request')
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    store.resetState()
    resolvePersisted({
      agent_results: [{ id: 91, status: 'success', content: 'Stale result' }],
      final_report: { report: 'Stale final report' }
    })
    await Promise.resolve()
    await Promise.resolve()

    expect(store.agentResults).toEqual([])
    expect(store.finalReport).toBe('')
    expect(store.resultsReconciled).toBe(false)
  })

  it('页面跳转后仍使用首页冻结的 locale 快照', async () => {
    i18n.global.locale.value = 'zh-CN'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(createEmptySSE()))
    const store = useLeaderStore()

    await store.startLeaderSession(
      99,
      'Analyze this request',
      [],
      { source: 'home' },
      'en-US'
    )

    const body = JSON.parse(fetch.mock.calls[0][1].body)
    expect(body.locale).toBe('en-US')
    store.clearData()
  })

  it('英文 UI 模板启动时发送 locale 快照', async () => {
    i18n.global.locale.value = 'en-US'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(createEmptySSE()))
    const store = useLeaderStore()

    await store.applyTemplateSession(12, 99, 'Run template', [8])

    const body = JSON.parse(fetch.mock.calls[0][1].body)
    expect(body).toEqual({
      conversation_id: 99,
      message: 'Run template',
      file_ids: [8],
      locale: 'en-US'
    })
    store.clearData()
  })

  it('assessment_result 只记录一条评估并同步英文实时内容', () => {
    const store = useLeaderStore()

    store.handleSSEMessage({
      data: {
        type: 'assessment_result',
        session_id: 910,
        score: 25,
        details: {
          scores: { '目标明确性': 15 },
          analysis: 'The request needs a clearer outcome.',
          risk_reason: 'Choosing a direction may affect team investment.',
        },
        risk_level: 'medium',
        passed: false,
        content_locale: 'en-US',
      }
    })

    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].type).toBe('assessment')
    expect(store.thinkingContent).toBe(store.messages[0].content)
    expect(store.thinkingContent).toContain('## Requirement Assessment')
    expect(store.thinkingContent).toContain('Goal clarity: 15 points')
    expect(store.thinkingContent).toContain('The request needs a clearer outcome.')
    expect(store.thinkingContent).toContain('Risk Rationale')
    expect(store.thinkingContent).toContain('Choosing a direction may affect team investment.')
  })

  it('done 事件会回读持久化结果并标记对账完成', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        agent_results: [{
          id: 31,
          agent_id: 'researcher',
          agent_name: 'Researcher',
          status: 'success',
          content: 'Persisted result',
          content_locale: 'en-US',
        }],
        final_report: {
          id: 41,
          report: 'Persisted final report',
          content_locale: 'en-US',
        },
      }),
    }))
    const store = useLeaderStore()
    store.currentSession = { id: 12 }

    store.handleSSEMessage({ data: { type: 'done', session_id: 12 } })
    await vi.waitFor(() => expect(store.resultsReconciled).toBe(true))

    expect(fetch).toHaveBeenCalledWith(
      '/api/leader/status/12?include_results=true',
      expect.any(Object),
    )
    expect(store.agentResults[0]).toMatchObject({ id: 31, content_locale: 'en-US' })
    expect(store.finalReport).toMatchObject({ id: 41, content_locale: 'en-US' })
  })

  it('回答追问请求体不发送 locale', async () => {
    i18n.global.locale.value = 'en-US'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(createEmptySSE()))
    const store = useLeaderStore()
    store.currentSession = { id: 77 }
    store.currentQuestions = [{ question: 'Which target?', options: [] }]

    await store.submitAnswers(['Existing cluster'])

    const body = JSON.parse(fetch.mock.calls[0][1].body)
    expect(body).toEqual({
      session_id: 77,
      answers: ['Existing cluster']
    })
    expect(body).not.toHaveProperty('locale')
  })

  it('受限回答流完成后不回读 owner 持久化接口', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(createSSE({
      type: 'done',
      session_id: 77,
    })))
    const store = useLeaderStore()
    store.currentSession = { id: 77 }
    store.currentQuestions = [{ question: 'Which target?', options: [] }]

    await store.submitAnswers(['Existing cluster'], {
      endpoint: '/api/integrations/agentteams/embed-sessions/embed-token/answers',
      includeAuthorization: false,
      reconcileOnDone: false,
    })

    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).not.toHaveBeenCalledWith(
      '/api/leader/status/77?include_results=true',
      expect.any(Object),
    )
  })

  it('重置后旧回答流的 done 对账响应不会覆盖当前 store', async () => {
    let resolvePersisted
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(createSSE({ type: 'done', session_id: 77 }))
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn(() => new Promise(resolve => {
          resolvePersisted = resolve
        }))
      }))
    const store = useLeaderStore()
    store.currentSession = { id: 77 }
    store.currentQuestions = [{ question: 'Which target?', options: [] }]

    await store.submitAnswers(['Existing cluster'])
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    store.resetState()
    resolvePersisted({
      agent_results: [{ id: 92, status: 'success', content: 'Stale answer result' }],
      final_report: { report: 'Stale answer final report' }
    })
    await Promise.resolve()
    await Promise.resolve()

    expect(store.agentResults).toEqual([])
    expect(store.finalReport).toBe('')
    expect(store.resultsReconciled).toBe(false)
  })
})

describe('SSE Event Handlers', () => {
  let store

  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    store = useLeaderStore()
  })

  describe('handleToolCallStarted', () => {
    it('应设置 agent 的 currentTool 并积累到 toolCallHistory', () => {
      // 预设一个 agent 状态
      store.agentStatuses = [{
        agent_id: 'cardiology-expert',
        agent_name: '心血管内科专家',
        status: 'pending',
        toolCallHistory: []
      }]

      store.handleToolCallStarted({
        agent_id: 'cardiology-expert',
        agent_name: '心血管内科专家',
        tool_name: 'file_read',
        tool_input: { path: '/data/report.md' }
      })

      const agent = store.agentStatuses.find(s => s.agent_id === 'cardiology-expert')
      expect(agent.currentTool).toBeDefined()
      expect(agent.currentTool.name).toBe('file_read')
      expect(agent.currentTool.status).toBe('running')
      expect(agent.status).toBe('running')
      expect(agent.toolCallHistory).toHaveLength(1)
      expect(agent.toolCallHistory[0].name).toBe('file_read')
    })

    it('新 agent 应自动创建并附带 toolCallHistory', () => {
      store.agentStatuses = []

      store.handleToolCallStarted({
        agent_id: 'new-agent',
        agent_name: '新 Agent',
        tool_name: 'web_search'
      })

      const agent = store.agentStatuses.find(s => s.agent_id === 'new-agent')
      expect(agent).toBeDefined()
      expect(agent.toolCallHistory).toHaveLength(1)
    })

    it('多次调用应累积到 toolCallHistory', () => {
      store.agentStatuses = [{
        agent_id: 'cardiology-expert',
        agent_name: '心血管内科专家',
        status: 'pending',
        toolCallHistory: []
      }]

      store.handleToolCallStarted({
        agent_id: 'cardiology-expert',
        tool_name: 'file_read'
      })

      store.handleToolCallStarted({
        agent_id: 'cardiology-expert',
        tool_name: 'grep'
      })

      const agent = store.agentStatuses.find(s => s.agent_id === 'cardiology-expert')
      expect(agent.toolCallHistory).toHaveLength(2)
    })
  })

  describe('handleToolCallCompleted', () => {
    it('应更新 toolCallHistory 中工具状态并清除 currentTool', () => {
      store.agentStatuses = [{
        agent_id: 'cardiology-expert',
        agent_name: '心血管内科专家',
        status: 'running',
        currentTool: {
          name: 'file_read',
          params: {},
          startedAt: Date.now() - 1000,
          status: 'running'
        },
        toolCallHistory: [{
          name: 'file_read',
          params: {},
          startedAt: Date.now() - 1000,
          status: 'running'
        }]
      }]

      store.handleToolCallCompleted({
        agent_id: 'cardiology-expert',
        tool_name: 'file_read',
        tool_output_summary: 'File content loaded'
      })

      const agent = store.agentStatuses.find(s => s.agent_id === 'cardiology-expert')
      expect(agent.currentTool).toBeNull()
      expect(agent.toolCallHistory[0].status).toBe('completed')
      expect(agent.toolCallHistory[0].output).toBeUndefined()
      expect(agent.toolCallHistory[0].duration).toBeDefined()
    })

    it('无历史记录时应安全处理', () => {
      store.agentStatuses = [{
        agent_id: 'cardiology-expert',
        agent_name: '心血管内科专家',
        status: 'running',
        currentTool: null,
        toolCallHistory: []
      }]

      // 不应抛出异常
      store.handleToolCallCompleted({
        agent_id: 'cardiology-expert',
        tool_name: 'file_read'
      })

      const agent = store.agentStatuses.find(s => s.agent_id === 'cardiology-expert')
      expect(agent.toolCallHistory).toHaveLength(0)
    })
  })

  describe('task orchestration handlers', () => {
    it('subtask_started 应将对应子任务标记为 running', () => {
      store.agentStatuses = [{
        agent_id: 'research-agent',
        agent_name: '研究专家',
        status: 'running',
        decomposition: {
          subtasks: [
            { id: 'subtask_1', goal: '先读代码', status: 'pending', tools: [], result: '' },
            { id: 'subtask_2', goal: '写结论', status: 'pending', tools: [], result: '' }
          ],
          currentSubtaskId: 'subtask_1',
          currentSubtaskGoal: '先读代码'
        }
      }]

      store.handleSubtaskStarted({
        agent_id: 'research-agent',
        subtask_id: 'subtask_1',
        goal: '先读代码',
        tools: ['file_read']
      })

      const agent = store.agentStatuses.find(s => s.agent_id === 'research-agent')
      expect(agent.currentSubtaskId).toBe('subtask_1')
      expect(agent.decomposition.subtasks[0].status).toBe('running')
    })

    it('agent_result 应用后端返回的 decomposition 作为兜底状态', () => {
      store.agentStatuses = [{
        agent_id: 'research-agent',
        agent_name: '研究专家',
        status: 'running',
        decomposition: {
          subtasks: [
            { id: 'subtask_1', goal: '先读代码', status: 'pending', tools: [], result: '' }
          ],
          currentSubtaskId: 'subtask_1',
          currentSubtaskGoal: '先读代码'
        }
      }]

      store.handleAgentResult({
        agent_id: 'research-agent',
        agent_name: '研究专家',
        status: 'success',
        content: 'done',
        decomposition: {
          subtasks: [
            { id: 'subtask_1', goal: '先读代码', status: 'completed', tools: [], result: 'ok' },
            { id: 'subtask_2', goal: '写结论', status: 'completed', tools: [], result: 'done' }
          ]
        },
        progress_summary: {
          currentSubtaskId: null,
          currentSubtaskGoal: null,
          completedCount: 2,
          totalCount: 2,
        }
      })

      const agent = store.agentStatuses.find(s => s.agent_id === 'research-agent')
      expect(agent.status).toBe('completed')
      expect(agent.decomposition.subtasks).toHaveLength(2)
      expect(agent.decomposition.subtasks.every(s => s.status === 'completed')).toBe(true)
      expect(agent.decomposition.subtasks.every(s => s.result === '')).toBe(true)
      expect(agent.decomposition.completedCount).toBe(2)
    })

    it('subtask_result 只更新工具完成状态，不暴露中间摘要正文', () => {
      store.agentStatuses = [{
        agent_id: 'research-agent',
        agent_name: '研究专家',
        status: 'running',
        toolCallHistory: [{
          subtaskId: 'subtask_1',
          name: 'web_search',
          input: { query: '测试' },
          startedAt: Date.now() - 1000,
          status: 'running'
        }]
      }]

      store.handleSubtaskResult({
        agent_id: 'research-agent',
        subtask_id: 'subtask_1',
        result: '这是一段很长的中间工具摘要，不应进入前端展示',
        evidence: {
          evidence_id: 'ev_subtask_1_web_search_1',
          title: 'web_search: 测试',
          excerpt: '摘要'
        }
      })

      const agent = store.agentStatuses.find(s => s.agent_id === 'research-agent')
      expect(agent.toolCallHistory[0].status).toBe('completed')
      expect(agent.toolCallHistory[0].output).toBeUndefined()
      expect(agent.toolCallHistory[0].evidenceId).toBe('ev_subtask_1_web_search_1')
      expect(agent.toolCallHistory[0].duration).toBeDefined()
    })
  })
})
