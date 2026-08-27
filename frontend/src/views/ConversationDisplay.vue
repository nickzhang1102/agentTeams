<template>
  <div class="conversation-display" :class="{ 'embed-mode': isEmbedMode }">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>{{ t('conversation.display.loading') }}</p>
    </div>

    <div v-else-if="loadError" class="load-error-state">
      <p>{{ loadError }}</p>
      <button v-if="isEmbedMode" class="retry-button" type="button" @click="retryEmbedSession">
        {{ t('leader.evidence.retry') }}
      </button>
    </div>

    <!-- 主内容 -->
    <template v-else>
      <!-- 顶部信息条 -->
      <header class="info-header">
        <div class="header-top">
          <div class="header-left">
            <button v-if="!isEmbedMode" @click="handleBack" class="back-button">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="19" y1="12" x2="5" y2="12"/>
                <polyline points="12 19 5 12 12 5"/>
              </svg>
            </button>
            <div
              class="question-preview"
              :class="{ 'is-mobile': isMobile, expanded: isHeaderExpanded }"
              @click="!isEditingQuestion && (isHeaderExpanded = !isHeaderExpanded)"
            >
              <span class="question-label">{{ t('conversation.display.question') }}</span>
              <!-- 编辑模式 -->
              <template v-if="isEditingQuestion">
                <textarea
                  v-model="editingQuestionText"
                  class="edit-question-textarea"
                  ref="editQuestionTextareaRef"
                  @keydown.enter.ctrl.prevent="saveEditQuestion"
                  @keydown.escape="cancelEditQuestion"
                ></textarea>
                <div class="edit-question-actions">
                  <button class="edit-action-btn save" @click="saveEditQuestion" :disabled="isEditSaving">
                    {{ isEditSaving ? t('conversation.display.saving') : t('conversation.display.save') }}
                  </button>
                  <button class="edit-action-btn cancel" @click="cancelEditQuestion">{{ t('common.actions.cancel') }}</button>
                </div>
              </template>
              <!-- 显示模式 -->
              <template v-else>
                <span class="question-text" :class="{ expanded: isHeaderExpanded }">
                  {{ userQuestion }}
                  <EditIndicator
                    :edited-at="firstUserMessage?.edited_at"
                    :content="firstUserMessage?.content"
                  />
                </span>
                <!-- 编辑按钮（hover 显示） -->
                <button
                  v-if="!isEmbedMode && userMessageId && leaderStore.leaderState === 'completed'"
                  class="edit-question-btn"
                  @click.stop="startEditQuestion"
                  :title="t('conversation.display.editAndRegenerate')"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </button>
              </template>
              <span class="expand-hint">
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :style="{ transform: isHeaderExpanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </span>
            </div>
          </div>
          <div class="header-right">
            <!-- 重新生成按钮 -->
            <button
              v-if="!isEmbedMode && userMessageId && leaderStore.leaderState === 'completed'"
              class="regenerate-btn"
              @click="handleRegenerate"
              :disabled="isRegenerating"
              :title="t('conversation.display.regenerateTitle')"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="{ spinning: isRegenerating }">
                <polyline points="23 4 23 10 17 10"/>
                <polyline points="1 20 1 14 7 14"/>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
              <span>{{ isRegenerating ? t('conversation.display.regenerating') : t('conversation.display.regenerate') }}</span>
            </button>
            <!-- 模型选择器（已隐藏） -->
            <div class="status-badge" :class="statusClass">
              <span class="status-dot"></span>
              <span class="status-text">{{ statusText }}</span>
            </div>
            <span class="time-display">{{ formattedTime }}</span>
            <!-- 停止生成按钮：Leader 运行中显示，置于问题栏最右侧 -->
            <button
              v-if="!isEmbedMode && leaderStore.isActive"
              class="stop-btn"
              @click="handleStop"
              :disabled="leaderStore.stopRequested"
              :title="t('leader.actions.stopGenerating')"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2"/>
              </svg>
              <span>{{ leaderStore.stopRequested ? t('leader.actions.stopSent') : t('leader.actions.stopGenerating') }}</span>
            </button>
          </div>
        </div>
        <!-- 附件列表 -->
        <div v-if="!isEmbedMode && attachments.length > 0" class="header-attachments">
          <span class="attachments-label">{{ t('conversation.display.attachments') }}</span>
          <div class="attachments-list">
            <div
              v-for="file in attachments"
              :key="file.id"
              class="attachment-item"
              @click="handlePreviewFile(file)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              <span class="attachment-name">{{ file.filename }}</span>
            </div>
          </div>
        </div>
      </header>

      <!-- 文件预览对话框 -->
      <el-dialog
        v-model="showPreviewDialog"
        :title="previewFile?.filename || t('conversation.display.filePreview')"
        width="80%"
        top="5vh"
        class="preview-dialog"
      >
        <div v-if="previewLoading" class="preview-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ t('conversation.display.loading') }}</span>
        </div>
        <div v-else-if="previewContent" class="preview-content">
          <pre v-if="!previewIsBinary">{{ previewContent }}</pre>
          <div v-else class="preview-binary">
            <el-icon><Document /></el-icon>
            <p>{{ previewContent }}</p>
          </div>
        </div>
        <template #footer>
          <el-button @click="showPreviewDialog = false">{{ t('conversation.display.close') }}</el-button>
          <el-button type="primary" @click="handleDownloadFile">{{ t('conversation.display.downloadFile') }}</el-button>
        </template>
      </el-dialog>

    <!-- 主体内容：双列布局 -->
    <main class="main-content">
      <!-- 桌面端：使用 Splitpanes -->
      <Splitpanes
        v-if="!isMobile"
        class="default-theme"
        @resize="onSplitResize"
      >
        <!-- 左侧：消息记录 (默认 1/3 宽度) -->
        <Pane :size="isSidebarCollapsed ? 3 : sidebarSize" min-size="3" max-size="50">
          <aside class="message-sidebar" :class="{ collapsed: isSidebarCollapsed }">
            <!-- 收缩/展开按钮 -->
            <button class="collapse-toggle" @click="toggleSidebar">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline :points="isSidebarCollapsed ? '9 18 15 12 9 6' : '15 18 9 12 15 6'"/>
              </svg>
            </button>
            <!-- 标题区域 -->
            <div v-show="!isSidebarCollapsed" class="sidebar-title">
              <span>{{ t('conversation.display.leaderMessages') }}</span>
            </div>
            <div v-show="!isSidebarCollapsed" class="messages-container" ref="messagesContainer">
              <!-- 有 session 时显示 Leader 思考内容 -->
              <LeaderThinking
                v-if="leaderSessionId"
                :session-id="leaderSessionId"
                :allow-stop="!isEmbedMode"
              />
              
              <!-- 正在启动 Leader 会话时显示加载动画 -->
              <div v-else-if="isStartingSession" class="starting-indicator">
                <div class="starting-spinner"></div>
                <p class="starting-text">{{ t('conversation.display.starting') }}</p>
                <p class="starting-hint">{{ t('conversation.display.startingHint') }}</p>
              </div>
              
              <!-- 真正没有数据时才显示空状态 -->
              <div v-else class="empty-state">
                <p>{{ t('conversation.display.noLeaderMessages') }}</p>
              </div>
            </div>
          </aside>
        </Pane>

        <!-- 右侧：报告展示区 (默认 2/3 宽度) -->
        <Pane :size="isSidebarCollapsed ? 97 : 100 - sidebarSize">
          <section class="report-panel">
            <div class="panel-header">
              <div class="tabs">
                <button
                  :class="['tab', { active: activeTab === 'agents' }]"
                  @click="activeTab = 'agents'"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                    <circle cx="9" cy="7" r="4"/>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                    <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                  </svg>
                  <span>{{ t('conversation.display.agentReport') }}</span>
                </button>
                <button
                  :class="['tab', { active: activeTab === 'final' }]"
                  @click="activeTab = 'final'"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/>
                    <polyline points="10 9 9 9 8 9"/>
                  </svg>
                  <span>{{ t('conversation.display.finalReport') }}</span>
                </button>
              </div>
            </div>

            <div class="panel-content" ref="reportContainerRef">
              <!-- Agent 报告标签页 -->
              <div v-show="activeTab === 'agents'" class="agents-view">
                <!-- Agent 面板顶部锚点（用于返回顶部按钮的默认目标） -->
                <div ref="agentPanelTopRef" data-message-id="agent-panel-top"></div>
                <AgentStatusPanel
                  v-if="conversationId"
                  :conversation-id="conversationId"
                  :evidence-detail-enabled="!isEmbedMode"
                  @agent-scroll-target="handleAgentScrollTarget"
                />
                <div v-else class="empty-state">
                  <p>{{ t('conversation.display.noAgentReports') }}</p>
                </div>
              </div>

              <!-- 最终报告标签页 -->
              <div v-show="activeTab === 'final'" class="final-report-view">
                <LeaderFinalReport
                  v-if="conversationId && leaderSessionId"
                  :conversation-id="conversationId"
                  :session-id="leaderSessionId"
                  :evidence-detail-enabled="!isEmbedMode"
                  @report-scroll-target="handleReportScrollTarget"
                />
                <div v-else class="empty-state">
                  <p>{{ t('conversation.display.noFinalReport') }}</p>
                </div>
              </div>

              <!-- 桌面端返回顶部按钮 -->
              <ScrollToTopButton
                v-if="currentScrollTarget && reportContainerRef"
                :target-ref="currentScrollTarget"
                :container-ref="reportContainerRef"
                position-mode="fixed"
              />
            </div>
          </section>
        </Pane>
      </Splitpanes>

      <!-- 移动端：标签切换布局 -->
      <template v-else>
        <!-- 移动端标签切换栏 -->
        <div class="mobile-tab-bar">
          <button
            :class="['mobile-tab', { active: mobileActiveTab === 'messages' }]"
            @click="mobileActiveTab = 'messages'"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <span>{{ t('conversation.display.messagesTab') }}</span>
          </button>
          <button
            :class="['mobile-tab', { active: mobileActiveTab === 'agents' }]"
            @click="mobileActiveTab = 'agents'"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
            <span>Agent</span>
          </button>
          <button
            :class="['mobile-tab', { active: mobileActiveTab === 'final' }]"
            @click="mobileActiveTab = 'final'"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
            <span>{{ t('conversation.display.reportsTab') }}</span>
          </button>
        </div>

        <!-- 移动端内容区域 -->
        <div class="mobile-content">
          <!-- 对话记录标签页 -->
          <div v-show="mobileActiveTab === 'messages'" class="mobile-panel" style="position: relative;">
            <div class="mobile-panel-body" ref="mobileMessagesContainerRef">
              <template v-if="leaderSessionId">
                <div ref="leaderThinkingRef">
                  <LeaderThinking
                    :session-id="leaderSessionId"
                    :allow-stop="!isEmbedMode"
                  />
                </div>
              </template>
              <!-- 正在启动 Leader 会话时显示加载动画 -->
              <div v-else-if="isStartingSession" class="starting-indicator">
                <div class="starting-spinner"></div>
                <p class="starting-text">{{ t('conversation.display.starting') }}</p>
                <p class="starting-hint">{{ t('conversation.display.startingHint') }}</p>
              </div>
              <div v-else class="empty-state">
                <p>{{ t('conversation.display.noConversations') }}</p>
              </div>
            </div>
            <!-- 返回顶部按钮 -->
            <ScrollToTopButton
              v-if="currentScrollTarget && mobileMessagesContainerRef"
              :target-ref="currentScrollTarget"
              :container-ref="mobileMessagesContainerRef"
              position-mode="fixed"
            />
          </div>

          <!-- Agent 报告标签页 -->
          <div v-show="mobileActiveTab === 'agents'" class="mobile-panel" style="position: relative;">
            <div class="mobile-panel-body" ref="mobileAgentContainerRef">
              <!-- Agent 面板顶部锚点（用于返回顶部按钮的默认目标） -->
              <div ref="mobileAgentPanelTopRef" data-message-id="agent-panel-top"></div>
              <AgentStatusPanel
                v-if="conversationId"
                :conversation-id="conversationId"
                :evidence-detail-enabled="!isEmbedMode"
                @agent-scroll-target="handleAgentScrollTarget"
                @agent-expanded="handleAgentExpanded"
              />
              <div v-else class="empty-state">
                <p>{{ t('conversation.display.noAgentReports') }}</p>
              </div>
            </div>
            <!-- 返回顶部按钮 -->
            <ScrollToTopButton
              v-if="currentScrollTarget && mobileAgentContainerRef"
              :target-ref="currentScrollTarget"
              :container-ref="mobileAgentContainerRef"
              position-mode="fixed"
            />
          </div>

          <!-- 最终报告标签页 -->
          <div v-show="mobileActiveTab === 'final'" class="mobile-panel" style="position: relative;">
            <div class="mobile-panel-body" ref="mobileFinalContainerRef">
              <LeaderFinalReport
                v-if="conversationId && leaderSessionId"
                :conversation-id="conversationId"
                :session-id="leaderSessionId"
                :evidence-detail-enabled="!isEmbedMode"
                @report-scroll-target="handleReportScrollTarget"
              />
              <div v-else class="empty-state">
                <p>{{ t('conversation.display.noFinalReport') }}</p>
              </div>
            </div>
            <!-- 返回顶部按钮 -->
            <ScrollToTopButton
              v-if="currentScrollTarget && mobileFinalContainerRef"
              :target-ref="currentScrollTarget"
              :container-ref="mobileFinalContainerRef"
              position-mode="fixed"
            />
          </div>
        </div>
      </template>
    </main>
    </template>

    <!-- Leader 问题对话框 -->
    <LeaderQuestionDialog
      :answer-endpoint="answerEndpoint"
      :include-authorization="!isEmbedMode"
      :reconcile-on-done="!isEmbedMode"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useLeaderStore } from '@/stores/leader'
