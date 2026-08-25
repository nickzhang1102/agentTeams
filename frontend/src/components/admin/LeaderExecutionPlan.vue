<template>
  <section class="execution-plan">
    <div class="plan-header">
      <div class="plan-header__main">
        <h4>{{ t('admin.executionPlan.title') }}</h4>
        <p>{{ planSummary }}</p>
      </div>
      <div class="plan-metrics">
        <div class="metric-chip">
          <span class="metric-label">{{ t('admin.executionPlan.batches') }}</span>
          <strong>{{ batches.length }}</strong>
        </div>
        <div class="metric-chip">
          <span class="metric-label">Agent</span>
          <strong>{{ orderedAgents.length }}</strong>
        </div>
        <div class="metric-chip">
          <span class="metric-label">{{ t('admin.executionPlan.completed') }}</span>
          <strong>{{ completedCount }}/{{ orderedAgents.length }}</strong>
        </div>
      </div>
    </div>

    <div v-if="batches.length" class="flow-board" :class="{ 'flow-board--single': batches.length === 1 }">
      <article
        v-for="(batch, batchIndex) in batches"
        :key="`batch-${batchIndex}`"
        class="flow-stage"
        :class="stageClass(batch)"
      >
        <div class="flow-stage__rail" aria-hidden="true">
          <div class="flow-stage__rail-line" />
          <div class="flow-stage__rail-index">{{ batchIndex + 1 }}</div>
        </div>

        <div class="flow-stage__body">
          <header class="flow-stage__header">
            <div class="flow-stage__title-wrap">
              <div class="flow-stage__title-row">
                <h5>{{ t('admin.executionPlan.batch', { number: batchIndex + 1 }) }}</h5>
                <el-tag size="small" effect="plain" :type="stageTagType(batchStatus(batch))">
                  {{ batchStatusLabel(batchStatus(batch)) }}
                </el-tag>
              </div>
              <div class="flow-stage__subtitle">
                <span>{{ batchModeLabel(batch) }}</span>
                <span class="flow-stage__dot" />
                <span>{{ t('admin.executionPlan.priority', { value: batch.priority ?? '-' }) }}</span>
                <span v-if="batchDependsLabel(batchIndex)" class="flow-stage__dependency">
                  {{ t('admin.executionPlan.dependsOn', { batch: batchDependsLabel(batchIndex) }) }}
                </span>
              </div>
            </div>

            <div class="flow-stage__summary">
              <span>{{ t('admin.executionPlan.completedCount', { completed: batchCompletedCount(batch), total: batch.agents.length }) }}</span>
            </div>
          </header>

          <div class="flow-stage__explain">
            <div class="explain-pill">
              <span class="explain-pill__label">{{ t('admin.executionPlan.prerequisite') }}</span>
              <span>{{ batchExplain(batch, batchIndex) }}</span>
            </div>
          </div>

          <div class="agent-lane" :class="{ 'agent-lane--single': batch.agents.length === 1 }">
            <button
              v-for="agentId in batch.agents"
              :key="agentId"
              type="button"
              class="agent-node"
              :class="agentNodeClass(agentId)"
              @click="$emit('select-agent', agentId)"
            >
              <div class="agent-node__head">
                <div class="agent-node__identity">
                  <span class="agent-node__name">
                    {{ agentLookup.get(agentId)?.agent_name || agentLookup.get(agentId)?.agent_id || agentId }}
                  </span>
                  <span class="agent-node__id">{{ agentId }}</span>
                </div>
                <span class="agent-node__dot" />
              </div>

              <div class="agent-node__status-row">
                <el-tag size="small" :type="statusType(resolveAgentStatus(agentId))">
                  {{ agentStatusLabel(resolveAgentStatus(agentId)) }}
                </el-tag>
                <span class="agent-node__sequence">
                  #{{ agentSequence(agentId) }}
                </span>
              </div>

              <div class="agent-node__meta">
                <span>{{ agentMetaText(agentId) }}</span>
                <span>{{ formatAgentTime(agentId) }}</span>
              </div>

              <div class="agent-node__role">
                {{ agentRoleText(agentId) }}
              </div>
            </button>
          </div>
        </div>
      </article>
    </div>

    <div v-else-if="orderedAgents.length" class="fallback-board">
      <button
        v-for="agent in orderedAgents"
        :key="agent.agent_id"
        type="button"
        class="fallback-node"
        :class="agentNodeClass(agent.agent_id)"
        @click="$emit('select-agent', agent.agent_id)"
      >
        <div class="fallback-node__index">{{ agent.order + 1 }}</div>
        <div class="fallback-node__content">
          <div class="fallback-node__title">
            <span>{{ agent.agent_name || agent.agent_id }}</span>
            <el-tag size="small" :type="statusType(resolveAgentStatus(agent.agent_id))">
              {{ agentStatusLabel(resolveAgentStatus(agent.agent_id)) }}
            </el-tag>
          </div>
          <div class="fallback-node__meta">
            <span>{{ agentRoleText(agent.agent_id) }}</span>
            <span>#{{ agentSequence(agent.agent_id) }}</span>
          </div>
        </div>
      </button>
    </div>

    <div v-else class="plan-empty">
      {{ t('admin.executionPlan.noPlan') }}
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  teamConfig: {
    type: Object,
    default: () => ({})
  },
  dagPlan: {
    type: Object,
    default: () => ({})
  },
  agentResults: {
    type: Array,
    default: () => []
  },
  sessionState: {
    type: String,
    default: ''
  }
})

