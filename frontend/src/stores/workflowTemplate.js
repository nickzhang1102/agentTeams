import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import api from '@/utils/api'
import { useLocaleStore } from '@/stores/locale'

export const useWorkflowTemplateStore = defineStore('workflowTemplate', () => {
  const localeStore = useLocaleStore()
  const templates = ref([])
  const loading = ref(false)
  const pagination = ref({ total: 0, page: 1, per_page: 20 })
  let latestRequestId = 0
  let loaded = false
  let lastParams = {}

  async function fetchTemplates(params = {}) {
    const requestId = ++latestRequestId
    const requestLocale = localeStore.locale
    lastParams = { ...params }
    loading.value = true
    try {
      const response = await api.get('/api/workflow-templates', {
        params: { ...params, locale: requestLocale },
      })
      if (requestId !== latestRequestId) return { success: false, stale: true }
      templates.value = response.data.items || []
      pagination.value = {
        total: response.data.total || 0,
        page: response.data.page || 1,
        per_page: response.data.per_page || 20,
      }
      loaded = true
      return { success: true }
    } catch (err) {
      if (requestId !== latestRequestId) return { success: false, stale: true }
      return { success: false, error: err.response?.data?.error || '获取方案列表失败' }
    } finally {
      if (requestId === latestRequestId) loading.value = false
    }
  }

  async function fetchTemplate(id) {
    const response = await api.get(`/api/workflow-templates/${id}`, {
      params: { locale: localeStore.locale },
    })
    return response.data
  }

  async function createTemplate(data) {
    try {
      const response = await api.post('/api/workflow-templates', data)
      templates.value.unshift(response.data)
      return { success: true, template: response.data }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || '创建方案失败' }
    }
  }

  async function updateTemplate(id, data) {
    try {
      const response = await api.put(`/api/workflow-templates/${id}`, data)
      const idx = templates.value.findIndex(t => t.id === id)
      if (idx >= 0) templates.value[idx] = response.data
      return { success: true, template: response.data }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || '更新方案失败' }
    }
  }

  async function deleteTemplate(id) {
    try {
      await api.delete(`/api/workflow-templates/${id}`)
      templates.value = templates.value.filter(t => t.id !== id)
      return { success: true }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || '删除方案失败' }
    }
  }

  async function applyTemplate(id, data) {
    try {
      const response = await api.post(`/api/workflow-templates/${id}/apply`, data)
      return { success: true, data: response.data }
    } catch (err) {
      return { success: false, error: err.response?.data?.error || '启动方案失败' }
    }
  }

  watch(() => localeStore.locale, () => {
    if (loaded) fetchTemplates(lastParams)
  })

  return {
    templates,
    loading,
    pagination,
    fetchTemplates,
    fetchTemplate,
    createTemplate,
    updateTemplate,
    deleteTemplate,
    applyTemplate,
  }
})