import { useConversationsStore } from '@/stores/conversations'
import { useContentTranslationStore } from '@/stores/contentTranslation'
import LeaderThinking from '@/components/LeaderThinking.vue'
import AgentStatusPanel from '@/components/AgentStatusPanel.vue'
import LeaderFinalReport from '@/components/LeaderFinalReport.vue'
import LeaderQuestionDialog from '@/components/LeaderQuestionDialog.vue'
import ScrollToTopButton from '@/components/ScrollToTopButton.vue'
import EditIndicator from '@/components/EditIndicator.vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import dayjs from 'dayjs'
import { Loading, Document } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatMessageContent, extractQuestions } from '@/utils/messageContentFormatter'
import api from '@/utils/api'
import { collectLeaderTranslationSources } from '@/utils/contentTranslationSources'
import { useAgentTeamsEmbedAccess } from '@/composables/useAgentTeamsEmbedAccess'

const router = useRouter()
const route = useRoute()
const { t, locale } = useI18n()
const leaderStore = useLeaderStore()
const conversationsStore = useConversationsStore()
const translationStore = useContentTranslationStore()

const props = defineProps({
  token: {
    type: String,
    default: ''
  },
  accessMode: {
    type: String,
    default: 'standard',
    validator: value => ['standard', 'embed'].includes(value)
  }
})

