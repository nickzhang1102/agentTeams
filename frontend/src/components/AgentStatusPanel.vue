<template>
  <div class="agent-status-panel" ref="panelRef">
    <div class="panel-body" ref="panelBodyRef">
      <section v-if="executionStages.length > 0" class="execution-plan">
        <div class="execution-plan-header">
          <div>
            <div class="execution-plan-title">{{ t('leader.agent.executionPlan') }}</div>
            <div class="execution-plan-subtitle">
              {{ t('leader.agent.executionPlanHint') }}
            </div>
          </div>
          <div class="execution-plan-summary">
            <span>{{ t('leader.agent.stageCount', { count: executionStages.length }) }}</span>
            <span>{{ t('leader.agent.agentCount', { count: allAgents.length }) }}</span>
          </div>
        </div>

        <div class="execution-plan-flow">
          <template v-for="(stage, stageIndex) in executionStages" :key="stage.key">
            <div
              class="stage-card"
              :class="[
                `stage-${stage.status}`,
                {
                  'is-parallel': stage.parallel,
                  'is-running': stage.status === 'running' || stage.status === 'starting'
                }
              ]"
            >
              <div class="stage-card-header">
                <div class="stage-card-meta">
                  <span class="stage-index">{{ String(stageIndex + 1).padStart(2, '0') }}</span>
                  <div class="stage-heading">
                    <div class="stage-title">{{ stage.parallel ? t('leader.agent.parallelStage') : t('leader.agent.sequentialStage') }}</div>
                    <div class="stage-hint">{{ getStageHint(stage, stageIndex) }}</div>
                  </div>
                </div>
                <el-tag size="small" :type="getStatusType(stage.status)">
                  {{ getStatusText(stage.status) }}
                </el-tag>
              </div>

              <div class="stage-agents" :class="{ 'is-parallel': stage.parallel }">
                <button
                  v-for="agent in stage.agents"
                  :key="agent.agent_id"
                  type="button"
                  class="stage-agent-chip"
                  :class="[
                    `status-${agent.status}`,
                    {
                      active: activeAgents === agent.agent_id,
                      'is-running': agent.status === 'running' || agent.status === 'starting'
                    }
                  ]"
                  @click="focusAgent(agent.agent_id)"
                >
                  <span class="stage-agent-sequence">
                    {{ getAgentSequence(agent.agent_id) }}
                  </span>
                  <span class="stage-agent-name">{{ agent.agent_name }}</span>
                  <span class="stage-agent-state">{{ getStatusText(agent.status) }}</span>
                </button>
              </div>
            </div>

            <div v-if="stageIndex < executionStages.length - 1" class="stage-connector">
              <span class="stage-connector-line"></span>
              <span class="stage-connector-text">
                <template v-if="executionStages[stageIndex + 1].status === 'running' || executionStages[stageIndex + 1].status === 'starting'">{{ t('leader.agent.statuses.running') }}</template>
                <template v-else-if="executionStages[stageIndex + 1].status === 'completed'">{{ t('leader.agent.statuses.completed') }}</template>
                <template v-else>{{ t('leader.agent.waitingForPrevious') }}</template>
              </span>
            </div>
          </template>
        </div>
      </section>

      <div class="agent-list">
        <el-collapse v-model="activeAgents" accordion>
          <el-collapse-item
            v-for="agent in allAgents"
            :key="agent.agent_id"
            :name="agent.agent_id"
          >
            <template #title>
              <div class="agent-title">
                <el-avatar :size="28">{{ getAgentInitial(agent.agent_name) }}</el-avatar>
                <div class="agent-title-info">
                  <div class="agent-name">
                    {{ agent.agent_name }}
                    <!-- 任务进度摘要（缩起时显示） -->
                    <span v-if="agent.decomposition && activeAgents !== agent.agent_id" class="progress-summary">
                      {{ getProgressText(agent.decomposition) }}
                    </span>
                  </div>
                  <el-tag size="small" :type="getStatusType(agent.status)">
                    {{ getStatusText(agent.status) }}
                  </el-tag>
                </div>
              </div>
            </template>
            <div
              class="agent-content"
              :ref="(el) => setAgentRef(el, agent.agent_id)"
              :data-message-id="`agent-result-${agent.agent_id}`"
            >
              <!-- 任务分解列表（展开时显示） -->
              <div v-if="agent.decomposition" class="task-decomposition">
                <div class="decomposition-header">
                  <el-icon><List /></el-icon>
                  <span>{{ t('leader.agent.taskBreakdown') }}</span>
                  <span class="subtask-count">
                    {{ t('leader.agent.completedCount', { completed: getCompletedCount(agent.decomposition), total: agent.decomposition.subtasks?.length || 0 }) }}
                  </span>
                </div>
                <div class="subtask-list">
                  <div
                    v-for="subtask in agent.decomposition.subtasks"
                    :key="subtask.id"
                    :class="['subtask-item', subtask.status, { 'added-dynamically': subtask.added_dynamically }]"
                  >
                    <div class="subtask-header">
                      <el-icon :class="getSubtaskIconClass(subtask.status)">
                        <component :is="getSubtaskIcon(subtask.status)" />
                      </el-icon>
                      <span class="subtask-goal">{{ subtask.goal }}</span>
                      <el-tag size="small" :type="getSubtaskStatusType(subtask.status)">
                        {{ getSubtaskStatusText(subtask.status) }}
                      </el-tag>
                      <!-- 动态追加标记 -->
                      <el-tag v-if="subtask.added_dynamically" size="small" type="warning">
                        {{ t('leader.agent.added') }}
                      </el-tag>
                    </div>
                    <!-- 工具链显示 -->
                    <div v-if="subtask.tools && subtask.tools.length > 0" class="subtask-tools">
                      <span class="tools-label">{{ t('leader.agent.tools') }}</span>
                      <el-tag v-for="tool in subtask.tools" :key="tool" size="small" type="info" effect="plain">
                        {{ tool }}
                      </el-tag>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 实时工具调用指示器（运行中） -->
              <div v-if="agent.currentTool" class="current-tool">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>{{ t('leader.agent.calling', { name: agent.currentTool.name }) }}</span>
              </div>

              <!-- 嵌套折叠：工具调用历史（默认折叠） -->
              <el-collapse
                v-if="agent.toolCallHistory && agent.toolCallHistory.length > 0"
                v-model="activeToolCalls[agent.agent_id]"
                class="tool-calls-collapse"
              >
                <el-collapse-item :name="agent.agent_id">
                  <template #title>
                    <div class="tool-calls-summary">
                      <el-icon><Tools /></el-icon>
                      <span>{{ t('leader.agent.toolCalls', { count: agent.toolCallHistory.length }) }}</span>
                      <span v-if="getEvidenceCount(agent.toolCallHistory)" class="evidence-count">
                        {{ t('leader.report.evidenceCount', { count: getEvidenceCount(agent.toolCallHistory) }) }}
                      </span>
                      <span v-if="!activeToolCalls[agent.agent_id]" class="latest-tool-hint">
                        {{ t('leader.agent.latest', { name: getLatestToolCallName(agent.toolCallHistory) }) }}
                      </span>
                    </div>
                  </template>
                  <ToolCallVisualization :calls="mapToolCallHistory(agent.toolCallHistory)" />
                </el-collapse-item>
              </el-collapse>

              <!-- Agent 响应内容（仅已完成时显示） -->
              <template v-if="agent.content">
                <div class="content-label">
                  <span>{{ t('leader.agent.analysisReport') }}</span>
                  <el-button
                    v-if="getAgentEvidence(agent).length"
                    size="small"
                    text
                    type="primary"
                    @click="openAgentEvidence(agent)"
                  >
                    {{ t('leader.report.evidenceCount', { count: getAgentEvidence(agent).length }) }}
                  </el-button>
                </div>
                <ContentTranslationStatus :state="agent.translationState" />
                <MarkdownRenderer
                  class="content-body"
                  :content="agent.content"
                  :evidence-map="mergedEvidence"
                  :evidence-label="t('leader.evidence.inlineReference')"
                  @evidence-click="(evidenceId) => handleAgentEvidenceClick(agent, evidenceId)"
                />
                <!-- 操作工具条 -->
                <ChatActionBar
                  :message="{ id: `agent-result-${agent.agent_id}`, content: agent.content, user_content: '评审模式Agent分析' }"
                  :conversation-id="conversationId || 'leader-session'"
                />
              </template>

              <!-- 运行中但无内容时的占位提示 -->
              <div
                v-else-if="(agent.status === 'running' || agent.status === 'starting') && !agent.decomposition?.subtasks?.length"
                class="running-placeholder"
              >
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>{{ t('leader.agent.waitingForResult') }}</span>
              </div>

              <!-- 失败时显示错误 -->
              <div v-else-if="agent.status === 'failed'" class="error-placeholder">
                <span>{{ t('leader.agent.executionFailed') }}</span>
                <p v-if="agent.message" class="error-detail">{{ agent.message }}</p>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>
    <ReportEvidenceDrawer
      v-model="evidenceDrawerVisible"
      :evidence-map="activeEvidenceMap"
      :session-id="activeEvidenceSessionId"
      :highlight-id="highlightEvidenceId"
      :title="activeEvidenceTitle"
      :detail-enabled="evidenceDetailEnabled"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLeaderStore } from '@/stores/leader'
