<template>
  <div class="sidebar" :class="{ collapsed: !expanded, 'mobile-overlay': isMobile && expanded }">
    <!-- 移动端遮罩 -->
    <div v-if="isMobile && expanded" class="sidebar-overlay" @click="$emit('collapse')"></div>

    <div class="sidebar-inner">
      <!-- 顶部：Logo + 新建按钮 -->
      <div class="sidebar-header">
        <div class="header-row">
          <div class="logo" @click="route.path.startsWith('/chat') ? router.push('/chat') : router.push('/')">
            <img src="/logo.svg" alt="Logo" class="logo-icon" />
            <span v-show="expanded" class="logo-text">Agent Teams</span>
          </div>
          <!-- 桌面端折叠按钮 -->
          <button v-if="!isMobile && expanded" class="toggle-btn" @click="$emit('collapse')" :title="t('conversation.navigation.collapseSidebar')">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="11 17 6 12 11 7"/></svg>
          </button>
          <button v-if="!isMobile && !expanded" class="toggle-btn" @click="$emit('expand')" :title="t('conversation.navigation.expandSidebar')">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 17 18 12 13 7"/></svg>
          </button>
        </div>
        <el-button
          v-show="expanded"
          type="primary"
          class="new-chat-btn"
          @click="handleNewChat"
        >
          <el-icon><Plus /></el-icon>
          <span>{{ t('conversation.sidebar.newConversation') }}</span>
        </el-button>
        <button
          v-show="expanded"
          class="template-start-btn"
          @click="showTemplatePicker = true"
        >
          {{ t('conversation.sidebar.startFromPlan') }}
        </button>
      </div>

      <!-- 搜索框 -->
      <div v-show="expanded" class="sidebar-search">
        <el-input
          v-model="searchQuery"
          :placeholder="t('conversation.sidebar.search')"
          clearable
          size="small"
          :prefix-icon="Search"
        />
      </div>

      <!-- 对话列表 -->
      <div v-show="expanded" class="sidebar-list" v-loading="loading">
        <el-scrollbar>
          <div
            v-for="conv in filteredConversations"
            :key="conv.id"
            class="conv-item"
            :class="{ active: isActive(conv) }"
            @click="handleSelect(conv)"
          >
            <div class="conv-item-content">
              <div class="conv-title">{{ conv.title || t('conversation.sidebar.defaultTitle') }}</div>
              <div class="conv-time">{{ formatRelativeTime(conv.updated_at) }}</div>
            </div>
            <button class="conv-delete" @click.stop="handleDelete(conv)" :title="t('conversation.sidebar.delete')">
              <el-icon :size="14"><Delete /></el-icon>
            </button>
          </div>
          <div v-if="!loading && filteredConversations.length === 0" class="empty-list">
            <p>{{ searchQuery ? t('conversation.sidebar.noMatches') : t('conversation.sidebar.noConversations') }}</p>
          </div>
        </el-scrollbar>
      </div>

      <!-- 底部：医疗免责声明入口 -->
      <div class="sidebar-footer">
        <router-link to="/disclaimer" class="disclaimer-entry">
          {{ t('common.disclaimerTitle') }}
        </router-link>
      </div>
    </div>

    <TemplateQuickPicker
      v-model="showTemplatePicker"
      @select="onTemplateSelect"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useConversationsStore } from '@/stores/conversations'
import { useLeaderStore } from '@/stores/leader'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Delete } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import TemplateQuickPicker from '@/components/TemplateQuickPicker.vue'

dayjs.extend(relativeTime)

const props = defineProps({
  expanded: { type: Boolean, default: true },
  isMobile: { type: Boolean, default: false }
})

const emit = defineEmits(['collapse', 'expand'])

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const conversationsStore = useConversationsStore()
const leaderStore = useLeaderStore()

const searchQuery = ref('')
const loading = ref(false)
const showTemplatePicker = ref(false)

const conversations = computed(() => conversationsStore.conversations)

const filteredConversations = computed(() => {
  if (!searchQuery.value) return conversations.value
  const q = searchQuery.value.toLowerCase()
  return conversations.value.filter(c => (c.title || '').toLowerCase().includes(q))
})

function isActive(conv) {
  // 通过路由参数或 share_token 判断当前对话
  const currentToken = route.params.token
  return conv.share_token === currentToken || String(conv.id) === currentToken
}

function formatRelativeTime(time) {
  if (!time) return ''
  const d = dayjs(time)
  const now = dayjs()
  if (now.diff(d, 'day') < 1) return d.fromNow()
  if (now.diff(d, 'year') < 1) return d.format(t('conversation.sidebar.dateFormat'))
  return d.format(t('conversation.sidebar.yearDateFormat'))
}

async function loadConversations() {
  loading.value = true
  await conversationsStore.fetchConversations()
  loading.value = false
}

function handleNewChat() {
  // 在 ChatLayout 内使用 /chat 路径，否则使用首页
  if (route.path.startsWith('/chat')) {
    router.push('/chat')
  } else {
    router.push('/')
  }
  if (props.isMobile) emit('collapse')
}

function handleSelect(conv) {
  const token = conv.share_token || conv.id
  // 在 ChatLayout 内使用 /chat/:token 路径，保持侧边栏
  if (route.path.startsWith('/chat')) {
    router.push(`/chat/${token}`)
  } else {
    router.push(`/conversation/${token}`)
  }
  if (props.isMobile) emit('collapse')
}

