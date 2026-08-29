import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/utils/api'
import { formatMessageContent, extractQuestions } from '@/utils/messageContentFormatter'
import { consumeSSEStream } from '@/utils/sseConsumer'
import { i18n } from '@/locales'

const LEADER_STREAM_TIMEOUT = 60 * 60 * 1000  // 60 分钟
const LEADER_HEARTBEAT_TIMEOUT = 3 * 60 * 1000

function formatLeaderTime(value = Date.now()) {
  return new Date(value).toLocaleTimeString(i18n.global.locale.value, {
    hour: '2-digit',
    minute: '2-digit'
  })
}

function leaderText(key, params) {
  return i18n.global.t(`leader.runtime.${key}`, params)
}

export const useLeaderStore = defineStore('leader', () => {
  // 新的消息列表结构
  const sessions = ref([])          // LeaderSession 列表
  const messages = ref([])          // LeaderMessage 列表
  const isLoading = ref(false)
  const error = ref(null)

  // State
  const currentSession = ref(null)
  const leaderState = ref('idle')
  const thinkingContent = ref('')
  const currentPhase = ref('')
  const leaderPhases = computed(() => [
    { id: 'assessing', name: i18n.global.t('conversation.display.states.assessing') },
    { id: 'forming_team', name: i18n.global.t('conversation.display.states.forming_team') },
    { id: 'monitoring', name: i18n.global.t('conversation.display.states.monitoring') },
    { id: 'summarizing', name: i18n.global.t('conversation.display.states.summarizing') }
  ])

  const teamCandidates = ref([])
  const selectedAgents = ref([])
  const agentStatuses = ref([])
  const agentResults = ref([])
  const finalReport = ref('')
  const resultsReconciled = ref(false)

  // 团队分析内容
  const teamAnalysis = ref('')
  const teamStrategy = ref('')

  const totalTime = ref(0)
  const totalTokens = ref(0)
  const stopRequested = ref(false)

  const retryCount = ref(0)
  const MAX_RETRIES = 3
  const _sessionActive = ref(false)  // 防重入锁
  const _questionAsked = ref(false)  // 问题去重
  let _abortController = null  // 中断 submitAnswers 的 SSE 流（追问弹出时提前结束）
  let _executionAbortController = null
  let _executionGeneration = 0

  function invalidateExecution() {
    _executionGeneration += 1
    _executionAbortController?.abort()
    _executionAbortController = null
    _sessionActive.value = false
  }

  function beginExecution() {
    const generation = _executionGeneration
    const controller = new AbortController()
    _executionAbortController = controller
    _sessionActive.value = true
    return {
      controller,
      generation,
      isCurrent: () => (
        generation === _executionGeneration &&
        !controller.signal.aborted
      )
    }
  }

  function captureExecution() {
    if (!_executionAbortController || _executionAbortController.signal.aborted) {
      _executionAbortController = new AbortController()
    }
    const controller = _executionAbortController
    const generation = _executionGeneration
    return {
      controller,
      generation,
      isCurrent: () => (
        generation === _executionGeneration &&
        !controller.signal.aborted
      )
    }
  }

  // 实时计时器
  const sessionStartTime = ref(null)
  const sessionTimer = ref(null)

  // 历史消息记录（用于恢复显示）
  const historicalMessages = ref([])

  // 待启动会话的数据（用于页面跳转时传递参数，避免暴露在 URL 中）
  const pendingSessionData = ref(null)

  // 当前追问问题（结构化数组）
  const currentQuestions = ref([])
  const agentExecutionOrder = ref({})

  // Computed
  const isLeaderMode = computed(() => {
    return leaderState.value !== 'idle' && leaderState.value !== 'completed'
  })

  const isActive = computed(() => {
    return ['assessing', 'forming_team', 'monitoring', 'summarizing'].includes(leaderState.value)
  })

  // Actions
  function resetState() {
    invalidateExecution()
    currentSession.value = null
    leaderState.value = 'idle'
    thinkingContent.value = ''
    currentPhase.value = ''
    teamCandidates.value = []
    selectedAgents.value = []
    agentStatuses.value = []
    agentResults.value = []
    finalReport.value = ''
    resultsReconciled.value = false
    totalTime.value = 0
    totalTokens.value = 0
    stopRequested.value = false
    retryCount.value = 0
    if (_abortController) {
      _abortController.abort()
      _abortController = null
    }
    historicalMessages.value = []
    messages.value = []
    _questionAsked.value = false
    currentQuestions.value = []
    agentExecutionOrder.value = {}
    teamAnalysis.value = ''
    teamStrategy.value = ''

    // 清除计时器
    if (sessionTimer.value) {
      clearInterval(sessionTimer.value)
      sessionTimer.value = null
    }
    sessionStartTime.value = null
  }

  /**
   * 启动实时计时器
   */
  function startTimer() {
    // 先清除已有计时器
    if (sessionTimer.value) {
      clearInterval(sessionTimer.value)
    }

    sessionStartTime.value = Date.now()
    totalTime.value = 0

    // 每秒更新一次
    sessionTimer.value = setInterval(() => {
      if (sessionStartTime.value) {
        // 统一约定：totalTime 一律为毫秒（消费端 formattedTime 再 /1000，
        // 分享/嵌入恢复路径也产毫秒；此前此处置秒导致属主视图显示 0秒）
        totalTime.value = Math.max(0, Date.now() - sessionStartTime.value)
      }
    }, 1000)
  }

  /**
   * 停止计时器
   */
  function stopTimer() {
    if (sessionTimer.value) {
      clearInterval(sessionTimer.value)
      sessionTimer.value = null
    }
  }

  /**
   * 启动 Leader 会话（带重连机制）
   */
  async function startLeaderSessionWithRetry(conversationId, message, context = {}) {
    let attempts = 0
    retryCount.value = 0
    while (true) {
      try {
        await startLeaderSession(conversationId, message, [], context)
        return
      } catch (error) {
        retryCount.value = attempts
        if (!isNetworkError(error) || attempts >= MAX_RETRIES) {
          throw error
        }
        attempts++
        retryCount.value = attempts
        await new Promise(resolve => setTimeout(resolve, 1000 * attempts))
      }
    }
  }

  /**
   * 判断是否为网络错误
   */
  function isNetworkError(error) {
    return (
      error.name === 'TypeError' ||
      error.message.includes('network') ||
      error.message.includes('Network') ||
      error.message.includes('Failed to fetch')
    )
  }

  async function startLeaderSession(
    conversationId,
    message,
    fileIds = [],
    context = {},
    generationLocale = i18n.global.locale.value
  ) {
    // 防重入：避免组件双重挂载导致重复请求
    if (_sessionActive.value) {
      console.warn('[Leader] Session already active, skipping duplicate startLeaderSession')
      return
    }
    resetState()
    const execution = beginExecution()

    // 启动实时计时器
    startTimer()

    try {
      // 使用 Fetch API 发送 POST 请求并接收 SSE 流
      const response = await fetch('/api/leader/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: message,
          file_ids: fileIds,
          context: context,
          locale: generationLocale
        }),
        signal: execution.controller.signal
      })

      if (!execution.isCurrent()) return

      // 总超时定时器（60 分钟）
      const totalTimer = setTimeout(() => {
        if (!execution.isCurrent()) return
        console.error('[SSE] Stream total timeout (60 minutes)')
        // 先中止底层流：否则迟到的 SSE 事件会在 failed 态后继续到达并翻转状态
        execution.controller.abort()
        handleError({ message: leaderText('requestTimeout') })
      }, LEADER_STREAM_TIMEOUT)

      try {
        await consumeSSEStream(response, (data) => {
          if (execution.isCurrent()) {
            handleSSEMessage({ data }, { execution })
          }
        }, {
          signal: execution.controller.signal,
          heartbeatTimeout: LEADER_HEARTBEAT_TIMEOUT,
          on401: () => {
            if (!execution.isCurrent()) return
            _sessionActive.value = false
            handleError({ message: leaderText('authExpired') })
          }
        })

        // SSE 流结束后，检测是否异常断连
        // 如果 leaderState 不在终态，说明 SSE 可能提前断开，后台任务可能仍在运行
        if (execution.isCurrent() && currentSession.value &&
            !['completed', 'failed', 'stopped', 'questioning', 'idle'].includes(leaderState.value)) {
          await recoverFromDisconnect(currentSession.value.id, execution)
        }
      } finally {
        clearTimeout(totalTimer)
      }
    } catch (error) {
      if (error?.name === 'AbortError' || !execution.isCurrent()) return
      console.error('Leader session failed:', error)
      _sessionActive.value = false
      handleError({
        message: error.message || leaderText('startFailed')
      })
      throw error
    }
  }

  async function applyTemplateSession(
    templateId,
    conversationId,
    message,
    fileIds = [],
    generationLocale = i18n.global.locale.value
  ) {
    if (_sessionActive.value) {
      console.warn('[Leader] Session already active, skipping applyTemplateSession')
      return
    }
    resetState()
    const execution = beginExecution()
    startTimer()

    try {
      const response = await fetch(`/api/workflow-templates/${templateId}/apply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: message,
          file_ids: fileIds || [],
          locale: generationLocale,
        }),
        signal: execution.controller.signal
      })

      if (!execution.isCurrent()) return

      const totalTimer = setTimeout(() => {
        if (!execution.isCurrent()) return
        console.error('[SSE] Template stream total timeout (60 minutes)')
        // 先中止底层流：否则迟到的 SSE 事件会在 failed 态后继续到达并翻转状态
        execution.controller.abort()
        handleError({ message: leaderText('requestTimeout') })
      }, LEADER_STREAM_TIMEOUT)

      try {
        await consumeSSEStream(response, (data) => {
          if (execution.isCurrent()) {
            handleSSEMessage({ data }, { execution })
          }
        }, {
          signal: execution.controller.signal,
          heartbeatTimeout: LEADER_HEARTBEAT_TIMEOUT,
          on401: () => {
            if (!execution.isCurrent()) return
            _sessionActive.value = false
            handleError({ message: leaderText('authExpired') })
          }
        })

        // SSE 流结束后，检测是否异常断连
        if (execution.isCurrent() && currentSession.value &&
            !['completed', 'failed', 'stopped', 'questioning', 'idle'].includes(leaderState.value)) {
          await recoverFromDisconnect(currentSession.value.id, execution)
        }
      } finally {
        clearTimeout(totalTimer)
      }
    } catch (error) {
      if (error?.name === 'AbortError' || !execution.isCurrent()) return
      console.error('Template session failed:', error)
      _sessionActive.value = false
      handleError({ message: error.message || leaderText('templateStartFailed') })
      throw error
    }
  }

  function handleSSEMessage(event, { reconcileOnDone = true, execution = null } = {}) {
    if (execution && !execution.isCurrent()) return
    const data = event.data

    if (!data || !data.type) {
      console.warn('Invalid SSE message format:', data)
      return
    }



    // 在收到第一个 SSE 事件时，立即更新用户消息
    // 这样 LeaderExecutionView 就能立即显示
    if (data.session_id && !currentSession.value) {
      currentSession.value = { id: data.session_id }

      // 触发一个自定义事件，通知 Chat.vue 更新用户消息
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('leader-session-started', {
          detail: { sessionId: data.session_id }
        }))
      }
    }

    // 将 SSE 事件同步写入 messages，供实时渲染
    const sseTypeToMessageType = {
      leader_thinking: 'progress',
      assessment_result: 'assessment',
      leader_question: 'question',
      team_forming: 'progress',
      team_ready: 'team_config',
      team_start: 'progress',
      agent_status: 'progress',
      agent_result: 'agent_result',
      agent_error: 'error',
      // tool_call_started/completed 不写入 messages，仅更新 agentStatuses.toolCallHistory
      // 避免在 LeaderThinking 中显示冗余的空"搜索结果"条目
      team_complete: 'progress',
      execution_status: 'progress',
      execution_complete: 'progress',
      leader_summarizing: 'progress',
      final_report: 'final_report',
      execution_stopped: 'error',
      error: 'error'
    }

    const messageType = sseTypeToMessageType[data.type]
    if (messageType) {
      // 保留原始 SSE 数据（rawContent），供模板结构化渲染；
      // content 使用格式化后的字符串，供 MarkdownRenderer 等场景使用。
      const formatted = formatMessageContent(data, messageType)
      const msg = {
        id: `sse-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: messageType,
        message_type: messageType,
        content: formatted,
        rawContent: data,
        content_locale: data.content_locale,
        leader_session_id: data.session_id || currentSession.value?.id,
        created_at: new Date().toISOString()
      }
      // question 类型：提取结构化问题数组，供弹窗和模板直接使用
      if (messageType === 'question' && data.questions) {
        msg.questions = data.questions
      }
      messages.value.push(msg)
    }

    switch (data.type) {
      case 'leader_thinking':
        handleLeaderThinking(data)
        break
      case 'assessment_result':
        handleAssessmentResult(data)
        break
      case 'leader_question':
        // 去重：同一会话只处理一次问题
        if (_questionAsked.value) {
          console.warn('[Leader] Duplicate leader_question ignored')
          break
        }
        _questionAsked.value = true
        handleLeaderQuestion(data)
        break
      case 'team_forming':
        handleTeamForming(data)
        break
      case 'team_ready':
        handleTeamReady(data)
        break
      case 'team_start':
        handleTeamStart(data)
        break
      case 'agent_status':
        handleAgentStatus(data)
        break
      case 'agent_result':
        handleAgentResult(data)
        break
      case 'agent_error':
        handleAgentError(data)
        break
      case 'tool_call_started':
        handleToolCallStarted(data)
        break
      case 'tool_call_completed':
        handleToolCallCompleted(data)
        break
      case 'team_complete':
        handleTeamComplete(data)
        break
      case 'execution_status':
        handleExecutionStatus(data)
        break
      case 'execution_complete':
        handleExecutionComplete(data)
        break
      case 'leader_summarizing':
        handleLeaderSummarizing(data)
        break
      case 'final_report':
        handleFinalReport(data)
        break
      case 'execution_stopped':
        handleExecutionStopped(data)
        break
      case 'api_retry':
        handleApiRetry(data)
        break
      // === 任务编排事件 ===
      case 'task_decomposition':
        handleTaskDecomposition(data)
        break
      case 'subtask_started':
        handleSubtaskStarted(data)
        break
      case 'subtool_call':
        handleSubtoolCall(data)
        break
      case 'subtask_result':
        handleSubtaskResult(data)
        break
      case 'subtask_completed':
        handleSubtaskCompleted(data)
        break
      case 'task_adjusted':
        handleTaskAdjusted(data)
        break
      case 'error':
        handleError(data)
        break
      case 'done':
        // 工作流完成，释放防重入锁
        _sessionActive.value = false
        if (reconcileOnDone && currentSession.value?.id) {
          void reconcilePersistedResults(currentSession.value.id, execution)
        }
        break
      default:
        console.warn('Unknown SSE event type:', data.type)
    }
  }

  async function stopExecution() {
    if (!currentSession.value) {
      console.warn('No active session to stop')
      return
    }

    try {
      stopRequested.value = true
      await api.post('/api/leader/stop', {
        session_id: currentSession.value.id
      })
    } catch (error) {
      stopRequested.value = false
      console.error('Stop execution failed:', error)
      throw error
    }
  }

  // Event Handlers
  function handleLeaderThinking(data) {
    // 不覆盖 'questioning' 状态 —— 对话框打开期间保持不变
    if (leaderState.value !== 'questioning') {
      leaderState.value = data.phase || leaderState.value
    }
    currentPhase.value = data.phase || currentPhase.value
    thinkingContent.value = data.content || ''
  }

  function handleAssessmentResult(data) {
    currentSession.value = { id: data.session_id }

    // assessment_result 是评估的唯一事件；同步到实时思考区，历史与实时共用同一格式。
    thinkingContent.value = formatMessageContent(data, 'assessment', data.content_locale)

    // 不在此处覆盖 leaderState —— 状态由后续 SSE 事件驱动：
    // - 需要补充信息 → leader_question 事件设置 'questioning'
    // - 直接通过 → team_forming 事件设置 'forming_team'
    // 避免评估未通过时错误跳到 'forming_team'

  }

  function attachQuestionLocale(questions, contentLocale) {
    if (!contentLocale) return questions
    return questions.map(question => (
      typeof question === 'object' && question !== null
        ? { ...question, content_locale: question.content_locale || contentLocale }
        : question
    ))
  }

  function handleLeaderQuestion(data) {

    if (data.session_id) {
      currentSession.value = { id: data.session_id }
    }

    leaderState.value = 'questioning'

    // 直接存储结构化问题数组（不做 JSON.stringify 转换）
    if (data.questions && data.questions.length > 0) {
      currentQuestions.value = attachQuestionLocale(data.questions, data.content_locale)

      // 将问题文本写入 thinkingContent，供 LeaderThinking 实时渲染
      const questionText = `## ${leaderText('followupHeading')}\n\n` +
        data.questions.map((q, i) => {
          const text = typeof q === 'string' ? q : (q?.question || String(q))
          return `${i + 1}. ${text}`
        }).join('\n\n')
      thinkingContent.value = questionText
    }


    // 新一轮追问已弹出，中断 submitAnswers 的 SSE 流，避免 handleSubmit 在流结束后关闭 dialog
    if (_abortController) {
      _abortController.abort()
      _abortController = null
    }
  }

  function handleTeamForming(data) {
    leaderState.value = 'forming_team'
    currentPhase.value = 'forming_team'

    // 处理不同阶段的 team_forming 事件
    if (data.phase === 'analyzing') {
      // 正在分析需求阶段
      const content = typeof data.content === 'object' ? (data.content.text || '') : data.content
      thinkingContent.value = content || leaderText('analyzingTeam')
    } else if (data.phase === 'selection_complete') {
      // selection_complete: data.content 可能是纯文本字符串、JSON 字符串或结构化对象
      // 结构化对象: {analysis, selected_agents, team_strategy}
      let teamStrategyText = ''
      let agents = []
      let analysisText = ''

      // 解析 content（可能是对象、JSON 字符串或纯文本）
      let contentObj = data.content
      if (typeof contentObj === 'string') {
        try {
          const trimmed = contentObj.trim()
          if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
            contentObj = JSON.parse(trimmed)
          }
        } catch {
          // 非 JSON 字符串，保持原样
        }
      }

      if (typeof contentObj === 'object' && contentObj !== null) {
        // 结构化对象格式
        analysisText = contentObj.analysis || ''
        teamStrategyText = contentObj.team_strategy || ''
        agents = contentObj.selected_agents || []
      } else {
        // 纯文本格式
        teamStrategyText = typeof contentObj === 'string' ? contentObj : ''
        agents = data.selected_agents || []
      }

      if (analysisText) {
        teamAnalysis.value = analysisText
      }

      // 构建展示内容
      let displayContent = ''
      if (analysisText) {
        displayContent += `## ${leaderText('requirementAnalysisHeading')}\n${analysisText}\n\n`
      }
      if (teamStrategyText) {
        teamStrategy.value = teamStrategyText
        displayContent += `## ${leaderText('teamStrategyHeading')}\n${teamStrategyText}\n\n`
      }

      if (agents.length > 0) {
        displayContent += `## ${leaderText('selectedExpertsHeading')}\n`
        agents.forEach((agent, index) => {
          displayContent += `${index + 1}. **${agent.agent_name || agent.name || agent.agent_id}** - ${agent.reason || ''}\n`
        })
      }

      thinkingContent.value = displayContent || leaderText('teamSelectionComplete')
    } else {
      // 其他情况（向后兼容）
      if (data.candidates) {
        teamCandidates.value = data.candidates
      }
      if (data.progress) {
        thinkingContent.value = data.progress
      }
    }
  }

  function handleTeamReady(data) {
    const executionOrder = {}
    const batches = data.team?.dag_plan?.execution_batches || []
    let sequence = 0
    batches.forEach((batch, batchIndex) => {
      ;(batch.agents || []).forEach((agentId, agentIndex) => {
        executionOrder[agentId] = {
          batchIndex,
          agentIndex,
          sequence: sequence++
        }
      })
    })
    agentExecutionOrder.value = executionOrder

    if (data.team && data.team.agents) {
      // 为每个 agent 添加 leader_session_id，优先使用 data.session_id
      selectedAgents.value = data.team.agents.map(agent => ({
        ...agent,
        leader_session_id: data.session_id || currentSession.value?.id
      }))
    }

    leaderState.value = 'monitoring'
    currentPhase.value = 'monitoring'

    // 构建团队信息显示
    let displayContent = `## ${leaderText('teamReadyHeading')}\n\n`

    if (data.team) {
      if (data.team.name) {
        displayContent += `**${leaderText('teamName')}**: ${data.team.name}\n\n`
      }
      if (data.team.description) {
        displayContent += `**${leaderText('teamDescription')}**: ${data.team.description}\n\n`
      }
      if (data.team.agents && data.team.agents.length > 0) {
        displayContent += `**${leaderText('teamMembers', { count: data.team.agents.length })}**:\n`
        data.team.agents.forEach((agent, index) => {
          displayContent += `${index + 1}. ${agent.agent_name}`
          if (agent.reason) {
            displayContent += ` - ${agent.reason}`
          }
          displayContent += '\n'
        })
      }
    }

    thinkingContent.value = displayContent
  }

  function handleTeamStart(data) {
    thinkingContent.value = leaderText('teamStarted', { count: data.total_agents })
  }

  function handleAgentStatus(data) {
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)

    const statusUpdate = {
      agent_id: data.agent_id,
      agent_name: data.agent_name,
      status: data.status,
      message: data.message,
      timestamp: data.timestamp || new Date().toISOString()
    }

    if (index >= 0) {
      // Merge: preserve toolCallHistory and currentTool from previous updates
      const existing = agentStatuses.value[index]
      agentStatuses.value[index] = {
        ...existing,
        ...statusUpdate,
        // Preserve tool data that may have been set by handleToolCallStarted/Completed
        toolCallHistory: existing.toolCallHistory || [],
        currentTool: existing.currentTool || null,
      }
    } else {
      agentStatuses.value.push(statusUpdate)
    }
  }

  function handleToolCallStarted(data) {
    // 更新对应 agent 的当前工具调用状态
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)
    const toolRecord = {
      name: data.tool_name,
      params: data.tool_input || {},
      startedAt: Date.now(),
      status: 'running',
    }

    if (index >= 0) {
      agentStatuses.value[index].currentTool = toolRecord
      agentStatuses.value[index].status = 'running'
      // 积累工具调用历史
      if (!agentStatuses.value[index].toolCallHistory) {
        agentStatuses.value[index].toolCallHistory = []
      }
      agentStatuses.value[index].toolCallHistory.push(toolRecord)
    } else {
      agentStatuses.value.push({
        agent_id: data.agent_id,
        agent_name: data.agent_name || data.agent_id,
        status: 'running',
        currentTool: toolRecord,
        toolCallHistory: [toolRecord],
      })
    }
  }

  function handleToolCallCompleted(data) {
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)
    if (index >= 0) {
      // 更新历史记录中对应工具的状态
      // 并行工具调用完成顺序不等于开始顺序，需匹配第一个 running 且同名的记录
      const history = agentStatuses.value[index].toolCallHistory
      if (history && history.length > 0) {
        const targetTool = history.find(
          h => h.status === 'running' && h.name === data.tool_name
        )
        if (targetTool) {
          targetTool.status = 'completed'
          targetTool.completedAt = Date.now()
          targetTool.duration = ((targetTool.completedAt - targetTool.startedAt) / 1000).toFixed(1)
        }
      }
      // 清除当前工具指示器（仅当没有其他 running 工具时）
      const hasRunning = history?.some(h => h.status === 'running')
      if (!hasRunning) {
        agentStatuses.value[index].currentTool = null
      }
    }
  }

  function handleAgentResult(data) {
    // 数据库格式：status 字段，转换为 success
    const result = {
      id: data.id || null,
      agent_id: data.agent_id,
      agent_name: data.agent_name,
      content: data.content,
      summary: data.summary || null,
      structured_report: data.structured_report || null,
      content_locale: data.content_locale || null,
      raw_tool_results: data.raw_tool_results || null,
      evidence_map: data.evidence_map || [],
      confidence: data.confidence,
      execution_time: data.execution_time,
      tool_calls: data.tool_calls || [],  // 新增：工具调用记录
      tokens_used: data.tokens_used || 0,  // 新增：令牌使用量
      success: data.status === 'success',  // 将 status 转换为 success
      leader_session_id: data.session_id || currentSession.value?.id  // 优先使用 data.session_id
    }

    agentResults.value.push(result)

    // 更新Agent状态
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)
    if (index >= 0) {
      const agent = agentStatuses.value[index]
      agent.status = 'completed'
      agent.message = leaderText('executionCompleted')
      if (data.decomposition?.subtasks) {
        const subtasks = sanitizeSubtasksForDisplay(data.decomposition.subtasks)
        const nextPending = subtasks.find(s => s.status === 'pending')
        agent.decomposition = {
          subtasks,
          currentSubtaskId: data.progress_summary?.currentSubtaskId || nextPending?.id || null,
          currentSubtaskGoal: data.progress_summary?.currentSubtaskGoal || nextPending?.goal || null,
          completedCount: data.progress_summary?.completedCount ?? subtasks.filter(s => s.status === 'completed' || s.status === 'skipped').length,
          totalCount: data.progress_summary?.totalCount ?? subtasks.length,
        }
      }
      agent.summary = data.summary || null
      agent.structured_report = data.structured_report || null
      agent.content_locale = data.content_locale || null
      agent.raw_tool_results = data.raw_tool_results || null
      agent.evidence_map = data.evidence_map || []
      agent.content = data.content
    } else {
      agentStatuses.value.push({
        agent_id: data.agent_id,
        agent_name: data.agent_name,
        status: 'completed',
        message: leaderText('executionCompleted'),
        content: data.content,
        summary: data.summary || null,
        structured_report: data.structured_report || null,
        content_locale: data.content_locale || null,
        raw_tool_results: data.raw_tool_results || null,
        evidence_map: data.evidence_map || [],
        timestamp: new Date().toISOString(),
        leader_session_id: data.session_id || currentSession.value?.id  // 优先使用 data.session_id
      })
    }
  }

  function handleAgentError(data) {
    // 数据库格式：status 字段，转换为 success
    const result = {
      agent_id: data.agent_id,
      agent_name: data.agent_name,
      error: data.error,
      content: data.content || data.error || leaderText('executionFailed'),  // 保留 content 供展开视图展示
      success: false,  // 错误即为失败
      leader_session_id: data.session_id || currentSession.value?.id  // 优先使用 data.session_id
    }

    agentResults.value.push(result)

    // 更新Agent状态
    const errorMessage = data.error || data.content || leaderText('executionFailed')
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)
    if (index >= 0) {
      agentStatuses.value[index].status = 'failed'
      agentStatuses.value[index].message = errorMessage
    } else {
      agentStatuses.value.push({
        agent_id: data.agent_id,
        agent_name: data.agent_name,
        status: 'failed',
        message: errorMessage,
        timestamp: new Date().toISOString(),
        leader_session_id: data.session_id || currentSession.value?.id  // 优先使用 data.session_id
      })
    }
  }

  function handleTeamComplete(data) {
    thinkingContent.value = leaderText('teamComplete', {
      successful: data.successful,
      failed: data.failed,
      total: data.total_agents
    })
  }

  function handleExecutionStatus(data) {
    thinkingContent.value = data.content || leaderText('executing')
  }

  function handleExecutionComplete(data) {
    if (data.results) {
      agentResults.value = data.results.agent_results || []
      totalTokens.value = data.results.total_tokens || 0
    }

    leaderState.value = 'summarizing'
    currentPhase.value = 'summarizing'
  }

  function handleLeaderSummarizing(data) {
    leaderState.value = 'summarizing'
    currentPhase.value = 'summarizing'
    thinkingContent.value = data.content || leaderText('summarizing')
  }

  function handleFinalReport(data) {
    // 停止计时器（使用后端返回的精确时间）
    stopTimer()

    finalReport.value = data.id
      ? {
          id: data.id,
          report: data.report || '',
          content_locale: data.content_locale || null,
          summary: data.summary || data.executive_summary || null,
          structured_report: data.structured_report || null,
          evidence_map: data.evidence_map || [],
          rating: data.rating || null,
          rating_comment: data.rating_comment || null,
          rating_updated_at: data.rating_updated_at || null
        }
      : data.report || ''
    totalTime.value = (data.total_time || 0) * 1000
    // 停止请求触发的最终报告（跳过 LLM 生成）应显示为"已停止"，而非"已完成"
    leaderState.value = data.quality_status === 'stopped' ? 'stopped' : 'completed'

    // 清空思考内容
    thinkingContent.value = ''
  }

  function handleExecutionStopped(data) {
    // 停止计时器
    stopTimer()

    leaderState.value = 'stopped'
    thinkingContent.value = data.message || leaderText('stopped')
  }

  function handleError(data) {
    // 停止计时器
    stopTimer()

    console.error('Leader error:', data.message)
    leaderState.value = 'failed'
    thinkingContent.value = data.message || leaderText('genericError')
    _sessionActive.value = false
  }

  /**
   * SSE 断连恢复：轮询等待后台任务完成
   *
   * 当 SSE 连接意外断开（超时或客户端断连）时，后台任务可能仍在运行。
   * 此函数通过轮询 /status/{session_id} 等待任务完成，并恢复最终结果。
   *
   * @param {number} sessionId - Leader 会话 ID
   */
  async function recoverFromDisconnect(sessionId, execution = null) {

    const POLL_INTERVAL = 3000  // 3 秒
    const MAX_POLLS = 1200      // 最多轮询 60 分钟（3s * 1200）

    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise(r => setTimeout(r, POLL_INTERVAL))
      if (execution && !execution.isCurrent()) return false

      try {
        const token = localStorage.getItem('token')
        const resp = await fetch(`/api/leader/status/${sessionId}`, {
          headers: { 'Authorization': `Bearer ${token}` },
          signal: execution?.controller.signal
        })

        if (execution && !execution.isCurrent()) return false

        if (!resp.ok) {
          console.warn(`[Leader] Poll failed with status ${resp.status}`)
          continue
        }

        const data = await resp.json()
        if (execution && !execution.isCurrent()) return false

        if (data.state === 'completed') {
          // 任务已完成，加载结果
          await reconcilePersistedResults(sessionId, execution)
          return
        }

        if (data.state === 'failed') {
          console.error('[Leader] Background task failed')
          handleError({ message: data.error_message || leaderText('taskFailed') })
          return
        }

        if (data.state === 'stopped') {
          handleExecutionStopped({ message: leaderText('stopped') })
          return
        }

        if (!data.is_running) {
          // 任务不在运行且不在终态 — 异常情况
          console.error('[Leader] Task not running and not in terminal state')
          handleError({ message: leaderText('interrupted') })
          return
        }

        // 仍在运行，更新进度提示
        if (i % 10 === 0) {
          thinkingContent.value = leaderText('backgroundRunning', {
            seconds: Math.floor(i * POLL_INTERVAL / 1000)
          })
        }
      } catch (err) {
        if (err?.name === 'AbortError' || (execution && !execution.isCurrent())) {
          return false
        }
        console.warn('[Leader] Poll request failed:', err)
        // 继续轮询，瞬态错误不中断
      }
    }

    // 轮询超时
    console.error('[Leader] Poll timeout reached')
    handleError({ message: leaderText('recoveryTimeout') })
  }

  /**
   * 从 DB 加载完整结果并恢复前端状态
   */
  async function _fetchAndRestoreResults(sessionId, execution = null) {
    try {
      if (execution && !execution.isCurrent()) return false
      const token = localStorage.getItem('token')
      // 使用 /status/{session_id} 端点，返回完整数据（agent_results + final_report）
      const resp = await fetch(`/api/leader/status/${sessionId}?include_results=true`, {
        headers: { 'Authorization': `Bearer ${token}` },
        signal: execution?.controller.signal
      })

      if (execution && !execution.isCurrent()) return false

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`)
      }

      const data = await resp.json()
      if (execution && !execution.isCurrent()) return false

      // 恢复 agent 结果
      if (data.agent_results && data.agent_results.length > 0) {
        agentResults.value = data.agent_results.map(r => ({
          ...r,
          success: r.status === 'success'
        }))
      }

      // 恢复最终报告
      if (data.final_report && data.final_report.report) {
        handleFinalReport({
          ...data.final_report,
          total_time: data.total_time
        })
      } else {
        // 没有最终报告但任务完成了
        leaderState.value = 'completed'
        _sessionActive.value = false
        stopTimer()
      }
      return true
    } catch (err) {
      if (err?.name === 'AbortError' || (execution && !execution.isCurrent())) {
        return false
      }
      console.error('[Leader] Failed to fetch results:', err)
      handleError({ message: leaderText('resultFetchFailed') })
      return false
    }
  }

  /**
   * Restore the unanswered question round from persisted session messages.
   * This is used after a page reload or when a backgrounded browser resumes
   * after missing the original SSE event.
   */
  function restorePendingQuestions(session, sessionMessages = []) {
    currentQuestions.value = []

    if (!session || session.state !== 'questioning') {
      return []
    }

    const pendingMessage = [...sessionMessages].reverse().find(msg => {
      const messageType = msg.type || msg.message_type
      return messageType === 'question' &&
        Number(msg.leader_session_id) === Number(session.id)
    })
    const questions = attachQuestionLocale(
      extractQuestions(pendingMessage?.content || pendingMessage?.rawContent),
      pendingMessage?.content_locale,
    )

    if (!questions || questions.length === 0) {
      console.warn(`[Leader] Session ${session.id} is questioning but has no persisted questions`)
      return []
    }

    currentSession.value = { id: session.id }
    leaderState.value = 'questioning'
    currentQuestions.value = questions
    _questionAsked.value = true
    return questions
  }

  async function reconcilePersistedResults(sessionId, execution = null) {
    if (execution && !execution.isCurrent()) return false
    resultsReconciled.value = false
    const restored = await _fetchAndRestoreResults(sessionId, execution)
    if (execution && !execution.isCurrent()) return false
    resultsReconciled.value = restored
    return restored
  }

  /**
   * 处理 API 重试事件
   */
  function handleApiRetry(data) {
    const { attempt, max_attempts, message } = data
    console.warn(`[API Retry] ${attempt}/${max_attempts}: ${message}`)

    // 更新思考内容显示重试信息
    thinkingContent.value = leaderText('retrying', { message, attempt, max: max_attempts })
  }

  // ==================== 任务编排 Handler ====================

  /**
   * 处理任务分解事件
   * SSE task_decomposition: 更新 agentStatuses.decomposition
   */
  function handleTaskDecomposition(data) {
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)
    const subtasks = sanitizeSubtasksForDisplay(data.subtasks || [])

    const decomposition = {
      subtasks,
      currentSubtaskId: subtasks.find(s => s.status === 'pending')?.id || null,
      currentSubtaskGoal: subtasks.find(s => s.status === 'pending')?.goal || null,
      completedCount: subtasks.filter(s => s.status === 'completed' || s.status === 'skipped').length,
      totalCount: subtasks.length,
    }

    if (index >= 0) {
      agentStatuses.value[index].decomposition = decomposition
    } else {
      agentStatuses.value.push({
        agent_id: data.agent_id,
        agent_name: data.agent_name || data.agent_id,
        status: 'running',
        message: leaderText('taskDecompositionComplete'),
        timestamp: new Date().toISOString(),
        decomposition,
      })
    }
  }

  /**
   * 处理子任务开始事件
   * SSE subtask_started: 更新当前子任务状态
   */
  function handleSubtaskStarted(data) {
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)

    if (index >= 0) {
      const agent = agentStatuses.value[index]
      agent.status = 'running'
      agent.currentSubtaskId = data.subtask_id
      agent.currentSubtaskGoal = data.goal
      agent.currentSubtaskTools = data.tools || []

      // 更新 decomposition.currentSubtaskId
      if (agent.decomposition) {
        agent.decomposition.currentSubtaskId = data.subtask_id
        agent.decomposition.currentSubtaskGoal = data.goal
        const subtask = agent.decomposition.subtasks?.find(s => s.id === data.subtask_id)
        if (subtask) {
          subtask.status = 'running'
          subtask.goal = data.goal || subtask.goal
        }
      }
    }
  }

  /**
   * 处理子任务工具调用事件
   * SSE subtool_call: 追加工具调用记录
   */
  function handleSubtoolCall(data) {
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)

    const toolRecord = {
      subtaskId: data.subtask_id,
      name: data.tool_name,
      input: data.tool_input || {},
      startedAt: Date.now(),
      status: 'running',
    }

    if (index >= 0) {
      if (!agentStatuses.value[index].toolCallHistory) {
        agentStatuses.value[index].toolCallHistory = []
      }
      agentStatuses.value[index].toolCallHistory.push(toolRecord)
    }
  }

  /**
   * 处理子任务结果事件
   * SSE subtask_result: 更新工具调用结果
   */
  function handleSubtaskResult(data) {
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)

    if (index >= 0) {
      const history = agentStatuses.value[index].toolCallHistory
      if (history && history.length > 0) {
        // 找到对应的 running 工具记录
        const targetTool = history.find(
          h => h.status === 'running' && h.subtaskId === data.subtask_id
        )
        if (targetTool) {
          targetTool.status = 'completed'
          targetTool.evidence = data.evidence || null
          targetTool.evidenceId = data.evidence?.evidence_id || null
          targetTool.completedAt = Date.now()
          targetTool.duration = ((targetTool.completedAt - targetTool.startedAt) / 1000).toFixed(1)
        }
      }
    }
  }

  /**
   * 处理子任务完成事件
   * SSE subtask_completed: 更新子任务状态
   */
  function handleSubtaskCompleted(data) {
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)

    if (index >= 0) {
      const agent = agentStatuses.value[index]
      const decomposition = agent.decomposition

      if (decomposition && decomposition.subtasks) {
        // 更新对应子任务状态
        const subtask = decomposition.subtasks.find(s => s.id === data.subtask_id)
        if (subtask) {
          subtask.status = data.status || 'completed'
          subtask.goal = data.goal || subtask.goal
        }

        // 更新进度摘要
        const completedCount = decomposition.subtasks.filter(s => s.status === 'completed' || s.status === 'skipped').length
        const nextPending = decomposition.subtasks.find(s => s.status === 'pending')
        decomposition.currentSubtaskId = nextPending?.id || null
        decomposition.currentSubtaskGoal = nextPending?.goal || null
        decomposition.completedCount = completedCount
        decomposition.totalCount = decomposition.subtasks.length
      }

      // 所有子任务完成（含跳过）时更新 Agent 状态
      if (decomposition?.subtasks?.every(s => s.status === 'completed' || s.status === 'skipped')) {
        // 子任务结束后仍在合成 Agent 报告；真正完成由 agent_result 事件确认。
        agent.status = 'running'
      }
    }
  }

  /**
   * 处理任务调整事件
   * SSE task_adjusted: 追加/修改子任务，标记动态新增
   */
  function handleTaskAdjusted(data) {
    const index = agentStatuses.value.findIndex(s => s.agent_id === data.agent_id)

    if (index >= 0) {
      const decomposition = agentStatuses.value[index].decomposition
      if (!decomposition) return

      const action = data.action
      const newSubtasks = data.new_subtasks || []

      if (action === 'add_subtask') {
        // 追加新子任务，标记动态新增
        for (const newSubtask of newSubtasks) {
          newSubtask.added_dynamically = true
          decomposition.subtasks.push(newSubtask)
        }
        decomposition.totalCount = decomposition.subtasks.length
      } else if (action === 'modify_subtask') {
        // 修改现有子任务（按 id 匹配）
        for (const newSubtask of newSubtasks) {
          const existing = decomposition.subtasks.find(s => s.id === newSubtask.id)
          if (existing) {
            Object.assign(existing, newSubtask)
          }
        }
      } else if (action === 'skip') {
        // 跳过当前子任务
        const currentId = decomposition.currentSubtaskId
        const currentSubtask = decomposition.subtasks.find(s => s.id === currentId)
        if (currentSubtask) {
          currentSubtask.status = 'skipped'
        }
        // 继续下一个
        const nextPending = decomposition.subtasks.find(s => s.status === 'pending')
        decomposition.currentSubtaskId = nextPending?.id || null
        decomposition.currentSubtaskGoal = nextPending?.goal || null
      }
    }
  }

  function sanitizeSubtasksForDisplay(subtasks) {
    return (subtasks || []).map(({ result, ...subtask }) => ({
      ...subtask,
      result: ''
    }))
  }

  function sanitizeDecompositionForDisplay(decomposition) {
    if (!decomposition) return decomposition
    return {
      ...decomposition,
      subtasks: sanitizeSubtasksForDisplay(decomposition.subtasks || [])
    }
  }

  async function submitAnswers(
    answers,
    {
      abortController,
      endpoint = '/api/leader/answer-questions',
      includeAuthorization = true,
      reconcileOnDone = true
    } = {}
  ) {
    if (!currentSession.value) {
      console.warn('No active session to submit answers')
      return
    }

    const execution = captureExecution()
    const streamController = abortController || new AbortController()
    _abortController = streamController

    try {
      // 构建含问题文本的回答内容（供实时和历史显示）
      const qs = currentQuestions.value
      const answerData = answers.map((a, i) => ({
        question: qs[i] ? (typeof qs[i] === 'string' ? qs[i] : (qs[i].question || '')) : '',
        answer: a
      }))

      const answerContent = `## ${leaderText('userAnswersHeading')}\n\n` +
        answerData.map((item, i) => {
          const qText = item.question ? `${item.question}${leaderText('answerSeparator')}` : ''
          return `${i + 1}. ${qText}${item.answer}`
        }).join('\n\n')

      const answerMsg = {
        id: `answer-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: 'answer',
        message_type: 'answer',
        content: answerContent,
        rawContent: { answers: answerData },
        leader_session_id: currentSession.value.id,
        created_at: new Date().toISOString()
      }

      // 同时推入 messages（实时渲染）和 historicalMessages（历史恢复）
      messages.value.push(answerMsg)
      historicalMessages.value.push({
        ...answerMsg,
        time: formatLeaderTime()
      })
      
      // 立即设置 thinkingContent 为用户答案，触发 LeaderThinking 显示
      thinkingContent.value = answerContent
      
      // 使用 Fetch API 处理 SSE 流
      const headers = { 'Content-Type': 'application/json' }
      if (includeAuthorization) {
        headers.Authorization = `Bearer ${localStorage.getItem('token')}`
      }
      const response = await fetch(endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          session_id: currentSession.value.id,
          answers: answers
        }),
        signal: streamController.signal
      })

      if (!execution.isCurrent()) return

      // 重置追问状态，确保第二轮追问弹窗能正常触发
      currentQuestions.value = []
      _questionAsked.value = false

      // 注册中断控制器：handleLeaderQuestion 收到新追问时调用 abort()
      // 重置状态，等待继续处理
      leaderState.value = 'assessing'

      await consumeSSEStream(
        response,
        (data) => handleSSEMessage(
          { data },
          { reconcileOnDone, execution },
        ),
        {
          signal: streamController.signal,
          on401: () => {
            if (execution.isCurrent()) {
              handleError({ message: leaderText('authExpired') })
            }
          }
        }
      )

    } catch (error) {
      // AbortError 是正常中断（追问弹出时提前结束），不视为错误
      if (error.name === 'AbortError' || !execution.isCurrent()) {
        return
      }
      console.error('Submit answers failed:', error)
      throw error
    } finally {
      if (_abortController === streamController) {
        _abortController = null
      }
    }
  }


  /**
   * 按类型获取消息
   */
  function getMessagesByType(messageType) {
    return messages.value.filter(m => m.type === messageType)
  }

  /**
   * 按会话 ID 获取消息
   * 支持两种数据结构：
   * 1. 新结构：messages 数组（实时执行）
   * 2. 旧结构：historicalMessages 数组（历史加载）
   */
  function getMessagesBySession(sessionId) {
    // 快照和实时 SSE 是两套来源；实时消息可能只包含回答/继续执行事件，
    // 不能因此丢掉快照中已经持久化的 assessment/team_config。
    const scopedHistorical = historicalMessages.value.filter(
      message => String(message.leader_session_id) === String(sessionId),
    )
    const scopedLive = messages.value.filter(
      message => String(message.leader_session_id) === String(sessionId),
    )
    const merged = []
    const indexes = new Map()
    for (const message of [...scopedHistorical, ...scopedLive]) {
      const key = message.id != null
        ? `id:${message.id}`
        : `fallback:${message.type || message.message_type}:${message.sequence_number ?? merged.length}`
      if (indexes.has(key)) {
        merged[indexes.get(key)] = message
      } else {
        indexes.set(key, merged.length)
        merged.push(message)
      }
    }
    return merged
  }

  /**
   * 清空数据
   */
  function clearData() {
    sessions.value = []
    messages.value = []
    currentSession.value = null
    error.value = null
  }

  /**
   * 获取阶段文本
   */
  /**
   * 加载历史 Leader 会话（用于恢复界面）
   * 支持多个 LeaderSession，返回所有 sessions 数据供 Chat.vue 使用
   */
  async function loadHistoricalSession(conversationId) {
    try {
      const response = await api.get(`/api/leader/session/${conversationId}`)

      if (!response.data.success) {
        console.warn('[Leader] No historical session found')
        return false
      }

      const { sessions, messages } = response.data

      if (!sessions || sessions.length === 0) {
        console.warn('[Leader] No sessions in response')
        return false
      }

      // 获取最新的 session（数组最后一个）
      const latestSession = sessions[sessions.length - 1]

      // 恢复 session 数据
      currentSession.value = { id: latestSession.id }
      // 历史会话：如果已完成，状态设为 idle，避免阻塞 UI
      leaderState.value = latestSession.state === 'completed' ? 'idle' : latestSession.state
      totalTime.value = (latestSession.total_time || 0) * 1000

      // 恢复评估详情（历史模式下不设置 thinkingContent，避免重复）
      // thinkingContent 会触发 LeaderThinking 的 watch，导致重复添加
      // 历史消息已经包含评估详情，会通过 historicalMessages 恢复

      // 恢复团队配置
      if (latestSession.team_config && latestSession.team_config.agent_details) {
        // 数据库格式：agent_details 包含完整信息
        // 为每个 agent 添加 leader_session_id
        selectedAgents.value = latestSession.team_config.agent_details.map(agent => ({
          ...agent,
          leader_session_id: latestSession.id
        }))
        const executionOrder = {}
        const dagPlan = latestSession.team_config.dag_plan || latestSession.team_config.dag_execution_plan || {}
        const batches = dagPlan.execution_batches || []
        let sequence = 0
        batches.forEach((batch, batchIndex) => {
          ;(batch.agents || []).forEach((agentId, agentIndex) => {
            executionOrder[agentId] = {
              batchIndex,
              agentIndex,
              sequence: sequence++
            }
          })
        })
        if (Object.keys(executionOrder).length === 0) {
          latestSession.team_config.agent_details.forEach((agent, index) => {
            executionOrder[agent.agent_id] = {
              batchIndex: index,
              agentIndex: 0,
              sequence: index
            }
          })
        }
        agentExecutionOrder.value = executionOrder
        currentPhase.value = 'monitoring'
      } else if (latestSession.team_config && latestSession.team_config.agents) {
        // 兼容旧格式（如果 agents 已经是对象数组）
        const agents = latestSession.team_config.agents
        if (agents.length > 0 && typeof agents[0] === 'object') {
          // 为每个 agent 添加 leader_session_id
          selectedAgents.value = agents.map(agent => ({
            ...agent,
            leader_session_id: latestSession.id
          }))
          agentExecutionOrder.value = agents.reduce((acc, agent, index) => {
            acc[agent.agent_id] = {
              batchIndex: index,
              agentIndex: 0,
              sequence: index
            }
            return acc
          }, {})
          currentPhase.value = 'monitoring'
        }
      } else if (latestSession.agent_results && latestSession.agent_results.length > 0) {
        // 备选方案：从 agent_results 中提取 agent 信息
        selectedAgents.value = latestSession.agent_results.map(result => ({
          agent_id: result.agent_id,
          agent_name: result.agent_name,
          reason: result.status === 'success'
            ? leaderText('executionCompleted')
            : leaderText('executionFailed'),
          leader_session_id: latestSession.id  // 添加 session_id
        }))
        agentExecutionOrder.value = latestSession.agent_results.reduce((acc, result, index) => {
          acc[result.agent_id] = {
            batchIndex: index,
            agentIndex: 0,
            sequence: index
          }
          return acc
        }, {})
        currentPhase.value = 'monitoring'
      }

      // 恢复 Agent 结果（数据库格式：status 字段）
      if (latestSession.agent_results) {
        // 转换格式：status -> success
        agentResults.value = latestSession.agent_results.map(result => ({
          ...result,
          success: result.status === 'success'
        }))

        // 恢复 Agent 状态
        agentStatuses.value = agentResults.value.map(result => ({
          agent_id: result.agent_id,
          agent_name: result.agent_name,
          status: result.success ? 'completed' : 'failed',
          message: result.success ? leaderText('executionCompleted') : result.error,
          leader_session_id: result.leader_session_id,
          decomposition: sanitizeDecompositionForDisplay(result.decomposition),
          content: result.content,
          summary: result.summary || null,
          structured_report: result.structured_report || null,
          raw_tool_results: result.raw_tool_results || null,
          evidence_map: result.evidence_map || [],
          tool_calls: result.tool_calls,
          tokens_used: result.tokens_used,
          execution_time: result.execution_time,
        }))
      }

      // 恢复最终报告
      if (latestSession.final_report) {
        finalReport.value = latestSession.final_report
        currentPhase.value = 'summarizing'
      }

      // 如果会话已完成，设置阶段
      if (latestSession.state === 'completed') {
        currentPhase.value = 'summarizing'
      }
      resultsReconciled.value = ['completed', 'failed', 'stopped'].includes(latestSession.state)

      // 保存历史消息（转换格式供 LeaderThinking 组件使用）
      if (messages && messages.length > 0) {
        historicalMessages.value = messages.map(msg => {
          const msgType = msg.type || msg.message_type
          const formatted = formatMessageContent(msg.content, msgType, msg.content_locale)

          // question 类型需保留原始问题数组用于弹窗恢复
          if (msgType === 'question') {
            const questions = extractQuestions(msg.content)
            if (questions) {
              return {
                id: msg.id,
                content: formatted,
                rawContent: msg.content,
                questions,
                time: msg.created_at
                  ? formatLeaderTime(msg.created_at)
                  : formatLeaderTime(),
                type: 'question',
                content_locale: msg.content_locale,
                leader_session_id: msg.leader_session_id
              }
            }
          }

          return {
            id: msg.id,
            content: formatted,
            rawContent: msg.content,
            time: msg.created_at
              ? formatLeaderTime(msg.created_at)
              : formatLeaderTime(),
            type: msgType,
            content_locale: msg.content_locale,
            leader_session_id: msg.leader_session_id
          }
        })

      }

      restorePendingQuestions(latestSession, messages || [])

      // 返回完整数据供 Chat.vue 使用
      return {
        sessions,
        messages,
        latestSession
      }

    } catch (error) {
      console.error('[Leader] Load historical session failed:', error)
      return false
    }
  }

  return {
    // 新的消息列表结构
    sessions,
    messages,
    isLoading,
    error,

    // State
    currentSession,
    leaderState,
    thinkingContent,
    currentPhase,
    leaderPhases,
    teamCandidates,
    selectedAgents,
    agentStatuses,
    agentResults,
    finalReport,
    resultsReconciled,
    totalTime,
    totalTokens,
    stopRequested,
    retryCount,
    teamAnalysis,
    teamStrategy,
    historicalMessages,
    pendingSessionData,
    currentQuestions,
    agentExecutionOrder,

    // Computed
    isLeaderMode,
    isActive,

    // Actions
    resetState,
    startLeaderSession,
    startLeaderSessionWithRetry,
    applyTemplateSession,
    stopExecution,
    submitAnswers,
    loadHistoricalSession,
    restorePendingQuestions,
    reconcilePersistedResults,

    // 新方法
    getMessagesByType,
    getMessagesBySession,
    clearData,

    // Event Handlers (exposed for testing)
    handleSSEMessage,
    handleLeaderThinking,
    handleAssessmentResult,
    handleLeaderQuestion,
    handleTeamForming,
    handleTeamReady,
    handleTeamStart,
    handleAgentStatus,
    handleAgentResult,
    handleAgentError,
    handleToolCallStarted,
    handleToolCallCompleted,
    handleTeamComplete,
    handleExecutionStatus,
    handleExecutionComplete,
    handleLeaderSummarizing,
    handleFinalReport,
    handleExecutionStopped,
    handleError,
    handleApiRetry,
    // 任务编排 Handler
    handleTaskDecomposition,
    handleSubtaskStarted,
    handleSubtoolCall,
    handleSubtaskResult,
    handleSubtaskCompleted,
    handleTaskAdjusted,
  }
})