import { applyTranslationOverlay, useContentTranslationStore } from '@/stores/contentTranslation'
import { Loading, Tools, List, Check, Close, Clock } from '@element-plus/icons-vue'
import ChatActionBar from './ChatActionBar.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ToolCallVisualization from './ToolCallVisualization.vue'
import ReportEvidenceDrawer from './ReportEvidenceDrawer.vue'
import ContentTranslationStatus from './ContentTranslationStatus.vue'

const props = defineProps({
  conversationId: {
    type: [Number, String],
    default: ''
  },
  evidenceDetailEnabled: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['agent-scroll-target', 'agent-expanded'])

const leaderStore = useLeaderStore()
const translationStore = useContentTranslationStore()
const { t, locale } = useI18n()


const activeAgents = ref(null)
const activeToolCalls = ref({})  // 按 agent_id 控制工具调用折叠状态
const evidenceDrawerVisible = ref(false)
const activeEvidenceMap = ref([])
const activeEvidenceSessionId = ref('')
const activeEvidenceAgentName = ref('')
const activeEvidenceTitle = computed(() => activeEvidenceAgentName.value
  ? t('leader.agent.evidenceTitle', { name: activeEvidenceAgentName.value })
  : t('leader.agent.reportEvidenceTitle'))
const highlightEvidenceId = ref('')
const panelRef = ref(null)
const panelBodyRef = ref(null)
const agentRefs = ref({})

function getAgentEvidence(agent) {
  const evidence = agent.evidence_map || agent.structured_report?.evidence_map || []
  return Array.isArray(evidence) ? evidence : Object.values(evidence || {})
}

function openAgentEvidence(agent) {
  activeEvidenceMap.value = getAgentEvidence(agent)
  activeEvidenceSessionId.value = agent.leader_session_id || leaderStore.currentSession?.id || ''
  activeEvidenceAgentName.value = agent.agent_name
  highlightEvidenceId.value = ''
  evidenceDrawerVisible.value = true
}

function handleAgentEvidenceClick(agent, evidenceId) {
  // 报告正文可能引用其他 Agent 的证据（批次上下文中的 scoped evidence_id），
  // 因此点击引用时用全会话合并证据表定位，保证跨 Agent 引用也能打开抽屉。
  activeEvidenceMap.value = mergedEvidence.value.length ? mergedEvidence.value : getAgentEvidence(agent)
  activeEvidenceSessionId.value = agent.leader_session_id || leaderStore.currentSession?.id || ''
  activeEvidenceAgentName.value = agent.agent_name
  highlightEvidenceId.value = evidenceId
  evidenceDrawerVisible.value = true
}

function getEvidenceCount(history) {
  return (history || []).filter(item => item.evidenceId || item.evidence?.evidence_id).length
}

// 设置 Agent 内容引用
function setAgentRef(el, agentId) {
  if (el) {
    agentRefs.value[agentId] = el

    // 如果这是当前展开的 Agent，立即通知父组件
    if (activeAgents.value === agentId) {
      nextTick(() => {
        emit('agent-scroll-target', el)
      })
    }
  }
}


// 所有Agent
function getExecutionMeta(agentId) {
  return leaderStore.agentExecutionOrder?.[agentId] || null
}

function compareAgentsByExecution(a, b) {
  const orderA = getExecutionMeta(a.agent_id)
  const orderB = getExecutionMeta(b.agent_id)

  if (orderA && orderB) {
    return orderA.sequence - orderB.sequence
  }
  if (orderA) return -1
  if (orderB) return 1
  return 0
}

const allAgents = computed(() => {
  const selected = leaderStore.selectedAgents
  const statuses = leaderStore.agentStatuses
  const results = leaderStore.agentResults

  return selected.map(agent => {
    const status = statuses.find(s => s.agent_id === agent.agent_id)
    const result = results.find(r => r.agent_id === agent.agent_id)
    const source = Number.isInteger(result?.id) && result.id > 0
      ? { type: 'leader_agent_result', id: result.id }
      : null
    const entry = source ? translationStore.getEntry(source, locale.value) : null
    const displayResult = applyTranslationOverlay(
      'leader_agent_result',
      result,
      entry?.state === 'ready' ? entry.payload : null,
    )

    return {
      ...agent,
      status: status?.status || 'pending',
      result_id: result?.id || null,
      content_locale: result?.content_locale || status?.content_locale || null,
      content: displayResult?.content || status?.content || '',
      summary: displayResult?.summary || status?.summary || null,
      structured_report: displayResult?.structured_report || status?.structured_report || null,
      evidence_map: result?.evidence_map || status?.evidence_map || [],
      success: result?.success || false,
      toolCalls: result?.toolCalls || result?.tool_calls || [],
      toolCallHistory: status?.toolCallHistory || [],
      currentTool: status?.currentTool || null,
      // 任务分解数据
      decomposition: status?.decomposition || null,
      translationState: entry?.state || 'original',
    }
  }).sort(compareAgentsByExecution)
})

// 全会话合并证据表：每个 Agent 的 evidence_map 在批次上下文中带 agent 前缀
// （如 laboratory-expert_ev_subtask_2_llm_analysis_1），跨 Agent 全局唯一，
// 因此报告正文对其他 Agent 证据的引用也能在合并表中命中并转为可点击引用。
const mergedEvidence = computed(() => {
  const seen = new Set()
  const merged = []
  for (const agent of allAgents.value) {
    for (const item of getAgentEvidence(agent)) {
      const id = item?.evidence_id
      if (!id) continue
      if (seen.has(id)) continue
      seen.add(id)
      merged.push(item)
    }
  }
  return merged
})

const executionStages = computed(() => {
  const agents = allAgents.value
  if (!agents.length) return []

  const stages = []
  const hasBatchPlan = agents.some(agent => getExecutionMeta(agent.agent_id)?.batchIndex !== undefined)

  if (!hasBatchPlan) {
    return agents.map((agent, index) => ({
      key: `stage-${agent.agent_id}`,
      parallel: false,
      agents: [agent],
      status: resolveStageStatus([agent]),
      stageIndex: index
    }))
  }

  const grouped = new Map()
  agents.forEach((agent, index) => {
    const meta = getExecutionMeta(agent.agent_id)
    const key = meta?.batchIndex ?? `fallback-${index}`

    if (!grouped.has(key)) {
      grouped.set(key, [])
    }
    grouped.get(key).push(agent)
  })

  Array.from(grouped.entries()).forEach(([key, stageAgents], stageIndex) => {
    stages.push({
      key: `stage-${key}`,
      parallel: stageAgents.length > 1,
      agents: [...stageAgents].sort(compareAgentsByExecution),
      status: resolveStageStatus(stageAgents),
      stageIndex
    })
  })

  return stages
})

// 监听 allAgents 变化，自动展开第一个运行中的 Agent
watch(allAgents, (agents) => {
  nextTick(() => {
    // 如果没有手动展开任何 Agent，自动展开第一个运行中的
    if (!activeAgents.value) {
      const runningAgent = agents.find(a => a.status === 'running')
      if (runningAgent) {
        activeAgents.value = runningAgent.agent_id
      }
    }
  })
}, { immediate: true })

// 监听 activeAgents 变化，当用户展开某个 Agent 时，传递其 ref
watch(activeAgents, (newActiveAgentId) => {
  if (newActiveAgentId && agentRefs.value[newActiveAgentId]) {
    // 等待 DOM 更新后再 emit
    nextTick(() => {
      emit('agent-scroll-target', agentRefs.value[newActiveAgentId])
      // 延迟通知父组件折叠面板已展开（等待动画完成）
      setTimeout(() => {
        emit('agent-expanded')
      }, 350)
    })
  } else if (!newActiveAgentId) {
    // 用户收起了所有 Agent，emit null 让父组件切换到最终报告
    emit('agent-scroll-target', null)
  }
})

function getAgentInitial(name) {
  if (!name) return 'A'
  return name.charAt(0).toUpperCase()
}

function resolveStageStatus(agents) {
  if (agents.some(agent => agent.status === 'failed')) return 'failed'
  if (agents.some(agent => agent.status === 'running' || agent.status === 'starting')) return 'running'
  if (agents.every(agent => agent.status === 'completed')) return 'completed'
  return 'pending'
}

function getStageHint(stage, stageIndex) {
  // 按状态优先级返回实时描述
  switch (stage.status) {
    case 'running':
    case 'starting':
      return t(stage.parallel ? 'leader.agent.stageHints.parallelRunning' : 'leader.agent.stageHints.sequentialRunning')
    case 'completed':
      return t('leader.agent.stageHints.completed')
    case 'failed':
      return t('leader.agent.stageHints.failed')
  }

  // pending 状态：显示依赖关系
  if (stageIndex === 0) {
    return t(stage.parallel ? 'leader.agent.stageHints.firstParallel' : 'leader.agent.stageHints.firstSequential')
  }
  return t(stage.parallel ? 'leader.agent.stageHints.waitingParallel' : 'leader.agent.stageHints.waitingSequential')
}

function getAgentSequence(agentId) {
  const sequence = getExecutionMeta(agentId)?.sequence
  return String((sequence ?? allAgents.value.findIndex(agent => agent.agent_id === agentId)) + 1).padStart(2, '0')
}

function focusAgent(agentId) {
  activeAgents.value = agentId

  if (agentRefs.value[agentId]) {
    nextTick(() => {
      emit('agent-scroll-target', agentRefs.value[agentId])
    })
  }
}

// 将 toolCallHistory 映射为 ToolCallVisualization 所需格式
function mapToolCallHistory(history) {
  if (!history || history.length === 0) return []
  return history.map(call => ({
    tool: call.name,
    params: call.params || call.input || {},
    result_summary: '',
    status: call.status || 'completed',
    timestamp: call.duration ? `${call.duration}s` : ''
  }))
}

// 获取最新工具调用名称（折叠时预览）
function getLatestToolCallName(history) {
  if (!history || history.length === 0) return ''
  return history[history.length - 1].name
}

function getStatusType(status) {
  const types = {
    'pending': 'info',
    'starting': 'info',
    'running': 'warning',
    'completed': 'success',
    'failed': 'danger'
  }
  return types[status] || 'info'
}

function getStatusText(status) {
  return ['pending', 'starting', 'running', 'completed', 'failed'].includes(status)
    ? t(`leader.agent.statuses.${status}`)
    : status
}

// ==================== 任务分解相关函数 ====================

// 获取进度摘要文本（缩起时显示）
function getProgressText(decomposition) {
  if (!decomposition || !decomposition.subtasks) return ''

  const done = decomposition.subtasks.filter(s => s.status === 'completed' || s.status === 'skipped').length
  const total = decomposition.subtasks.length
  const current = decomposition.currentSubtaskGoal

  if (done === total) {
    return t('leader.agent.statuses.completed')
  } else if (current) {
    return t('leader.agent.progress.current', { number: done + 1, goal: current.substring(0, 20) })
  } else {
    return t('leader.agent.completedCount', { completed: done, total })
  }
}

// 获取已完成子任务数量
function getCompletedCount(decomposition) {
  if (!decomposition || !decomposition.subtasks) return 0
  return decomposition.subtasks.filter(s => s.status === 'completed' || s.status === 'skipped').length
}

// 子任务状态图标
function getSubtaskIcon(status) {
  const icons = {
    'pending': Clock,
    'running': Loading,
    'completed': Check,
    'failed': Close,
    'skipped': Close,
  }
  return icons[status] || Clock
}

// 子任务图标类名
function getSubtaskIconClass(status) {
  const classes = {
    'pending': 'icon-pending',
    'running': 'icon-running is-loading',
    'completed': 'icon-completed',
    'failed': 'icon-failed',
    'skipped': 'icon-skipped',
  }
  return classes[status] || ''
}

// 子任务状态类型（用于 el-tag）
function getSubtaskStatusType(status) {
  const types = {
    'pending': 'info',
    'running': 'warning',
    'completed': 'success',
    'failed': 'danger',
    'skipped': 'info',
  }
  return types[status] || 'info'
}

// 子任务状态文本
function getSubtaskStatusText(status) {
  return ['pending', 'running', 'completed', 'failed', 'skipped'].includes(status)
    ? t(`leader.agent.statuses.${status}`)
    : status
}
</script>

<style scoped>
.agent-status-panel {
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  background: #f0f9ff;
  border-bottom: 1px solid #bfdbfe;
  font-size: 14px;
  font-weight: 500;
}

.panel-header .el-icon {
  margin-right: 6px;
  font-size: 16px;
}

.agent-count {
  margin-left: auto;
  font-size: 12px;
  color: #606266;
  font-weight: normal;
}

.panel-body {
  flex: 1;
}

.execution-plan {
  margin-bottom: 12px;
  padding: 14px;
  background: linear-gradient(180deg, #f8fbff 0%, #f3f7ff 100%);
  border: 1px solid #dbe7ff;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.06);
}

.execution-plan-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.execution-plan-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e3a5f;
}

.execution-plan-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #5b6b82;
  line-height: 1.5;
}

