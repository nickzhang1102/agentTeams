<template>
  <div class="admin-tools">
    <div class="page-header">
      <h2>{{ t('admin.tools.title') }}</h2>
      <p class="page-desc">{{ t('admin.tools.description') }}</p>
    </div>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" class="tools-tabs">
      <!-- 工具清单 Tab -->
      <el-tab-pane :label="t('admin.tools.catalog')" name="tools">
        <div v-loading="toolListLoading" class="tool-list">
          <div v-for="tool in adminStore.toolList" :key="tool.name" class="tool-card">
            <div class="tool-card-header">
              <div class="tool-title">
                <span class="tool-name">{{ tool.name }}</span>
                <span class="tool-desc-short">({{ tool.description }})</span>
              </div>
              <div class="tool-actions">
                <el-switch
                  v-model="tool.enabled"
                  @change="(val) => handleToggleTool(tool.name, val)"
                  size="small"
                />
                <el-button type="primary" link size="small" @click="openDebugPanel(tool)">
                  {{ t('admin.tools.debug') }}
                </el-button>
              </div>
            </div>

            <!-- 详细说明 -->
            <div v-if="tool.detailed_description" class="tool-detail-desc">
              {{ tool.detailed_description }}
            </div>

            <!-- 参数列表 -->
            <div v-if="getParams(tool.input_schema).length > 0" class="tool-params">
              <span class="params-label">{{ t('admin.tools.parameters') }}:</span>
              <span v-for="(param, idx) in getParams(tool.input_schema)" :key="param.name" class="param-item">
                <code>{{ param.name }}</code>
                <span class="param-type">({{ param.type }})</span>
                <span v-if="param.description" class="param-desc"> - {{ param.description }}</span>
                <span v-if="idx < getParams(tool.input_schema).length - 1">, </span>
              </span>
            </div>
          </div>

          <el-empty v-if="!toolListLoading && adminStore.toolList.length === 0" :description="t('admin.tools.noTools')" />
        </div>
      </el-tab-pane>

      <!-- 调用日志 Tab -->
      <el-tab-pane :label="t('admin.tools.logs')" name="logs">
        <!-- 筛选条件 -->
        <el-card class="filter-card">
          <div class="filter-row">
            <el-input
              v-model="logFilters.agent_id"
              placeholder="Agent ID"
              clearable
              style="width: 180px"
            />
            <el-input
              v-model="logFilters.tool_name"
              :placeholder="t('admin.tools.toolName')"
              clearable
              style="width: 180px"
            />
            <el-select v-model="logFilters.status" :placeholder="t('admin.common.status')" clearable style="width: 120px">
              <el-option :label="t('admin.status.success')" value="success" />
              <el-option :label="t('admin.status.failed')" value="error" />
            </el-select>
            <el-button type="primary" :icon="Search" @click="searchLogs">{{ t('admin.actions.search') }}</el-button>
            <el-button @click="resetLogFilters">{{ t('admin.actions.reset') }}</el-button>
          </div>
        </el-card>

        <!-- 工具统计卡片 -->
        <div class="stats-grid">
          <StatsCard :icon="SetUp" :label="t('admin.tools.totalTools')" :value="statsSummary.totalTools" color="#409eff" />
          <StatsCard :icon="DataLine" :label="t('admin.tools.totalCalls')" :value="statsSummary.totalCalls" color="#67c23a" />
          <StatsCard :icon="CircleCheck" :label="t('admin.tools.averageSuccessRate')" :value="formatPercent(statsSummary.avgSuccessRate)" color="#e6a23c" />
        </div>

        <!-- 工具统计表 -->
        <el-card v-if="adminStore.toolStats.length > 0" class="section-card">
          <template #header>
            <span class="card-title">{{ t('admin.tools.statistics') }}</span>
          </template>
          <el-table :data="adminStore.toolStats" stripe style="width: 100%" size="small">
            <el-table-column prop="tool_name" :label="t('admin.tools.toolName')" min-width="150" />
            <el-table-column prop="total_calls" :label="t('admin.tools.calls')" width="100" align="center" />
            <el-table-column :label="t('admin.tools.successRate')" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="row.success_rate >= 90 ? 'success' : row.success_rate >= 70 ? 'warning' : 'danger'" size="small">
                  {{ row.success_rate }}%
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="avg_time" :label="t('admin.tools.averageDuration')" width="110" align="center">
              <template #default="{ row }">{{ row.avg_time }}s</template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 工具日志表 -->
        <el-card class="section-card">
          <template #header>
            <span class="card-title">{{ t('admin.tools.logs') }}</span>
          </template>
          <el-table :data="adminStore.toolLogs" stripe style="width: 100%" v-loading="logLoading">
            <el-table-column prop="tool_name" :label="t('admin.tools.toolName')" min-width="140" />
            <el-table-column prop="agent_id" label="Agent ID" min-width="120" />
            <el-table-column :label="t('admin.common.status')" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('admin.tools.duration')" width="90" align="center">
              <template #default="{ row }">{{ row.execution_time }}s</template>
            </el-table-column>
            <el-table-column :label="t('admin.common.time')" width="170" align="center">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('admin.common.operations')" width="80" align="center" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="viewLogDetail(row)">{{ t('admin.actions.details') }}</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 分页 -->
          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="currentLogPage"
              :page-size="adminStore.toolLogPagination.per_page"
              :total="adminStore.toolLogPagination.total"
              layout="total, prev, pager, next"
              @current-change="handleLogPageChange"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 调试面板抽屉 -->
    <el-drawer
      v-model="debugPanelVisible"
      :title="t('admin.tools.debugTitle', { name: debugTool?.name || '' })"
      size="550px"
      direction="rtl"
    >
      <template v-if="debugTool">
        <!-- 工具详细说明 -->
        <div class="debug-section">
          <h4>{{ t('admin.tools.toolDescription') }}</h4>
          <p class="debug-tool-desc">{{ debugTool.detailed_description || debugTool.description }}</p>
        </div>

        <!-- 参数输入 -->
        <div class="debug-section">
          <h4>{{ t('admin.tools.parameters') }}</h4>
          <div v-if="getParams(debugTool.input_schema).length > 0" class="debug-params-info">
            <div v-for="param in getParams(debugTool.input_schema)" :key="param.name" class="debug-param-item">
              <code>{{ param.name }}</code>
              <span class="param-type">({{ param.type }})</span>
              <span v-if="param.description" class="param-desc"> - {{ param.description }}</span>
              <span v-if="param.required" class="param-required">*</span>
            </div>
          </div>
          <el-input
            v-model="debugParams"
            type="textarea"
            :rows="6"
            placeholder='{"key": "value"}'
            class="debug-params-input"
          />
          <div class="debug-params-hint">{{ t('admin.tools.jsonHint') }}</div>
        </div>

        <!-- 执行按钮 -->
        <div class="debug-section">
          <el-button
            type="primary"
            :loading="debugExecuting"
            @click="executeDebug"
            style="width: 100%"
          >
            {{ debugExecuting ? t('admin.actions.executing') : t('admin.actions.execute') }}
          </el-button>
        </div>

        <!-- 执行结果 -->
        <div v-if="debugResult" class="debug-section">
          <h4>{{ t('admin.tools.result') }}</h4>
          <div class="debug-result-status">
            <el-tag :type="debugResult.status === 'success' ? 'success' : debugResult.status === 'timeout' ? 'warning' : 'danger'" size="small">
              {{ statusLabel(debugResult.status) }}
            </el-tag>
            <span class="debug-result-time">{{ t('admin.tools.durationSeconds', { value: formatNumber(debugResult.execution_time) }) }}</span>
          </div>
          <pre class="debug-result-output">{{ formatDebugOutput(debugResult) }}</pre>
        </div>
      </template>
    </el-drawer>

    <!-- 日志详情抽屉 -->
    <el-drawer v-model="logDetailVisible" :title="t('admin.tools.detailTitle')" size="500px">
      <template v-if="logDetailData">
        <el-descriptions :column="1" border size="small" class="detail-descriptions">
          <el-descriptions-item :label="t('admin.tools.toolName')">{{ logDetailData.tool_name }}</el-descriptions-item>
          <el-descriptions-item label="Agent ID">{{ logDetailData.agent_id }}</el-descriptions-item>
          <el-descriptions-item :label="t('admin.common.status')">
            <el-tag :type="logDetailData.status === 'success' ? 'success' : 'danger'" size="small">
              {{ statusLabel(logDetailData.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.tools.duration')">{{ logDetailData.execution_time }}s</el-descriptions-item>
          <el-descriptions-item :label="t('admin.common.time')">{{ formatTime(logDetailData.created_at) }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-section" v-if="logDetailData.tool_input">
          <h4>{{ t('admin.tools.input') }}</h4>
          <pre class="detail-json">{{ formatJson(logDetailData.tool_input) }}</pre>
        </div>

        <div class="detail-section" v-if="logDetailData.tool_output">
          <h4>{{ t('admin.tools.output') }}</h4>
          <pre class="detail-json">{{ formatJson(logDetailData.tool_output) }}</pre>
        </div>

        <div class="detail-section" v-if="logDetailData.error_message">
          <h4>{{ t('admin.tools.error') }}</h4>
          <pre class="detail-json detail-error">{{ logDetailData.error_message }}</pre>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search, SetUp, DataLine, CircleCheck } from '@element-plus/icons-vue'
import { useAdminStore } from '@/stores/admin'
import { ElMessage } from 'element-plus'
import StatsCard from '@/components/admin/StatsCard.vue'
import api from '@/utils/api'
import { formatLocaleDateTime, formatLocaleNumber } from '@/utils/localeFormat'

const adminStore = useAdminStore()
const { t, locale } = useI18n()

// Tab 状态
const activeTab = ref('tools')

// 工具清单状态
const toolListLoading = ref(false)

// 日志状态
const logLoading = ref(false)
const currentLogPage = ref(1)
const logFilters = ref({ agent_id: '', tool_name: '', status: '' })

// 调试面板状态
const debugPanelVisible = ref(false)
const debugTool = ref(null)
const debugParams = ref('{}')
const debugExecuting = ref(false)
const debugResult = ref(null)

// 日志详情状态
const logDetailVisible = ref(false)
const logDetailData = ref(null)

// 统计摘要
const statsSummary = computed(() => {
  const stats = adminStore.toolStats
  const totalTools = stats.length
  const totalCalls = stats.reduce((sum, s) => sum + (s.total_calls || 0), 0)
  const avgSuccessRate = totalTools > 0
    ? Math.round(stats.reduce((sum, s) => sum + (s.success_rate || 0), 0) / totalTools)
    : 0
  return { totalTools, totalCalls, avgSuccessRate }
})

// 获取参数列表
function getParams(schema) {
  if (!schema || !schema.properties) return []
  const required = schema.required || []
  return Object.entries(schema.properties).map(([name, prop]) => ({
    name,
    type: prop.type || 'any',
    description: prop.description || '',
    required: required.includes(name)
  }))
}

// 加载工具清单
async function loadToolList() {
  toolListLoading.value = true
  try {
    await adminStore.fetchToolList()
  } finally {
    toolListLoading.value = false
  }
}

// 加载日志数据
async function loadLogs() {
  logLoading.value = true
  try {
    const params = {
      page: currentLogPage.value.toString(),
      per_page: adminStore.toolLogPagination.per_page.toString()
    }
    if (logFilters.value.agent_id) params.agent_id = logFilters.value.agent_id
    if (logFilters.value.tool_name) params.tool_name = logFilters.value.tool_name
    if (logFilters.value.status) params.status = logFilters.value.status

    await Promise.allSettled([
      adminStore.fetchToolLogs(params),
      adminStore.fetchToolStats()
    ])
  } finally {
    logLoading.value = false
  }
}

// 切换工具启用状态
async function handleToggleTool(toolName, enabled) {
  try {
    await adminStore.updateToolConfig(toolName, { enabled })
    ElMessage.success(t('admin.tools.configUpdated', {
      name: toolName,
      status: t(enabled ? 'admin.status.enabled' : 'admin.status.disabled')
    }))
  } catch (err) {
    ElMessage.error(t('admin.tools.configUpdateFailed'))
    // 回滚状态
    const tool = adminStore.toolList.find(t => t.name === toolName)
    if (tool) tool.enabled = !enabled
  }
}

// 打开调试面板
function openDebugPanel(tool) {
  debugTool.value = tool
  debugParams.value = '{}'
  debugResult.value = null
  debugPanelVisible.value = true
}

// 执行调试
async function executeDebug() {
  if (!debugTool.value) return

  // 验证 JSON
  try {
    JSON.parse(debugParams.value)
  } catch {
    ElMessage.error(t('admin.errors.invalidJson'))
    return
  }

  debugExecuting.value = true
  debugResult.value = null

  try {
    const params = JSON.parse(debugParams.value)
    const response = await adminStore.debugTool(debugTool.value.name, params)
    debugResult.value = response.result
  } catch (err) {
    debugResult.value = {
      status: 'error',
      error: err.response?.data?.detail?.message || err.message || t('admin.tools.debugFailed'),
      execution_time: 0
    }
  } finally {
    debugExecuting.value = false
  }
}

// 格式化调试输出
function formatDebugOutput(result) {
  if (!result) return ''
  if (result.error) return result.error
  try {
    return JSON.stringify(result.output, null, 2)
  } catch {
    return String(result.output)
  }
}

// 日志相关方法
function searchLogs() {
  currentLogPage.value = 1
  loadLogs()
}

function resetLogFilters() {
  logFilters.value = { agent_id: '', tool_name: '', status: '' }
  currentLogPage.value = 1
  loadLogs()
}

function handleLogPageChange(page) {
  currentLogPage.value = page
  loadLogs()
}

async function viewLogDetail(row) {
  try {
    const response = await api.get(`/api/admin/tools/logs/${row.id}`)
    logDetailData.value = response.data.log
    logDetailVisible.value = true
  } catch {
    logDetailData.value = row
    logDetailVisible.value = true
  }
}

function formatTime(timeStr) {
  if (!timeStr) return '-'
  return formatLocaleDateTime(timeStr, locale.value)
}

function formatNumber(value) {
  return formatLocaleNumber(value || 0, locale.value)
}

function formatPercent(value) {
  return `${formatNumber(value)}%`
}

function statusLabel(status) {
  if (status === 'success') return t('admin.status.success')
  if (status === 'timeout') return t('admin.status.timeout')
  return t('admin.status.failed')
}

function formatJson(str) {
  if (!str) return ''
  try {
    const obj = typeof str === 'string' ? JSON.parse(str) : str
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(str)
  }
}

onMounted(() => {
  loadToolList()
  loadLogs()
})
</script>

<style lang="scss" scoped>
.admin-tools {
  max-width: 1200px;
}

.page-header {
  margin-bottom: 20px;

  h2 {
    margin: 0 0 8px;
    font-size: 20px;
    color: var(--el-text-color-primary);
  }

  .page-desc {
    margin: 0;
    color: var(--el-text-color-secondary);
    font-size: 14px;
  }
}

.tools-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 20px;
  }
}

// 工具卡片列表
.tool-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tool-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px;
  transition: box-shadow 0.2s;

  &:hover {
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  }
}