async function onTemplateSelect(tpl) {
  try {
    const result = await conversationsStore.createConversation(
      tpl.name,
      true,
      null,
    )
    if (!result.success) {
      ElMessage.error(t('conversation.sidebar.createFailed'))
      return
    }
    const token = result.conversation.share_token || result.conversation.id
    leaderStore.pendingSessionData = {
      message: tpl.description || tpl.name,
      fileIds: [],
      templateId: tpl.id,
    }
    if (route.path.startsWith('/chat')) {
      router.push(`/chat/${token}`)
    } else {
      router.push(`/conversation/${token}`)
    }
    if (props.isMobile) emit('collapse')
  } catch (err) {
    ElMessage.error(t('conversation.sidebar.startPlanFailed'))
  }
}

async function handleDelete(conv) {
  try {
    await ElMessageBox.confirm(t('conversation.sidebar.deleteConfirm'), t('conversation.sidebar.deleteConfirmTitle'), {
      confirmButtonText: t('conversation.sidebar.delete'),
      cancelButtonText: t('common.actions.cancel'),
      type: 'warning'
    })
    const result = await conversationsStore.deleteConversation(conv.id)
    if (result.success) {
      ElMessage.success(t('conversation.sidebar.deleted'))
      // 若删除的是当前对话，返回首页
      if (isActive(conv)) {
        if (route.path.startsWith('/chat')) {
          router.push('/chat')
        } else {
          router.push('/')
        }
      }
    } else {
      ElMessage.error(result.error || t('conversation.sidebar.deleteFailed'))
    }
  } catch {
    // 用户取消
  }
}

// 当路由变化时刷新列表（例如新建对话后）
watch(() => route.path, () => {
  loadConversations()
})

onMounted(() => {
  loadConversations()
})
</script>

<style scoped lang="scss">
.sidebar {
  position: relative;
  height: 100%;
  transition: width 0.25s ease;
  flex-shrink: 0;

  &.mobile-overlay {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 2000;
    width: 100%;
    height: 100%;
  }
}

.sidebar-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 1;
}

.sidebar-inner {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 260px;
  background: #1e1e2e;
  color: #cdd6f4;
  border-right: 1px solid #313244;
  transition: width 0.25s ease;
  overflow: hidden;

  .collapsed & {
    width: 0;
    overflow: hidden;
    border-right: none;
  }

  .mobile-overlay & {
    width: 280px;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.3);
  }
}

/* Header */
.sidebar-header {
  padding: 16px 16px 8px;
  flex-shrink: 0;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.logo-icon {
  width: 28px;
  height: 28px;
}

.logo-text {
  font-size: 15px;
  font-weight: 700;
  color: #cdd6f4;
  white-space: nowrap;
}

.toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid #45475a;
  border-radius: 6px;
  color: #a6adc8;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: #313244;
    color: #cdd6f4;
    border-color: #585b70;
  }
}

.new-chat-btn {
  width: 100%;
  height: 38px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 8px;
  gap: 6px;
}

.template-start-btn {
  width: 100%;
  padding: 6px 0;
  background: none;
  border: none;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  cursor: pointer;
  text-align: center;
  transition: color 0.2s;

  &:hover {
    color: var(--el-color-primary);
  }
}

/* Search */
.sidebar-search {
  padding: 0 16px 8px;
  flex-shrink: 0;

  :deep(.el-input__wrapper) {
    background: #313244;
    border-radius: 8px;
    box-shadow: none;
    border: 1px solid #45475a;

    &:hover, &.is-focus {
      border-color: #89b4fa;
    }
  }

  :deep(.el-input__inner) {
    color: #cdd6f4;
    &::placeholder { color: #6c7086; }
  }

  :deep(.el-input__prefix .el-icon) {
    color: #6c7086;
  }
}

/* List */
.sidebar-list {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 0 8px;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 2px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: #313244;

    .conv-delete { opacity: 1; }
  }

  &.active {
    background: #45475a;
  }
}

.conv-item-content {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-size: 13px;
  font-weight: 500;
  color: #cdd6f4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.conv-time {
  font-size: 11px;
  color: #6c7086;
  margin-top: 2px;
}

.conv-delete {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: #6c7086;
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s ease;
  flex-shrink: 0;

  &:hover {
    background: #f38ba8;
    color: #1e1e2e;
  }
}

.empty-list {
  text-align: center;
  padding: 32px 16px;
  color: #6c7086;
  font-size: 13px;

  p { margin: 0; }
}

/* Scrollbar 暗色覆盖 */
:deep(.el-scrollbar__bar) {
  .el-scrollbar__thumb {
    background: #45475a;
    &:hover { background: #585b70; }
  }
}

/* 底部：免责声明入口 */
.sidebar-footer {
  padding: 10px 12px;
  border-top: 1px solid var(--color-border, #e5e7eb);
  display: flex;
  justify-content: center;
  align-items: center;
  background: var(--color-card, #ffffff);
  flex-shrink: 0;
}

.disclaimer-entry {
  font-size: var(--font-size-xs, 12px);
  color: var(--color-text-secondary, #64748b);
  text-decoration: none;
}

.disclaimer-entry:hover {
  color: var(--color-primary, #2563eb);
  text-decoration: underline;
}

.sidebar.collapsed .sidebar-footer {
  display: none;
}
</style>