.execution-plan-summary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
  font-size: 11px;
  color: #5b6b82;
}

.execution-plan-summary span {
  padding: 5px 8px;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid #dbe7ff;
  border-radius: 999px;
  white-space: nowrap;
}

.execution-plan-flow {
  display: flex;
  align-items: stretch;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.stage-card {
  min-width: 240px;
  max-width: 280px;
  flex: 0 0 240px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #dbe7ff;
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.stage-card.is-running {
  border-color: #f2c97d;
  box-shadow: 0 10px 24px rgba(230, 162, 60, 0.14);
}

.stage-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.08);
}

.stage-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.stage-card-meta {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.stage-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: #eaf2ff;
  color: #2563eb;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.stage-heading {
  min-width: 0;
}

.stage-title {
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
}

.stage-hint {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.5;
  color: #6b7280;
}

.stage-agents {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stage-agent-chip {
  width: 100%;
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 10px 10px 10px 8px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
}

.stage-agent-chip:hover {
  border-color: #93c5fd;
  background: #eff6ff;
}

.stage-agent-chip.active {
  border-color: #2563eb;
  background: #eff6ff;
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.08);
}

.stage-agent-chip.is-running {
  border-color: #f2c97d;
  background: #fffbeb;
}

.stage-agent-chip.status-completed {
  border-color: #ccebd8;
  background: #f3fbf5;
}