const accessToken = computed(() => props.token || route.params.token || '')
// 判断是否在 ChatLayout 内部（/chat 路径下）
const isInChatLayout = computed(() => route.path.startsWith('/chat'))
const isEmbedMode = computed(() => props.accessMode === 'embed')
// 只有 /chat 由路由守卫确认真实 owner 身份；公开分享页即使残留登录态也只能读取现有译文。
const canResolveOwnerTranslations = computed(
  () => !isEmbedMode.value && isInChatLayout.value
)

// 状态
const activeTab = ref('agents')
const mobileActiveTab = ref('agents') // 移动端标签：'messages' | 'agents' | 'final'
const messagesContainer = ref(null)
const reportContainerRef = ref(null)  // 右侧报告区域的滚动容器
const conversationId = ref('')
const leaderSessionId = ref('')
const standardLoading = ref(true)
const isStartingSession = ref(false) // 是否正在启动 Leader 会话
const isMobile = ref(false)
const sidebarSize = ref(33.33) // 默认 1/3 宽度
const isSidebarCollapsed = ref(false) // 侧边栏收缩状态
const isHeaderExpanded = ref(false) // 移动端顶部信息条展开状态
const shareToken = ref('')
const lastTranslationSignature = ref('')
const userQuestion = ref('')
const attachments = ref([])

// 消息编辑
const userMessageId = ref(null) // 首条用户消息的 ID
const firstUserMessage = ref(null) // 首条用户消息完整对象（用于 EditIndicator）
const embedAccess = useAgentTeamsEmbedAccess({
  token: () => props.token || route.params.token,
  leaderStore,
  t,
  locale,
  onSnapshot: snapshot => {
    conversationId.value = snapshot.conversationId
    leaderSessionId.value = snapshot.leaderSessionId
    userQuestion.value = snapshot.userQuestion
    firstUserMessage.value = snapshot.firstUserMessage
    userMessageId.value = snapshot.userMessageId
  }
})
const loading = computed(() => isEmbedMode.value ? embedAccess.loading.value : standardLoading.value)
const loadError = computed(() => isEmbedMode.value ? embedAccess.error.value : '')
const answerEndpoint = computed(() => isEmbedMode.value
  ? embedAccess.answerEndpoint.value
  : '/api/leader/answer-questions'
)
const retryEmbedSession = () => embedAccess.retry()
const isEditingQuestion = ref(false)
const editingQuestionText = ref('')
const isEditSaving = ref(false)
const editQuestionTextareaRef = ref(null)

// 重新生成
const isRegenerating = ref(false)

// 文件预览
const showPreviewDialog = ref(false)
const previewFile = ref(null)
const previewContent = ref('')
const previewIsBinary = ref(false)
let componentMounted = false
let componentDisposed = false
let analysisGeneration = 0
let standardRequest = null
const previewLoading = ref(false)
let pendingQuestionRefresh = null

// 当前滚动目标（用于返回顶部按钮）
const currentScrollTarget = ref(null)
const finalReportRef = ref(null)
const leaderThinkingRef = ref(null)  // LeaderThinking 组件引用
const mobileAgentContainerRef = ref(null)  // 移动端 Agent 标签页容器
const mobileFinalContainerRef = ref(null)  // 移动端最终报告标签页容器
const mobileMessagesContainerRef = ref(null)  // 移动端消息记录标签页容器
const agentPanelTopRef = ref(null)  // Agent 面板顶部锚点（桌面端）
const mobileAgentPanelTopRef = ref(null)  // Agent 面板顶部锚点（移动端）

// 获取当前移动端活动的容器
function getActiveMobileContainer() {
  if (mobileActiveTab.value === 'messages') {
    return mobileMessagesContainerRef.value
  } else if (mobileActiveTab.value === 'agents') {
    return mobileAgentContainerRef.value
  } else if (mobileActiveTab.value === 'final') {
    return mobileFinalContainerRef.value
  }
  return null
}

// Agent 折叠面板展开后触发检查
function handleAgentExpanded() {
  setTimeout(updateCurrentScrollTarget, 100)
}

// 更新当前滚动目标
function updateCurrentScrollTarget() {
  // 移动端：根据当前标签页选择容器
  const container = isMobile.value ? getActiveMobileContainer() : reportContainerRef.value
  if (!container) return

  const containerRect = container.getBoundingClientRect()
  let topMostTarget = null
  let minTop = Infinity

  // 检查最终报告
  if (finalReportRef.value && (isMobile.value ? mobileActiveTab.value === 'final' : activeTab.value === 'final')) {
    const rect = finalReportRef.value.getBoundingClientRect()
    const isLong = finalReportRef.value.scrollHeight > 200
    if (isLong && rect.bottom > containerRect.top && rect.top < containerRect.bottom) {
      if (rect.top < minTop && rect.top < containerRect.top + 100) {
        minTop = rect.top
        topMostTarget = finalReportRef.value
      }
    }
  }

  // Agent 标签页：直接使用面板顶部锚点作为滚动目标
  // ScrollToTopButton 会根据 scrollTop 判断是否显示按钮
  const isAgentTab = isMobile.value ? mobileActiveTab.value === 'agents' : activeTab.value === 'agents'
  if (isAgentTab) {
    const agentPanelTop = isMobile.value ? mobileAgentPanelTopRef.value : agentPanelTopRef.value
    if (agentPanelTop) {
      topMostTarget = agentPanelTop
    }
  }

  // 检查消息记录（LeaderThinking）
  if (isMobile.value ? mobileActiveTab.value === 'messages' : false) {
    if (leaderThinkingRef.value) {
      const isLong = leaderThinkingRef.value.scrollHeight > 200
      if (isLong) {
        const rect = leaderThinkingRef.value.getBoundingClientRect()
        if (rect.bottom > containerRect.top && rect.top < containerRect.bottom) {
          if (rect.top < minTop && rect.top < containerRect.top + 100) {
            minTop = rect.top
            topMostTarget = leaderThinkingRef.value
          }
        }
      }
    }
  }

  currentScrollTarget.value = topMostTarget
}

