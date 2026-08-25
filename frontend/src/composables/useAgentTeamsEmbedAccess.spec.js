import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useLeaderStore } from '@/stores/leader'
import { useAgentTeamsEmbedAccess } from './useAgentTeamsEmbedAccess'

const { consumeSSEStreamMock } = vi.hoisted(() => ({
  consumeSSEStreamMock: vi.fn(),
}))

vi.mock('@/utils/sseConsumer', () => ({
  consumeSSEStream: consumeSSEStreamMock,
}))

function deferred() {
  let resolve
  const promise = new Promise(resolvePromise => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function snapshot(id, state = 'completed', locale = 'zh-CN') {
  return {
    version: `${id}:${state}`,
    locale,
    conversation: { id, title: `Conversation ${id}` },
    sessions: [{
      id,
      state,
      agent_results: [],
      final_report: state === 'completed' ? { report: `Report ${id}` } : null,
    }],
    messages: [],
  }
}

function response(data) {
  return {
    ok: true,
    json: () => Promise.resolve(data),
  }
}

function createAccess(store, onSnapshot = vi.fn()) {
  const locale = { value: 'en-US' }
  return useAgentTeamsEmbedAccess({
    token: () => 'embed-token',
    leaderStore: store,
    t: key => key,
    locale,
    onSnapshot,
  })
}

describe('useAgentTeamsEmbedAccess request generations', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    consumeSSEStreamMock.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('does not apply an initial snapshot after stop', async () => {
    const pending = deferred()
    vi.stubGlobal('fetch', vi.fn(() => pending.promise))
    const store = useLeaderStore()
    const onSnapshot = vi.fn()
    const access = createAccess(store, onSnapshot)

    const starting = access.start()
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    access.stop()
    pending.resolve(response(snapshot(20)))
    await starting

    expect(onSnapshot).not.toHaveBeenCalled()
    expect(store.currentSession).toBeNull()
    expect(store.finalReport).toBe('')
  })

  it('does not let a queued refresh overwrite a retry generation', async () => {
    const oldRefresh = deferred()
    let detailRequestCount = 0
    vi.stubGlobal('fetch', vi.fn(url => {
      if (url.endsWith('/events')) {
        return Promise.resolve({ ok: true, body: {} })
      }
      detailRequestCount += 1
      if (detailRequestCount === 1) return Promise.resolve(response(snapshot(10, 'monitoring')))
      if (detailRequestCount === 2) return oldRefresh.promise
      return Promise.resolve(response(snapshot(30)))
    }))
    consumeSSEStreamMock.mockImplementation(async (_response, onMessage) => {
      onMessage({ type: 'embed_snapshot', version: '20:completed', terminal: true })
    })
    const store = useLeaderStore()
    const access = createAccess(store)

    await access.start()
    await vi.waitFor(() => expect(detailRequestCount).toBe(2))
    await access.retry()
    expect(store.currentSession).toEqual({ id: 30 })

    oldRefresh.resolve(response(snapshot(20)))
    await Promise.resolve()
    await Promise.resolve()

    expect(store.currentSession).toEqual({ id: 30 })
    expect(store.finalReport).toMatchObject({ report: 'Report 30' })
    access.stop()
  })

  it('applies the client locale from the embed snapshot', async () => {
    const postMessage = vi.spyOn(window, 'postMessage').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response(snapshot(20)))))
    const store = useLeaderStore()
    const locale = { value: 'en-US' }
    const access = useAgentTeamsEmbedAccess({
      token: () => 'embed-token',
      leaderStore: store,
      t: key => key,
      locale,
      onSnapshot: vi.fn(),
    })

    await access.start()

    expect(locale.value).toBe('zh-CN')
    expect(postMessage).toHaveBeenCalledWith({
      type: 'agentteams:embed-status',
      status: 'completed',
      version: '20:completed',
    }, '*')
    access.stop()
  })

  it('restores the durable decision stage and parallel DAG from team_config', async () => {
    const data = snapshot(40, 'assessing')
    data.sessions[0].decision_run = { state: 'running', current_stage: 'execution' }
    data.sessions[0].agent_results = [{
      agent_id: 'agent-a',
      agent_name: 'Agent A',
      status: 'success',
      content: 'done',
    }]
    data.messages = [{
      id: 1,
      type: 'team_config',
      leader_session_id: 40,
      content: {
        agent_details: [
          { agent_id: 'agent-a', agent_name: 'Agent A' },
          { agent_id: 'agent-b', agent_name: 'Agent B' },
          { agent_id: 'agent-c', agent_name: 'Agent C' },
        ],
        dag_plan: {
          execution_batches: [
            { agents: ['agent-a', 'agent-b'] },
            { agents: ['agent-c'] },
          ],
        },
      },
    }]
    data.tool_calls = [{
      id: 8,
      leader_session_id: 40,
      agent_id: 'agent-b',
      tool_name: 'web_search',
      tool_input: { query: 'guideline' },
      status: 'success',
      execution_time: 0.5,
      created_at: '2026-08-10T10:00:00Z',
    }]
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response(data))))
    const store = useLeaderStore()
    const access = createAccess(store)

    await access.start()

    expect(store.leaderState).toBe('monitoring')
    expect(store.selectedAgents.map(agent => agent.agent_name)).toEqual([
      'Agent A', 'Agent B', 'Agent C',
    ])
    expect(store.agentExecutionOrder['agent-a'].batchIndex).toBe(0)
    expect(store.agentExecutionOrder['agent-b'].batchIndex).toBe(0)
    expect(store.agentExecutionOrder['agent-c'].batchIndex).toBe(1)
    expect(Object.fromEntries(store.agentStatuses.map(agent => [agent.agent_id, agent.status]))).toEqual({
      'agent-a': 'completed',
      'agent-b': 'running',
      'agent-c': 'pending',
    })
    expect(store.agentStatuses.find(agent => agent.agent_id === 'agent-b').toolCallHistory).toEqual([{
      name: 'web_search',
      params: { query: 'guideline' },
      status: 'completed',
      duration: 0.5,
      completedAt: '2026-08-10T10:00:00Z',
    }])
    access.stop()
  })

  it('uses the complete Agent Teams prompt stored in a structured user message', async () => {
    const data = snapshot(41)
    const fullPrompt = '病人概况：\n' + '完整病历'.repeat(800) + '\n诊断要求：逐项分析'
    data.messages = [{
      id: 11,
      type: 'user',
      leader_session_id: null,
      content: { text: fullPrompt },
    }]
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response(data))))
    const onSnapshot = vi.fn()
    const access = createAccess(useLeaderStore(), onSnapshot)

    await access.start()

    expect(onSnapshot).toHaveBeenCalledWith(expect.objectContaining({
      userQuestion: fullPrompt,
    }))
    access.stop()
  })

  it('restores durable running subtask progress before the Agent result exists', async () => {
    const data = snapshot(42, 'monitoring')
    data.sessions[0].selected_agents = ['agent-a']
    data.agent_progress = [{
      agent_id: 'agent-a',
      agent_name: 'Agent A',
      status: 'running',
      currentSubtaskId: 'subtask-2',
      currentSubtaskGoal: '核对治疗方案',
      decomposition: {
        subtasks: [
          { id: 'subtask-1', goal: '整理病史', status: 'completed', tools: [] },
          { id: 'subtask-2', goal: '核对治疗方案', status: 'running', tools: ['web_search'] },
        ],
        completedCount: 1,
        totalCount: 2,
        currentSubtaskId: 'subtask-2',
        currentSubtaskGoal: '核对治疗方案',
      },
    }]
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response(data))))
    const store = useLeaderStore()
    const access = createAccess(store)

    await access.start()

    expect(store.agentStatuses[0]).toMatchObject({
      agent_id: 'agent-a',
      status: 'running',
      currentSubtaskId: 'subtask-2',
      decomposition: {
        completedCount: 1,
        totalCount: 2,
      },
    })
    expect(store.agentStatuses[0].decomposition.subtasks[1]).toMatchObject({
      goal: '核对治疗方案',
      status: 'running',
    })
    access.stop()
  })

  it('restores an individual Agent report before all Agent results are durable', async () => {
    const data = snapshot(43, 'monitoring')
    data.sessions[0].selected_agents = ['agent-a', 'agent-b']
    data.agent_progress = [{
      agent_id: 'agent-a',
      agent_name: 'Agent A',
      status: 'completed',
      report_ready: true,
      content: 'Agent A 的实时完整报告',
      summary: { one_sentence: 'Agent A 结论' },
      decomposition: {
        subtasks: [{ id: 'subtask-1', goal: '分析', status: 'completed', tools: [] }],
        completedCount: 1,
        totalCount: 1,
      },
    }]
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response(data))))
    const store = useLeaderStore()
    const access = createAccess(store)

    await access.start()

    expect(store.agentResults).toEqual([])
    expect(store.agentStatuses.find(agent => agent.agent_id === 'agent-a')).toMatchObject({
      status: 'completed',
      content: 'Agent A 的实时完整报告',
      summary: { one_sentence: 'Agent A 结论' },
    })
    expect(store.agentStatuses.find(agent => agent.agent_id === 'agent-b').status).toBe('pending')
    access.stop()
  })

  it('asks the parent to renew an expired embed token', async () => {
    const postMessage = vi.spyOn(window, 'postMessage').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: { message: 'expired' } }),
    })))
    const access = createAccess(useLeaderStore())

    await access.start()

    expect(postMessage).toHaveBeenCalledWith({
      type: 'agentteams:embed-renew-required',
    }, '*')
    access.stop()
  })

  it('uses localized fallback text when the embed response has no message', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: false,
      status: 500,
      json: () => Promise.resolve({}),
    })))
    const locale = { value: 'en-US' }
    const access = useAgentTeamsEmbedAccess({
      token: () => 'embed-token',
      leaderStore: useLeaderStore(),
      t: key => ({
        'leader.runtime.embedAccessDenied': 'Localized access error',
        'leader.runtime.embedLoadFailed': 'Localized load error',
      })[key],
      locale,
      onSnapshot: vi.fn(),
    })

    await access.start()

    expect(access.error.value).toBe('Localized access error')
    access.stop()
  })
})