.stage-agent-chip.status-failed {
  border-color: #f3c1c1;
  background: #fff5f5;
}

.stage-agent-sequence {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: #ffffff;
  border: 1px solid #dbe7ff;
  color: #2563eb;
  font-size: 11px;
  font-weight: 700;
}

.stage-agent-name {
  min-width: 0;
  font-size: 12px;
  font-weight: 600;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stage-agent-state {
  font-size: 11px;
  color: #6b7280;
  white-space: nowrap;
}

.stage-connector {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  min-width: 72px;
  justify-content: center;
}

.stage-connector-line {
  width: 24px;
  height: 2px;
  background: linear-gradient(90deg, #93c5fd 0%, #2563eb 100%);
  border-radius: 999px;
}

.stage-connector-text {
  font-size: 11px;
  color: #6b7280;
  white-space: nowrap;
}

.agent-list {
  padding: 8px;
}

/* 折叠面板样式 */
.agent-list :deep(.el-collapse) {
  border: none;
}

.agent-list :deep(.el-collapse-item__header) {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 6px;
  height: auto;
  line-height: normal;
  font-size: 13px;
  transition: all 0.3s ease;
  cursor: pointer;
}

.agent-list :deep(.el-collapse-item__header:hover) {
  background: var(--el-fill-color-light);
  border-color: var(--el-color-primary);
}

/* 展开状态样式 */
.agent-list :deep(.el-collapse-item__header.is-active) {
  background: var(--el-fill-color);
  border-color: var(--el-color-primary);
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
  margin-bottom: 0;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.1);
}

/* 箭头图标动画 */
.agent-list :deep(.el-collapse-item__arrow) {
  transition: transform 0.3s ease;
  color: var(--el-text-color-secondary);
}

.agent-list :deep(.el-collapse-item__header:hover .el-collapse-item__arrow) {
  color: var(--el-color-primary);
}

.agent-list :deep(.el-collapse-item__header.is-active .el-collapse-item__arrow) {
  transform: rotate(90deg);
  color: var(--el-color-primary);
}

.agent-list :deep(.el-collapse-item__wrap) {
  border: none;
  background: transparent;
  transition: height 0.3s ease-in-out;
}

.agent-list :deep(.el-collapse-item__content) {
  padding: 0;
  background: transparent;
}

.agent-title {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.agent-title-info {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.agent-name {
  font-weight: 500;
  font-size: 13px;
}

.agent-content {
  position: relative;
  background: var(--el-bg-color);
  border: 1px solid var(--el-color-primary);
  border-top: none;
  border-radius: 0 0 8px 8px;
  padding: 12px;
  margin-bottom: 8px;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.08);
}

/* 嵌套折叠：工具调用历史 */
.tool-calls-collapse {
  margin-bottom: 12px;
}

.tool-calls-collapse :deep(.el-collapse-item__header) {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 6px 10px;
  height: auto;
  line-height: normal;
  font-size: 12px;
  transition: all 0.3s ease;
}

.tool-calls-collapse :deep(.el-collapse-item__header:hover) {
  border-color: #409eff;
  background: #ecf5ff;
}

.tool-calls-collapse :deep(.el-collapse-item__header.is-active) {
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
  border-color: #409eff;
  background: #ecf5ff;
}

.tool-calls-collapse :deep(.el-collapse-item__wrap) {
  border: 1px solid #409eff;
  border-top: none;
  border-radius: 0 0 6px 6px;
  background: transparent;
}

.tool-calls-collapse :deep(.el-collapse-item__content) {
  padding: 8px;
}

.tool-calls-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #606266;
}

.evidence-count {
  color: var(--el-color-success);
}

.latest-tool-hint {
  margin-left: auto;
  color: #909399;
  font-size: 11px;
}

.content-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: #909399;
  margin-bottom: 8px;
  font-weight: 500;
}