// 检测移动端
const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
}

// 计算属性
const statusClass = computed(() => {
  const state = leaderStore.leaderState
  if (state === 'completed') return 'status-success'
  if (state === 'failed' || state === 'stopped') return 'status-error'
  if (['assessing', 'questioning', 'forming_team', 'monitoring', 'summarizing'].includes(state)) return 'status-active'
  return 'status-idle'
})

const statusText = computed(() => {
  const state = leaderStore.leaderState
  return t(`conversation.display.states.${[
    'idle', 'assessing', 'questioning', 'forming_team', 'monitoring',
    'summarizing', 'completed', 'stopped', 'failed',
  ].includes(state) ? state : 'unknown'}`)
})

const formattedTime = computed(() => {
  if (leaderStore.totalTime > 0) {
    const seconds = Math.floor(leaderStore.totalTime / 1000)
    const minutes = Math.floor(seconds / 60)
    const secs = seconds % 60
    return minutes > 0
      ? t('conversation.display.duration.minutesSeconds', { minutes, seconds: secs })
      : t('conversation.display.duration.seconds', { seconds: secs })
  }
  return '00:00'
})

// 方法
const handleBack = () => {
  router.push(isInChatLayout.value ? '/chat' : '/')
}

const handleAgentScrollTarget = (target) => {
  // 处理 Agent 滚动目标
  // Agent 展开后触发检查
  setTimeout(updateCurrentScrollTarget, 350)
}

const handleReportScrollTarget = (target) => {
  // 设置最终报告引用
  if (target) {
    finalReportRef.value = target
  }
}

// Splitpanes 大小变化处理
const onSplitResize = (panes) => {
  if (panes && panes.length > 0) {
    sidebarSize.value = panes[0].size
  }
}

// 切换侧边栏收缩状态
const toggleSidebar = () => {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
}

// 编辑问题
const startEditQuestion = () => {
  editingQuestionText.value = userQuestion.value
  isEditingQuestion.value = true
  nextTick(() => {
    editQuestionTextareaRef.value?.focus()
  })
}

const cancelEditQuestion = () => {
  isEditingQuestion.value = false
  editingQuestionText.value = ''
}

const saveEditQuestion = async () => {
  if (!editingQuestionText.value.trim() || isEditSaving.value) return
  isEditSaving.value = true
  try {
    const newContent = editingQuestionText.value.trim()
    const result = await conversationsStore.editMessage(userMessageId.value, newContent)
    if (result.success) {
      userQuestion.value = newContent
      // 更新 firstUserMessage 以反映 edited_at
      if (firstUserMessage.value) {
        firstUserMessage.value = {
          ...firstUserMessage.value,
          content: { text: newContent },
          edited_at: new Date().toISOString()
        }
      }
      isEditingQuestion.value = false
      ElMessage.success(t('conversation.display.questionUpdated'))
    } else {
      ElMessage.error(result.error)
    }
  } catch (e) {
    console.error('编辑问题失败:', e)
    ElMessage.error(t('conversation.display.editFailed'))
  } finally {
    isEditSaving.value = false
  }
}

// 重新生成
const handleRegenerate = async () => {
  if (isRegenerating.value || !userMessageId.value) return

  // 弹窗确认
  try {
    await ElMessageBox.confirm(
      t('conversation.display.regenerateConfirm'),
      t('conversation.display.regenerateConfirmTitle'),
      {
        confirmButtonText: t('conversation.display.confirm'),
        cancelButtonText: t('common.actions.cancel'),
        type: 'warning'
      }
    )
  } catch {
    return // 用户取消
  }

  isRegenerating.value = true
  try {
    lastTranslationSignature.value = ''
    translationStore.invalidateView({ clearEntries: true })
    // 清除当前 Leader 结果
    leaderStore.clearData()

    // 重新启动 Leader 流程
    await leaderStore.startLeaderSession(conversationId.value, userQuestion.value)
    ElMessage.success(t('conversation.display.regenerated'))
  } catch (e) {
    console.error('重新生成失败:', e)
    ElMessage.error(t('conversation.display.regenerateFailed'))
  } finally {
    isRegenerating.value = false
  }
}

// 停止生成
const handleStop = async () => {
  try {
    await leaderStore.stopExecution()
    ElMessage.success(t('leader.actions.stopSent'))
  } catch (error) {
    ElMessage.error(
      error?.response?.data?.detail?.error || t('leader.actions.stopFailed')
    )
  }
}

// 文件预览方法
const handlePreviewFile = async (file) => {
  previewFile.value = file
  showPreviewDialog.value = true
  previewLoading.value = true
  previewContent.value = ''

  try {
    const response = await fetch(`/api/files/share/${shareToken.value}/${file.id}/preview`)
    if (!response.ok) {
      throw new Error(t('conversation.display.previewFailed'))
    }
    const data = await response.json()
    previewContent.value = data.content
    previewIsBinary.value = data.is_binary
  } catch (error) {
    console.error('预览文件失败:', error)
    previewContent.value = t('conversation.display.previewFailed')
    previewIsBinary.value = true
  } finally {
    previewLoading.value = false
  }
}

const handleDownloadFile = () => {
  if (previewFile.value && shareToken.value) {
    window.open(`/api/files/share/${shareToken.value}/${previewFile.value.id}`, '_blank')
  }
}

