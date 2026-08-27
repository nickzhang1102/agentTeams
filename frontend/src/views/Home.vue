<template>
  <div class="home-page">
    <!-- 顶部导航 -->
    <header class="header">
      <div class="container header-content">
        <div class="header-left">
          <div class="logo" @click="router.push('/')">
            <img src="/logo.svg" alt="Agent Teams" class="logo-icon" />
            <span class="logo-text">Agent Teams</span>
          </div>
        </div>

        <div class="header-right">
          <div class="header-actions">
            <LanguageSelector />
            <!-- 用户菜单 -->
            <UserMenuDropdown :auth-store="authStore" />
          </div>
        </div>
      </div>
    </header>

    <!-- Hero 区域 -->
    <section class="hero">
      <div class="container hero-content">
        <h1 class="hero-title animate-slide-up">
          {{ t('home.hero.titleLine1') }}<br/>{{ t('home.hero.titleLine2') }}
        </h1>

        <p class="hero-description animate-slide-up">
          {{ t('home.hero.description') }}
        </p>

        <!-- 核心输入区域 -->
        <div class="main-input-section animate-slide-up">
          <div class="main-input-wrapper">
            <textarea
              v-model="userInput"
              class="main-input"
              :placeholder="t('home.input.placeholder')"
              @keydown.enter.exact.prevent="handleSendMessage"
            ></textarea>

            <!-- 已上传文件列表 -->
            <div v-if="uploadedFiles.length > 0" class="uploaded-files">
              <div v-for="file in uploadedFiles" :key="file.id" class="file-tag">
                <el-icon><Document /></el-icon>
                <span>{{ file.name }}</span>
                <!-- 知识库入库状态角标 -->
                <span
                  v-if="addToKnowledge && knowledgeUploading[file.id]"
                  class="knowledge-badge"
                  :class="'knowledge-badge--' + knowledgeUploading[file.id]"
                >
                  {{ t(`home.files.knowledgeStatus.${knowledgeUploading[file.id]}`) }}
                </span>
                <el-icon class="remove-icon" @click="removeFile(file.id)">
                  <Close />
                </el-icon>
              </div>
              <!-- 加入知识库勾选 -->
              <label class="knowledge-checkbox">
                <input type="checkbox" v-model="addToKnowledge" @change="onKnowledgeToggle" />
                <span>{{ t('home.files.addToKnowledge') }}</span>
              </label>
            </div>

            <div class="input-actions">
              <div class="input-tools">
                <!-- 文件上传 -->
                <button 
                  class="tool-button" 
                  :class="{ 'uploading': uploadingCount > 0 }"
                  @click="triggerFileUpload" 
                  :title="uploadingCount > 0 ? t('home.files.uploading') : t('home.files.upload')"
                >
                  <svg v-if="uploadingCount === 0" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
                  </svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spinner">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 6v6l4 2"/>
                  </svg>
                </button>
                <input
                  ref="fileInput"
                  type="file"
                  multiple
                  accept=".txt,.md,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx"
                  style="display: none"
                  @change="handleFileUpload"
                />

                <!-- 评审模式（默认开启，不可取消） -->
                <button
                  class="tool-button active"
                  disabled
                  :title="t('home.tools.reviewEnabled')"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                    <circle cx="9" cy="7" r="4"/>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                    <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                  </svg>
                  <span class="mode-badge">{{ t('home.tools.review') }}</span>
                </button>

                <!-- 团队方案 -->
                <button
                  class="tool-button"
                  :class="{ active: selectedTemplate }"
                  @click="showTemplatePicker = true"
                  :title="selectedTemplate ? selectedTemplateLabel : t('home.tools.selectTemplate')"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
                  </svg>
                  <span v-if="selectedTemplate" class="mode-badge template-badge">{{ selectedTemplateLabel.length > 4 ? selectedTemplateLabel.slice(0, 4) : selectedTemplateLabel }}</span>
                </button>

                <!-- 模型选择器 -->
                <div class="model-selector">
                  <button
                    class="tool-button model-trigger"
                    :class="{ active: modelDropdownOpen }"
                    @click.stop="toggleModelDropdown"
                    :title="selectedModelName || t('home.tools.selectModel')"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="3"/>
                      <path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72 1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
                    </svg>
                    <span class="model-name">{{ selectedModelName || t('home.tools.model') }}</span>
                    <svg class="model-chevron" :class="{ open: modelDropdownOpen }" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="6 9 12 15 18 9"/>
                    </svg>
                  </button>
                  <Teleport to="body">
                    <transition name="dropdown">
                      <div v-if="modelDropdownOpen" class="model-dropdown" :style="modelDropdownStyle">
                        <button
                          v-for="m in availableModels"
                          :key="m.model_id"
                          class="model-option"
                          :class="{ selected: m.model_id === selectedModel, disabled: m.last_test_ok === false }"
                          :disabled="m.last_test_ok === false"
                          @click="selectModel(m.model_id)"
                        >
                          <span class="model-option-name">{{ m.display_name }}</span>
                          <span v-if="m.last_test_ok === false" class="model-option-warn">⚠</span>
                          <svg v-if="m.model_id === selectedModel" class="model-check" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"/>
                          </svg>
                        </button>
                      </div>
                    </transition>
                  </Teleport>
                </div>
              </div>

              <button
                class="send-button"
                :class="{ 'sending': isSending }"
                :disabled="!userInput.trim() || uploadingCount > 0 || isSending"
                @click="handleSendMessage"
              >
                <span v-if="isSending">{{ t('home.send.sending') }}</span>
                <span v-else>{{ t('home.send.idle') }}</span>
                <svg v-if="!isSending" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spinner">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M12 6v6l4 2"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 快捷入口区 -->
    <section class="quick-access-section">
      <div class="container">
        <div class="quick-access-grid">
          <div
            class="quick-access-card knowledge-card"
            @click="handleKnowledgeClick"
          >
            <div class="card-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                <path d="M8 7h8"/>
                <path d="M8 11h6"/>
              </svg>
            </div>
            <div class="card-content">
              <h3 class="card-title">{{ t('home.knowledge.title') }}</h3>
              <p class="card-desc">{{ t('home.knowledge.description') }}</p>
            </div>
            <div class="card-arrow">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"/>
                <polyline points="12 5 19 12 12 19"/>
              </svg>
            </div>
          </div>

          <!-- Agent Teams 项目引导入口 -->
          <a
            class="quick-access-card partner-card"
            href="https://github.com/nickzhang1102/agentTeams"
            target="_blank"
            rel="noopener noreferrer"
          >
            <div class="card-icon">⚕</div>
            <div class="card-content">
              <h3 class="card-title">{{ t('home.partnerCard.title') }}</h3>
              <p class="card-desc">{{ t('home.partnerCard.description') }}</p>
            </div>
            <div class="card-arrow">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"/>
                <polyline points="12 5 19 12 12 19"/>
              </svg>
            </div>
          </a>
        </div>
      </div>
    </section>

    <!-- 案例区域 -->
    <section class="cases-section">
      <div class="container">
        <!-- Tab 导航 -->
        <div class="tabs">
          <button
            :class="['tab', { active: activeTab === 'featured' }]"
            @click="activeTab = 'featured'"
          >
            {{ t('home.cases.featured') }}
          </button>
          <button
            :class="['tab', { active: activeTab === 'mine' }]"
            @click="activeTab = 'mine'"
          >
            {{ t('home.cases.mine') }}
          </button>
        </div>

        <!-- 精选案例 -->
        <div v-if="activeTab === 'featured'" class="cases-grid">
          <!-- Loading 状态 -->
          <div v-if="featuredLoading" class="loading-state">
            <el-icon class="is-loading" :size="32"><Loading /></el-icon>
            <p>{{ t('home.cases.loading') }}</p>
          </div>

          <template v-else>
            <div
              v-for="caseItem in featuredCases"
              :key="caseItem.id"
              class="case-card"
              @click="handleFeaturedCaseClick(caseItem)"
            >
              <div class="case-content">
                <div class="tag-row">
                  <span class="case-tag" :class="getCategoryClass(caseItem.category)">{{ getCategoryLabel(caseItem.category) }}</span>
                  <span class="status-tag status-completed">{{ t('home.cases.completed') }}</span>
                </div>
                <h3 class="case-title">{{ caseItem.title }}</h3>
                <p class="case-description">{{ caseItem.description }}</p>
              </div>
            </div>

            <div v-if="featuredCases.length === 0" class="empty-state">
              <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
              </svg>
              <p>{{ t('home.cases.noFeatured') }}</p>
              <p class="empty-hint">{{ t('home.cases.featuredAdminHint') }}</p>
            </div>
          </template>
        </div>

        <!-- 我的案例 -->
        <div v-else class="cases-grid">
          <div
            v-for="conversation in recentConversations"
            :key="conversation.id"
            class="case-card"
            @click="handleConversationClick(conversation)"
          >
            <!-- 删除按钮 -->
            <button
              class="delete-btn"
              @click.stop="handleDeleteConversation(conversation)"
              :title="t('home.cases.deleteTitle')"
            >
              <el-icon><Delete /></el-icon>
            </button>
            <div class="case-content">
              <div class="tag-row">
                <span class="case-tag" :class="getCategoryClass(conversation.category)">{{ getCategoryLabel(conversation.category) }}</span>
                <span v-if="conversation.status" class="status-tag" :class="getStatusClass(conversation.status)">{{ getStatusLabel(conversation.status) }}</span>
              </div>
              <h3 class="case-title">{{ conversation.title }}</h3>
              <p class="case-description">{{ conversation.preview }}</p>
              <span class="case-time">{{ formatTime(conversation.updated_at) }}</span>
            </div>
          </div>

          <div v-if="recentConversations.length === 0" class="empty-state">
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="9" y1="9" x2="15" y2="15"/>
              <line x1="15" y1="9" x2="9" y2="15"/>
            </svg>
            <p>{{ t('home.cases.noConversations') }}</p>
            <p class="empty-hint">{{ t('home.cases.startFirst') }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Agent Teams 项目首次引导 -->
    <PartnerProjectGuide v-model:show="showPartnerGuide" />

    <!-- 团队方案快选 -->
    <TemplateQuickPicker
      v-model="showTemplatePicker"
      @select="onTemplateSelect"
    />

    <!-- 首次进入项目主页时的运行时配置引导 -->
    <el-dialog
      v-model="showConfigOnboarding"
      :title="t('home.onboarding.title')"
      width="min(560px, calc(100vw - 32px))"
      append-to-body
      :close-on-click-modal="false"
    >
      <div class="onboarding-content">
        <p>{{ t('home.onboarding.description') }}</p>
        <div class="onboarding-grid">
          <div class="onboarding-item">
            <span class="onboarding-icon">✦</span>
            <div><strong>{{ t('home.onboarding.llmTitle') }}</strong><span>{{ t('home.onboarding.llmDescription') }}</span></div>
          </div>
          <div class="onboarding-item">
            <span class="onboarding-icon">⌕</span>
            <div><strong>{{ t('home.onboarding.searchTitle') }}</strong><span>{{ t('home.onboarding.searchDescription') }}</span></div>
          </div>
        </div>
        <p class="onboarding-note">{{ t('home.onboarding.note') }}</p>
      </div>
      <template #footer>
        <el-button @click="showConfigOnboarding = false">{{ t('home.onboarding.later') }}</el-button>
        <el-button type="primary" @click="openProjectSettings">{{ t('home.onboarding.configure') }}</el-button>
      </template>
    </el-dialog>

    <!-- 固定在页面角落的新手帮助；首次访问自动展开，之后保留浮动入口 -->
    <div v-if="showBeginnerHelp" class="beginner-help" aria-live="polite">
      <transition name="help-popover">
        <div v-if="helpExpanded" class="beginner-help-panel">
          <div class="beginner-help-header">
            <div><strong>{{ t('home.help.title') }}</strong><span>{{ t('home.help.subtitle') }}</span></div>
            <button class="help-close" :aria-label="t('home.help.close')" @click="collapseHelp">×</button>
          </div>
          <div class="help-items">
            <div v-for="item in beginnerHelpItems" :key="item.key" class="help-item">
              <span class="help-item-icon">{{ item.icon }}</span>
              <div><strong>{{ t(`home.help.items.${item.key}.title`) }}</strong><span>{{ t(`home.help.items.${item.key}.description`) }}</span></div>
            </div>
          </div>
          <button class="help-settings-link" @click="openProjectSettings">{{ t('home.help.settings') }} →</button>
        </div>
      </transition>
      <button class="beginner-help-fab" :aria-label="t('home.help.open')" @click="toggleHelp">
        <span>?</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useConversationsStore } from '@/stores/conversations'