.content-body {
  line-height: 1.6;
  color: #303133;
  word-wrap: break-word;
  font-size: 13px;
}

.content-body :deep(h2) {
  margin: 12px 0 6px;
  font-size: 15px;
  font-weight: 600;
}

.content-body :deep(h3) {
  margin: 10px 0 4px;
  font-size: 14px;
  font-weight: 600;
}

.content-body :deep(p) {
  margin: 6px 0;
}

.content-body :deep(ul),
.content-body :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.content-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 12px;
}

.content-body :deep(th),
.content-body :deep(td) {
  border: 1px solid #ddd;
  padding: 6px;
  text-align: left;
}

.content-body :deep(th) {
  background-color: #f5f7fa;
  font-weight: 600;
}

/* 当前工具调用指示器 */
.current-tool {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: #ecf5ff;
  border-radius: 4px;
  font-size: 13px;
  color: #409eff;
}

/* 运行中占位提示 */
.running-placeholder {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px;
  color: #909399;
  font-size: 13px;
}

/* 失败占位提示 */
.error-placeholder {
  padding: 12px;
  color: #f56c6c;
  font-size: 13px;

  .error-detail {
    margin-top: 8px;
    font-size: 12px;
    color: #909399;
    word-break: break-word;
    white-space: pre-wrap;
  }
}

