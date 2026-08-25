/**
 * 草稿状态管理
 * - 保存用户在主页输入的问题和上传的文件
 * - 用于在登录后恢复用户操作
 * - mode: 'edit' 返回主页继续编辑, 'analyze' 直接继续分析
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const DRAFT_KEY = 'agent_teams_draft'

export const useDraftStore = defineStore('draft', () => {
  // 状态
  const message = ref('')
  const files = ref([]) // [{id, name}]
  const timestamp = ref(null)
  const mode = ref('edit') // 'edit' 或 'analyze'

  // 计算属性
  const hasDraft = computed(() => {
    return message.value.trim() !== '' || files.value.length > 0
  })

  // 从 sessionStorage 加载草稿
  function loadFromStorage() {
    try {
      const stored = sessionStorage.getItem(DRAFT_KEY)
      if (stored) {
        const data = JSON.parse(stored)
        message.value = data.message || ''
        files.value = data.files || []
        timestamp.value = data.timestamp || null
        mode.value = data.mode || 'edit'
      }
    } catch (e) {
      console.error('加载草稿失败:', e)
    }
  }

  // 保存到 sessionStorage
  function saveToStorage() {
    try {
      const data = {
        message: message.value,
        files: files.value,
        timestamp: Date.now(),
        mode: mode.value
      }
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify(data))
    } catch (e) {
      console.error('保存草稿失败:', e)
    }
  }

  // 保存草稿（编辑模式 - 上传附件时）
  function saveDraftForEdit(msg, fileList) {
    message.value = msg
    files.value = fileList
    mode.value = 'edit'
    saveToStorage()
  }

  // 保存草稿（分析模式 - 点击开始分析时）
  function saveDraftForAnalyze(msg, fileList) {
    message.value = msg
    files.value = fileList
    mode.value = 'analyze'
    saveToStorage()
  }

  // 恢复草稿
  function restoreDraft() {
    loadFromStorage()
    return {
      message: message.value,
      files: files.value,
      mode: mode.value
    }
  }

  // 清除草稿
  function clearDraft() {
    message.value = ''
    files.value = []
    timestamp.value = null
    mode.value = 'edit'
    sessionStorage.removeItem(DRAFT_KEY)
  }

  // 初始化时加载
  loadFromStorage()

  return {
    // 状态
    message,
    files,
    timestamp,
    mode,
    hasDraft,
    
    // 方法
    saveDraftForEdit,
    saveDraftForAnalyze,
    restoreDraft,
    clearDraft
  }
})