import { useLeaderStore } from '@/stores/leader'
import { useDraftStore } from '@/stores/draft'
import { useLocaleStore } from '@/stores/locale'
import { useWorkflowTemplateStore } from '@/stores/workflowTemplate'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Close, Delete, Loading } from '@element-plus/icons-vue'
import api from '@/utils/api'
import dayjs from 'dayjs'
import TemplateQuickPicker from '@/components/TemplateQuickPicker.vue'
import LanguageSelector from '@/components/LanguageSelector.vue'
import UserMenuDropdown from '@/components/UserMenuDropdown.vue'
import PartnerProjectGuide, { PARTNER_GUIDE_SEEN_KEY } from '@/components/PartnerProjectGuide.vue'
import { catalogLabel } from '@/utils/catalog'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const authStore = useAuthStore()
const conversationsStore = useConversationsStore()
const leaderStore = useLeaderStore()
const draftStore = useDraftStore()
const localeStore = useLocaleStore()
const workflowTemplateStore = useWorkflowTemplateStore()

// 判断是否在 ChatLayout 内部（/chat 路径下）
const isInChatLayout = computed(() => route.path.startsWith('/chat'))

// 根据上下文构建对话导航路径
function convPath(token) {
  return isInChatLayout.value ? `/chat/${token}` : `/conversation/${token}`
}