/* 任务分解列表样式 */
.task-decomposition {
  margin-bottom: 12px;
  background: #f5f7fa;
  border-radius: 6px;
  padding: 8px;
}

.decomposition-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 8px;
}

.decomposition-header .el-icon {
  font-size: 14px;
}

.subtask-count {
  margin-left: auto;
  font-size: 11px;
  color: #909399;
}

.subtask-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.subtask-item {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 6px 8px;
  transition: all 0.3s ease;
}

.subtask-item.running {
  border-color: #e6a23c;
  background: #fdf6ec;
}

.subtask-item.completed {
  border-color: #67c23a;
  background: #f0f9eb;
}

.subtask-item.failed {
  border-color: #f56c6c;
  background: #fef0f0;
}

.subtask-item.skipped {
  border-color: #c0c4cc;
  background: #f4f4f5;
  opacity: 0.6;
}

.subtask-item.added-dynamically {
  border-left: 3px solid #e6a23c;
}

.subtask-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.subtask-header .el-icon {
  font-size: 12px;
}

.icon-pending {
  color: #909399;
}

.icon-running {
  color: #e6a23c;
}

.icon-completed {
  color: #67c23a;
}

.icon-failed {
  color: #f56c6c;
}

.icon-skipped {
  color: #909399;
}

