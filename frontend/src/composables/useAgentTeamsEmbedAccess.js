import { computed, ref } from 'vue'
import { applyLocale, isSupportedLocale } from '@/locales'
import { formatMessageContent, extractQuestions } from '@/utils/messageContentFormatter'
import { consumeSSEStream } from '@/utils/sseConsumer'

const TERMINAL_STATES = new Set(['completed', 'failed', 'stopped'])
const INITIAL_POLL_DELAY_MS = 2000
const MAX_POLL_DELAY_MS = 10000
const SSE_RECONNECT_DELAY_MS = 3000
const SSE_HEARTBEAT_TIMEOUT_MS = 90000
const DECISION_STAGE_STATES = {
  intake: 'assessing',
  assessment: 'assessing',
  team_form: 'forming_team',
  execution: 'monitoring',
  review: 'monitoring',
  synthesis: 'summarizing',
  persistence: 'summarizing'
}

function extractMessageText(content) {
  if (typeof content === 'string') return content
  if (!content || typeof content !== 'object') return ''
  if (typeof content.text === 'string') return content.text
  if (typeof content.content === 'string') return content.content
  return ''
}

export function useAgentTeamsEmbedAccess({ token, leaderStore, t, locale, onSnapshot }) {
  const loading = ref(true)
  const error = ref('')
  const snapshotVersion = ref('')
  const answerEndpoint = computed(
    () => `/api/integrations/agentteams/embed-sessions/${currentToken()}/answers`
  )

  let pollTimer = null
  let reconnectTimer = null
  let pollDelay = INITIAL_POLL_DELAY_MS
  let activeRequest = null
  let eventRequest = null
  let disposed = false
  let generation = 0
  let referrerMeta = null
  let previousReferrerPolicy = null
  let referrerPolicyInstalled = false

  function currentToken() {
    return typeof token === 'function' ? token() : token
  }

  function currentState() {
    return leaderStore.leaderState || 'created'
  }

  function isTerminal() {
    return TERMINAL_STATES.has(currentState())
  }

  function isCurrent(requestGeneration) {
    return !disposed && requestGeneration === generation
  }

  function notifyParentStatus(status, version) {
    if (typeof window === 'undefined' || !window.parent) return
    window.parent.postMessage({
      type: 'agentteams:embed-status',
      status,
      version: version || ''
    }, '*')
  }

  function projectedSessionState(session) {
    const leaderState = session?.state || 'idle'
    if (TERMINAL_STATES.has(leaderState) || leaderState === 'questioning') return leaderState
    const decisionRun = session?.decision_run
    if (TERMINAL_STATES.has(decisionRun?.state)) return decisionRun.state
    return DECISION_STAGE_STATES[decisionRun?.current_stage] || leaderState
  }

  function findTeamConfig(messages, sessionId) {
    return [...messages].reverse().find(message => {
      const type = message.type || message.message_type
      return type === 'team_config' && message.leader_session_id === sessionId
    })?.content || {}
  }

  function executionOrderFromDag(dagPlan) {
    const order = {}
    let sequence = 0
    ;(dagPlan?.execution_batches || []).forEach((batch, batchIndex) => {
      ;(batch.agents || []).forEach((agentId, agentIndex) => {
        order[agentId] = { batchIndex, agentIndex, sequence: sequence++ }
      })
    })
    return order
  }

  function resetStore() {
    leaderStore.resetState()
    leaderStore.clearData()
  }

  function formatTime(message) {
    return message.created_at
      ? new Date(message.created_at).toLocaleTimeString(locale.value, {
          hour: '2-digit',
          minute: '2-digit'
        })
      : ''
  }

  function applySnapshot(data, requestGeneration) {
    if (!isCurrent(requestGeneration)) return
    const sessions = data.sessions || []
    const messages = data.messages || []
    const originalUserMessage = messages.find(message => {
      const messageType = message.type || message.message_type
      return messageType === 'user'
    })
    const latestSession = sessions[sessions.length - 1]
    const snapshotLocale = data.locale || latestSession?.locale
    if (isSupportedLocale(snapshotLocale)) {
      locale.value = snapshotLocale
      applyLocale(snapshotLocale)
    }

    onSnapshot({
      conversationId: data.conversation?.id ? String(data.conversation.id) : '',
      leaderSessionId: latestSession?.id ? String(latestSession.id) : '',
      userQuestion: extractMessageText(originalUserMessage?.content) || data.conversation?.title || '',
      firstUserMessage: originalUserMessage || null,
      userMessageId: originalUserMessage?.id || null
    })

    if (!latestSession) return

    leaderStore.leaderState = projectedSessionState(latestSession)
    notifyParentStatus(leaderStore.leaderState, data.version)
    leaderStore.resultsReconciled = TERMINAL_STATES.has(leaderStore.leaderState)
    leaderStore.currentSession = { id: latestSession.id }
    leaderStore.totalTime = latestSession.started_at && latestSession.completed_at
      ? Math.max(0, new Date(latestSession.completed_at) - new Date(latestSession.started_at))
      : 0

    const agentResults = latestSession.agent_results || []
    const agentProgress = data.agent_progress || []
    const toolCalls = (data.tool_calls || []).filter(
      call => call.leader_session_id === latestSession.id,
    )
    const teamConfig = findTeamConfig(messages, latestSession.id)
    const agentDetails = teamConfig.agent_details || []
    const dagPlan = teamConfig.dag_plan || teamConfig.dag_execution_plan || {}
    const fallbackAgents = agentResults.length
      ? agentResults.map(result => ({
          agent_id: result.agent_id,
          agent_name: result.agent_name || result.agent_id,
          leader_session_id: latestSession.id
        }))
      : agentProgress.map(progress => ({
          agent_id: progress.agent_id,
          agent_name: progress.agent_name || progress.agent_id,
          leader_session_id: latestSession.id
        }))
    leaderStore.selectedAgents = agentDetails.length
      ? agentDetails.map(agent => ({ ...agent, leader_session_id: latestSession.id }))
      : latestSession.selected_agents?.length
        ? latestSession.selected_agents.map(agent => ({
            agent_id: agent,
            agent_name: agent,
            leader_session_id: latestSession.id
          }))
      : fallbackAgents

    leaderStore.agentResults = agentResults.map(result => ({
      ...result,
      success: result.status === 'success' || result.status === 'completed'
    }))
    const resultsByAgent = new Map(agentResults.map(result => [result.agent_id, result]))
    const progressByAgent = new Map(agentProgress.map(progress => [progress.agent_id, progress]))
    const toolsByAgent = new Map()
    toolCalls.forEach(call => {
      const history = toolsByAgent.get(call.agent_id) || []
      history.push({
        name: call.tool_name,
        params: call.tool_input || {},
        status: call.status === 'success' ? 'completed' : 'failed',
        duration: call.execution_time,
        completedAt: call.created_at,
      })
      toolsByAgent.set(call.agent_id, history)
    })
    const executionOrder = executionOrderFromDag(dagPlan)
    const incompleteBatch = leaderStore.leaderState === 'monitoring'
      ? Math.min(...leaderStore.selectedAgents
          .filter(agent => !resultsByAgent.has(agent.agent_id))
          .map(agent => executionOrder[agent.agent_id]?.batchIndex)
          .filter(Number.isInteger), Infinity)
      : Infinity
    leaderStore.agentStatuses = leaderStore.selectedAgents.map(agent => {
      const result = resultsByAgent.get(agent.agent_id)
      const progress = progressByAgent.get(agent.agent_id)
      const isRunning = executionOrder[agent.agent_id]?.batchIndex === incompleteBatch
      return {
        ...agent,
        status: result
          ? (result.status === 'success' || result.status === 'completed' ? 'completed' : 'failed')
          : (progress?.status || (isRunning ? 'running' : 'pending')),
        message: result
          ? (result.status === 'success' || result.status === 'completed'
              ? t('leader.runtime.executionCompleted')
              : result.error)
          : '',
        decomposition: result?.decomposition || progress?.decomposition,
        currentSubtaskId: progress?.currentSubtaskId || progress?.decomposition?.currentSubtaskId,
        currentSubtaskGoal: progress?.currentSubtaskGoal || progress?.decomposition?.currentSubtaskGoal,
        content: result?.content || progress?.content || '',
        summary: result?.summary || progress?.summary || null,
        structured_report: result?.structured_report || progress?.structured_report || null,
        evidence_map: result?.evidence_map || progress?.evidence_map || [],
        content_locale: result?.content_locale || progress?.content_locale || null,
        tool_calls: result?.tool_calls || progress?.tool_calls,
        tokens_used: result?.tokens_used || progress?.tokens_used,
        execution_time: result?.execution_time || progress?.execution_time,
        toolCallHistory: toolsByAgent.get(agent.agent_id) || []
      }
    })
    leaderStore.agentExecutionOrder = Object.keys(executionOrder).length
      ? executionOrder
      : Object.fromEntries(leaderStore.selectedAgents.map((agent, index) => [agent.agent_id, {
          batchIndex: 0,
          agentIndex: index,
          sequence: index
        }]))
    leaderStore.finalReport = latestSession.final_report || ''
    leaderStore.sessions = sessions.map(session => ({
      ...session,
      final_report: session.final_report
    }))
    leaderStore.historicalMessages = messages.map(message => {
      const messageType = message.type || message.message_type
      const normalized = {
        id: message.id,
        content: formatMessageContent(message.content, messageType, message.content_locale),
        rawContent: message.content,
        time: formatTime(message),
        type: messageType,
        content_locale: message.content_locale,
        leader_session_id: message.leader_session_id
      }
      if (messageType !== 'question') return normalized
      const questions = extractQuestions(message.content)
      return questions ? { ...normalized, questions } : normalized
    })
    leaderStore.restorePendingQuestions(latestSession, messages)
  }

  function stopPolling() {
    if (!pollTimer) return
    clearTimeout(pollTimer)
    pollTimer = null
  }

  function stopEventStream() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    eventRequest?.abort()
    eventRequest = null
  }

  function schedulePoll(requestGeneration = generation) {
    stopPolling()
    if (!isCurrent(requestGeneration) || isTerminal()) return
    pollTimer = setTimeout(async () => {
      await loadStatus(requestGeneration)
      if (!isCurrent(requestGeneration) || error.value) return
      pollDelay = Math.min(Math.round(pollDelay * 1.5), MAX_POLL_DELAY_MS)
      schedulePoll(requestGeneration)
    }, pollDelay)
  }

  async function loadSession({ background = false, requestGeneration = generation } = {}) {
    if (!isCurrent(requestGeneration)) return
    if (!background) loading.value = true
    error.value = ''
    activeRequest?.abort()
    const request = new AbortController()
    activeRequest = request
    try {
      const response = await fetch(
        `/api/integrations/agentteams/embed-sessions/${currentToken()}`,
        { signal: request.signal }
      )
      if (!isCurrent(requestGeneration)) return
      const data = await response.json().catch(() => ({}))
      if (!isCurrent(requestGeneration)) return
      if (!response.ok) {
        throw new Error(data?.detail?.message || data?.message || t('leader.runtime.embedAccessDenied'))
      }
      snapshotVersion.value = data.version || ''
      applySnapshot(data, requestGeneration)
    } catch (requestError) {
      if (requestError.name === 'AbortError') return
      if (!isCurrent(requestGeneration)) return
      error.value = requestError.message || t('leader.runtime.embedLoadFailed')
      stopPolling()
    } finally {
      if (activeRequest === request) activeRequest = null
      if (!background && isCurrent(requestGeneration)) loading.value = false
    }
  }

  async function loadStatus(requestGeneration = generation) {
    if (!isCurrent(requestGeneration)) return
    error.value = ''
    activeRequest?.abort()
    const request = new AbortController()
    activeRequest = request
    try {
      const response = await fetch(
        `/api/integrations/agentteams/embed-sessions/${currentToken()}/status`,
        { signal: request.signal }
      )
      if (!isCurrent(requestGeneration)) return
      const data = await response.json().catch(() => ({}))
      if (!isCurrent(requestGeneration)) return
      if (!response.ok) {
        throw new Error(data?.detail?.message || data?.message || t('leader.runtime.embedAccessDenied'))
      }
      if (data.terminal || data.version !== snapshotVersion.value) {
        await loadSession({ background: true, requestGeneration })
      }
    } catch (requestError) {
      if (requestError.name === 'AbortError') return
      if (!isCurrent(requestGeneration)) return
      error.value = requestError.message || t('leader.runtime.embedLoadFailed')
      stopPolling()
    } finally {
      if (activeRequest === request) activeRequest = null
    }
  }

  function scheduleReconnect(requestGeneration = generation) {
    if (!isCurrent(requestGeneration) || isTerminal() || reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (isCurrent(requestGeneration)) void startEventStream(requestGeneration)
    }, SSE_RECONNECT_DELAY_MS)
  }

  async function startEventStream(requestGeneration = generation) {
    if (!isCurrent(requestGeneration) || isTerminal() || eventRequest) return

    const request = new AbortController()
    eventRequest = request
    let refreshChain = Promise.resolve()
    try {
      const response = await fetch(
        `/api/integrations/agentteams/embed-sessions/${currentToken()}/events`,
        {
          headers: { Accept: 'text/event-stream' },
          signal: request.signal
        }
      )
      if (!isCurrent(requestGeneration)) return
      stopPolling()
      await consumeSSEStream(response, data => {
        if (data.type !== 'embed_snapshot' || !isCurrent(requestGeneration)) return
        refreshChain = refreshChain.then(async () => {
          if (!isCurrent(requestGeneration)) return
          if (data.version !== snapshotVersion.value || data.terminal) {
            await loadSession({ background: true, requestGeneration })
          }
        })
      }, {
        signal: request.signal,
        heartbeatTimeout: SSE_HEARTBEAT_TIMEOUT_MS
      })
      await refreshChain
    } catch (streamError) {
      if (streamError.name !== 'AbortError' && isCurrent(requestGeneration)) {
        schedulePoll(requestGeneration)
      }
    } finally {
      if (eventRequest === request) eventRequest = null
    }

    if (isCurrent(requestGeneration) && !isTerminal()) {
      schedulePoll(requestGeneration)
      scheduleReconnect(requestGeneration)
    }
  }

  function installReferrerPolicy() {
    if (referrerPolicyInstalled) return
    referrerMeta = document.querySelector('meta[name="referrer"]')
    if (!referrerMeta) {
      referrerMeta = document.createElement('meta')
      referrerMeta.name = 'referrer'
      document.head.appendChild(referrerMeta)
    } else {
      previousReferrerPolicy = referrerMeta.content
    }
    referrerMeta.content = 'no-referrer'
    referrerPolicyInstalled = true
  }

  function restoreReferrerPolicy() {
    if (!referrerPolicyInstalled || !referrerMeta) return
    if (previousReferrerPolicy === null) referrerMeta.remove()
    else referrerMeta.content = previousReferrerPolicy
    referrerPolicyInstalled = false
    referrerMeta = null
    previousReferrerPolicy = null
  }

  async function start() {
    disposed = false
    const requestGeneration = ++generation
    stopPolling()
    stopEventStream()
    activeRequest?.abort()
    installReferrerPolicy()
    resetStore()
    await loadSession({ requestGeneration })
    if (isCurrent(requestGeneration) && !error.value && !isTerminal()) {
      void startEventStream(requestGeneration)
    }
  }

  async function retry() {
    disposed = false
    const requestGeneration = ++generation
    stopPolling()
    stopEventStream()
    activeRequest?.abort()
    pollDelay = INITIAL_POLL_DELAY_MS
    resetStore()
    await loadSession({ requestGeneration })
    if (isCurrent(requestGeneration) && !error.value && !isTerminal()) {
      void startEventStream(requestGeneration)
    }
  }

  function stop() {
    disposed = true
    generation += 1
    stopPolling()
    stopEventStream()
    activeRequest?.abort()
    restoreReferrerPolicy()
  }

  return {
    loading,
    error,
    answerEndpoint,
    start,
    stop,
    retry
  }
}