defineEmits(['select-agent'])

const { t } = useI18n()

const normalizedResults = computed(() => (
  [...props.agentResults].sort((a, b) => {
    const seqA = Number(a.sequence_number || Number.MAX_SAFE_INTEGER)
    const seqB = Number(b.sequence_number || Number.MAX_SAFE_INTEGER)
    if (seqA !== seqB) return seqA - seqB
    return String(a.agent_id || '').localeCompare(String(b.agent_id || ''))
  })
))

const resultLookup = computed(() => {
  const map = new Map()
  for (const result of normalizedResults.value) {
    map.set(result.agent_id, result)
  }
  return map
})

const orderedAgents = computed(() => {
  const nodes = Array.isArray(props.dagPlan?.nodes) ? props.dagPlan.nodes : []
  if (nodes.length > 0) {
    return nodes.map((node, index) => ({
      ...node,
      order: index
    }))
  }

  const teamAgents = Array.isArray(props.teamConfig?.agent_details)
    ? props.teamConfig.agent_details
    : []
  if (teamAgents.length > 0) {
    return teamAgents.map((agent, index) => ({
      ...agent,
      order: index
    }))
  }

  return normalizedResults.value.map((result, index) => ({
    agent_id: result.agent_id,
    agent_name: result.agent_name,
    role_description: result.status === 'success'
      ? t('admin.executionPlan.resultProduced')
      : t('admin.executionPlan.executionRecorded'),
    order: index
  }))
})

const agentLookup = computed(() => {
  const map = new Map()
  for (const agent of orderedAgents.value) {
    map.set(agent.agent_id, agent)
  }
  for (const result of normalizedResults.value) {
    if (!map.has(result.agent_id)) {
      map.set(result.agent_id, {
        agent_id: result.agent_id,
        agent_name: result.agent_name
      })
    }
  }
  return map
})

const batches = computed(() => {
  const explicit = Array.isArray(props.dagPlan?.execution_batches)
    ? props.dagPlan.execution_batches.filter(batch => Array.isArray(batch?.agents) && batch.agents.length > 0)
    : []
  if (explicit.length > 0) {
    return explicit
  }

  if (orderedAgents.value.length > 0) {
    return orderedAgents.value.map((agent, index) => ({
      priority: agent.priority ?? index + 1,
      agents: [agent.agent_id],
      inferred: true
    }))
  }

  return []
})

const completedCount = computed(() => (
  normalizedResults.value.filter(result => ['success', 'failed'].includes(result.status)).length
))

const activeBatchIndex = computed(() => {
  if (!batches.value.length) return -1

  const firstIncomplete = batches.value.findIndex(batch => (
    (batch.agents || []).some(agentId => !resultLookup.value.has(agentId))
  ))

  if (firstIncomplete !== -1) return firstIncomplete
  if (['monitoring', 'summarizing'].includes(props.sessionState)) return batches.value.length - 1
  return -1
})

const planSummary = computed(() => {
  if (!batches.value.length) {
    return t('admin.executionPlan.noRecoverablePlan')
  }

  const parallelStages = batches.value.filter(batch => (batch.agents || []).length > 1).length
  if (!parallelStages) {
    return t('admin.executionPlan.serialSummary')
  }

  return t('admin.executionPlan.parallelSummary', {
    stages: batches.value.length,
    parallel: parallelStages
  })
})