// 状态
const userInput = ref('')
const isReviewMode = ref(true) // 默认选中评审模式，不可取消
const selectedModel = ref(localStorage.getItem('preferred_model') || '')
const availableModels = ref([])
const modelDropdownOpen = ref(false)
const modelDropdownStyle = ref({})
const selectedTemplate = ref(null)
const showTemplatePicker = ref(false)
const showConfigOnboarding = ref(false)
const showPartnerGuide = ref(false)
const showBeginnerHelp = ref(false)
const helpExpanded = ref(false)
const beginnerHelpItems = [
  { key: 'analysis', icon: '✦' },
  { key: 'plan', icon: '▦' },
  { key: 'model', icon: '◉' },
  { key: 'knowledge', icon: '▤' },
  { key: 'cases', icon: '▤' },
]
let selectedTemplateRequestId = 0

const selectedTemplateLabel = computed(() => catalogLabel(selectedTemplate.value))

watch(() => localeStore.locale, async () => {
  if (!selectedTemplate.value?.id) return
  const templateId = selectedTemplate.value.id
  const requestId = ++selectedTemplateRequestId
  try {
    const template = await workflowTemplateStore.fetchTemplate(templateId)
    if (requestId === selectedTemplateRequestId && selectedTemplate.value?.id === templateId) {
      selectedTemplate.value = template
    }
  } catch {
    // Keep the selected stable ID and previous label if refresh fails.
  }
})

const selectedModelName = computed(() => {
  const m = availableModels.value.find(m => m.model_id === selectedModel.value)
  return m ? m.display_name : ''
})

function toggleModelDropdown(e) {
  modelDropdownOpen.value = !modelDropdownOpen.value
  if (modelDropdownOpen.value) {
    const btn = e.currentTarget
    const rect = btn.getBoundingClientRect()
    modelDropdownStyle.value = {
      position: 'fixed',
      bottom: `${window.innerHeight - rect.top + 6}px`,
      left: `${rect.left}px`,
      minWidth: `${rect.width}px`,
    }
  }
}
const activeTab = ref('featured')
const isSending = ref(false)