.subtask-goal {
  flex: 1;
  font-size: 12px;
  color: #303133;
}

.subtask-tools {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  padding-left: 18px;
}

.tools-label {
  font-size: 11px;
  color: #909399;
}

.subtask-tools .el-tag {
  font-size: 10px;
  height: 18px;
  line-height: 16px;
  padding: 0 4px;
}

.subtask-result {
  margin-top: 4px;
  padding-left: 18px;
  font-size: 11px;
  color: #606266;
  background: #f5f7fa;
  border-radius: 2px;
  padding: 4px 6px;
}

/* 进度摘要（缩起时显示） */
.progress-summary {
  margin-left: 8px;
  font-size: 11px;
  color: #909399;
  font-weight: normal;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .execution-plan {
    padding: 12px;
    border-radius: 10px;
  }

  .execution-plan-header {
    flex-direction: column;
  }

  .execution-plan-summary {
    justify-content: flex-start;
  }

  .execution-plan-flow {
    flex-direction: column;
    gap: 8px;
    overflow-x: visible;
  }

  .stage-card {
    min-width: 0;
    max-width: none;
    flex-basis: auto;
    width: 100%;
  }

  .stage-connector {
    min-width: 0;
    flex-direction: column;
    gap: 6px;
  }

  .stage-connector-line {
    width: 2px;
    height: 16px;
    background: linear-gradient(180deg, #93c5fd 0%, #2563eb 100%);
  }

  .stage-agent-chip {
    grid-template-columns: 28px minmax(0, 1fr);
  }

  .stage-agent-state {
    grid-column: 2;
  }

  .panel-header {
    padding: 8px 10px;
    font-size: 13px;
  }

  .agent-list {
    padding: 4px;
  }

  .agent-title {
    gap: 6px;
  }

  .agent-name {
    font-size: 12px;
  }

  .agent-content {
    padding: 6px;
  }

  .content-body {
    font-size: 12px;
  }

  .content-body :deep(h2) {
    font-size: 14px;
  }

  .content-body :deep(h3) {
    font-size: 13px;
  }
}
</style>