// 通过 share_token 加载对话数据（公开访问）
const loadConversationByToken = async (token, { signal, requestGeneration } = {}) => {
  const isCurrentLoad = () => (
    !componentDisposed &&
    requestGeneration === analysisGeneration &&
    props.accessMode === 'standard'
  )
  if (!isCurrentLoad()) return false
  shareToken.value = token
  try {
    // 调用公开 API
    const response = await fetch(`/api/conversations/share/${token}`, { signal })
    if (!isCurrentLoad()) return false
    if (!response.ok) {
      throw new Error('对话不存在或链接已失效')
    }

    const data = await response.json()
    if (!isCurrentLoad()) return false
    conversationId.value = data.conversation.id

    // 获取对话标题
    if (data.conversation.title) {
      userQuestion.value = data.conversation.title
    }


    // 获取附件
    if (data.files && data.files.length > 0) {
      attachments.value = data.files
    }

    // 获取首条用户消息 ID（用于编辑/重新生成）
    if (data.messages && data.messages.length > 0) {
      const firstUserMsg = data.messages.find(m => m.role === 'user')
      if (firstUserMsg) {
        userMessageId.value = firstUserMsg.id
        firstUserMessage.value = firstUserMsg
      }
    }

    // 加载 Leader Session
    const leaderResponse = await fetch(`/api/leader/session/share/${token}`, { signal })
    if (!isCurrentLoad()) return false
    if (leaderResponse.ok) {
      const leaderData = await leaderResponse.json()
      if (!isCurrentLoad()) return false
      if (leaderData.success && leaderData.sessions && leaderData.sessions.length > 0) {
        // 获取最新的 session
        const latestSession = leaderData.sessions[leaderData.sessions.length - 1]
        leaderSessionId.value = latestSession.id

        // 更新 leader store 状态
        leaderStore.leaderState = latestSession.state
        leaderStore.resultsReconciled = ['completed', 'failed', 'stopped'].includes(latestSession.state)
        leaderStore.totalTime = (latestSession.total_time || 0) * 1000

        // 恢复 session 数据
        leaderStore.currentSession = { id: latestSession.id }

        // 恢复执行顺序（历史分享链路此前遗漏了这一步）
        const executionOrder = {}
        const dagPlan = latestSession.team_config?.dag_plan || latestSession.team_config?.dag_execution_plan || {}
        const batches = dagPlan.execution_batches || []
        let sequence = 0
        batches.forEach((batch, batchIndex) => {
          ;(batch.agents || []).forEach((agentId, agentIndex) => {
            executionOrder[agentId] = {
              batchIndex,
              agentIndex,
              sequence: sequence++
            }
          })
        })

        // 恢复团队配置
        if (latestSession.team_config && latestSession.team_config.agent_details) {
          leaderStore.selectedAgents = latestSession.team_config.agent_details.map(agent => ({
            ...agent,
            leader_session_id: latestSession.id
          }))
          if (Object.keys(executionOrder).length === 0) {
            latestSession.team_config.agent_details.forEach((agent, index) => {
              executionOrder[agent.agent_id] = {
                batchIndex: index,
                agentIndex: 0,
                sequence: index
              }
            })
          }
        } else if (latestSession.selected_agents && latestSession.selected_agents.length > 0) {
          // 从 selected_agents 恢复
          leaderStore.selectedAgents = latestSession.selected_agents.map(agent => ({
            agent_id: agent,
            agent_name: agent,
            leader_session_id: latestSession.id
          }))
          if (Object.keys(executionOrder).length === 0) {
            latestSession.selected_agents.forEach((agentId, index) => {
              executionOrder[agentId] = {
                batchIndex: index,
                agentIndex: 0,
                sequence: index
              }
            })
          }
        }

        // 恢复 Agent 结果
        if (latestSession.agent_results && latestSession.agent_results.length > 0) {
          leaderStore.agentResults = latestSession.agent_results.map(result => ({
            ...result,
            success: result.status === 'success'
          }))

          // 恢复 Agent 状态
          leaderStore.agentStatuses = latestSession.agent_results.map(result => ({
            agent_id: result.agent_id,
            agent_name: result.agent_name,
            status: result.status === 'success' ? 'completed' : 'failed',
            message: result.status === 'success' ? t('leader.runtime.executionCompleted') : result.error,
            leader_session_id: latestSession.id,
            decomposition: result.decomposition,
            content: result.content,
            tool_calls: result.tool_calls,
            tokens_used: result.tokens_used,
            execution_time: result.execution_time,
          }))

          if (Object.keys(executionOrder).length === 0) {
            latestSession.agent_results.forEach((result, index) => {
              executionOrder[result.agent_id] = {
                batchIndex: index,
                agentIndex: 0,
                sequence: index
              }
            })
          }
        }

        leaderStore.agentExecutionOrder = executionOrder

        // 恢复最终报告
        if (latestSession.final_report) {
          leaderStore.finalReport = latestSession.final_report
        }

        // 恢复历史消息
        if (leaderData.messages && leaderData.messages.length > 0) {
          leaderStore.historicalMessages = leaderData.messages.map(msg => {
            const msgType = msg.message_type || msg.type

            // question 类型需保留原始问题数组用于弹窗恢复
            if (msgType === 'question') {
              const questions = extractQuestions(msg.content)
              if (questions) {
                return {
                  id: msg.id,
                  content: formatMessageContent(msg.content, msgType, msg.content_locale),
                  rawContent: msg.content,
                  questions,
                  time: msg.created_at ? new Date(msg.created_at).toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' }) : '',
                  type: 'question',
                  content_locale: msg.content_locale,
                  leader_session_id: msg.leader_session_id
                }
              }
            }

            return {
              id: msg.id,
              content: formatMessageContent(msg.content, msgType, msg.content_locale),
              rawContent: msg.content,
              time: msg.created_at ? new Date(msg.created_at).toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' }) : '',
              type: msgType,
              content_locale: msg.content_locale,
              leader_session_id: msg.leader_session_id
            }
          })
        }

        leaderStore.restorePendingQuestions(latestSession, leaderData.messages || [])
      }
    }

    return true
  } catch (error) {
    if (error.name === 'AbortError') return false
    console.error('加载对话失败:', error)
    return false
  }
}

function resetLocalAnalysisState() {
  conversationId.value = ''
  leaderSessionId.value = ''
  shareToken.value = ''
  userQuestion.value = ''
  attachments.value = []
  userMessageId.value = null
  firstUserMessage.value = null
  lastTranslationSignature.value = ''
}

function resetStandardAnalysisState() {
  resetLocalAnalysisState()
  leaderStore.resetState()
  leaderStore.clearData()
}

async function loadAnalysisAccess(token, accessMode = props.accessMode) {
  const requestGeneration = ++analysisGeneration
  translationStore.invalidateView()
  pendingQuestionRefresh = null
  standardRequest?.abort()
  standardRequest = null

  if (!token) {
    console.error('缺少分享令牌')
    router.push('/')
    return
  }

  if (accessMode === 'embed') {
    standardLoading.value = true
    resetLocalAnalysisState()
    await embedAccess.start()
    return
  }

  embedAccess.stop()
  resetStandardAnalysisState()
  standardLoading.value = true
  const request = new AbortController()
  standardRequest = request

  try {
    const success = await loadConversationByToken(token, {
      signal: request.signal,
      requestGeneration,
    })
    if (componentDisposed || requestGeneration !== analysisGeneration) return

    if (!success) {
      console.error('加载对话失败')
      return
    }

    await activateTranslations()
    if (componentDisposed || requestGeneration !== analysisGeneration) return

    if (leaderStore.pendingSessionData) {
      // 不 await：startLeaderSessionIfNeeded 会消费整段 SSE 流，等待它会让
      // standardLoading 一直为 true，分析详情页被卡在加载动画后面。
      // 后台启动即可：SSE 事件由 leader store 实时驱动渲染，旧流由 resetState 中断。
      void startLeaderSessionIfNeeded()
    }
  } catch (loadError) {
    if (loadError.name !== 'AbortError') {
      console.error('加载数据失败:', loadError)
    }
  } finally {
    if (standardRequest === request) standardRequest = null
    if (!componentDisposed && requestGeneration === analysisGeneration) {
      standardLoading.value = false
    }
  }
}