// 文件上传
const fileInput = ref(null)
const uploadedFiles = ref([])
const uploadingCount = ref(0)

// 知识库入库
const addToKnowledge = ref(false)
const knowledgeUploading = ref({}) // {[fileId]: 'uploading'|'done'|'error'|'duplicate'}

// 文件验证常量
const ALLOWED_FILE_TYPES = [
  '.txt', '.md', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'
]
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
const MAX_FILES = 5

// 精选案例数据（从 API 获取）
const featuredCases = ref([])
const featuredLoading = ref(false)

// 获取精选案例
const fetchFeaturedCases = async () => {
  featuredLoading.value = true
  try {
    const response = await api.get('/api/conversations/featured')
    featuredCases.value = response.data
  } catch (error) {
    console.error('获取精选案例失败:', error)
  } finally {
    featuredLoading.value = false
  }
}

// 计算属性
const recentConversations = computed(() => {
  return conversationsStore.recentConversations || []
})

// 方法
function onTemplateSelect(tpl) {
  selectedTemplate.value = tpl
}

const handleSendMessage = async () => {
  if (!userInput.value.trim() || isSending.value) return

  // 保存当前输入内容（用于后续恢复）
  const messageContent = userInput.value.trim()
  const files = uploadedFiles.value.map(f => ({ id: f.id, name: f.name }))
  const generationLocale = localeStore.locale

  // 检查是否登录
  if (!authStore.isAuthenticated) {
    // 保存草稿，登录后自动继续分析
    draftStore.saveDraftForAnalyze(messageContent, files)
    router.push('/login')
    return
  }

  // 防止在上传过程中发送
  if (uploadingCount.value > 0) {
    ElMessage.warning(t('home.files.waitForUpload'))
    return
  }

  isSending.value = true
  const fileIds = files.map(f => f.id)

  try {
    // 创建新对话
    const result = await conversationsStore.createConversation(
      messageContent, // 使用完整内容作为标题
      isReviewMode.value,
      selectedModel.value || null
    )

    if (!result.success) {
      ElMessage.error(t('home.messages.createConversationFailed'))
      isSending.value = false
      return
    }

    const conversationId = result.conversation.id
    const shareToken = result.conversation.share_token

    // 清空输入并清除草稿
    userInput.value = ''
    uploadedFiles.value = []
    draftStore.clearDraft()

    // ✅ 优化：有了 share_token 后立即跳转到分析界面
    // Leader 会话在 ConversationDisplay.vue 中启动
    if (shareToken) {
      // 通过 store 传递初始消息和文件 ID，避免暴露在 URL 中
      leaderStore.pendingSessionData = {
        message: messageContent,
        fileIds: fileIds,
        templateId: selectedTemplate.value?.id || null,
        locale: generationLocale,
      }
      selectedTemplate.value = null
      router.push(convPath(shareToken))
    } else {
      // 兼容旧数据，使用 id
      router.push(convPath(conversationId))
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    ElMessage.error(error.message || t('home.messages.sendFailed'))
  } finally {
    isSending.value = false
  }
}

// 触发文件选择
const triggerFileUpload = () => {
  // 检查是否登录
  if (!authStore.isAuthenticated) {
    // 保存当前输入内容，登录后返回主页继续编辑
    const messageContent = userInput.value.trim()
    const files = uploadedFiles.value.map(f => ({ id: f.id, name: f.name }))
    draftStore.saveDraftForEdit(messageContent, files)
    ElMessage.warning(t('home.files.loginRequired'))
    router.push('/login')
    return
  }
  fileInput.value?.click()
}

// 处理文件上传
const handleFileUpload = async (event) => {
  const files = event.target.files
  if (!files || files.length === 0) return

  // 检查文件总数限制
  if (files.length > MAX_FILES) {
    ElMessage.error(t('home.files.maxFiles', { count: MAX_FILES }))
    event.target.value = ''
    return
  }

  if (files.length + uploadedFiles.value.length > MAX_FILES) {
    ElMessage.error(t('home.files.remainingFiles', {
      uploaded: uploadedFiles.value.length,
      remaining: MAX_FILES - uploadedFiles.value.length,
    }))
    event.target.value = ''
    return
  }

  for (const file of files) {
    // 验证文件类型
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!ALLOWED_FILE_TYPES.includes(ext)) {
      ElMessage.error(t('home.files.unsupportedType', { extension: ext }))
      continue
    }

    // 验证文件大小
    if (file.size > MAX_FILE_SIZE) {
      ElMessage.error(t('home.files.tooLarge', { name: file.name }))
      continue
    }

    const formData = new FormData()
    formData.append('file', file)

    uploadingCount.value++
    try {
      const response = await fetch('/api/files/upload', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: formData
      })

      const data = await response.json()
      if (data.success) {
        uploadedFiles.value.push({
          id: data.file_id,
          name: file.name,
          rawFile: file
        })
        ElMessage.success(t('home.files.uploadSuccess', { name: file.name }))

        // 勾选了"加入知识库"时，立即触发入库
        if (addToKnowledge.value) {
          uploadToKnowledge(file, data.file_id)
        }
      } else {
        ElMessage.error(data.error || t('home.files.uploadFailed', { name: file.name }))
      }
    } catch (error) {
      ElMessage.error(t('home.files.uploadFailed', { name: file.name }))
      console.error('上传错误:', error)
    } finally {
      uploadingCount.value--
    }
  }

  // 清空文件输入
  event.target.value = ''
}

