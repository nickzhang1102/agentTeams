<template>
  <div class="leader-thinking">
    <!-- 运行中显示"停止生成"按钮，让用户对结果不满意时可主动及时退出（避免继续消耗 token） -->
    <div class="stop-bar" v-if="allowStop && leaderStore.isActive">
      <el-button
        size="small"
        type="warning"
        plain
        :icon="CircleClose"
        :loading="leaderStore.stopRequested"
        :disabled="leaderStore.stopRequested"
        @click="handleStop"
      >
        {{ t('leader.actions.stopGenerating') }}
      </el-button>
    </div>

    <div class="phase-indicator" v-if="phases && phases.length > 0">
      <ol class="phase-track">
        <li
          v-for="(phase, index) in phases"
          :key="phase.id"
          class="phase-step"
          :class="{
            'is-complete': index < currentPhaseIndex,
            'is-current': index === currentPhaseIndex
          }"
          :aria-current="index === currentPhaseIndex ? 'step' : undefined"
        >
          <span class="phase-title" :title="phase.name">{{ phase.name }}</span>
        </li>
      </ol>
    </div>

    <!-- 消息列表头部 -->
    <div class="messages-header" v-if="allMessages.length > 0">
      <el-icon class="thinking-icon" :class="{ 'is-spinning': leaderStore.isActive }">
        <Loading />
      </el-icon>
      <span>{{ t('leader.thinking.messages') }}</span>
      <span class="message-count">({{ allMessages.length }})</span>
    </div>

    <!-- 消息列表 -->
    <div class="messages-body" v-if="allMessages.length > 0">
      <div class="messages-list">
        <div
          v-for="(message, index) in reversedMessages"
          :key="index"
          :class="['message-item']"
        >
          <div class="message-time">{{ message.time }}</div>

          <!-- 消息内容 -->
          <div class="message-content markdown-body">
            <ContentTranslationStatus :state="message.translationState" />
            <MarkdownRenderer :content="message.content" />
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="messages-body empty">
      <div class="empty-state">
        <el-empty :description="t('leader.thinking.waiting')" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useLeaderStore } from '@/stores/leader'
import { useContentTranslationStore } from '@/stores/contentTranslation'
import { formatMessageContent } from '@/utils/messageContentFormatter'
import { Loading, CircleClose } from '@element-plus/icons-vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ContentTranslationStatus from './ContentTranslationStatus.vue'

const props = defineProps({
  sessionId: {
    type: [Number, String],
    default: ''
  },
  allowStop: {
    type: Boolean,
    default: true
  }
})

const leaderStore = useLeaderStore()
const translationStore = useContentTranslationStore()
const { t, locale } = useI18n()

const phases = computed(() => leaderStore.leaderPhases)
const currentPhase = computed(() => leaderStore.currentPhase)
const thinkingContent = computed(() => leaderStore.thinkingContent)

// 安全获取当前阶段索引，避免越界
const currentPhaseIndex = computed(() => {
  if (!phases.value || phases.value.length === 0) return 0
  if (leaderStore.leaderState === 'completed') return phases.value.length - 1
  const index = phases.value.findIndex(p => p.id === currentPhase.value)
  return index >= 0 ? index : 0
})

// 存储所有消息（只包含thinking，不包含report）
const allMessages = ref([])

// 监听thinkingContent变化，添加到消息列表
watch(thinkingContent, (newContent) => {
  if (newContent && newContent.trim()) {
    addMessage(newContent)
  }
}, { immediate: true })

// 监听 sessionId 变化，清空旧消息并重新加载
watch(() => props.sessionId, (newId, oldId) => {
  if (newId && newId !== oldId) {
    reloadMessagesForLocale()
  }
})

watch(locale, () => {
  reloadMessagesForLocale()
})

watch(() => translationStore.entries, () => {
  reloadMessagesForLocale()
}, { deep: true })

watch(() => leaderStore.historicalMessages, () => {
  reloadMessagesForLocale()
}, { deep: true })

watch(() => leaderStore.messages, () => {
  reloadMessagesForLocale()
}, { deep: true })