function resolveAgentStatus(agentId) {
  const result = resultLookup.value.get(agentId)
  if (result) {
    if (result.status === 'success') return 'success'
    if (result.status === 'failed') return 'failed'
  }

  if (['completed', 'failed', 'stopped'].includes(props.sessionState)) {
    return 'pending'
  }

  const batchIndex = batches.value.findIndex(batch => batch.agents.includes(agentId))
  if (batchIndex === -1) return 'pending'

  if (activeBatchIndex.value === -1) {
    return props.sessionState === 'monitoring' ? 'queued' : 'pending'
  }
  if (batchIndex < activeBatchIndex.value) return 'completed'
  if (batchIndex === activeBatchIndex.value && ['monitoring', 'summarizing'].includes(props.sessionState)) {
    return 'running'
  }
  return 'pending'
}

function batchStatus(batch) {
  const statuses = (batch.agents || []).map(resolveAgentStatus)
  if (statuses.some(status => status === 'running')) return 'running'
  if (statuses.every(status => ['success', 'failed', 'completed'].includes(status))) return 'completed'
  if (statuses.some(status => status === 'queued')) return 'queued'
  return 'pending'
}

function stageClass(batch) {
  const status = batchStatus(batch)
  return {
    'flow-stage--running': status === 'running',
    'flow-stage--completed': status === 'completed',
    'flow-stage--queued': status === 'queued',
    'flow-stage--pending': status === 'pending'
  }
}

function batchCompletedCount(batch) {
  return (batch.agents || []).filter(agentId => ['success', 'failed', 'completed'].includes(resolveAgentStatus(agentId))).length
}

function batchModeLabel(batch) {
  return t((batch.agents || []).length > 1
    ? 'admin.executionPlan.parallelMode'
    : 'admin.executionPlan.singleMode')
}

function batchDependsLabel(batchIndex) {
  if (batchIndex <= 0) return ''
  return t('admin.executionPlan.batch', { number: batchIndex })
}

function batchExplain(batch, batchIndex) {
  if (batchIndex === 0) {
    return (batch.agents || []).length > 1
      ? t('admin.executionPlan.firstParallelExplanation')
      : t('admin.executionPlan.firstSingleExplanation')
  }
  return (batch.agents || []).length > 1
    ? t('admin.executionPlan.laterParallelExplanation')
    : t('admin.executionPlan.laterSingleExplanation')
}

function agentNodeClass(agentId) {
  const status = resolveAgentStatus(agentId)
  return {
    'agent-node--success': status === 'success' || status === 'completed',
    'agent-node--failed': status === 'failed',
    'agent-node--running': status === 'running',
    'agent-node--queued': status === 'queued',
    'agent-node--pending': status === 'pending'
  }
}

function stageTagType(status) {
  return statusType(status)
}

function statusType(status) {
  const map = {
    success: 'success',
    completed: 'success',
    failed: 'danger',
    running: 'warning',
    queued: 'info',
    pending: 'info'
  }
  return map[status] || 'info'
}

function batchStatusLabel(status) {
  return t(`admin.executionPlan.status.${status}`, status)
}

function agentStatusLabel(status) {
  const key = status === 'success' ? 'completed' : status
  return t(`admin.executionPlan.status.${key}`, t('admin.executionPlan.status.unknown'))
}

function agentSequence(agentId) {
  const result = resultLookup.value.get(agentId)
  if (result?.sequence_number) return result.sequence_number
  const order = orderedAgents.value.findIndex(agent => agent.agent_id === agentId)
  return order >= 0 ? order + 1 : '-'
}

function formatAgentTime(agentId) {
  const result = resultLookup.value.get(agentId)
  if (!result?.execution_time) return '--'
  return `${Number(result.execution_time).toFixed(1)}s`
}

function agentRoleText(agentId) {
  const agent = agentLookup.value.get(agentId)
  return agent?.role_description || agent?.reason || t('admin.executionPlan.roleNotProvided')
}

function agentMetaText(agentId) {
  const status = resolveAgentStatus(agentId)
  if (status === 'success' || status === 'failed') {
    const result = resultLookup.value.get(agentId)
    return `Token ${result?.tokens_used || 0}`
  }
  if (status === 'running') return t('admin.executionPlan.currentBatchRunning')
  if (status === 'queued') return t('admin.executionPlan.waitingCurrentBatch')
  return t('admin.executionPlan.waitingPrerequisite')
}
</script>

<style scoped>
.execution-plan {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.plan-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.plan-header__main h4 {
  margin: 0;
  font-size: 16px;
}

.plan-header__main p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
  max-width: 620px;
}