// 移除已上传文件
const removeFile = (fileId) => {
  uploadedFiles.value = uploadedFiles.value.filter(f => f.id !== fileId)
  delete knowledgeUploading.value[fileId]
}

// 上传文件到知识库
const uploadToKnowledge = async (file, fileId) => {
  knowledgeUploading.value[fileId] = 'uploading'
  try {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('category', 'default')

    await api.post('/api/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    knowledgeUploading.value[fileId] = 'done'
  } catch (error) {
    if (error.response?.status === 409) {
      knowledgeUploading.value[fileId] = 'duplicate'
    } else {
      knowledgeUploading.value[fileId] = 'error'
      console.error('知识库入库失败:', error)
    }
  }
}

// 勾选"加入知识库"时，对已上传文件补触发入库
const onKnowledgeToggle = () => {
  if (!addToKnowledge.value) return
  for (const file of uploadedFiles.value) {
    if (!knowledgeUploading.value[file.id] && file.rawFile) {
      uploadToKnowledge(file.rawFile, file.id)
    }
  }
}

// 精选案例点击 - 跳转到会话详情页
const handleFeaturedCaseClick = (caseItem) => {
  if (caseItem.share_token) {
    window.open(`/conversation/${caseItem.share_token}`, '_blank')
  }
}

const handleConversationClick = (conversation) => {
  // 优先使用 share_token，兼容旧的 id
  if (conversation.share_token) {
    router.push(convPath(conversation.share_token))
  } else {
    router.push(convPath(conversation.id))
  }
}

// 删除对话
const handleDeleteConversation = async (conversation) => {
  try {
    await ElMessageBox.confirm(
      t('home.cases.deleteConfirm'),
      t('home.cases.deleteConfirmTitle'),
      {
        confirmButtonText: t('home.cases.confirmDelete'),
        cancelButtonText: t('common.actions.cancel'),
        type: 'warning'
      }
    )
    
    // 用户确认后执行删除
    const result = await conversationsStore.deleteConversation(conversation.id)
    
    if (result.success) {
      ElMessage.success(t('home.cases.deleted'))
    } else {
      ElMessage.error(result.error || t('home.cases.deleteFailed'))
    }
  } catch {
    // 用户取消删除，不做任何操作
  }
}

// 知识库点击处理
const handleKnowledgeClick = () => {
  if (!authStore.isAuthenticated) {
    router.push('/login')
    return
  }
  router.push('/knowledge')
}

function openProjectSettings() {
  showConfigOnboarding.value = false
  helpExpanded.value = false
  router.push('/project/settings')
}

function toggleHelp() {
  helpExpanded.value = !helpExpanded.value
  if (helpExpanded.value) localStorage.setItem('agent-teams.help-seen', '1')
}

function collapseHelp() {
  helpExpanded.value = false
  localStorage.setItem('agent-teams.help-seen', '1')
}

const formatTime = (time) => {
  return dayjs(time).format('YYYY-MM-DD HH:mm')
}

// 分类映射（样式类基于共享标签派生）
const categoryMap = {
  technology: 'category-technology',
  business: 'category-business',
  medical: 'category-medical',
  investment: 'category-investment',
  science: 'category-science',
  writing: 'category-writing',
  legal: 'category-legal',
  education: 'category-education',
  lifestyle: 'category-lifestyle',
  other: 'category-other',
}

// 状态映射（样式类基于共享标签派生）
const statusMap = {
  new: 'status-new',
  analyzing: 'status-analyzing',
  error: 'status-error',
  completed: 'status-completed',
}

// 获取分类标签
const getCategoryLabel = (category) => {
  return t(`home.categories.${categoryMap[category] ? category : 'other'}`)
}

// 获取分类样式类
const getCategoryClass = (category) => {
  return categoryMap[category] || 'category-other'
}

// 获取状态标签
const getStatusLabel = (status) => {
  return statusMap[status] ? t(`home.statuses.${status}`) : ''
}

// 获取状态样式类
const getStatusClass = (status) => {
  return statusMap[status] || ''
}

// 生命周期
onMounted(async () => {
  // 点击外部关闭模型下拉
  const closeModelDropdown = (e) => {
    if (!e.target.closest('.model-selector')) {
      modelDropdownOpen.value = false
    }
  }
  document.addEventListener('click', closeModelDropdown)
  onBeforeUnmount(() => document.removeEventListener('click', closeModelDropdown))

  // 恢复草稿内容（如果有）
  const draft = draftStore.restoreDraft()
  if (draft.message && draft.mode === 'edit') {
    // 编辑模式：恢复输入内容
    userInput.value = draft.message
    // 注意：文件无法恢复，因为需要重新上传
    if (draft.files && draft.files.length > 0) {
      ElMessage.info(t('home.files.reuploadAttachments'))
    }
    // 清除草稿（文件需要重新上传）
    draftStore.clearDraft()
  }

  // 获取精选案例
  await fetchFeaturedCases()

  if (route.path === '/') {
    const helpSeen = localStorage.getItem('agent-teams.help-seen')
    showBeginnerHelp.value = true
    helpExpanded.value = !helpSeen
    if (authStore.isAuthenticated && !localStorage.getItem('agent-teams.project-onboarding-seen')) {
      showConfigOnboarding.value = true
      localStorage.setItem('agent-teams.project-onboarding-seen', '1')
    }
    // 首次访问时展示 Agent Teams 项目引导
    if (!localStorage.getItem(PARTNER_GUIDE_SEEN_KEY)) {
      showPartnerGuide.value = true
    }
  }

  if (authStore.isAuthenticated) {
    await conversationsStore.fetchRecentConversations(10)
    // 加载可用模型列表
    try {
      const res = await api.get('/api/llm-models')
      availableModels.value = res.data.models || []
      // 默认选中 default_model
      if (!selectedModel.value && res.data.default_model) {
        selectedModel.value = res.data.default_model
      }
    } catch {
      // 静默失败，不影响页面使用
    }
  }

  })

// 模型切换（保存到 localStorage）
function selectModel(modelId) {
  selectedModel.value = modelId
  modelDropdownOpen.value = false
  onModelChange(modelId)
}

function onModelChange(val) {
  if (val) {
    localStorage.setItem('preferred_model', val)
  } else {
    localStorage.removeItem('preferred_model')
  }
}
</script>

<style scoped lang="scss">
.home-page {
  min-height: 100vh;
  background: var(--color-background);
}

.onboarding-content { color: var(--color-text); }
.onboarding-content > p { line-height: 1.65; margin: 0 0 18px; color: var(--color-text-secondary); }
.onboarding-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.onboarding-item { display: flex; gap: 12px; padding: 14px; border: 1px solid var(--color-border); border-radius: 12px; background: var(--color-card); }
.onboarding-icon { display: grid; place-items: center; width: 30px; height: 30px; flex: 0 0 30px; border-radius: 9px; color: var(--color-primary); background: var(--color-primary-light, #eff6ff); font-size: 18px; }
.onboarding-item div { display: flex; flex-direction: column; gap: 5px; }
.onboarding-item span { font-size: 12px; line-height: 1.5; color: var(--color-text-secondary); }
.onboarding-note { margin-top: 16px !important; font-size: 12px; }
/* 抬升到全局主题切换圆钮（bottom: footer+12px，40px 高，顶边在 footer+52px）上方，避免两圆重叠 */
.beginner-help { position: fixed; right: 24px; bottom: calc(var(--footer-height) + 68px); z-index: 1200; display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }
.beginner-help-fab { width: 48px; height: 48px; border: 0; border-radius: 50%; color: #fff; background: var(--color-primary); box-shadow: 0 8px 24px rgba(37, 99, 235, .28); cursor: pointer; font-size: 22px; font-weight: 700; transition: transform .2s, box-shadow .2s; }
.beginner-help-fab:hover, .beginner-help-fab:focus-visible { transform: translateY(-2px); box-shadow: 0 12px 28px rgba(37, 99, 235, .36); outline: none; }
.beginner-help-panel { width: min(350px, calc(100vw - 32px)); padding: 18px; border: 1px solid var(--color-border); border-radius: 16px; background: var(--color-card); box-shadow: 0 16px 40px rgba(15, 23, 42, .18); }
.beginner-help-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--color-border); }
.beginner-help-header div { display: flex; flex-direction: column; gap: 4px; }
.beginner-help-header span { font-size: 12px; color: var(--color-text-secondary); }
.help-close { border: 0; background: transparent; color: var(--color-text-secondary); cursor: pointer; font-size: 20px; line-height: 1; }
.help-items { display: flex; flex-direction: column; gap: 12px; padding: 14px 0; }
.help-item { display: flex; align-items: flex-start; gap: 10px; }
.help-item-icon { display: grid; place-items: center; width: 24px; height: 24px; flex: 0 0 24px; border-radius: 7px; background: var(--color-primary-light, #eff6ff); color: var(--color-primary); font-size: 12px; }
.help-item div { display: flex; flex-direction: column; gap: 2px; }
.help-item span { font-size: 12px; line-height: 1.45; color: var(--color-text-secondary); }
.help-settings-link { padding: 0; border: 0; color: var(--color-primary); background: transparent; cursor: pointer; font-size: 13px; }
.help-popover-enter-active, .help-popover-leave-active { transition: opacity .18s, transform .18s; transform-origin: bottom right; }
.help-popover-enter-from, .help-popover-leave-to { opacity: 0; transform: translateY(8px) scale(.98); }
@media (max-width: 560px) { .onboarding-grid { grid-template-columns: 1fr; } .beginner-help { right: 16px; bottom: calc(var(--footer-height) + 64px); } }

/* 头部导航 */
.header {
  position: sticky;
  top: 0;
  background: var(--color-card);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--color-border);
  z-index: 100;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
}

.header-left {
  display: flex;
  align-items: center;
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
}

.logo-icon {
  width: 32px;
  height: 32px;
}

.logo-text {
  font-family: var(--font-heading);
  font-size: var(--font-size-h4);
  font-weight: 700;
  color: var(--color-text);

  @media (max-width: 640px) {
    display: none;
  }
}

.header-right {
  display: flex;
  align-items: center;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

/* Hero 区域 */
.hero {
  padding: 0 0 var(--spacing-2xl) 0;

  @media (min-width: 768px) {
    padding: 0 0 var(--spacing-3xl) 0;
  }

  text-align: center;
}

.hero-content {
  max-width: 800px;
  margin: 0 auto;
}

.hero-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-h1);
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: var(--spacing-lg);
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-secondary) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  padding: 20px 0 0 0;

  @media (min-width: 768px) {
    font-size: var(--font-size-hero);
  }
}

.hero-description {
  font-size: var(--font-size-base);
  color: #64748B;
  margin-bottom: var(--spacing-2xl);
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;

  @media (min-width: 768px) {
    font-size: var(--font-size-lg);
  }
}

/* 主输入区域 */
.main-input-section {
  margin-top: var(--spacing-lg);

  @media (min-width: 768px) {
    margin-top: var(--spacing-xl);
  }
}

.main-input-wrapper {
  display: flex;
  flex-direction: column;
  background: var(--color-card);
  border: 2px solid var(--color-border);
  padding: var(--spacing-md);
  border-radius: var(--radius-xl);
  transition: all var(--duration-normal) var(--ease-in-out);
  min-height: 260px;

  @media (min-width: 768px) {
    min-height: 300px;
  }

  &:hover,
  &:focus-within {
    border-color: var(--color-primary);
    box-shadow: 0 8px 24px rgba(37, 99, 235, 0.12);
  }
}

.main-input {
  flex: 1;
  width: 100%;
  min-height: 80px;
  padding: 0;
  font-family: var(--font-body);
  font-size: var(--font-size-lg);
  line-height: var(--line-height-relaxed);
  color: var(--color-text);
  background: transparent;
  border: none;
  resize: none;
  outline: none;
  box-shadow: none;

  @media (min-width: 768px) {
    min-height: 100px;
    font-size: var(--font-size-input);
  }

  &:focus {
    outline: none;
    border: none;
    box-shadow: none;
  }

  &::placeholder {
    color: #94A3B8;
  }
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border);
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.input-tools {
  display: flex;
  gap: var(--spacing-sm);
}

.tool-button {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-in-out);

  &:hover {
    background: var(--color-hover);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }

  &.active {
    background: var(--color-primary);
    border-color: var(--color-primary);
    color: white;
  }
}