.tool-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.tool-title {
  flex: 1;
}

.tool-name {
  font-weight: 600;
  font-size: 15px;
  color: var(--el-text-color-primary);
  margin-right: 8px;
}

.tool-desc-short {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.tool-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.tool-detail-desc {
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 8px;
}

.tool-params {
  font-size: 12px;
  color: var(--el-text-color-secondary);

  .params-label {
    font-weight: 500;
    margin-right: 4px;
  }

  .param-item {
    code {
      background: var(--el-fill-color-light);
      padding: 1px 4px;
      border-radius: 3px;
      font-size: 11px;
    }

    .param-type {
      color: var(--el-text-color-placeholder);
      font-size: 11px;
    }

    .param-desc {
      color: var(--el-text-color-secondary);
    }
  }
}

// 调试面板
.debug-section {
  margin-bottom: 20px;

  h4 {
    margin: 0 0 8px;
    font-size: 14px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }
}

.debug-tool-desc {
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
  background: var(--el-fill-color-light);
  padding: 10px;
  border-radius: 4px;
}

.debug-params-info {
  margin-bottom: 8px;
}

.debug-param-item {
  font-size: 12px;
  margin-bottom: 4px;

  code {
    background: var(--el-fill-color-light);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 11px;
  }

  .param-type {
    color: var(--el-text-color-placeholder);
    font-size: 11px;
  }

  .param-desc {
    color: var(--el-text-color-secondary);
  }

  .param-required {
    color: var(--el-color-danger);
    margin-left: 2px;
  }
}

.debug-params-input {
  :deep(textarea) {
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 12px;
  }
}

.debug-params-hint {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
}

.debug-result-status {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;

  .debug-result-time {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

.debug-result-output {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  font-family: 'Consolas', 'Monaco', monospace;
}

// 日志相关样式
.filter-card {
  margin-bottom: 20px;

  .filter-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    align-items: center;
  }
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.section-card {
  margin-bottom: 20px;
}

.card-title {
  font-weight: 600;
  font-size: 15px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.detail-descriptions {
  margin-bottom: 20px;
}

.detail-section {
  margin-bottom: 20px;

  h4 {
    font-size: 14px;
    color: var(--el-text-color-primary);
    margin: 0 0 8px;
  }
}

.detail-json {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.detail-error {
  background: var(--el-color-danger-light-9);
  border-color: var(--el-color-danger-light-5);
  color: var(--el-color-danger);
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .filter-card .filter-row {
    flex-direction: column;

    .el-input, .el-select {
      width: 100% !important;
    }
  }

  .tool-card-header {
    flex-direction: column;
    gap: 8px;
  }

  .tool-actions {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