// 启动 Leader 会话（从 Home.vue 跳转时调用）
const startLeaderSessionIfNeeded = async () => {
  // 从 store 获取待启动的会话数据
  const pendingData = leaderStore.pendingSessionData

  if (!pendingData || !pendingData.message) {
    return // 没有待启动的会话数据，不启动会话
  }

  const { message, fileIds, templateId, locale: generationLocale } = pendingData

  // 立即清除 store 中的临时数据，避免重复启动
  leaderStore.pendingSessionData = null

  // 设置启动状态，显示加载动画
  isStartingSession.value = true

  try {
    if (templateId) {
      // 模板启动：使用工作流模板端点
      await leaderStore.applyTemplateSession(
        templateId,
        conversationId.value,
        message,
        fileIds || [],
        generationLocale,
      )
    } else {
      // 普通启动
      await leaderStore.startLeaderSession(
        conversationId.value,
        message,
        fileIds || [],
        { project_ids: [] },
        generationLocale,
      )
    }
  } catch (error) {
    console.error('[ConversationDisplay] Failed to start Leader session:', error)
  } finally {
    // 无论成功或失败，都清除启动状态
    isStartingSession.value = false
  }
}

const refreshPendingQuestion = async () => {
  if (!shareToken.value || document.hidden || pendingQuestionRefresh) return

  const requestToken = shareToken.value
  const requestGeneration = analysisGeneration

  const refreshRequest = (async () => {
    try {
      const response = await fetch(`/api/leader/session/share/${requestToken}`)
      if (!response.ok) return

      const data = await response.json()
      if (
        componentDisposed ||
        requestGeneration !== analysisGeneration ||
        requestToken !== shareToken.value
      ) return
      const latestSession = data.sessions?.[data.sessions.length - 1]
      if (!data.success || !latestSession) return

      if (latestSession.state === 'questioning') {
        leaderSessionId.value = latestSession.id
        leaderStore.restorePendingQuestions(latestSession, data.messages || [])
      } else if (
        leaderStore.currentSession?.id === latestSession.id &&
        leaderStore.leaderState === 'questioning'
      ) {
        // The question may have been answered in another browser window.
        leaderStore.currentQuestions = []
        leaderStore.leaderState = latestSession.state
      }
    } catch (error) {
      console.warn('[ConversationDisplay] Failed to refresh pending question:', error)
    }
  })()
  pendingQuestionRefresh = refreshRequest

  try {
    await refreshRequest
  } finally {
    if (pendingQuestionRefresh === refreshRequest) {
      pendingQuestionRefresh = null
    }
  }
}

const handlePageResume = () => {
  if (!document.hidden) {
    void refreshPendingQuestion()
  }
}

function currentTranslationSources() {
  return collectLeaderTranslationSources({
    messages: leaderStore.historicalMessages,
    agentResults: leaderStore.agentResults,
    finalReport: leaderStore.finalReport,
    targetLocale: locale.value,
  })
}

async function activateOwnerTranslations() {
  if (!canResolveOwnerTranslations.value || !leaderStore.resultsReconciled) {
    return
  }

  const sources = currentTranslationSources()
  const signature = `${locale.value}:${sources.map(source => `${source.type}:${source.id}`).join(',')}`
  if (signature === lastTranslationSignature.value) {
    return
  }

  const requestEpoch = translationStore.beginView(locale.value)
  lastTranslationSignature.value = signature
  await translationStore.resolveOwner(sources, locale.value, requestEpoch)
}

async function activateShareTranslations() {
  // 登录用户在分享页看「别人的」会话时也会走 share 只读快照（由 activateTranslations 回退触发），
  // 因此 guard 只按 shareToken 有无判断，不再按登录态短路。
  if (!shareToken.value) {
    return
  }

  const sources = currentTranslationSources()
  const signature = `share:${shareToken.value}:${locale.value}:${sources.map(source => `${source.type}:${source.id}`).join(',')}`
  if (signature === lastTranslationSignature.value) {
    return
  }

  const requestEpoch = translationStore.beginView(locale.value)
  lastTranslationSignature.value = signature
  await translationStore.lookupShare(sources, locale.value, shareToken.value, requestEpoch)
}

async function activateTranslations() {
  // /chat owner 页面可触发翻译补齐；公开分享页始终只读取 ready 缓存。
  if (canResolveOwnerTranslations.value) {
    await activateOwnerTranslations()
    return
  }
  await activateShareTranslations()
}

// 生命周期
onMounted(async () => {
  componentMounted = true
  // 检测移动端
  checkMobile()
  window.addEventListener('resize', checkMobile)
  window.addEventListener('focus', handlePageResume)
  window.addEventListener('pageshow', handlePageResume)
  document.addEventListener('visibilitychange', handlePageResume)

  // 延迟添加滚动监听（等待 DOM 完全渲染）
  setTimeout(() => {
    // 桌面端容器
    if (reportContainerRef.value) {
      reportContainerRef.value.addEventListener('scroll', updateCurrentScrollTarget)
    }
    // 移动端容器
    if (mobileAgentContainerRef.value) {
      mobileAgentContainerRef.value.addEventListener('scroll', updateCurrentScrollTarget)
    }
    if (mobileFinalContainerRef.value) {
      mobileFinalContainerRef.value.addEventListener('scroll', updateCurrentScrollTarget)
    }
    if (mobileMessagesContainerRef.value) {
      mobileMessagesContainerRef.value.addEventListener('scroll', updateCurrentScrollTarget)
    }
    // 初始检查
    updateCurrentScrollTarget()
  }, 500)

  await loadAnalysisAccess(accessToken.value, props.accessMode)
})