.mode-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  padding: 2px 6px;
  background: var(--color-cta);
  color: white;
  font-size: 10px;
  font-weight: 600;
  border-radius: 10px;
  line-height: 1.2;
}

.template-badge {
  background: var(--el-color-warning);
  max-width: 48px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-selector {
  position: relative;
}

.model-trigger {
  gap: 4px;
  padding: 0 10px;
  width: auto;
  max-width: 200px;
}

.model-name {
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 110px;
}

.model-chevron {
  flex-shrink: 0;
  transition: transform var(--duration-fast) var(--ease-in-out);
  opacity: 0.6;

  &.open {
    transform: rotate(180deg);
  }
}

.model-dropdown {
  min-width: 180px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  padding: 4px;
  z-index: 9999;
}

.model-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  color: var(--color-text);
  text-align: left;
  transition: background var(--duration-fast) var(--ease-in-out);

  &:hover:not(:disabled) {
    background: var(--color-hover);
  }

  &.selected {
    color: var(--color-primary);
    font-weight: 600;
  }

  &.disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
}

.model-option-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.model-option-warn {
  font-size: 12px;
  color: #f56c6c;
  flex-shrink: 0;
}

.model-check {
  flex-shrink: 0;
  color: var(--color-primary);
}

.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

/* 上传中状态 */
.tool-button.uploading {
  cursor: wait;
  opacity: 0.7;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 已上传文件列表 */
.uploaded-files {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) 0;
  margin-bottom: var(--spacing-sm);
  flex-shrink: 0;
}

