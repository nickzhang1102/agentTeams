import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import api from '@/utils/api'
import { useLocaleStore } from '@/stores/locale'
import { i18n } from '@/locales'

export const useAdminStore = defineStore('admin', () => {
  const localeStore = useLocaleStore()

  function text(key, params) {
    return i18n.global.t(`admin.${key}`, params)
  }

  // 状态
  const isAdmin = ref(false)
  const loading = ref(false)
  const error = ref(null)

  // 仪表盘状态
  const dashboardStats = ref(null)
  const reportQualityInsights = ref(null)
  const reportQualityInsightsLoading = ref(false)
  const reportQualityInsightsError = ref(null)

  // 会话管理状态
  const conversations = ref([])
  const conversationPagination = ref({ page: 1, per_page: 15, total: 0, pages: 0 })
  const conversationFilters = ref({ user_id: '', category: '', status: '' })
  const users = ref([])

  // Agent 管理状态
  const agents = ref([])
  const currentAgent = ref(null)
  const agentPagination = ref({ page: 1, per_page: 20, total: 0, pages: 0 })
  const agentFilters = ref({ search: '', is_enabled: '', is_system: undefined, category: '' })

  // Leader 会话管理状态
  const leaderSessions = ref([])
  const leaderSessionPagination = ref({ page: 1, per_page: 20, total: 0, pages: 0 })
  const leaderSessionFilters = ref({ state: '', risk_level: '', start_date: '', end_date: '' })
  const leaderStats = ref(null)
  const currentLeaderSession = ref(null)

  // 检查管理员权限
  async function checkAdminStatus() {
    try {
      const response = await api.get('/api/admin/dashboard/stats')
      if (response.status === 403) {
        isAdmin.value = false
        return false
      }
      if (response.data) {
        isAdmin.value = true
        return true
      }
      isAdmin.value = false
      return false
    } catch (err) {
      isAdmin.value = false
      return false
    }
  }

  // 获取仪表盘统计数据
  async function fetchDashboardStats() {
    try {
      const response = await api.get('/api/admin/dashboard/stats')
      dashboardStats.value = response.data
    } catch (err) {
      console.error('获取仪表盘统计失败:', err)
    }
  }

  async function fetchReportQualityInsights(period = '30d') {
    reportQualityInsightsLoading.value = true
    reportQualityInsightsError.value = null
    try {
      const response = await api.get('/api/admin/dashboard/report-quality-insights', {
        params: { period }
      })
      reportQualityInsights.value = response.data
      return response.data
    } catch (err) {
      reportQualityInsightsError.value = err.response?.data?.error || text('errors.loadFailed')
      console.error('获取报告质量洞察失败:', err)
      return null
    } finally {
      reportQualityInsightsLoading.value = false
    }
  }

  // 获取会话列表
  async function fetchConversations(page = 1) {
    loading.value = true
    error.value = null
    try {
      const params = {
        page: page.toString(),
        per_page: conversationPagination.value.per_page.toString()
      }
      if (conversationFilters.value.user_id) {
        params.user_id = conversationFilters.value.user_id
      }
      if (conversationFilters.value.category) {
        params.category = conversationFilters.value.category
      }
      if (conversationFilters.value.status) {
        params.status = conversationFilters.value.status
      }
      const response = await api.get('/api/admin/conversations', { params })
      conversations.value = response.data.conversations
      conversationPagination.value = {
        page: response.data.page,
        per_page: response.data.per_page,
        total: response.data.total,
        pages: response.data.pages
      }
    } catch (err) {
      error.value = err.response?.data?.error || text('errors.loadFailed')
    } finally {
      loading.value = false
    }
  }

  // 获取用户列表（筛选用）
  async function fetchUsers() {
    try {
      const response = await api.get('/api/admin/users')
      users.value = response.data.users || []
    } catch (err) {
      console.error('获取用户列表失败:', err)
    }
  }

  // 性能监控状态
  const performanceOverview = ref(null)
  const tokenTrend = ref([])
  const agentPerformance = ref([])

  // 工具调试状态
  const toolLogs = ref([])
  const toolLogPagination = ref({ page: 1, per_page: 20, total: 0 })
  const toolStats = ref([])

  // 工具管理状态（新增）
  const toolList = ref([])
  const toolListLoaded = ref(false)
  let toolListRequestId = 0

  // 系统设置状态
  const settings = ref([])

  // Agent 管理方法

  // 获取 Agent 列表
  async function fetchAgents(page = 1) {
    loading.value = true
    error.value = null
    try {
      const params = {
        page: page.toString(),
        per_page: agentPagination.value.per_page.toString()
      }
      if (agentFilters.value.search) {
        params.search = agentFilters.value.search
      }
      if (agentFilters.value.is_enabled !== '') {
        params.is_enabled = agentFilters.value.is_enabled
      }
      if (agentFilters.value.is_system !== undefined && agentFilters.value.is_system !== '') {
        params.is_system = agentFilters.value.is_system
      }
      if (agentFilters.value.category) {
        params.category = agentFilters.value.category
      }
      const response = await api.get('/api/admin/agents', { params })
      agents.value = response.data.agents
      agentPagination.value = {
        page: response.data.page,
        per_page: response.data.per_page,
        total: response.data.total,
        pages: response.data.pages
      }
    } catch (err) {
      error.value = err.response?.data?.error || text('errors.loadFailed')
    } finally {
      loading.value = false
    }
  }

  // 获取 Agent 详情
  async function fetchAgent(agentId) {
    loading.value = true
    error.value = null
    try {
      const response = await api.get(`/api/admin/agents/${agentId}`)
      currentAgent.value = response.data.agent
      return response.data.agent
    } catch (err) {
      error.value = err.response?.data?.error || text('errors.loadFailed')
      return null
    } finally {
      loading.value = false
    }
  }

  // 创建 Agent
  async function createAgent(data) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/api/admin/agents', data)
      return { success: true, agent: response.data.agent }
    } catch (err) {
      const msg = err.response?.data?.error || text('errors.operationFailed')
      error.value = msg
      return { success: false, error: msg }
    } finally {
      loading.value = false
    }
  }

  // 更新 Agent
  async function updateAgent(agentId, data) {
    loading.value = true
    error.value = null
    try {
      const response = await api.put(`/api/admin/agents/${agentId}`, data)
      return { success: true, agent: response.data.agent }
    } catch (err) {
      const msg = err.response?.data?.error || text('errors.updateFailed')
      error.value = msg
      return { success: false, error: msg }
    } finally {
      loading.value = false
    }
  }

  // 删除 Agent
  async function deleteAgent(agentId, soft = true) {
    loading.value = true
    error.value = null
    try {
      const params = soft ? { soft: 'true' } : {}
      await api.delete(`/api/admin/agents/${agentId}`, { params })
      return { success: true }
    } catch (err) {
      const msg = err.response?.data?.error || text('errors.deleteFailed')
      error.value = msg
      return { success: false, error: msg }
    } finally {
      loading.value = false
    }
  }

  // 切换 Agent 启用/禁用
  async function toggleAgent(agentId) {
    try {
      const response = await api.post(`/api/admin/agents/${agentId}/toggle`)
      // 更新列表中的对应项
      const idx = agents.value.findIndex(a => a.agent_id === agentId)
      if (idx !== -1) {
        agents.value[idx] = response.data.agent
      }
      // 更新当前详情
      if (currentAgent.value && currentAgent.value.agent_id === agentId) {
        currentAgent.value = response.data.agent
      }
      return { success: true, agent: response.data.agent }
    } catch (err) {
      const msg = err.response?.data?.error || text('errors.updateFailed')
      error.value = msg
      return { success: false, error: msg }
    }
  }

  // 同步 Agent（从文件系统到数据库）
  async function syncAgents() {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/api/admin/agents/sync')
      return { success: true, ...response.data }
    } catch (err) {
      const msg = err.response?.data?.error || text('errors.operationFailed')
      error.value = msg
      return { success: false, error: msg }
    } finally {
      loading.value = false
    }
  }

  // AI 生成 Agent 配置
  async function generateAgent(data) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/api/admin/agents/generate', data)
      return { success: true, content: response.data.content, metadata: response.data.metadata }
    } catch (err) {
      const msg = err.response?.data?.detail?.message || err.response?.data?.error || text('errors.operationFailed')
      error.value = msg
      return { success: false, error: msg }
    } finally {
      loading.value = false
    }
  }

  // 获取性能概览
  async function fetchPerformanceOverview(period = 'week') {
    loading.value = true
    error.value = null
    try {
      const response = await api.get('/api/admin/performance/overview', { params: { period } })
      performanceOverview.value = response.data
      return response.data
    } catch (err) {
      error.value = err.response?.data?.error || text('errors.loadFailed')
      return null
    } finally {
      loading.value = false
    }
  }

  // 获取 Token 趋势
  async function fetchTokenTrend(params = {}) {
    try {
      const response = await api.get('/api/admin/performance/tokens', { params })
      tokenTrend.value = response.data.data || []
      return response.data
    } catch (err) {
      console.error('获取Token趋势失败:', err)
      return null
    }
  }

  // 获取 Agent 性能
  async function fetchAgentPerformance() {
    try {
      const response = await api.get('/api/admin/performance/agents')
      agentPerformance.value = response.data.agents || []
      return response.data
    } catch (err) {
      console.error('获取Agent性能失败:', err)
      return null
    }
  }

  // 获取工具日志
  async function fetchToolLogs(params = {}) {
    loading.value = true
    error.value = null
    try {
      const response = await api.get('/api/admin/tools/logs', { params })
      toolLogs.value = response.data.logs || []
      toolLogPagination.value = {
        page: response.data.page || 1,
        per_page: response.data.per_page || 20,
        total: response.data.total || 0
      }
      return response.data
    } catch (err) {
      error.value = err.response?.data?.error || text('errors.loadFailed')
      return null
    } finally {
      loading.value = false
    }
  }

  // 获取工具统计
  async function fetchToolStats() {
    try {
      const response = await api.get('/api/admin/tools/stats')
      toolStats.value = response.data.tool_stats || []
      return response.data
    } catch (err) {
      console.error('获取工具统计失败:', err)
      return null
    }
  }

  // 获取工具清单（新增）
  async function fetchToolList() {
    const requestId = ++toolListRequestId
    const requestLocale = localeStore.locale
    try {
      const response = await api.get('/api/admin/tools', {
        params: { locale: requestLocale }
      })
      if (requestId !== toolListRequestId || requestLocale !== localeStore.locale) {
        return { success: false, stale: true }
      }
      toolList.value = response.data.tools || []
      toolListLoaded.value = true
      return { success: true, ...response.data }
    } catch (err) {
      if (requestId !== toolListRequestId) return { success: false, stale: true }
      console.error('获取工具清单失败:', err)
      return { success: false, error: err.response?.data?.error || text('errors.loadFailed') }
    }
  }

  // 更新工具配置（新增）
  async function updateToolConfig(toolName, config) {
    try {
      const response = await api.put(`/api/admin/tools/${toolName}/config`, config)
      return response.data
    } catch (err) {
      console.error('更新工具配置失败:', err)
      throw err
    }
  }

  // 调试执行工具（新增）
  async function debugTool(toolName, params = {}) {
    try {
      const response = await api.post(`/api/admin/tools/${toolName}/debug`, { params })
      return response.data
    } catch (err) {
      console.error('调试执行工具失败:', err)
      throw err
    }
  }

  // 获取系统设置
  async function fetchSettings() {
    loading.value = true
    error.value = null
    try {
      const response = await api.get('/api/admin/settings')
      settings.value = response.data.settings || []
      return response.data
    } catch (err) {
      error.value = err.response?.data?.error || text('errors.loadFailed')
      return null
    } finally {
      loading.value = false
    }
  }

  // 更新系统设置
  async function updateSetting(key, value) {
    try {
      const response = await api.put(`/api/admin/settings/${key}`, { value })
      const idx = settings.value.findIndex(s => s.key === key)
      if (idx !== -1) {
        settings.value[idx] = response.data.setting
      }
      return { success: true, setting: response.data.setting }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || text('errors.updateFailed') }
    }
  }

  // ==================== OpenHarness 配置 ====================

  // OpenHarness 状态
  const openharnessStatus = ref(null)
  const openharnessTools = ref([])
  const openharnessToolsLoaded = ref(false)
  const openharnessSkills = ref([])
  const openharnessMcpServers = ref([])
  let openharnessToolsRequestId = 0

  // Agent Teams 集成状态
  const agentteamsIntegration = ref(null)

  // 获取 OpenHarness 状态
  async function fetchOpenHarnessStatus() {
    try {
      const response = await api.get('/api/admin/openharness/status')
      openharnessStatus.value = response.data
      return response.data
    } catch (err) {
      console.error('获取OpenHarness状态失败:', err)
      return null
    }
  }

  // 批量更新 OpenHarness 配置
  async function updateOpenHarnessConfig(configs) {
    try {
      const response = await api.put('/api/admin/openharness/config', { configs })
      return { success: true, ...response.data }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || text('errors.updateFailed') }
    }
  }

  // 获取 Agent Teams 集成配置
  async function fetchAgentTeamsIntegration() {
    try {
      const response = await api.get('/api/admin/agentteams-integration')
      agentteamsIntegration.value = response.data
      return { success: true, config: response.data }
    } catch (err) {
      return { success: false, error: err.response?.data?.message || err.response?.data?.error || text('errors.loadFailed') }
    }
  }

  // 更新 Agent Teams 集成配置
  async function updateAgentTeamsIntegration(config) {
    try {
      const response = await api.put('/api/admin/agentteams-integration', config)
      agentteamsIntegration.value = response.data
      return { success: true, config: response.data }
    } catch (err) {
      return { success: false, error: err.response?.data?.message || err.response?.data?.error || text('errors.saveFailed') }
    }
  }

  // 生成 Agent Teams 集成密钥
  async function generateAgentTeamsIntegrationKey() {
    try {
      const response = await api.post('/api/admin/agentteams-integration/generate-key')
      agentteamsIntegration.value = response.data
      return { success: true, config: response.data }
    } catch (err) {
      return { success: false, error: err.response?.data?.message || err.response?.data?.error || text('errors.operationFailed') }
    }
  }

  // 获取工具列表
  async function fetchOpenHarnessTools() {
    const requestId = ++openharnessToolsRequestId
    const requestLocale = localeStore.locale
    try {
      const response = await api.get('/api/admin/openharness/tools', {
        params: { locale: requestLocale }
      })
      if (requestId !== openharnessToolsRequestId || requestLocale !== localeStore.locale) {
        return { success: false, stale: true }
      }
      openharnessTools.value = response.data.tools || []
      openharnessToolsLoaded.value = true
      return { success: true, ...response.data }
    } catch (err) {
      if (requestId !== openharnessToolsRequestId) return { success: false, stale: true }
      console.error('获取工具列表失败:', err)
      return { success: false, error: err.response?.data?.error || text('errors.loadFailed') }
    }
  }

  // 获取 Skills 列表
  async function fetchOpenHarnessSkills() {
    try {
      const response = await api.get('/api/admin/openharness/skills')
      openharnessSkills.value = response.data.skills || []
      return response.data
    } catch (err) {
      console.error('获取Skills列表失败:', err)
      return null
    }
  }

  // 切换 Skill 启用/禁用
  async function toggleOpenHarnessSkill(skillId) {
    try {
      const response = await api.put(`/api/admin/openharness/skills/${skillId}/toggle`)
      // 更新本地状态
      const idx = openharnessSkills.value.findIndex(s => s.id === skillId)
      if (idx !== -1) {
        openharnessSkills.value[idx].active = response.data.active
      }
      return { success: true, ...response.data }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || text('errors.updateFailed') }
    }
  }

  // 获取 MCP 服务器列表
  async function fetchOpenHarnessMcpServers() {
    try {
      const response = await api.get('/api/admin/openharness/mcp-servers')
      openharnessMcpServers.value = response.data.servers || []
      return response.data
    } catch (err) {
      console.error('获取MCP服务器列表失败:', err)
      return null
    }
  }

  // 新增 MCP 服务器
  async function createMcpServer(data) {
    try {
      const response = await api.post('/api/admin/openharness/mcp-servers', data)
      return { success: true, server: response.data.server }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || text('errors.operationFailed') }
    }
  }

  // 更新 MCP 服务器
  async function updateMcpServer(name, data) {
    try {
      const response = await api.put(`/api/admin/openharness/mcp-servers/${name}`, data)
      return { success: true, server: response.data.server }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || text('errors.updateFailed') }
    }
  }

  // 删除 MCP 服务器
  async function deleteMcpServer(name) {
    try {
      await api.delete(`/api/admin/openharness/mcp-servers/${name}`)
      return { success: true }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || text('errors.deleteFailed') }
    }
  }

  // ==================== Leader 会话管理 ====================

  async function fetchLeaderSessions(page = 1) {
    loading.value = true
    error.value = null
    try {
      const params = {
        page: page.toString(),
        per_page: leaderSessionPagination.value.per_page.toString()
      }
      if (leaderSessionFilters.value.state) { params.state = leaderSessionFilters.value.state }
      if (leaderSessionFilters.value.risk_level) { params.risk_level = leaderSessionFilters.value.risk_level }
      if (leaderSessionFilters.value.start_date) { params.start_date = leaderSessionFilters.value.start_date }
      if (leaderSessionFilters.value.end_date) { params.end_date = leaderSessionFilters.value.end_date }

      const response = await api.get('/api/admin/leader/sessions', { params })
      leaderSessions.value = response.data.items || []
      leaderSessionPagination.value = {
        page: response.data.page,
        per_page: response.data.per_page,
        total: response.data.total,
        pages: response.data.pages
      }
      return { success: true }
    } catch (err) {
      error.value = err.response?.data?.error || text('errors.loadFailed')
      return { success: false, error: error.value }
    } finally {
      loading.value = false
    }
  }

  async function fetchLeaderSessionDetail(sessionId) {
    loading.value = true
    error.value = null
    try {
      const response = await api.get(`/api/admin/leader/sessions/${sessionId}`)
      currentLeaderSession.value = response.data
      return { success: true, session: response.data }
    } catch (err) {
      error.value = err.response?.data?.error || text('errors.loadFailed')
      return { success: false, error: error.value }
    } finally {
      loading.value = false
    }
  }

  async function fetchLeaderStats() {
    try {
      const response = await api.get('/api/admin/leader/stats')
      leaderStats.value = response.data
      return { success: true, stats: response.data }
    } catch (err) {
      error.value = err.response?.data?.error || text('errors.loadFailed')
      return { success: false, error: error.value }
    }
  }

  async function adminStopLeaderSession(sessionId) {
    try {
      const response = await api.post(`/api/admin/leader/sessions/${sessionId}/stop`)
      // 更新列表中的状态
      const idx = leaderSessions.value.findIndex(s => s.id === sessionId)
      if (idx >= 0) {
        leaderSessions.value[idx].state = 'stopped'
      }
      return { success: true, ...response.data }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || text('leaderSessions.stopFailed') }
    }
  }

  async function batchDeleteLeaderSessions(sessionIds) {
    try {
      const response = await api.post('/api/admin/leader/sessions/batch-delete', { session_ids: sessionIds })
      return { success: true, ...response.data }
    } catch (err) {
      return { success: false, error: err.response?.data?.message || text('errors.deleteFailed') }
    }
  }

  watch(() => localeStore.locale, () => {
    if (toolListLoaded.value) fetchToolList()
    if (openharnessToolsLoaded.value) fetchOpenHarnessTools()
  })

  return {
    // 状态
    isAdmin,
    loading,
    error,
    dashboardStats,
    reportQualityInsights,
    reportQualityInsightsLoading,
    reportQualityInsightsError,
    conversations,
    conversationPagination,
    conversationFilters,
    users,
    agents,
    currentAgent,
    agentPagination,
    agentFilters,
    performanceOverview,
    tokenTrend,
    agentPerformance,
    toolLogs,
    toolLogPagination,
    toolStats,
    toolList,
    toolListLoaded,
    settings,
    openharnessStatus,
    openharnessTools,
    openharnessToolsLoaded,
    openharnessSkills,
    openharnessMcpServers,
    agentteamsIntegration,
    leaderSessions,
    leaderSessionPagination,
    leaderSessionFilters,
    leaderStats,
    currentLeaderSession,

    // 方法
    checkAdminStatus,
    fetchDashboardStats,
    fetchReportQualityInsights,
    fetchConversations,
    fetchUsers,
    fetchAgents,
    fetchAgent,
    createAgent,
    updateAgent,
    deleteAgent,
    toggleAgent,
    syncAgents,
    generateAgent,
    fetchPerformanceOverview,
    fetchTokenTrend,
    fetchAgentPerformance,
    fetchToolLogs,
    fetchToolStats,
    fetchToolList,
    updateToolConfig,
    debugTool,
    fetchSettings,
    updateSetting,
    fetchOpenHarnessStatus,
    updateOpenHarnessConfig,
    fetchAgentTeamsIntegration,
    updateAgentTeamsIntegration,
    generateAgentTeamsIntegrationKey,
    fetchOpenHarnessTools,
    fetchOpenHarnessSkills,
    toggleOpenHarnessSkill,
    fetchOpenHarnessMcpServers,
    createMcpServer,
    updateMcpServer,
    deleteMcpServer,
    fetchLeaderSessions,
    fetchLeaderSessionDetail,
    fetchLeaderStats,
    adminStopLeaderSession,
    batchDeleteLeaderSessions
  }
})
