<template>
  <div class="admin-openharness">
    <div class="page-header">
      <h2>{{ t('admin.openharness.title') }}</h2>
      <p class="page-desc">{{ t('admin.openharness.description') }}</p>
    </div>

    <!-- 状态概览卡片 -->
    <div class="status-grid" v-if="status">
      <div class="status-card" :class="{ 'is-enabled': status.enabled }">
        <div class="status-icon">
          <el-icon :size="28"><Connection /></el-icon>
        </div>
        <div class="status-info">
          <div class="status-value">{{ status.enabled ? t('admin.status.enabled') : t('admin.status.disabled') }}</div>
          <div class="status-label">OpenHarness v{{ status.version }}</div>
        </div>
      </div>
      <div class="status-card">
        <div class="status-icon tools-icon">
          <el-icon :size="28"><SetUp /></el-icon>
        </div>
        <div class="status-info">
          <div class="status-value">{{ formatNumber(status.tools_count) }}</div>
          <div class="status-label">{{ t('admin.openharness.tools') }}</div>
        </div>
      </div>
      <div class="status-card">
        <div class="status-icon agents-icon">
          <el-icon :size="28"><User /></el-icon>
        </div>
        <div class="status-info">
          <div class="status-value">{{ formatNumber(status.agents_count) }}</div>
          <div class="status-label">{{ t('admin.openharness.agents') }}</div>
        </div>
      </div>
      <div class="status-card">
        <div class="status-icon skills-icon">
          <el-icon :size="28"><MagicStick /></el-icon>
        </div>
        <div class="status-info">
          <div class="status-value">{{ formatNumber(status.skills_count) }} / {{ formatNumber(status.mcp_servers_count) }}</div>
          <div class="status-label">{{ t('admin.openharness.skillsMcp') }}</div>
        </div>
      </div>
    </div>

    <!-- Tab 面板 -->
    <el-tabs v-model="activeTab" type="border-card" @tab-change="handleTabChange">
      <!-- 基础配置 -->
      <el-tab-pane :label="t('admin.openharness.tabs.config')" name="config">
        <div v-loading="configLoading">
          <el-alert
            v-if="configSaved"
            :title="t('admin.openharness.restartRequired')"
            type="warning"
            show-icon
            :closable="true"
            style="margin-bottom: 16px"
          />

          <div v-if="status && status.config" class="config-groups">
            <div v-for="group in configGroups" :key="group.key" class="config-group">
              <h4 class="group-title">{{ group.label }}</h4>
              <div class="config-list">
                <div v-for="key in group.keys" :key="key" class="config-item">
                  <div class="config-info">
                    <div class="config-key">{{ key }}</div>
                    <div class="config-desc">{{ status.config[key]?.description }}</div>
                  </div>
                  <div class="config-control">
                    <template v-if="isBoolConfig(key)">
                      <el-switch
                        v-model="configEdits[key]"
                        active-value="true"
                        inactive-value="false"
                        @change="markChanged(key)"
                      />
                    </template>
                    <template v-else>
                      <el-input
                        v-model="configEdits[key]"
                        size="small"
                        style="width: 160px"
                        @input="markChanged(key)"
                      />
                    </template>
                    <el-tag
                      :type="sourceTagType(status.config[key]?.source)"
                      size="small"
                      class="source-tag"
                    >
                      {{ sourceLabel(status.config[key]?.source) }}
                    </el-tag>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="config-actions">
            <el-button type="primary" :loading="configSaving" :disabled="Object.keys(changedKeys).length === 0" @click="saveConfig">
              {{ t('admin.openharness.saveChanges', { count: formatNumber(Object.keys(changedKeys).length) }) }}
            </el-button>
            <el-button @click="resetConfig">{{ t('admin.actions.reset') }}</el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- 工具管理 -->
      <el-tab-pane :label="t('admin.openharness.tabs.tools')" name="tools">
        <div class="tab-toolbar">
          <el-input
            v-model="toolSearch"
            :placeholder="t('admin.openharness.searchTools')"
            prefix-icon="Search"
            clearable
            size="small"
            style="width: 240px"
          />
          <el-tag type="info" size="small">{{ t('admin.openharness.toolCount', { count: formatNumber(filteredTools.length) }) }}</el-tag>
        </div>
        <el-table :data="filteredTools" stripe size="small" v-loading="toolsLoading" max-height="500">
          <el-table-column prop="name" :label="t('admin.common.name')" width="180">
            <template #default="{ row }">
              <code class="tool-name">{{ row.name }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="description" :label="t('admin.common.description')" min-width="300" show-overflow-tooltip />
          <el-table-column prop="category" :label="t('admin.common.category')" width="120" align="center">
            <template #default="{ row }">
              <el-tag :type="categoryType(row.category)" size="small">{{ categoryLabel(row.category) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="enabled" :label="t('admin.common.status')" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? t('admin.status.active') : t('admin.status.inactive') }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Skills -->
      <el-tab-pane :label="t('admin.openharness.tabs.skills')" name="skills">
        <el-table :data="adminStore.openharnessSkills" stripe size="small" v-loading="skillsLoading" max-height="500">
          <el-table-column prop="name" :label="t('admin.common.name')" width="160" />
          <el-table-column prop="description" :label="t('admin.common.description')" min-width="250" show-overflow-tooltip />
          <el-table-column :label="t('admin.openharness.tools')" width="200">
            <template #default="{ row }">
              <div class="tool-tags">
                <el-tag v-for="t in row.enabled_tools?.slice(0, 3)" :key="t" size="small" type="info" class="tool-tag">{{ t }}</el-tag>
                <el-tag v-if="row.enabled_tools?.length > 3" size="small" type="info">+{{ row.enabled_tools.length - 3 }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="source" :label="t('admin.common.source')" width="120" align="center">
            <template #default="{ row }">
              <el-tag :type="row.source === 'openharness' ? 'warning' : ''" size="small">{{ row.source === 'openharness' ? 'OH' : t('admin.openharness.builtIn') }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.actions.enable')" width="80" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="row.active"
                @change="handleToggleSkill(row.id)"
                size="small"
              />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- MCP 服务器 -->
      <el-tab-pane :label="t('admin.openharness.tabs.mcp')" name="mcp">
        <!-- 预置服务区块 -->
        <div class="preset-services" v-loading="presetLoading">
          <h4 class="section-title">{{ t('admin.openharness.presets') }}</h4>
          <el-alert
            :title="t('admin.openharness.presetHelp')"
            type="info"
            show-icon
            :closable="false"
            style="margin-bottom: 16px"
          />
          <div class="preset-grid">
            <div v-for="preset in mcpPresets" :key="preset.name" class="preset-card">
              <div class="preset-header">
                <span class="preset-name">{{ preset.name }}</span>
                <el-tag :type="preset.category === 'search' ? 'primary' : 'success'" size="small">{{ preset.category }}</el-tag>
              </div>
              <div class="preset-desc">{{ preset.description }}</div>
              <div class="preset-footer">
                <el-tag
                  v-if="preset.credential_setting_key"
                  :type="preset.credential_configured ? 'success' : 'warning'"
                  size="small"
                >{{ preset.credential_configured
                    ? t('admin.openharness.credentialConfigured', { key: preset.credential_setting_key })
                    : t('admin.openharness.credentialMissing', { key: preset.credential_setting_key }) }}</el-tag>
                <el-button
                  v-if="preset.is_enabled"
                  type="success"
                  size="small"
                  disabled
                >{{ t('admin.status.enabled') }}</el-button>
                <el-button
                  v-else-if="preset.is_configured"
                  type="info"
                  size="small"
                  disabled
                >{{ t('admin.openharness.configured') }}</el-button>
                <el-button
                  v-else
                  type="primary"
                  size="small"
                  :disabled="preset.credential_setting_key && !preset.credential_configured"
                  :loading="presetEnabling === preset.name"
                  @click="handleEnablePreset(preset.name)"
                >{{ t('admin.actions.enable') }}</el-button>
              </div>
            </div>
          </div>
        </div>

        <div class="tab-toolbar">
          <span></span>
          <el-button type="primary" size="small" @click="showMcpDialog()">{{ t('admin.openharness.addServer') }}</el-button>
        </div>

        <el-table :data="adminStore.openharnessMcpServers" stripe size="small" v-loading="mcpLoading" max-height="500">
          <el-table-column prop="name" :label="t('admin.common.name')" width="160" />
          <el-table-column prop="transport" :label="t('admin.openharness.transport')" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.transport === 'sse' ? 'warning' : ''" size="small">{{ row.transport?.toUpperCase() }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.openharness.commandUrl')" min-width="250" show-overflow-tooltip>
            <template #default="{ row }">
              <code v-if="row.command">{{ row.command }} {{ (row.args || []).join(' ') }}</code>
              <code v-else-if="row.url">{{ row.url }}</code>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.common.status')" width="80" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="!row.disabled"
                @change="handleToggleMcp(row)"
                size="small"
              />
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.common.operations')" width="120" align="center" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="showMcpDialog(row)">{{ t('admin.actions.edit') }}</el-button>
              <el-popconfirm :title="t('admin.openharness.deleteServerConfirm', { name: row.name })" @confirm="handleDeleteMcp(row.name)">
                <template #reference>
                  <el-button link type="danger" size="small">{{ t('admin.actions.delete') }}</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <!-- MCP 服务器编辑弹窗 -->
        <el-dialog
          v-model="mcpDialogVisible"
          :title="mcpEditName ? t('admin.openharness.editServer') : t('admin.openharness.addMcpServer')"
          width="560px"
          destroy-on-close
        >
          <el-form :model="mcpForm" label-width="100px" size="default">
            <el-form-item :label="t('admin.openharness.serverName')" required>
              <el-input v-model="mcpForm.name" :disabled="!!mcpEditName" placeholder="my-mcp-server" />
            </el-form-item>
            <el-form-item :label="t('admin.openharness.transport')">
              <el-radio-group v-model="mcpForm.transport">
                <el-radio value="stdio">STDIO</el-radio>
                <el-radio value="sse">SSE</el-radio>
              </el-radio-group>
            </el-form-item>
            <template v-if="mcpForm.transport === 'stdio'">
              <el-form-item :label="t('admin.openharness.command')" required>
                <el-input v-model="mcpForm.command" placeholder="npx" />
              </el-form-item>
              <el-form-item :label="t('admin.openharness.arguments')">
                <el-select
                  v-model="mcpForm.args"
                  multiple
                  filterable
                  allow-create
                  default-first-option
                  style="width: 100%"
                  :placeholder="t('admin.openharness.argumentsPlaceholder')"
                />
              </el-form-item>
            </template>
            <template v-else>
              <el-form-item label="URL" required>
                <el-input v-model="mcpForm.url" placeholder="http://localhost:3000/sse" />
              </el-form-item>
            </template>
            <el-form-item :label="t('admin.openharness.environment')">
              <div class="env-list">
                <div v-for="(val, key, idx) in mcpForm.env" :key="idx" class="env-item">
                  <el-input :model-value="key" disabled size="small" style="width: 140px" />
                  <el-input :model-value="val" size="small" style="flex: 1" @input="(v) => mcpForm.env[key] = v" />
                  <el-button :icon="Delete" circle size="small" @click="delete mcpForm.env[key]" />
                </div>
                <div class="env-item">
                  <el-input v-model="newEnvKey" size="small" style="width: 140px" placeholder="KEY" />
                  <el-input v-model="newEnvVal" size="small" style="flex: 1" placeholder="VALUE" />
                  <el-button :icon="Plus" circle size="small" @click="addEnvVar" />
                </div>
              </div>
            </el-form-item>
            <el-form-item :label="t('admin.openharness.initialStatus')">
              <el-switch v-model="mcpForm.enabled" :active-text="t('admin.actions.enable')" :inactive-text="t('admin.actions.disable')" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="mcpDialogVisible = false">{{ t('admin.actions.cancel') }}</el-button>
            <el-button type="primary" :loading="mcpSaving" @click="handleSaveMcp">{{ t('admin.actions.save') }}</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- Agent MCP 权限 -->
      <el-tab-pane :label="t('admin.openharness.tabs.permissions')" name="agent-mcp">
        <div class="tab-toolbar">
          <el-select v-model="agentMcpType" :placeholder="t('admin.openharness.batchByType')" size="small" style="width: 180px">
            <el-option v-for="type in agentTypeValues" :key="type" :label="t(`admin.openharness.agentTypes.${type}`)" :value="type" />
          </el-select>
          <el-button type="primary" size="small" :loading="agentMcpBatchSaving" @click="showBatchMcpDialog">{{ t('admin.openharness.batchConfigure') }}</el-button>
          <span></span>
        </div>

        <el-alert
          :title="t('admin.openharness.permissionsHelp')"
          type="info"
          show-icon
          :closable="false"
          style="margin-bottom: 16px"
        />

        <el-table :data="agentMcpList" stripe size="small" v-loading="agentMcpLoading" max-height="500">
          <el-table-column prop="agent_id" label="Agent" width="200">
            <template #default="{ row }">
              <span class="agent-name">{{ row.agent_id }}</span>
              <el-tag :type="agentTypeTag(row.agent_type)" size="small" style="margin-left: 8px">{{ row.agent_type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.openharness.toolPermissions')" min-width="300">
            <template #default="{ row }">
              <div class="pattern-tags">
                <el-tag v-for="p in row.permissions" :key="p.mcp_tool_pattern" :type="p.enabled ? 'success' : 'info'" size="small" class="pattern-tag">
                  {{ p.mcp_tool_pattern }}
                </el-tag>
                <el-tag v-if="row.permissions?.length === 0" type="warning" size="small">{{ t('admin.openharness.noPermissions') }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.common.operations')" width="100" align="center" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="showAgentMcpDialog(row)">{{ t('admin.openharness.configure') }}</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Agent MCP 权限编辑弹窗 -->
        <el-dialog
          v-model="agentMcpDialogVisible"
          :title="t('admin.openharness.permissionsTitle', { agent: agentMcpEditId })"
          width="600px"
          destroy-on-close
        >
          <el-form label-width="100px" size="default">
            <el-form-item :label="t('admin.openharness.toolPattern')">
              <div class="pattern-list">
                <div v-for="(p, idx) in agentMcpForm.permissions" :key="idx" class="pattern-item">
                  <el-input v-model="p.mcp_tool_pattern" :placeholder="t('admin.openharness.patternExample')" style="flex: 1" />
                  <el-switch v-model="p.enabled" size="small" />
                  <el-button :icon="Delete" circle size="small" @click="agentMcpForm.permissions.splice(idx, 1)" />
                </div>
                <div class="pattern-item add-item">
                  <el-input v-model="newPattern" :placeholder="t('admin.openharness.newPattern')" style="flex: 1" />
                  <el-button :icon="Plus" circle size="small" @click="addPattern" />
                </div>
              </div>
              <div class="pattern-hint">
                <span>{{ t('admin.openharness.patternHint') }}</span>
              </div>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="agentMcpDialogVisible = false">{{ t('admin.actions.cancel') }}</el-button>
            <el-button type="primary" :loading="agentMcpSaving" @click="handleSaveAgentMcp">{{ t('admin.actions.save') }}</el-button>
          </template>
        </el-dialog>

        <!-- 批量配置弹窗 -->
        <el-dialog
          v-model="batchMcpDialogVisible"
          :title="t('admin.openharness.batchTitle', { type: agentMcpTypeLabel })"
          width="600px"
          destroy-on-close
        >
          <el-alert
            :title="t('admin.openharness.batchWarning', { count: formatNumber(batchMcpAffectedCount), type: agentMcpTypeLabel })"
            type="warning"
            show-icon
            :closable="false"
            style="margin-bottom: 16px"
          />
          <el-form label-width="100px" size="default">
            <el-form-item :label="t('admin.openharness.toolPattern')">
              <div class="pattern-list">
                <div v-for="(p, idx) in batchMcpForm.permissions" :key="idx" class="pattern-item">
                  <el-input v-model="p.mcp_tool_pattern" placeholder="mcp__exa__*" style="flex: 1" />
                  <el-switch v-model="p.enabled" size="small" />
                  <el-button :icon="Delete" circle size="small" @click="batchMcpForm.permissions.splice(idx, 1)" />
                </div>
                <div class="pattern-item add-item">
                  <el-input v-model="newBatchPattern" :placeholder="t('admin.openharness.batchNewPattern')" style="flex: 1" />
                  <el-button :icon="Plus" circle size="small" @click="addBatchPattern" />
                </div>
              </div>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="batchMcpDialogVisible = false">{{ t('admin.actions.cancel') }}</el-button>
            <el-button type="primary" :loading="agentMcpBatchSaving" @click="handleSaveBatchMcp">{{ t('admin.openharness.batchSave') }}</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Connection, SetUp, User, MagicStick, Delete, Plus } from '@element-plus/icons-vue'
import { useAdminStore } from '@/stores/admin'
import api from '@/utils/api'
import { formatLocaleNumber } from '@/utils/localeFormat'

const adminStore = useAdminStore()
const { t, locale } = useI18n()
const agentTypeValues = ['medical', 'technical', 'business']

const activeTab = ref('config')
const status = ref(null)
const configLoading = ref(false)
const configSaving = ref(false)
const configSaved = ref(false)
const configEdits = reactive({})
const changedKeys = reactive({})

const toolsLoading = ref(false)
const toolSearch = ref('')

const skillsLoading = ref(false)

const mcpLoading = ref(false)
const mcpDialogVisible = ref(false)
const mcpEditName = ref('')
const mcpSaving = ref(false)

// 预置服务状态
const presetLoading = ref(false)
const mcpPresets = ref([])
const presetEnabling = ref('')

const mcpForm = reactive({
  name: '',
  transport: 'stdio',
  command: '',
  args: [],
  url: '',
  env: {},
  enabled: false,
})
const newEnvKey = ref('')
const newEnvVal = ref('')

// Agent MCP 权限状态
const agentMcpLoading = ref(false)
const agentMcpList = ref([])
const agentMcpType = ref('medical')
const agentMcpDialogVisible = ref(false)
const agentMcpEditId = ref('')
const agentMcpSaving = ref(false)
const agentMcpForm = reactive({ permissions: [] })
const newPattern = ref('')
const batchMcpDialogVisible = ref(false)
const agentMcpBatchSaving = ref(false)
const batchMcpForm = reactive({ permissions: [] })
const newBatchPattern = ref('')
const batchMcpAffectedCount = ref(0)

// 配置分组定义
const configGroups = computed(() => [
  { key: 'core', label: t('admin.openharness.configGroups.core'), keys: ['OPENHARNESS_ENABLED', 'OPENHARNESS_TOOLS_ENABLED', 'OPENHARNESS_COORDINATOR_ENABLED'] },
  { key: 'execution', label: t('admin.openharness.configGroups.execution'), keys: ['OPENHARNESS_TOOLS_TIMEOUT', 'MAX_AGENT_ITERATIONS', 'MAX_AGENT_PARALLEL'] },
  { key: 'memory', label: t('admin.openharness.configGroups.memory'), keys: ['OPENHARNESS_MEMORY_ENABLED', 'OPENHARNESS_MEMORY_MAX_MESSAGES', 'OPENHARNESS_PERMISSION_ENABLED'] },
  { key: 'hooks', label: t('admin.openharness.configGroups.hooks'), keys: ['OPENHARNESS_HOOKS_ENABLED', 'OPENHARNESS_HOOKS_TIMEOUT'] },
  { key: 'paths', label: t('admin.openharness.configGroups.paths'), keys: ['WORKSPACE_DIR'] },
  { key: 'openharness', label: t('admin.openharness.configGroups.openharness'), keys: ['OPENHARNESS_MAX_TOKENS', 'OPENHARNESS_TIMEOUT', 'OPENHARNESS_CONFIG_DIR'] },
])

// 布尔配置项
const BOOL_KEYS = new Set([
  'OPENHARNESS_ENABLED', 'OPENHARNESS_TOOLS_ENABLED', 'OPENHARNESS_COORDINATOR_ENABLED',
  'OPENHARNESS_MEMORY_ENABLED', 'OPENHARNESS_PERMISSION_ENABLED', 'OPENHARNESS_HOOKS_ENABLED',
])

function isBoolConfig(key) {
  return BOOL_KEYS.has(key)
}

// 来源标签
function sourceLabel(source) {
  return source ? t(`admin.openharness.sources.${source}`, source) : ''
}

function sourceTagType(source) {
  return { db: 'success', env: 'warning', default: 'info' }[source] || 'info'
}

// 工具分类
const CATEGORY_TYPE = {
  filesystem: '', system: 'warning', network: 'success',
  integration: 'danger', agent: '', utility: 'info',
}
function categoryLabel(c) { return c ? t(`admin.openharness.categories.${c}`, c) : '' }
function categoryType(c) { return CATEGORY_TYPE[c] || 'info' }

// 过滤工具
const filteredTools = computed(() => {
  const q = toolSearch.value.toLowerCase().trim()
  if (!q) return adminStore.openharnessTools
  return adminStore.openharnessTools.filter(t =>
    t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q)
  )
})

// 加载数据
async function loadStatus() {
  configLoading.value = true
  try {
    const data = await adminStore.fetchOpenHarnessStatus()
    if (data) {
      status.value = data
      // 初始化编辑值
      for (const key of Object.keys(data.config || {})) {
        configEdits[key] = data.config[key].value
      }
    }
  } finally {
    configLoading.value = false
  }
}

async function loadTools() {
  toolsLoading.value = true
  try {
    await adminStore.fetchOpenHarnessTools()
  } finally {
    toolsLoading.value = false
  }
}

async function loadSkills() {
  skillsLoading.value = true
  try {
    await adminStore.fetchOpenHarnessSkills()
  } finally {
    skillsLoading.value = false
  }
}

async function loadMcpServers() {
  mcpLoading.value = true
  try {
    await adminStore.fetchOpenHarnessMcpServers()
  } finally {
    mcpLoading.value = false
  }
}

// 加载预置服务列表
async function loadMcpPresets() {
  presetLoading.value = true
  try {
    const res = await api.get('/api/admin/openharness/mcp-presets')
    mcpPresets.value = res.data.presets || []
  } catch (e) {
    console.error('Failed to load MCP presets:', e)
  } finally {
    presetLoading.value = false
  }
}

// 一键启用预置服务
async function handleEnablePreset(name) {
  presetEnabling.value = name
  try {
    const res = await api.post(`/api/admin/openharness/mcp-presets/${name}/enable`)
    if (res.data.success) {
      if (res.data.already_configured) {
        ElMessage.info(t('admin.openharness.presetConfigured', { name }))
      } else {
        ElMessage.success(t('admin.openharness.presetEnabled', { name }))
      }
      // 刷新预置列表和服务器列表
      await loadMcpPresets()
      await loadMcpServers()
      ElMessage.warning(t('admin.openharness.restartRequired'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail?.message || e.response?.data?.message || t('admin.openharness.enableFailed'))
  } finally {
    presetEnabling.value = ''
  }
}

// 标记配置变更
function markChanged(key) {
  if (status.value?.config?.[key]?.value !== configEdits[key]) {
    changedKeys[key] = true
  } else {
    delete changedKeys[key]
  }
}

// 保存配置
async function saveConfig() {
  if (Object.keys(changedKeys).length === 0) return
  configSaving.value = true
  try {
    const configs = {}
    for (const key of Object.keys(changedKeys)) {
      configs[key] = configEdits[key]
    }
    const result = await adminStore.updateOpenHarnessConfig(configs)
    if (result.success) {
      ElMessage.success(result.message || t('admin.openharness.configSaved'))
      configSaved.value = true
      // 清除变更标记并更新源
      for (const key of Object.keys(changedKeys)) {
        if (status.value?.config?.[key]) {
          status.value.config[key].value = configEdits[key]
          status.value.config[key].source = 'db'
        }
        delete changedKeys[key]
      }
    } else {
      ElMessage.error(result.error || t('admin.errors.saveFailed'))
    }
  } finally {
    configSaving.value = false
  }
}

// 重置配置
function resetConfig() {
  if (status.value?.config) {
    for (const key of Object.keys(status.value.config)) {
      configEdits[key] = status.value.config[key].value
    }
  }
  for (const key of Object.keys(changedKeys)) {
    delete changedKeys[key]
  }
}

// 切换 Skill
async function handleToggleSkill(skillId) {
  const result = await adminStore.toggleOpenHarnessSkill(skillId)
  if (!result.success) {
    ElMessage.error(result.error || t('admin.errors.operationFailed'))
  }
}

// MCP 服务器操作
function showMcpDialog(server = null) {
  mcpEditName.value = server?.name || ''
  mcpForm.name = server?.name || ''
  mcpForm.transport = server?.transport || 'stdio'
  mcpForm.command = server?.command || ''
  mcpForm.args = server?.args || []
  mcpForm.url = server?.url || ''
  mcpForm.env = { ...(server?.env || {}) }
  mcpForm.enabled = server ? !server.disabled : true
  newEnvKey.value = ''
  newEnvVal.value = ''
  mcpDialogVisible.value = true
}

function addEnvVar() {
  if (newEnvKey.value.trim()) {
    mcpForm.env[newEnvKey.value.trim()] = newEnvVal.value
    newEnvKey.value = ''
    newEnvVal.value = ''
  }
}

async function handleSaveMcp() {
  if (!mcpForm.name.trim()) {
    ElMessage.warning(t('admin.openharness.serverNameRequired'))
    return
  }
  mcpSaving.value = true
  try {
    const payload = {
      name: mcpForm.name.trim(),
      transport: mcpForm.transport,
      command: mcpForm.transport === 'stdio' ? mcpForm.command : undefined,
      args: mcpForm.transport === 'stdio' ? mcpForm.args : undefined,
      url: mcpForm.transport === 'sse' ? mcpForm.url : undefined,
      env: Object.keys(mcpForm.env).length > 0 ? mcpForm.env : undefined,
      disabled: !mcpForm.enabled,
    }

    let result
    if (mcpEditName.value) {
      result = await adminStore.updateMcpServer(mcpEditName.value, payload)
    } else {
      result = await adminStore.createMcpServer(payload)
    }

    if (result.success) {
      ElMessage.success(t(mcpEditName.value ? 'admin.openharness.updated' : 'admin.openharness.created'))
      mcpDialogVisible.value = false
      await loadMcpServers()
    } else {
      ElMessage.error(result.error || t('admin.errors.operationFailed'))
    }
  } finally {
    mcpSaving.value = false
  }
}

async function handleToggleMcp(server) {
  const result = await adminStore.updateMcpServer(server.name, { disabled: server.disabled })
  if (result.success) {
    server.disabled = !server.disabled
  } else {
    ElMessage.error(result.error || t('admin.errors.operationFailed'))
  }
}

async function handleDeleteMcp(name) {
  const result = await adminStore.deleteMcpServer(name)
  if (result.success) {
    ElMessage.success(t('admin.openharness.deleted'))
    await loadMcpServers()
  } else {
    ElMessage.error(result.error || t('admin.errors.deleteFailed'))
  }
}

// 懒加载：Tab 切换时加载数据
async function handleTabChange(tab) {
  if (tab === 'tools' && adminStore.openharnessTools.length === 0) {
    await loadTools()
  } else if (tab === 'skills' && adminStore.openharnessSkills.length === 0) {
    await loadSkills()
  } else if (tab === 'mcp' && adminStore.openharnessMcpServers.length === 0) {
    await loadMcpPresets()
    await loadMcpServers()
  } else if (tab === 'agent-mcp' && agentMcpList.value.length === 0) {
    await loadAgentTypes()
  }
}

// Agent MCP 权限相关方法
const agentTypeLabels = ref({})   // key → name，从 API 动态获取
const agentTypeTagMap = ref({})   // key → el-tag type，从 API color 映射
// hex 色 → Element Plus tag type
const COLOR_TO_TAG = { '#e74c3c': 'danger', '#3498db': '', '#2ecc71': 'success', '#9b59b6': 'warning' }
const agentMcpTypeLabel = computed(() => agentTypeLabels.value[agentMcpType.value] || t(`admin.openharness.agentTypes.${agentMcpType.value}`, agentMcpType.value))
function agentTypeTag(type) { return agentTypeTagMap.value[type] || 'info' }

async function loadAgentTypes() {
  agentMcpLoading.value = true
  try {
    const [typesRes, catsRes] = await Promise.all([
      fetch('/api/admin/agent-types', { headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } }),
      fetch('/api/agents/categories', { headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } }),
    ])
    const typesData = await typesRes.json()
    const catsData = await catsRes.json()
    if (catsData.categories) {
      const cats = catsData.categories.filter(c => c.key !== 'all')
      agentTypeLabels.value = Object.fromEntries(cats.map(c => [c.key, c.name]))
      agentTypeTagMap.value = Object.fromEntries(cats.map(c => [c.key, COLOR_TO_TAG[c.color] ?? 'info']))
    }
    if (typesData.types) {
      agentMcpList.value = typesData.types.map(t => ({
        type: t.type,
        agent_type: t.type,
        agents: t.agents || [],
        count: t.count,
        permissions: []
      }))
    }
  } catch (e) {
    console.error('Failed to load agent types:', e)
  } finally {
    agentMcpLoading.value = false
  }
}

async function showAgentMcpDialog(row) {
  agentMcpEditId.value = row.agent_id || row.type
  agentMcpForm.permissions = []
  newPattern.value = ''

  // 加载现有权限配置
  try {
    const response = await fetch(`/api/admin/agents/${agentMcpEditId.value}/mcp-tools`, {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
    const data = await response.json()
    if (data.permissions) {
      agentMcpForm.permissions = data.permissions.map(p => ({
        mcp_tool_pattern: p.mcp_tool_pattern,
        enabled: p.enabled
      }))
    }
  } catch (e) {
    console.error('Failed to load agent MCP permissions:', e)
  }

  agentMcpDialogVisible.value = true
}

function addPattern() {
  if (newPattern.value.trim()) {
    agentMcpForm.permissions.push({
      mcp_tool_pattern: newPattern.value.trim(),
      enabled: true
    })
    newPattern.value = ''
  }
}

async function handleSaveAgentMcp() {
  agentMcpSaving.value = true
  try {
    const response = await fetch(`/api/admin/agents/${agentMcpEditId.value}/mcp-tools`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({
        permissions: agentMcpForm.permissions.filter(p => p.mcp_tool_pattern.trim())
      })
    })
    const data = await response.json()
    if (data.success) {
      ElMessage.success(t('admin.openharness.permissionUpdated', { count: formatNumber(data.updated_count) }))
      agentMcpDialogVisible.value = false
      await loadAgentTypes()
    } else {
      ElMessage.error(data.error || t('admin.errors.saveFailed'))
    }
  } catch (e) {
    ElMessage.error(t('admin.errors.saveFailed'))
  } finally {
    agentMcpSaving.value = false
  }
}

async function showBatchMcpDialog() {
  if (!agentMcpType.value) {
    ElMessage.warning(t('admin.openharness.selectAgentType'))
    return
  }

  batchMcpForm.permissions = []
  newBatchPattern.value = ''

  // 获取该类型的 Agent 数量
  const typeRow = agentMcpList.value.find(t => t.type === agentMcpType.value)
  batchMcpAffectedCount.value = typeRow?.count || 0

  batchMcpDialogVisible.value = true
}

function addBatchPattern() {
  if (newBatchPattern.value.trim()) {
    batchMcpForm.permissions.push({
      mcp_tool_pattern: newBatchPattern.value.trim(),
      enabled: true
    })
    newBatchPattern.value = ''
  }
}

async function handleSaveBatchMcp() {
  agentMcpBatchSaving.value = true
  try {
    const response = await fetch(`/api/admin/agent-types/${agentMcpType.value}/mcp-tools`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({
        permissions: batchMcpForm.permissions.filter(p => p.mcp_tool_pattern.trim())
      })
    })
    const data = await response.json()
    if (data.success) {
      ElMessage.success(t('admin.openharness.batchUpdated', {
        count: formatNumber(data.count),
        type: agentTypeLabels.value[agentMcpType.value] || agentMcpType.value
      }))
      batchMcpDialogVisible.value = false
      await loadAgentTypes()
    } else {
      ElMessage.error(data.error || t('admin.openharness.batchFailed'))
    }
  } catch (e) {
    ElMessage.error(t('admin.openharness.batchFailed'))
  } finally {
    agentMcpBatchSaving.value = false
  }
}

onMounted(async () => {
  await loadStatus()
})

function formatNumber(value) {
  return formatLocaleNumber(value || 0, locale.value)
}
</script>

<style lang="scss" scoped>
.admin-openharness {
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

// 状态卡片
.status-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.status-card {
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);

  &.is-enabled {
    border-left: 3px solid #67c23a;
  }
}

.status-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ecf5ff;
  color: #409eff;

  &.tools-icon { background: #fdf6ec; color: #e6a23c; }
  &.agents-icon { background: #f0f9eb; color: #67c23a; }
  &.skills-icon { background: #fef0f0; color: #f56c6c; }
}

.status-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.status-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

// 配置组
.config-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.config-group {
  .group-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin: 0 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #ebeef5;
  }
}

.config-list {
  display: flex;
  flex-direction: column;
}

.config-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid #f5f5f5;

  &:last-child {
    border-bottom: none;
  }
}

.config-info {
  flex: 1;
  min-width: 0;
}

.config-key {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  font-family: 'SFMono-Regular', Consolas, monospace;
}

.config-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

.config-control {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.source-tag {
  min-width: 64px;
  text-align: center;
}

.config-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

// 工具
.tool-name {
  font-size: 12px;
  font-family: 'SFMono-Regular', Consolas, monospace;
  color: #409eff;
}

.tool-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.tool-tag {
  font-size: 11px;
}

// 工具栏
.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.text-muted {
  color: var(--el-text-color-placeholder);
}

// 环境变量
.env-list {
  width: 100%;
}

.env-item {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

// Agent MCP 权限
.agent-name {
  font-weight: 500;
}

.pattern-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.pattern-tag {
  font-size: 11px;
}

.pattern-list {
  width: 100%;
}

.pattern-item {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;

  &.add-item {
    margin-top: 12px;
  }
}

.pattern-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
}

// 预置服务
.section-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin: 0 0 12px;
}

.preset-services {
  margin-bottom: 20px;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.preset-card {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #e4e7ed;
}

.preset-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.preset-name {
  font-weight: 500;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.preset-desc {
  font-size: 13px;
  color: #606266;
  margin-bottom: 12px;
  line-height: 1.5;
}

.preset-footer {
  display: flex;
  align-items: center;
  gap: 12px;
}

// 响应式
@media (max-width: 1024px) {
  .status-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .status-grid {
    grid-template-columns: 1fr;
  }

  .config-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .config-control {
    width: 100%;
    flex-wrap: wrap;
  }
}
</style>