.file-tag {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 6px 12px;
  background: rgba(37, 99, 235, 0.08);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-text);
}

.file-tag .remove-icon {
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
  font-size: 14px;
}

.file-tag .remove-icon:hover {
  opacity: 1;
  color: #ef4444;
}

/* 知识库入库状态角标 */
.knowledge-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
}

.knowledge-badge--uploading {
  background: #DBEAFE;
  color: #1D4ED8;
  animation: badge-pulse 1.2s ease-in-out infinite;
}

.knowledge-badge--done {
  background: #D1FAE5;
  color: #047857;
}

.knowledge-badge--duplicate {
  background: #F3F4F6;
  color: #6B7280;
}

.knowledge-badge--error {
  background: #FEE2E2;
  color: #B91C1C;
}

@keyframes badge-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 加入知识库勾选框 */
.knowledge-checkbox {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary, #64748B);
  cursor: pointer;
  user-select: none;

  input[type="checkbox"] {
    width: 14px;
    height: 14px;
    accent-color: var(--color-primary);
    cursor: pointer;
  }
}

.send-button {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 8px 16px;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-in-out);

  @media (min-width: 768px) {
    padding: 10px 20px;
    font-size: var(--font-size-base);
  }

  &:hover:not(:disabled) {
    background: var(--color-secondary);
  }

  &:active:not(:disabled) {
    transform: scale(0.97);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

/* 快捷入口区 */
.quick-access-section {
  padding: var(--spacing-lg) 0 var(--spacing-xl);
  background: var(--color-background);

  @media (min-width: 768px) {
    padding: var(--spacing-xl) 0 var(--spacing-2xl);
  }
}

.quick-access-grid {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.quick-access-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg) var(--spacing-xl);
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: all 0.3s ease;
  max-width: 560px;
  width: 100%;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    border-color: var(--color-primary);
  }

  &:active {
    transform: translateY(-1px);
  }

  @media (max-width: 640px) {
    flex-direction: column;
    text-align: center;
    gap: var(--spacing-md);
    padding: var(--spacing-xl);
  }
}

