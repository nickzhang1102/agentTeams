import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import api from '@/utils/api'
import { useLocaleStore } from '@/stores/locale'
import { catalogLabel } from '@/utils/catalog'

export const useAgentsStore = defineStore('agents', () => {
  const localeStore = useLocaleStore()
  // State
  const agents = ref([]) // 所有 Agent 列表
  const agentTree = ref({}) // 分类树结构
  const categories = ref([]) // 动态分类列表
  const selectedAgent = ref(null) // 当前选中的 agent
  const loading = ref(false)
  const error = ref(null)
  let agentsRequestId = 0
  let categoriesRequestId = 0
  let treeRequestId = 0
  let userAgentsRequestId = 0
  let agentsLoaded = false
  let categoriesLoaded = false
  let treeLoaded = false
  let userAgentsLoaded = false
  let lastUserAgentParams = {}

  // Getters
  const agentsByCategory = computed(() => {
    // 按分类组织 agents（扁平结构）
    const result = {}
    if (agentTree.value && Object.keys(agentTree.value).length > 0) {
      for (const [categoryKey, category] of Object.entries(agentTree.value)) {
        result[categoryKey] = {
          name: catalogLabel(category),
          label: catalogLabel(category),
          icon: category.icon,
          agents: category.agents
        }
      }
    }
    return result
  })

  // Actions
  async function fetchAgents() {
    const requestId = ++agentsRequestId
    const requestLocale = localeStore.locale
    loading.value = true
    error.value = null
    try {
      const response = await api.get('/api/agents', { params: { locale: requestLocale } })
      if (requestId !== agentsRequestId) return { success: false, stale: true }
      agents.value = response.data.agents || []
      agentsLoaded = true
      if (selectedAgent.value) selectAgent(selectedAgent.value.agent_id || selectedAgent.value.id)
      return { success: true }
    } catch (err) {
      if (requestId !== agentsRequestId) return { success: false, stale: true }
      error.value = err.response?.data?.error || '获取 Agent 列表失败'
      return {
        success: false,
        error: error.value
      }
    } finally {
      if (requestId === agentsRequestId) loading.value = false
    }
  }

  async function fetchCategories() {
    const requestId = ++categoriesRequestId
    const requestLocale = localeStore.locale
    try {
      const response = await api.get('/api/agents/categories', { params: { locale: requestLocale } })
      if (requestId !== categoriesRequestId) return { success: false, stale: true }
      categories.value = response.data.categories || []
      categoriesLoaded = true
      return { success: true, categories: categories.value }
    } catch (err) {
      if (requestId !== categoriesRequestId) return { success: false, stale: true }
      return { success: false, error: err.response?.data?.detail || '获取分类失败' }
    }
  }

  async function fetchAgentTree() {
    const requestId = ++treeRequestId
    const requestLocale = localeStore.locale
    loading.value = true
    error.value = null
    try {
      const response = await api.get('/api/agents/tree', { params: { locale: requestLocale } })
      if (requestId !== treeRequestId) return { success: false, stale: true }
      agentTree.value = response.data.tree || {}
      agents.value = response.data.agents || []
      treeLoaded = true
      if (selectedAgent.value) selectAgent(selectedAgent.value.agent_id || selectedAgent.value.id)
      return { success: true }
    } catch (err) {
      if (requestId !== treeRequestId) return { success: false, stale: true }
      error.value = err.response?.data?.error || '获取 Agent 分类树失败'
      return {
        success: false,
        error: error.value
      }
    } finally {
      if (requestId === treeRequestId) loading.value = false
    }
  }

  function selectAgent(agentId) {
    if (agentId === null || agentId === 'default') {
      selectedAgent.value = null
    } else {
      selectedAgent.value = agents.value.find(a => (a.agent_id || a.id) === agentId) || null
    }
  }

  function clearSelectedAgent() {
    selectedAgent.value = null
  }

  function searchAgents(keyword) {
    if (!keyword || keyword.trim() === '') {
      return agents.value
    }

    const lowerKeyword = keyword.toLowerCase()
    return agents.value.filter(agent =>
      (agent.name || '').toLowerCase().includes(lowerKeyword) ||
      catalogLabel(agent).toLowerCase().includes(lowerKeyword) ||
      (agent.description && agent.description.toLowerCase().includes(lowerKeyword))
    )
  }

  // ==================== 用户端 Agent CRUD ====================

  // 用户端分页状态
  const userAgents = ref([])
  const userPagination = ref({ page: 1, per_page: 12, total: 0, pages: 0 })

  async function fetchUserAgents({ page = 1, perPage = 12, search = '', tags = '', is_system = '', category = '', append = false } = {}) {
    const requestId = ++userAgentsRequestId
    const requestLocale = localeStore.locale
    lastUserAgentParams = { page, perPage, search, tags, is_system, category, append: false }
    loading.value = true
    error.value = null
    try {
      const params = { page: page.toString(), per_page: perPage.toString(), locale: requestLocale }
      if (search) params.search = search
      if (tags) params.tags = tags
      if (is_system) params.is_system = is_system
      if (category) params.category = category
      const response = await api.get('/api/user/agents', { params })
      if (requestId !== userAgentsRequestId) return { success: false, stale: true }
      const newAgents = response.data.agents || []
      userAgents.value = append ? [...userAgents.value, ...newAgents] : newAgents
      userPagination.value = {
        page: response.data.page,
        per_page: response.data.per_page,
        total: response.data.total,
        pages: response.data.pages,
      }
      userAgentsLoaded = true
      return { success: true }
    } catch (err) {
      if (requestId !== userAgentsRequestId) return { success: false, stale: true }
      error.value = err.response?.data?.detail || '获取 Agent 列表失败'
      return { success: false, error: error.value }
    } finally {
      if (requestId === userAgentsRequestId) loading.value = false
    }
  }

  async function fetchUserAgent(agentId) {
    try {
      const response = await api.get(`/api/user/agents/${agentId}`, {
        params: { locale: localeStore.locale },
      })
      return response.data.agent
    } catch (err) {
      return null
    }
  }

  async function createUserAgent(data) {
    try {
      const response = await api.post('/api/user/agents', data)
      return { success: true, agent: response.data.agent }
    } catch (err) {
      return { success: false, error: err.response?.data?.detail || '创建失败' }
    }
  }

  async function updateUserAgent(agentId, data) {
    try {
      const response = await api.put(`/api/user/agents/${agentId}`, data)
      return { success: true, agent: response.data.agent }
    } catch (err) {
      return { success: false, error: err.response?.data?.detail || '更新失败' }
    }
  }

  async function deleteUserAgent(agentId) {
    try {
      await api.delete(`/api/user/agents/${agentId}`)
      return { success: true }
    } catch (err) {
      return { success: false, error: err.response?.data?.detail || '删除失败' }
    }
  }

  async function updateBatchPriority(items) {
    try {
      const resp = await api.patch('/api/agents/priority', { items })
      return { success: true, updated: resp.data.updated }
    } catch (err) {
      return { success: false, error: err.response?.data?.detail || '排序更新失败' }
    }
  }

  watch(() => localeStore.locale, () => {
    if (treeLoaded) fetchAgentTree()
    else if (agentsLoaded) fetchAgents()
    if (categoriesLoaded) fetchCategories()
    if (userAgentsLoaded) fetchUserAgents(lastUserAgentParams)
  })

  return {
    // State
    agents,
    agentTree,
    categories,
    selectedAgent,
    loading,
    error,
    userAgents,
    userPagination,
    // Getters
    agentsByCategory,
    // Actions
    fetchAgents,
    fetchAgentTree,
    fetchCategories,
    selectAgent,
    clearSelectedAgent,
    searchAgents,
    fetchUserAgents,
    fetchUserAgent,
    createUserAgent,
    updateUserAgent,
    deleteUserAgent,
    updateBatchPriority,
  }
})