.plan-metrics {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.metric-chip {
  min-width: 78px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.flow-board {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.flow-stage {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  gap: 14px;
  align-items: stretch;
}

.flow-stage__rail {
  position: relative;
  display: flex;
  justify-content: center;
}

.flow-stage__rail-line {
  position: absolute;
  top: 0;
  bottom: -14px;
  width: 2px;
  background: linear-gradient(180deg, var(--el-border-color) 0%, rgba(148, 163, 184, 0.18) 100%);
}

.flow-stage:last-child .flow-stage__rail-line {
  bottom: 0;
}

.flow-stage__rail-index {
  position: relative;
  z-index: 1;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: var(--el-bg-color);
  border: 2px solid var(--el-border-color);
  color: var(--el-text-color-primary);
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
  margin-top: 10px;
}

.flow-stage__body {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.flow-stage--running .flow-stage__body {
  border-color: var(--el-color-warning-light-5);
  box-shadow: 0 8px 24px rgba(230, 162, 60, 0.12);
}

.flow-stage--running .flow-stage__rail-index {
  border-color: var(--el-color-warning);
  color: var(--el-color-warning-dark-2);
}

.flow-stage--completed .flow-stage__rail-index {
  border-color: var(--el-color-success);
  color: var(--el-color-success);
}

.flow-stage__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.flow-stage__title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.flow-stage__title-row h5 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.flow-stage__subtitle {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.flow-stage__dot {
  width: 4px;
  height: 4px;
  border-radius: 999px;
  background: var(--el-border-color);
}

.flow-stage__dependency {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--el-fill-color);
  color: var(--el-text-color-regular);
}

.flow-stage__summary {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.flow-stage__explain {
  display: flex;
}

.explain-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--el-fill-color-extra-light);
  color: var(--el-text-color-regular);
  font-size: 12px;
  line-height: 1.5;
}

.explain-pill__label {
  color: var(--el-text-color-secondary);
  font-weight: 600;
}

.agent-lane {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.agent-lane--single {
  grid-template-columns: minmax(0, 1fr);
}

.agent-node,
.fallback-node {
  width: 100%;
  text-align: left;
  border: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-extra-light);
  border-radius: 8px;
  padding: 12px;
  transition: border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
  cursor: pointer;
}

.agent-node:hover,
.fallback-node:hover {
  border-color: var(--el-color-primary-light-5);
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
}

.agent-node__head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.agent-node__identity {
  min-width: 0;
}

.agent-node__name {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.4;
  word-break: break-word;
}

.agent-node__id {
  display: block;
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
  line-height: 1.4;
  word-break: break-all;
}

.agent-node__dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: currentColor;
  flex: none;
  margin-top: 4px;
}

.agent-node__status-row,
.agent-node__meta {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-node__sequence,
.agent-node__meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.agent-node__role,
.fallback-node__meta {
  margin-top: 10px;
  color: var(--el-text-color-regular);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.agent-node--success,
.fallback-node.agent-node--success {
  border-color: var(--el-color-success-light-5);
  color: var(--el-color-success);
}

.agent-node--failed,
.fallback-node.agent-node--failed {
  border-color: var(--el-color-danger-light-5);
  color: var(--el-color-danger);
}

.agent-node--running,
.fallback-node.agent-node--running {
  border-color: var(--el-color-warning-light-5);
  background: color-mix(in srgb, var(--el-color-warning-light-9) 68%, white);
  color: var(--el-color-warning-dark-2);
}

.agent-node--queued,
.fallback-node.agent-node--queued {
  border-color: var(--el-color-primary-light-7);
  color: var(--el-color-primary);
}

.agent-node--pending,
.fallback-node.agent-node--pending {
  color: var(--el-text-color-secondary);
}

.fallback-board {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.fallback-node {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 12px;
  align-items: flex-start;
}

.fallback-node__index {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  background: var(--el-fill-color);
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
}

.fallback-node__title {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 14px;
  font-weight: 600;
}

.fallback-node__meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.plan-empty {
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
  padding: 18px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  text-align: center;
}

@media (max-width: 768px) {
  .plan-header {
    flex-direction: column;
  }

  .plan-metrics {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .metric-chip {
    min-width: 0;
    padding: 10px;
  }

  .flow-stage {
    grid-template-columns: 28px minmax(0, 1fr);
    gap: 10px;
  }

  .flow-stage__rail-index {
    width: 24px;
    height: 24px;
    font-size: 12px;
    margin-top: 12px;
  }

  .flow-stage__body {
    padding: 14px 12px;
  }

  .flow-stage__header {
    flex-direction: column;
    align-items: stretch;
  }

  .flow-stage__summary {
    white-space: normal;
  }

  .agent-lane {
    grid-template-columns: 1fr;
  }

  .agent-node {
    padding: 12px 10px;
  }

  .agent-node__status-row,
  .agent-node__meta,
  .fallback-node__meta {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