.card-icon {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary);
  border-radius: var(--radius-lg);
  color: #fff;

  svg {
    width: 28px;
    height: 28px;
  }
}

.card-content {
  flex: 1;
  min-width: 0;
}

.card-title {
  font-size: var(--font-size-h4);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--spacing-xs);
}

.card-desc {
  font-size: var(--font-size-small);
  color: #64748B;
  line-height: 1.5;
}

.card-arrow {
  flex-shrink: 0;
  color: #94A3B8;
  transition: all 0.3s ease;

  .quick-access-card:hover & {
    transform: translateX(4px);
    color: var(--color-primary);
  }

  @media (max-width: 640px) {
    display: none;
  }
}

/* 案例区域 */
.cases-section {
  padding: var(--spacing-xl) 0 var(--spacing-2xl);

  @media (min-width: 768px) {
    padding: var(--spacing-2xl) 0 var(--spacing-3xl);
  }
}

.cases-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--spacing-md);

  @media (min-width: 640px) {
    grid-template-columns: repeat(2, 1fr);
    gap: var(--spacing-lg);
  }
}

.case-card {
  position: relative;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: all var(--duration-normal) var(--ease-in-out);

  &:hover {
    border-color: var(--color-primary);
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(37, 99, 235, 0.12);

    .delete-btn {
      opacity: 1;
    }
  }
}

/* 删除按钮 */
.delete-btn {
  position: absolute;
  bottom: 12px;
  right: 12px;
  z-index: 10;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  opacity: 0;
  color: #94A3B8;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: #FEE2E2;
    border-color: #EF4444;
    color: #EF4444;
  }

  &:active {
    transform: scale(0.95);
  }
}

.case-content {
  padding: var(--spacing-md);

  @media (min-width: 768px) {
    padding: var(--padding-card);
  }
}

.tag-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-sm);
}

.case-tag {
  display: inline-block;
  padding: 4px 12px;
  background: var(--color-primary);
  color: white;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: 500;
}

/* 分类标签颜色 */
.category-technology { background: #3B82F6; }
.category-business { background: #10B981; }
.category-medical { background: #EF4444; }
.category-investment { background: #F59E0B; }
.category-science { background: #8B5CF6; }
.category-writing { background: #EC4899; }
.category-legal { background: #6366F1; }
.category-education { background: #14B8A6; }
.category-lifestyle { background: #F97316; }
.category-other { background: #6B7280; }

/* 状态标签 */
.status-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 10px;
  font-weight: 500;
}

.status-new {
  background: #DBEAFE;
  color: #1D4ED8;
}

.status-analyzing {
  background: #FEF3C7;
  color: #B45309;
}

.status-error {
  background: #FEE2E2;
  color: #B91C1C;
}

.status-completed {
  background: #D1FAE5;
  color: #047857;
}

.case-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-base);
  font-weight: 600;
  margin-bottom: var(--spacing-sm);
  color: var(--color-text);
  
  /* 限制3行显示 */
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;

  @media (min-width: 768px) {
    font-size: var(--font-size-h4);
  }
}

.case-description {
  font-size: var(--font-size-xs);
  color: #64748B;
  margin-bottom: var(--spacing-sm);

  @media (min-width: 768px) {
    font-size: var(--font-size-sm);
  }
}

.case-time {
  font-size: var(--font-size-xs);
  color: #94A3B8;
}

/* 空状态 */
.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: var(--spacing-2xl);
  color: #94A3B8;

  @media (min-width: 768px) {
    padding: var(--spacing-3xl);
  }

  svg {
    margin-bottom: var(--spacing-md);
    opacity: 0.5;
  }

  p {
    margin-bottom: var(--spacing-sm);
  }
}

/* Loading 状态 */
.loading-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: var(--spacing-3xl);
  color: #94A3B8;

  .is-loading {
    margin-bottom: var(--spacing-md);
  }

  p {
    margin-top: var(--spacing-sm);
  }
}

.empty-hint {
  font-size: var(--font-size-sm);
}

/* 移动端工具栏：单行紧凑布局 */
@media (max-width: 640px) {
  .input-actions {
    flex-wrap: nowrap;
    gap: 6px;
  }

  .input-tools {
    gap: 6px;
    flex-shrink: 1;
    min-width: 0;
  }

  .model-name {
    display: none;
  }

  .model-trigger {
    padding: 0 6px;
    max-width: 36px;
  }

  .model-chevron {
    display: none;
  }

  .send-button {
    padding: 6px 10px;
    font-size: 12px;
    flex-shrink: 0;
    white-space: nowrap;
  }

  .tool-button {
    width: 32px;
    height: 32px;
  }
}

/* ===== Agent Teams 引导入口卡片 ===== */
.partner-card {
  text-decoration: none;

  .card-icon {
    font-size: 26px;
    background: linear-gradient(135deg, var(--color-primary), var(--color-success));
  }
}


</style>
