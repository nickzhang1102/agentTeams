<template>
  <div class="admin-leader-sessions">
    <div class="page-title">
      <h2>{{ t('admin.leaderSessions.title') }}</h2>
      <p>{{ t('admin.leaderSessions.description') }}</p>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row" v-if="adminStore.leaderStats">
      <div class="stat-card">
        <div class="stat-value">{{ formatNumber(adminStore.leaderStats.total || 0) }}</div>
        <div class="stat-label">{{ t('admin.leaderSessions.totalSessions') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ formatPercent(adminStore.leaderStats.success_rate || 0) }}</div>
        <div class="stat-label">{{ t('admin.leaderSessions.successRate') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ formatNumber(adminStore.leaderStats.avg_tokens || 0) }}</div>
        <div class="stat-label">{{ t('admin.leaderSessions.averageTokens') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ t('admin.common.seconds', { value: formatNumber(adminStore.leaderStats.avg_duration_seconds || 0) }) }}</div>
        <div class="stat-label">{{ t('admin.leaderSessions.averageDuration') }}</div>
      </div>
    </div>

    <el-card shadow="hover" class="section-card">
      <template #header>
        <div class="card-header">
          <span>{{ t('admin.leaderSessions.list') }}</span>
          <el-button
            type="danger"
            :disabled="selectedSessions.length === 0"
            @click="handleBatchDelete"
          >
            {{ selectedSessions.length > 0
              ? t('admin.leaderSessions.batchDeleteCount', { count: formatNumber(selectedSessions.length) })
              : t('admin.leaderSessions.batchDelete') }}
          </el-button>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-select
          v-model="adminStore.leaderSessionFilters.state"
          :placeholder="t('admin.leaderSessions.allStatuses')"
          clearable
          style="width: 160px"
          @change="handleFilterChange"
        >
          <el-option v-for="state in stateValues" :key="state" :label="getStateLabel(state)" :value="state" />
        </el-select>
        <el-select
          v-model="adminStore.leaderSessionFilters.risk_level"
          :placeholder="t('admin.leaderSessions.allRisks')"
          clearable
          style="width: 140px"
          @change="handleFilterChange"
        >
          <el-option v-for="risk in riskValues" :key="risk" :label="getRiskLabel(risk)" :value="risk" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="-"
          :start-placeholder="t('admin.leaderSessions.startDate')"
          :end-placeholder="t('admin.leaderSessions.endDate')"
          value-format="YYYY-MM-DD"
          style="width: 260px"
          @change="handleDateChange"
        />
        <el-button type="primary" @click="handleFilterChange">{{ t('admin.actions.filter') }}</el-button>
        <el-button @click="handleResetFilters">{{ t('admin.actions.reset') }}</el-button>
      </div>

      <!-- 错误提示 -->
      <el-alert
        v-if="adminStore.error"
        :title="adminStore.error"
        type="error"
        show-icon
        closable
        @close="adminStore.error = null"
        style="margin-bottom: 16px"
      />

      <!-- 表格 -->
      <el-table
        :data="adminStore.leaderSessions"
        v-loading="adminStore.loading"
        stripe
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="user_message" :label="t('admin.leaderSessions.userMessage')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="state" :label="t('admin.common.status')" width="110">
          <template #default="{ row }">
            <el-tag :type="getStateType(row.state)" size="small">{{ getStateLabel(row.state) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="risk_level" :label="t('admin.leaderSessions.risk')" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.risk_level" :type="getRiskType(row.risk_level)" size="small">{{ getRiskLabel(row.risk_level) }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="agent_count" :label="t('admin.leaderSessions.agentCount')" width="90" align="center" />
        <el-table-column prop="total_tokens" label="Token" width="100" align="right" />
        <el-table-column prop="started_at" :label="t('admin.common.startedAt')" width="170">
          <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.common.operations')" width="160" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleViewDetail(row)">{{ t('admin.actions.details') }}</el-button>
            <el-button
              v-if="isActiveState(row.state)"
              type="danger"
              link
              size="small"
              @click="handleStop(row)"
            >{{ t('admin.actions.stop') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="adminStore.leaderSessionPagination.per_page"
          :total="adminStore.leaderSessionPagination.total"
          layout="total, prev, pager, next"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer
      v-model="showDetail"
      :title="t('admin.leaderSessions.detailTitle', { id: detailSession?.id || '' })"
      :size="drawerSize"
      direction="rtl"
    >
      <div v-if="detailSession" class="detail-content">
        <!-- 基本信息 -->
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('admin.common.status')">
            <el-tag :type="getStateType(detailSession.state)">{{ getStateLabel(detailSession.state) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.leaderSessions.riskLevel')">
            <el-tag v-if="detailSession.risk_level" :type="getRiskType(detailSession.risk_level)">{{ getRiskLabel(detailSession.risk_level) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.leaderSessions.assessmentScore')">{{ detailSession.assessment_score || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Token">{{ detailSession.total_tokens || 0 }}</el-descriptions-item>
          <el-descriptions-item :label="t('admin.common.startedAt')">{{ formatTime(detailSession.started_at) }}</el-descriptions-item>
          <el-descriptions-item :label="t('admin.common.completedAt')">{{ formatTime(detailSession.completed_at) }}</el-descriptions-item>
          <el-descriptions-item :label="t('admin.leaderSessions.userMessage')" :span="2">{{ detailSession.user_message }}</el-descriptions-item>
          <el-descriptions-item v-if="detailSession.error_message" :label="t('admin.leaderSessions.error')" :span="2">
            <el-alert :title="detailSession.error_message" type="error" :closable="false" />
          </el-descriptions-item>
        </el-descriptions>

        <!-- Agent 编排与结果 -->
        <div v-if="showExecutionPlan" class="section">
          <LeaderExecutionPlan
            :team-config="detailSession.team_config"
            :dag-plan="detailSession.dag_plan"
            :agent-results="detailSession.agent_results || []"
            :session-state="detailSession.state"
            @select-agent="handleSelectAgent"
          />

          <div v-if="detailSession.agent_results?.length" class="result-panel">
            <div class="result-panel__header">
              <h4>{{ t('admin.leaderSessions.agentResults') }}</h4>
              <span>{{ t('admin.leaderSessions.resultCount', { count: formatNumber(detailSession.agent_results.length) }) }}</span>
            </div>

            <el-collapse v-model="activeResultPanels">
              <el-collapse-item
                v-for="result in detailSession.agent_results"
                :key="result.id || result.agent_id"
                :name="result.agent_id"
                :title="`${result.agent_name || result.agent_id} - ${getAgentResultLabel(result.status)}`"
              >
                <div class="result-meta">
                  <el-tag :type="result.status === 'success' ? 'success' : 'danger'" size="small">
                    {{ getAgentResultLabel(result.status) }}
                  </el-tag>
                  <span>{{ t('admin.leaderSessions.sequence', { value: result.sequence_number || '-' }) }}</span>
                  <span>Token {{ result.tokens_used || 0 }}</span>
                  <span>{{ t('admin.leaderSessions.duration', { value: formatDuration(result.execution_time) }) }}</span>
                </div>
                <div v-if="result.tool_calls?.length" class="tool-call-list">
                  <strong>{{ t('admin.leaderSessions.toolCalls') }}</strong>
                  <div class="tool-call-tags">
                    <el-tag
                      v-for="(tc, i) in result.tool_calls"
                      :key="i"
                      size="small"
                      type="info"
                    >
                      {{ tc.tool || tc.tool_name }}
                    </el-tag>
                  </div>
                </div>
                <!-- 子任务分解详情 -->
                <div v-if="result.decomposition?.subtasks?.length" class="decomposition-section">
                  <strong>{{ t('admin.leaderSessions.subtasks', { count: formatNumber(result.decomposition.subtasks.length) }) }}</strong>
                  <div
                    v-for="st in result.decomposition.subtasks"
                    :key="st.id"
                    class="subtask-item"
                  >
                    <div class="subtask-header">
                      <el-tag :type="st.status === 'completed' ? 'success' : st.status === 'failed' ? 'danger' : 'info'" size="small">
                        {{ getGenericStatusLabel(st.status) }}
                      </el-tag>
                      <span class="subtask-goal">{{ st.goal }}</span>
                      <span v-if="st.tools?.length" class="subtask-tools">
                        <el-tag v-for="t in st.tools" :key="t" size="small" type="warning">{{ t }}</el-tag>
                      </span>
                    </div>
                    <MarkdownRenderer
                      v-if="st.result"
                      class="subtask-result"
                      :content="truncateText(st.result, 500)"
                    />
                  </div>
                </div>
                <div v-if="result.content" class="result-content">
                  <MarkdownRenderer :content="truncateText(result.content, 1200)" />
                </div>
                <div v-if="result.error" style="margin-top: 8px">
                  <el-alert :title="result.error" type="error" :closable="false" />
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>

        <!-- 最终报告 -->
        <div v-if="detailSession.final_report" class="section">
          <h4>{{ t('admin.leaderSessions.finalReport') }}</h4>
          <MarkdownRenderer class="report-content" :content="detailSession.final_report.report || ''" />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAdminStore } from '@/stores/admin'
import { ElMessage, ElMessageBox } from 'element-plus'
import LeaderExecutionPlan from '@/components/admin/LeaderExecutionPlan.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { formatLocaleDateTime, formatLocaleNumber } from '@/utils/localeFormat'

const adminStore = useAdminStore()
const { t, locale } = useI18n()
const stateValues = ['idle', 'assessing', 'questioning', 'forming_team', 'web_search', 'monitoring', 'summarizing', 'completed', 'stopped', 'failed']
const riskValues = ['low', 'medium', 'high']
const currentPage = ref(1)
const dateRange = ref(null)
const showDetail = ref(false)
const detailSession = ref(null)
const activeResultPanels = ref([])
const selectedSessions = ref([])
let detailRefreshTimer = null
const isMobile = ref(false)

const drawerSize = computed(() => (isMobile.value ? '100%' : '62%'))

const showExecutionPlan = computed(() => {
  const session = detailSession.value
  if (!session) return false
  const hasDag = Array.isArray(session.dag_plan?.execution_batches) && session.dag_plan.execution_batches.length > 0
  const hasTeamAgents = Array.isArray(session.team_config?.agent_details) && session.team_config.agent_details.length > 0
  const hasResults = Array.isArray(session.agent_results) && session.agent_results.length > 0
  return hasDag || hasTeamAgents || hasResults
})

onMounted(() => {
  syncViewport()
  window.addEventListener('resize', syncViewport)
  adminStore.fetchLeaderSessions(1)
  adminStore.fetchLeaderStats()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', syncViewport)
  stopDetailAutoRefresh()
})

watch(showDetail, (visible) => {
  if (!visible) {
    stopDetailAutoRefresh()
    return
  }
  syncDetailAutoRefresh()
})

function handleFilterChange() {
  currentPage.value = 1
  adminStore.fetchLeaderSessions(1)
}

function syncViewport() {
  isMobile.value = window.innerWidth <= 768
}

function handleDateChange(val) {
  if (val && val.length === 2) {
    adminStore.leaderSessionFilters.start_date = val[0]
    adminStore.leaderSessionFilters.end_date = val[1]
  } else {
    adminStore.leaderSessionFilters.start_date = ''
    adminStore.leaderSessionFilters.end_date = ''
  }
  handleFilterChange()
}

function truncateText(value, limit) {
  const text = typeof value === 'string' ? value : String(value || '')
  return text.length > limit ? `${text.substring(0, limit)}...` : text
}

function handleResetFilters() {
  adminStore.leaderSessionFilters.state = ''
  adminStore.leaderSessionFilters.risk_level = ''
  adminStore.leaderSessionFilters.start_date = ''
  adminStore.leaderSessionFilters.end_date = ''
  dateRange.value = null
  handleFilterChange()
}

function handlePageChange(page) {
  adminStore.fetchLeaderSessions(page)
}

async function handleViewDetail(row) {
  const result = await adminStore.fetchLeaderSessionDetail(row.id)
  if (result.success) {
    detailSession.value = result.session
    activeResultPanels.value = result.session?.agent_results?.[0]?.agent_id
      ? [result.session.agent_results[0].agent_id]
      : []
    showDetail.value = true
    syncDetailAutoRefresh()
  }
}

function handleSelectAgent(agentId) {
  activeResultPanels.value = agentId ? [agentId] : []
}

async function handleStop(row) {
  try {
    await ElMessageBox.confirm(
      t('admin.leaderSessions.stopConfirm', { id: row.id }),
      t('admin.leaderSessions.stopTitle'),
      { confirmButtonText: t('admin.actions.confirm'), cancelButtonText: t('admin.actions.cancel'), type: 'warning' }
    )
    const result = await adminStore.adminStopLeaderSession(row.id)
    if (result.success) {
      ElMessage.success(t('admin.leaderSessions.stopSent'))
    } else {
      ElMessage.error(result.error || t('admin.leaderSessions.stopFailed'))
    }
  } catch {
    // 取消操作
  }
}

function handleSelectionChange(selection) {
  selectedSessions.value = selection
}

async function handleBatchDelete() {
  const ids = selectedSessions.value.map(s => s.id)
  if (ids.length === 0) {
    ElMessage.warning(t('admin.leaderSessions.selectOne'))
    return
  }
  try {
    await ElMessageBox.confirm(
      t('admin.leaderSessions.deleteConfirm', { count: formatNumber(ids.length) }),
      t('admin.leaderSessions.deleteTitle'),
      { confirmButtonText: t('admin.actions.delete'), cancelButtonText: t('admin.actions.cancel'), type: 'warning' }
    )
    const result = await adminStore.batchDeleteLeaderSessions(ids)
    if (result.success) {
      ElMessage.success(t('admin.leaderSessions.deletedCount', { count: formatNumber(result.deleted) }))
      adminStore.fetchLeaderSessions(adminStore.leaderSessionPagination.page || 1)
      adminStore.fetchLeaderStats()
    } else {
      ElMessage.error(result.error || t('admin.errors.deleteFailed'))
    }
  } catch {
    // 取消操作
  }
}

function isActiveState(state) {
  return ['assessing', 'questioning', 'forming_team', 'web_search', 'monitoring', 'summarizing'].includes(state)
}

function stopDetailAutoRefresh() {
  if (detailRefreshTimer) {
    clearInterval(detailRefreshTimer)
    detailRefreshTimer = null
  }
}

function syncDetailAutoRefresh() {
  stopDetailAutoRefresh()
  if (!detailSession.value?.id || !isActiveState(detailSession.value.state)) {
    return
  }

  detailRefreshTimer = window.setInterval(async () => {
    if (!detailSession.value?.id) return
    const result = await adminStore.fetchLeaderSessionDetail(detailSession.value.id)
    if (result.success) {
      detailSession.value = result.session
      if (!isActiveState(result.session.state)) {
        stopDetailAutoRefresh()
      }
    }
  }, 3000)
}

function getStateType(state) {
  const map = {
    idle: 'info', assessing: 'warning', questioning: 'warning',
    forming_team: 'warning', web_search: 'warning', monitoring: '',
    summarizing: '', completed: 'success', stopped: 'info', failed: 'danger'
  }
  return map[state] || 'info'
}

function getStateLabel(state) {
  return t(`admin.status.${state}`, state)
}

function getRiskType(risk) {
  const map = { low: 'success', medium: 'warning', high: 'danger' }
  return map[risk] || 'info'
}

function getRiskLabel(risk) {
  return t(`admin.risk.${risk}`, risk)
}

function getAgentResultLabel(status) {
  return getGenericStatusLabel(status)
}

function getGenericStatusLabel(status) {
  return t(`admin.status.${status}`, status)
}

function formatDuration(value) {
  if (!value) return '--'
  return t('admin.common.seconds', {
    value: formatLocaleNumber(value, locale.value, { maximumFractionDigits: 1 })
  })
}

function formatTime(isoStr) {
  if (!isoStr) return '-'
  return formatLocaleDateTime(isoStr, locale.value)
}

function formatNumber(value) {
  return formatLocaleNumber(value || 0, locale.value)
}

function formatPercent(value) {
  return `${formatNumber(value)}%`
}
</script>

<style scoped>
.admin-leader-sessions {
  max-width: 1200px;
  margin: 0 auto;
}

.page-title {
  margin-bottom: 24px;
}

.page-title h2 {
  margin: 0 0 8px;
  font-size: 20px;
}

.page-title p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  flex: 1;
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.section-card {
  margin-bottom: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.detail-content {
  padding: 0 8px;
}

.section {
  margin-top: 24px;
}

.section h4 {
  margin: 0 0 12px;
  font-size: 15px;
}

.result-panel {
  margin-top: 20px;
}

.result-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.result-panel__header h4 {
  margin: 0;
}

.result-panel__header span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.result-meta {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  align-items: center;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.tool-call-list {
  margin-top: 10px;
}

.tool-call-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.result-content {
  margin-top: 12px;
  background: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 4px;
  white-space: pre-wrap;
  font-size: 13px;
  max-height: 200px;
  overflow-y: auto;
}

.decomposition-section {
  margin-top: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px;
}

.subtask-item {
  margin-top: 8px;
  padding: 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}

.subtask-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.subtask-goal {
  font-weight: 500;
  font-size: 13px;
}

.subtask-tools {
  display: flex;
  gap: 4px;
}

.subtask-result {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  max-height: 120px;
  overflow-y: auto;
}

.report-content {
  background: var(--el-fill-color-light);
  padding: 16px;
  border-radius: 8px;
  white-space: pre-wrap;
  font-size: 14px;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .stats-row {
    flex-wrap: wrap;
  }

  .stat-card {
    min-width: calc(50% - 8px);
  }

  .filter-bar {
    flex-direction: column;
  }

  .result-panel__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .detail-content {
    padding: 0 2px 20px;
  }

  :deep(.el-drawer__header) {
    margin-bottom: 12px;
    padding-right: 18px;
  }

  :deep(.el-drawer__body) {
    padding: 12px;
  }
}
</style>