// 加载历史消息
function loadHistoricalMessages() {
  // 根据 sessionId 过滤历史消息
  let historicalMsgs = []

  if (props.sessionId) {
    const sessionIdNum = Number(props.sessionId)
    if (!isNaN(sessionIdNum)) {
      historicalMsgs = leaderStore.getMessagesBySession(sessionIdNum)
    }
  } else {
    historicalMsgs = leaderStore.historicalMessages || []
  }

  if (historicalMsgs && historicalMsgs.length > 0) {
    historicalMsgs
      .filter(msg => {
        const msgType = msg.type || msg.message_type
        // 原始用户需求已在页头单独展示，不属于 Leader 的过程消息。
        // embed 快照使用 `user`，旧会话使用 `normal`，两种形态都要排除。
        return !['agent_result', 'final_report', 'normal', 'user'].includes(msgType)
      })
      .forEach(msg => {
        const rawContent = msg.rawContent ?? msg.content
        const source = Number.isInteger(msg.id) && msg.id > 0
          ? { type: 'message', id: msg.id }
          : null
        const entry = source ? translationStore.getEntry(source, locale.value) : null
        const translatedText = entry?.state === 'ready' && typeof entry.payload?.text === 'string'
          ? entry.payload.text
          : null
        const content = translatedText || (typeof rawContent === 'string'
          ? rawContent
          : formatMessageContent(rawContent, msg.type || msg.message_type, msg.content_locale))
        addMessage(content, msg.time, msg.type || 'thinking', {
          translationState: entry?.state || 'original',
        })
      })
  } else if (thinkingContent.value && thinkingContent.value.trim()) {
    addMessage(thinkingContent.value)
  }
}

// 组件挂载时，恢复历史消息
onMounted(() => {
  loadHistoricalMessages()
})

function addMessage(content, time = null, type = 'thinking', extra = {}) {
  // 避免重复添加
  const exists = allMessages.value.some(m => m.content === content)

  if (!exists) {
    allMessages.value.push({
      content,
      time: time || new Date().toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' }),
      type,
      ...extra,
    })
  }
}

function reloadMessagesForLocale() {
  allMessages.value = []
  loadHistoricalMessages()
}

// 反转消息列表，最新的在最前面
const reversedMessages = computed(() => {
  return [...allMessages.value].reverse()
})

// 停止生成
async function handleStop() {
  try {
    await leaderStore.stopExecution()
    ElMessage.success(t('leader.actions.stopSent'))
  } catch (error) {
    ElMessage.error(
      error?.response?.data?.detail?.error || t('leader.actions.stopFailed')
    )
  }
}

</script>

<style scoped>
.leader-thinking {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.stop-bar {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  padding: 6px 12px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
}

.phase-indicator {
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color);
  flex-shrink: 0;
}

.phase-track {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0;
  padding: 8px 0;
  list-style: none;
}

.phase-step {
  position: relative;
  min-width: 0;
  padding: 0 10px 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
  line-height: 20px;
  text-align: center;
}

.phase-step:not(:last-child)::after {
  position: absolute;
  top: 50%;
  right: 1px;
  color: var(--el-text-color-placeholder);
  content: ">";
  transform: translateY(-50%);
}

.phase-step.is-complete {
  color: var(--el-color-success);
}

.phase-step.is-current {
  color: var(--el-color-primary);
  font-weight: 600;
}

.phase-title {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 消息列表头部 */
.messages-header {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: var(--el-fill-color);
  border-bottom: 1px solid var(--el-border-color);
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 500;
}

.thinking-icon {
  margin-right: 6px;
  font-size: 14px;
}

.thinking-icon.is-spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.message-count {
  margin-left: 6px;
  font-size: 11px;
  color: var(--el-text-color-regular);
  font-weight: normal;
}

.messages-body {
  flex: 1;
  overflow-y: auto;
  background: var(--el-fill-color-lighter);
  padding: 8px;
  min-height: 0;
}

.messages-body.empty {
  display: flex;
  align-items: center;
  justify-content: center;
}

.message-item {
  background: var(--color-card);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
}

.message-time {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.message-content {
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-primary);
  word-wrap: break-word;
}

.message-content.markdown-body :deep(h2) {
  font-size: 14px;
  font-weight: 600;
  margin: 8px 0 4px 0;
  color: var(--el-text-color-primary);
}

.message-content.markdown-body :deep(h3) {
  font-size: 13px;
  font-weight: 600;
  margin: 6px 0 3px 0;
  color: var(--el-text-color-primary);
}

.message-content.markdown-body :deep(p) {
  margin: 4px 0;
}

.message-content.markdown-body :deep(ul),
.message-content.markdown-body :deep(ol) {
  margin: 4px 0;
  padding-left: 18px;
}

.message-content.markdown-body :deep(li) {
  margin: 2px 0;
}

.message-content.markdown-body :deep(strong) {
  font-weight: 600;
  color: var(--el-color-primary);
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .phase-indicator {
    padding: 6px 8px;
  }

  .phase-track {
    padding: 6px 0;
  }

  .messages-header {
    padding: 6px 10px;
    font-size: 12px;
  }

  .messages-body {
    padding: 6px;
  }

  .message-item {
    padding: 6px 8px;
    margin-bottom: 6px;
  }

  .message-content {
    font-size: 12px;
  }
}
</style>