onUnmounted(() => {
  componentDisposed = true
  componentMounted = false
  analysisGeneration += 1
  standardRequest?.abort()
  standardRequest = null
  embedAccess.stop()
  translationStore.invalidateView()
  window.removeEventListener('resize', checkMobile)
  window.removeEventListener('focus', handlePageResume)
  window.removeEventListener('pageshow', handlePageResume)
  document.removeEventListener('visibilitychange', handlePageResume)
  
  // 移除滚动监听
  if (reportContainerRef.value) {
    reportContainerRef.value.removeEventListener('scroll', updateCurrentScrollTarget)
  }
  if (mobileAgentContainerRef.value) {
    mobileAgentContainerRef.value.removeEventListener('scroll', updateCurrentScrollTarget)
  }
  if (mobileFinalContainerRef.value) {
    mobileFinalContainerRef.value.removeEventListener('scroll', updateCurrentScrollTarget)
  }
  if (mobileMessagesContainerRef.value) {
    mobileMessagesContainerRef.value.removeEventListener('scroll', updateCurrentScrollTarget)
  }
})

// 监听移动端容器 ref 变化，添加滚动监听
watch(mobileAgentContainerRef, (newRef) => {
  if (newRef) {
    newRef.addEventListener('scroll', updateCurrentScrollTarget)
    // 初始检查
    setTimeout(updateCurrentScrollTarget, 100)
  }
})

watch(mobileFinalContainerRef, (newRef) => {
  if (newRef) {
    newRef.addEventListener('scroll', updateCurrentScrollTarget)
    setTimeout(updateCurrentScrollTarget, 100)
  }
})

watch(mobileMessagesContainerRef, (newRef) => {
  if (newRef) {
    newRef.addEventListener('scroll', updateCurrentScrollTarget)
    setTimeout(updateCurrentScrollTarget, 100)
  }
})

// 监听移动端标签切换，触发检查
watch(mobileActiveTab, () => {
  setTimeout(updateCurrentScrollTarget, 100)
})

watch(
  [() => props.accessMode, accessToken],
  ([newMode, newToken], [oldMode, oldToken]) => {
    if (!componentMounted || (newMode === oldMode && newToken === oldToken)) return
    void loadAnalysisAccess(newToken, newMode)
  }
)

// 监听 leaderStore.currentSession 变化，同步更新 leaderSessionId
// 这在 SSE 启动后 leaderStore.currentSession 被设置时触发
watch(
  () => leaderStore.currentSession,
  (newSession) => {
    if (newSession && newSession.id) {
      leaderSessionId.value = newSession.id
    }
  },
  { deep: true }
)

watch(
  () => leaderStore.resultsReconciled,
  (reconciled) => {
    if (reconciled) {
      void activateTranslations()
    }
  }
)

watch(locale, () => {
  lastTranslationSignature.value = ''
  void activateTranslations()
})
</script>

<style scoped lang="scss">
.conversation-display {
  /* 预留全局底部状态栏高度，避免内容被遮挡 */
  height: calc(100vh - var(--footer-height));
  width: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-background);
  font-family: 'Fira Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.conversation-display.embed-mode {
  /* 嵌入模式无底部状态栏，保持满屏 */
  height: 100vh;
  max-width: none;
  margin: 0;
}

.load-error-state {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 24px;
  color: var(--color-text-secondary);
  text-align: center;
}

.retry-button {
  min-height: 36px;
  padding: 8px 16px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text-primary);
  cursor: pointer;
}

/* 顶部信息条 */
.info-header {
  background: var(--color-card);
  border-bottom: 1px solid var(--color-border);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  flex-shrink: 0;
  padding: 12px 20px;
}

.header-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.question-preview {
  flex: 1;
  min-width: 0;
  cursor: pointer;
  transition: all 0.2s ease;
}

.question-label {
  font-size: 12px;
  color: #909399;
  font-weight: 500;
}

.question-text {
  display: block;
  margin-top: 4px;
  font-size: 14px;
  color: var(--color-text-primary);
  line-height: 1.5;
  word-break: break-word;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  transition: all 0.2s ease;

  &.expanded {
    -webkit-line-clamp: unset;
    display: block;
    max-height: min(36vh, 320px);
    overflow-y: auto;
    white-space: pre-wrap;
    padding-right: 4px;
  }
}

.header-attachments {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.attachments-label {
  font-size: 12px;
  color: #909399;
  font-weight: 500;
  flex-shrink: 0;
  margin-top: 6px;
}

.attachments-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.attachment-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #ecf5ff;
    border-color: #409eff;
    color: #409eff;
  }

  svg {
    flex-shrink: 0;
  }
}

.attachment-name {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 编辑问题按钮 */
.edit-question-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  color: #909399;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
  opacity: 0;

  .question-preview:hover & {
    opacity: 1;
  }

  &:hover {
    background: #ecf5ff;
    border-color: #409eff;
    color: #409eff;
  }
}

/* 编辑问题文本框 */
.edit-question-textarea {
  width: 100%;
  min-height: 60px;
  padding: 8px 12px;
  border: 1px solid #409eff;
  border-radius: 6px;
  font-size: 14px;
  line-height: 1.5;
  resize: vertical;
  outline: none;
  font-family: inherit;
  margin-top: 4px;

  &:focus {
    box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
  }
}

.edit-question-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.edit-action-btn {
  padding: 4px 14px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid;

  &.save {
    background: #409eff;
    color: white;
    border-color: #409eff;

    &:hover:not(:disabled) {
      background: #337ecc;
    }

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  }

  &.cancel {
    background: var(--color-card);
    color: #606266;
    border-color: #dcdfe6;

    &:hover {
      border-color: #409eff;
      color: #409eff;
    }
  }
}

/* 停止生成按钮 */
.stop-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  color: #E11D48;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;

  &:hover:not(:disabled) {
    border-color: #E11D48;
    color: #E11D48;
    background: rgba(225, 29, 72, 0.06);
  }

  &:active:not(:disabled) {
    transform: scale(0.97);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  svg {
    flex-shrink: 0;
    animation: none;
  }
}

/* 重新生成按钮 */
.regenerate-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.2s;

  &:hover:not(:disabled) {
    border-color: var(--color-primary);
    color: var(--color-primary);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  svg.spinning {
    animation: spin 1s linear infinite;
  }
}

/* 文件预览对话框 */
.preview-dialog {
  .preview-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 40px;
    color: #909399;
  }

  .preview-content {
    max-height: 60vh;
    overflow: auto;

    pre {
      margin: 0;
      padding: 16px;
      background: #f5f7fa;
      border-radius: 8px;
      font-size: 13px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
    }
  }

  .preview-binary {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px;
    color: #909399;

    .el-icon {
      font-size: 48px;
      margin-bottom: 16px;
    }
  }
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.back-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  background: var(--color-card);
  border: 2px solid var(--color-border);
  border-radius: 10px;
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);

  &:hover {
    background: var(--color-card);
    border-color: var(--color-primary);
    color: var(--color-primary);
    box-shadow: 0 2px 8px rgba(37, 99, 235, 0.15);
    transform: translateY(-1px);
  }

  &:active {
    transform: translateY(0) scale(0.98);
    box-shadow: 0 1px 3px rgba(37, 99, 235, 0.1);
  }
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 6px 12px;
  background: var(--color-hover);
  border-radius: 20px;
  font-size: var(--font-size-sm);
  font-weight: 500;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94A3B8;
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

