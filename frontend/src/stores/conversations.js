import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/api'

export const useConversationsStore = defineStore('conversations', () => {
  const conversations = ref([])
  const currentConversation = ref(null)
  const messages = ref([])
  const recentConversations = ref([]) // 缓存最近20条已归档对话

  async function fetchConversations() {
    try {
      const response = await api.get('/api/conversations')
      // API返回格式: { conversations: [...] }
      conversations.value = response.data.conversations || []
      return { success: true }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.error || '获取对话列表失败'
      }
    }
  }

  async function fetchConversation(id) {
    try {
      const response = await api.get(`/api/conversations/${id}`)
      const conversation = response.data.conversation
      const fetchedMessages = response.data.messages

      // 会话级评审模式与历史消息中的 leader_session_id 任一命中，都视为 Leader 历史对话
      const hasLeaderSession = Boolean(conversation?.is_review_mode) ||
        fetchedMessages.some(msg => msg.leader_session_id)

      // 如果有 Leader 会话，先加载历史数据
      if (hasLeaderSession) {
        const leaderStore = await import('./leader').then(m => m.useLeaderStore())
        await leaderStore.loadHistoricalSession(id)
      }

      // 设置对话和消息（过滤掉 Leader 内部过程消息，只保留 user/assistant 聊天消息）
      currentConversation.value = conversation
      messages.value = fetchedMessages.filter(msg => msg.role === 'user' || msg.role === 'assistant')

      // 返回是否是 Leader 会话的标志，供 Chat.vue 使用
      return { success: true, hasLeaderSession }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.error || '获取对话详情失败'
      }
    }
  }

  async function createConversation(title, isReviewMode = false, model = null) {
    try {
      const payload = {
        title,
        is_review_mode: Boolean(isReviewMode)
      }
      if (model) {
        payload.model = model
      }
      const response = await api.post('/api/conversations', payload)
      const newConversation = response.data

      // 同步到两个列表
      conversations.value.unshift(newConversation)
      recentConversations.value.unshift(newConversation)

      // 设置当前对话
      currentConversation.value = newConversation
      messages.value = []

      return { success: true, conversation: newConversation }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.error || '创建对话失败'
      }
    }
  }

  async function updateConversation(id, data) {
    try {
      const response = await api.put(`/api/conversations/${id}`, data)
      const index = conversations.value.findIndex(c => c.id === id)
      if (index !== -1) {
        conversations.value[index] = response.data
      }
      if (currentConversation.value?.id === id) {
        currentConversation.value = response.data
      }
      return { success: true }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.error || '更新对话失败'
      }
    }
  }

  async function deleteConversation(id) {
    try {
      await api.delete(`/api/conversations/${id}`)
      conversations.value = conversations.value.filter(c => c.id !== id)
      // 从历史对话列表中移除
      recentConversations.value = recentConversations.value.filter(c => c.id !== id)
      if (currentConversation.value?.id === id) {
        currentConversation.value = null
        messages.value = []
        
        // 清理 Leader 会话状态（Agent 结果、最终报告等）
        const leaderStore = await import('./leader').then(m => m.useLeaderStore())
        leaderStore.resetState()
      }
      return { success: true }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.error || '删除对话失败'
      }
    }
  }

  async function fetchRecentConversations(limit = 20) {
    try {
      const response = await api.get('/api/conversations', {
        params: {
          limit: limit,
          sort: 'updated_at:desc'
        }
      })
      // API返回格式: { conversations: [...] }
      const data = response.data
      recentConversations.value = data.conversations || []
      return { success: true }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.error || '获取历史对话失败'
      }
    }
  }

  async function archiveCurrentConversation() {
    if (!currentConversation.value) {
      return { success: true }
    }

    try {
      // 归档当前对话
      await api.post(`/api/conversations/${currentConversation.value.id}/archive`)

      // 刷新历史对话列表
      await fetchRecentConversations()

      return { success: true }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.error || '归档对话失败'
      }
    }
  }

  function clearCurrentConversation() {
    currentConversation.value = null
    messages.value = []
  }

  // 编辑消息内容
  async function editMessage(messageId, content) {
    try {
      const response = await api.put(`/api/conversations/messages/${messageId}`, { content })
      return { success: true, message: response.data }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.error || '编辑消息失败'
      }
    }
  }

  // 添加消息到当前对话（用于乐观更新）
  function addMessage(message) {
    messages.value = [...messages.value, message]
  }

  return {
    conversations,
    currentConversation,
    messages,
    recentConversations,
    fetchConversations,
    fetchConversation,
    createConversation,
    updateConversation,
    deleteConversation,
    fetchRecentConversations,
    archiveCurrentConversation,
    clearCurrentConversation,
    addMessage,
    editMessage
  }
})
