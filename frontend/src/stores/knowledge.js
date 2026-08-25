import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import api from '@/utils/api'
import { useLocaleStore } from '@/stores/locale'
import { i18n } from '@/locales'

export const useKnowledgeStore = defineStore('knowledge', () => {
  const localeStore = useLocaleStore()
  const documents = ref([])
  const status = ref({ total_docs: 0, indexed_docs: 0, pending_docs: 0, graph_stats: null })
  const loading = ref(false)
  const currentCategory = ref(null)
  const graphData = ref(null)
  const graphDataLoading = ref(false)
  const gapAnalysis = ref(null)
  const gapAnalysisLoading = ref(false)

  // 分类相关状态
  const categories = ref([])  // 活跃分类列表（含文档统计）
  const adminCategories = ref([])  // 全部分类列表（Admin 管理）
  const categoriesLoading = ref(false)
  let categoriesRequestId = 0
  let adminCategoriesRequestId = 0
  let categoriesLoaded = false
  let adminCategoriesLoaded = false

  function text(key, params) {
    return i18n.global.t(`knowledge.${key}`, params)
  }

  async function fetchDocuments(category = null) {
    loading.value = true
    currentCategory.value = category
    try {
      const params = category ? { category } : {}
      const response = await api.get('/api/knowledge/documents', { params })
      documents.value = response.data.documents || []
      return { success: true, documents: documents.value }
    } catch (error) {
      console.error('获取文档列表失败:', error)
      return { success: false, error: error.response?.data?.error || text('documents.fetchFailed') }
    } finally {
      loading.value = false
    }
  }

  async function fetchStatus() {
    try {
      const response = await api.get('/api/knowledge/status')
      status.value = response.data
      return { success: true, status: status.value }
    } catch (error) {
      console.error('获取状态失败:', error)
      return { success: false, error: error.response?.data?.error || text('stats.fetchFailed') }
    }
  }

  async function fetchCategories() {
    const requestId = ++categoriesRequestId
    const requestLocale = localeStore.locale
    categoriesLoading.value = true
    try {
      const response = await api.get('/api/knowledge/categories', {
        params: { locale: requestLocale }
      })
      if (requestId !== categoriesRequestId || requestLocale !== localeStore.locale) {
        return { success: false, stale: true }
      }
      categories.value = response.data.categories || []
      categoriesLoaded = true
      return { success: true, categories: categories.value }
    } catch (error) {
      if (requestId !== categoriesRequestId) return { success: false, stale: true }
      console.error('获取分类列表失败:', error)
      return { success: false, error: error.response?.data?.error || text('categories.fetchFailed') }
    } finally {
      if (requestId === categoriesRequestId) categoriesLoading.value = false
    }
  }

  async function fetchAdminCategories() {
    const requestId = ++adminCategoriesRequestId
    const requestLocale = localeStore.locale
    categoriesLoading.value = true
    try {
      const response = await api.get('/api/knowledge/admin/categories', {
        params: { locale: requestLocale }
      })
      if (requestId !== adminCategoriesRequestId || requestLocale !== localeStore.locale) {
        return { success: false, stale: true }
      }
      adminCategories.value = response.data.categories || []
      adminCategoriesLoaded = true
      return { success: true, categories: adminCategories.value }
    } catch (error) {
      if (requestId !== adminCategoriesRequestId) return { success: false, stale: true }
      console.error('获取管理分类列表失败:', error)
      return { success: false, error: error.response?.data?.error || text('categories.fetchFailed') }
    } finally {
      if (requestId === adminCategoriesRequestId) categoriesLoading.value = false
    }
  }

  async function createCategory(data) {
    try {
      const response = await api.post('/api/knowledge/admin/categories', data)
      // 创建成功后刷新列表
      await fetchAdminCategories()
      await fetchCategories()
      return { success: true, category: response.data }
    } catch (error) {
      console.error('创建分类失败:', error)
      return { success: false, error: error.response?.data?.error || text('categories.operationFailed') }
    }
  }

  async function updateCategory(id, data) {
    try {
      const response = await api.put(`/api/knowledge/admin/categories/${id}`, data)
      // 更新成功后刷新列表
      await fetchAdminCategories()
      await fetchCategories()
      return { success: true, category: response.data }
    } catch (error) {
      console.error('更新分类失败:', error)
      return { success: false, error: error.response?.data?.error || text('categories.updateFailed') }
    }
  }

  async function deleteCategory(id) {
    try {
      await api.delete(`/api/knowledge/admin/categories/${id}`)
      // 删除成功后刷新列表
      await fetchAdminCategories()
      await fetchCategories()
      await fetchDocuments(currentCategory.value)
      return { success: true }
    } catch (error) {
      console.error('删除分类失败:', error)
      return { success: false, error: error.response?.data?.error || text('categories.deleteFailed') }
    }
  }

  async function deleteDocument(id) {
    try {
      await api.delete(`/api/knowledge/documents/${id}`)
      // 删除后刷新列表
      await fetchDocuments(currentCategory.value)
      return { success: true }
    } catch (error) {
      console.error('删除文档失败:', error)
      return { success: false, error: error.response?.data?.error || text('messages.deleteFailed') }
    }
  }

  async function previewDocument(id) {
    try {
      const response = await api.get(`/api/knowledge/documents/${id}/preview`)
      return { success: true, data: response.data }
    } catch (error) {
      console.error('预览文档失败:', error)
      return { success: false, error: error.response?.data?.error || text('preview.retry') }
    }
  }

  async function downloadDocument(id, filename) {
    try {
      const response = await api.get(`/api/knowledge/documents/${id}/download`, {
        responseType: 'blob'
      })
      // 创建下载链接
      const url = window.URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      return { success: true }
    } catch (error) {
      console.error('下载文档失败:', error)
      return { success: false, error: error.response?.data?.error || text('messages.downloadFailed') }
    }
  }

  async function uploadDocument(file, category, options = {}) {
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('category', category)
      if (options.allow_duplicate) {
        formData.append('allow_duplicate', 'true')
      }

      const response = await api.post('/api/knowledge/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })

      // 上传成功后刷新列表
      await fetchDocuments(currentCategory.value)
      await fetchStatus()
      await fetchCategories()  // 刷新分类统计

      return { success: true, document: response.data }
    } catch (error) {
      // 409 Conflict: 去重冲突
      if (error.response?.status === 409) {
        return {
          success: false,
          error_code: 'duplicate',
          duplicate_doc_id: error.response.data.duplicate_doc_id,
          content_hash: error.response.data.content_hash
        }
      }
      console.error('上传文档失败:', error)
      return { success: false, error: error.response?.data?.error || text('upload.failed') }
    }
  }

  async function fetchGraphData() {
    graphDataLoading.value = true
    try {
      const response = await api.get('/api/knowledge/graph-data')
      graphData.value = response.data
      return { success: true, data: graphData.value }
    } catch (error) {
      console.error('获取图谱数据失败:', error)
      if (error.response?.status === 404) {
        graphData.value = null
        return { success: true, data: null }
      }
      return { success: false, error: error.response?.data?.error || text('graph.loadFailed') }
    } finally {
      graphDataLoading.value = false
    }
  }

  async function fetchGapAnalysis() {
    gapAnalysisLoading.value = true
    try {
      const response = await api.get('/api/knowledge/gap-analysis')
      gapAnalysis.value = response.data
      return { success: true, data: gapAnalysis.value }
    } catch (error) {
      console.error('知识缺口分析失败:', error)
      if (error.response?.status === 404) {
        gapAnalysis.value = null
        return { success: true, data: null }
      }
      return { success: false, error: error.response?.data?.error || text('gap.failed') }
    } finally {
      gapAnalysisLoading.value = false
    }
  }

  async function refreshIndex() {
    try {
      const response = await api.post('/api/knowledge/refresh-index')
      await fetchStatus()
      return { success: true, result: response.data }
    } catch (error) {
      console.error('刷新索引失败:', error)
      return { success: false, error: error.response?.data?.error || text('messages.refreshFailed') }
    }
  }

  watch(() => localeStore.locale, () => {
    if (categoriesLoaded) fetchCategories()
    if (adminCategoriesLoaded) fetchAdminCategories()
  })

  return {
    documents,
    status,
    loading,
    currentCategory,
    graphData,
    graphDataLoading,
    gapAnalysis,
    gapAnalysisLoading,
    categories,
    adminCategories,
    categoriesLoading,
    fetchDocuments,
    fetchStatus,
    fetchCategories,
    fetchAdminCategories,
    createCategory,
    updateCategory,
    deleteCategory,
    deleteDocument,
    previewDocument,
    downloadDocument,
    uploadDocument,
    fetchGraphData,
    fetchGapAnalysis,
    refreshIndex
  }
})