.status-active .status-dot {
  background: #F59E0B;
}

.status-success .status-dot {
  background: #10B981;
  animation: none;
}

.status-error .status-dot {
  background: #EF4444;
  animation: none;
}

.status-text {
  color: var(--color-text);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.time-display {
  font-family: 'Fira Code', monospace;
  font-size: var(--font-size-sm);
  color: #64748B;
  font-weight: 500;
}

/* 主体内容：双列布局 */
.main-content {
  flex: 1;
  width: 100%;
  display: flex;
  overflow: hidden;
  height: calc(100vh - var(--footer-height) - 56px);
}

/* Splitpanes 自定义样式 */
:deep(.splitpanes.default-theme) {
  .splitpanes__splitter {
    background-color: var(--color-border);
    border: none;
    position: relative;
    
    &:before {
      content: '';
      position: absolute;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      width: 4px;
      height: 32px;
      background: linear-gradient(180deg, #CBD5E1 0%, #94A3B8 50%, #CBD5E1 100%);
      border-radius: 2px;
      opacity: 0.6;
      transition: opacity 0.2s;
    }
    
    &:hover:before {
      opacity: 1;
    }
  }
  
  .splitpanes__pane {
    background: transparent;
    overflow: hidden;
  }
}

/* 左侧消息侧边栏 */
.message-sidebar {
  position: relative;
  height: 100%;
  background: var(--color-card);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: all 0.3s ease;
  
  // 移动端样式
  &.mobile {
    border-right: none;
    border-bottom: 1px solid var(--color-border);
  }
  
  // 收缩状态
  &.collapsed {
    align-items: center;
    
    .collapse-toggle {
      position: relative;
      top: auto;
      right: auto;
      margin-top: 12px;
    }
  }
}

/* 收缩/展开按钮 */
.collapse-toggle {
  position: absolute;
  top: 12px;
  right: 8px;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: var(--color-card);
  border: 2px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);

  svg {
    transition: transform 0.3s ease;
  }

  &:hover {
    background: var(--color-primary);
    border-color: var(--color-primary);
    color: white;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.2);
    transform: translateY(-1px);
  }

  &:active {
    transform: translateY(0) scale(0.95);
    box-shadow: 0 1px 2px rgba(37, 99, 235, 0.1);
  }
}

/* 侧边栏标题 */
.sidebar-title {
  padding: 12px 16px 8px 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-card);
  flex-shrink: 0;
}


.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-md);
}

/* 右侧报告面板 */
.report-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-background);
  
  // 移动端样式
  &.mobile {
    flex: 1;
  }
}

.panel-header {
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-card);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.tabs {
  display: flex;
  gap: var(--spacing-sm);
}

.tab {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 10px 16px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-family: 'Fira Sans', sans-serif;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-in-out);

  &:hover {
    background: var(--color-hover);
    border-color: var(--color-primary);
  }

  &.active {
    background: var(--color-primary);
    border-color: var(--color-primary);
    color: white;
  }
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-lg);
}

/* Embed 页面本身已经是受限的会诊工作区，桌面端不再叠加居中留白。 */
.conversation-display.embed-mode .panel-content {
  padding: 12px;
}

.conversation-display.embed-mode .final-report {
  margin: 0;
}

.agents-view,
.final-report-view {
  animation: fadeIn var(--duration-normal) var(--ease-out);
}

/* 启动中指示器 */
.starting-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2xl);
  text-align: center;

  .starting-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: var(--spacing-md);
  }

  .starting-text {
    font-size: var(--font-size-base);
    font-weight: 500;
    color: var(--color-text);
    margin: 0 0 var(--spacing-xs) 0;
  }

  .starting-hint {
    font-size: var(--font-size-sm);
    color: #94A3B8;
    margin: 0;
  }
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2xl);
  color: #94A3B8;
  text-align: center;

  p {
    font-size: var(--font-size-base);
    margin: 0;
  }
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: calc(100vh - var(--footer-height));
  background: var(--color-background);
  gap: var(--spacing-md);

  p {
    font-size: var(--font-size-base);
    color: #64748B;
    margin: 0;
  }
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 动画 */
@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 移动端响应式 - 通过 isMobile 状态控制，非媒体查询 */

/* 移动端标签切换栏 */
.mobile-tab-bar {
  display: flex;
  background: var(--color-card);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 10;
}

.mobile-tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px 8px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  font-size: 12px;
  color: #64748B;
  cursor: pointer;
  transition: all 0.2s ease;

  svg {
    opacity: 0.7;
  }

  &:active {
    background: #f5f7fa;
  }

  &.active {
    color: var(--color-primary);
    border-bottom-color: var(--color-primary);

    svg {
      opacity: 1;
    }
  }
}

/* 移动端内容区域 */
.mobile-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0; // 关键！允许 flex 子项收缩
}

/* 移动端面板 */
.mobile-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.mobile-panel-body {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch; // iOS 平滑滚动
  padding: 4px;
  min-height: 0;
}

/* 移动端顶部信息条优化 */
@media (max-width: 768px) {
  .info-header {
    padding: 10px 12px;
  }

  .header-top {
    flex-wrap: wrap;
    gap: 8px;
  }

  .header-left {
    flex: 1;
    min-width: 0;
  }

  .question-preview {
    max-width: calc(100% - 50px);
    cursor: pointer;
    
    &.is-mobile {
      display: flex;
      align-items: flex-start;
      gap: 4px;
    }
  }

  .question-text {
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    transition: all 0.2s ease;
    
    &.expanded {
      -webkit-line-clamp: unset;
      display: block;
    }
  }

  .expand-hint {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    margin-top: 2px;
    flex-shrink: 0;
    
    svg {
      color: #909399;
    }
  }

  .header-right {
    width: 100%;
    justify-content: flex-start;
    padding-left: 46px; // 对齐返回按钮后的内容

    .stop-btn {
      margin-left: auto;
    }
  }

  .header-attachments {
    flex-wrap: wrap;
  }

  .attachment-name {
    max-width: 120px;
  }

  .back-button {
    width: 34px;
    height: 34px;
  }

  .status-badge {
    padding: 4px 8px;
    font-size: 11px;
  }

  .time-display {
    font-size: 11px;
  }

  /* 文件预览对话框移动端优化 */
  .preview-dialog {
    :deep(.el-dialog) {
      width: 95% !important;
      margin-top: 5vh !important;
      max-height: 90vh;
    }

    .preview-content {
      max-height: 50vh;

      pre {
        padding: 12px;
        font-size: 12px;
      }
    }
  }

  /* 主内容区域移动端优化 */
  .main-content {
    flex-direction: column;
    height: auto;
    flex: 1;
    min-height: 0;
  }

  .conversation-display.embed-mode .panel-content {
    padding: 4px;
  }
}
</style>
