<template>
  <div class="agents-page">
    <!-- 顶部导航 -->
    <header class="header">
      <div class="header-content">
        <div class="header-left">
          <el-button text class="back-btn" @click="handleBack">
            <el-icon><ArrowLeft /></el-icon>
            <span>{{ t('agentsPage.back') }}</span>
          </el-button>
        </div>
        <div class="header-center">
          <h1 class="page-title">{{ t('agentsPage.title') }}</h1>
        </div>
        <div class="header-right">
          <UserMenuDropdown :auth-store="authStore" />
        </div>
      </div>
    </header>

    <div class="page-body">
      <div class="page-actions">
        <el-button type="primary" @click="showCreateDialog = true">
          + {{ t('agentsPage.create') }}
        </el-button>
      </div>

    <!-- 分类 Tab（动态） -->
    <el-tabs v-model="filter.activeTab.value" class="category-tabs" @tab-change="onTabChange">
      <el-tab-pane
        v-for="cat in store.categories"
        :key="cat.key"
        :label="cat.key === 'all' ? catalogLabel(cat) : `${catalogLabel(cat)} (${cat.count})`"
        :name="cat.key"
      />
      <el-tab-pane :label="t('agentsPage.system')" name="system" />
      <el-tab-pane :label="t('agentsPage.custom')" name="custom" />
    </el-tabs>

    <!-- 搜索 -->
    <div class="filter-bar">
      <el-input
        v-model="filter.searchText.value"
        :placeholder="t('agentsPage.search')"
        clearable
        :prefix-icon="Search"
        @keyup.enter="filter.handleFilterChange()"
        @clear="filter.handleFilterChange()"
      />
    </div>

    <!-- 阵型布局 -->
    <div v-loading="store.loading">
      <AgentFormation
        v-if="store.userAgents.length > 0"
        :agents="store.userAgents"
        :can-drag="canDrag"
        :mode="authStore.user?.is_admin ? 'admin' : 'user'"
        @card-click="handleCardClick"
        @edit="handleEdit"
        @delete="handleDelete"
        @priority-change="handlePriorityChange"
      />
      <el-empty v-else-if="!store.loading" :description="t('agentsPage.empty')" />
    </div>

    </div><!-- /.page-body -->

    <!-- 创建/编辑弹窗 -->
    <AgentCreateDialog
      v-model="showCreateDialog"
      :edit-agent="editingAgent"
      @saved="onAgentSaved"
    />

    <!-- 详情弹窗 -->
    <AgentDetailDialog
      v-model="showDetailDialog"
      :agent="detailAgent"
    />
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, ArrowLeft } from '@element-plus/icons-vue'
import { useAgentsStore } from '@/stores/agents'
import { useAuthStore } from '@/stores/auth'
import { useAgentFilter } from '@/composables/useAgentFilter'
import AgentFormation from '@/components/agent/AgentFormation.vue'
import AgentDetailDialog from '@/components/agent/AgentDetailDialog.vue'
import UserMenuDropdown from '@/components/UserMenuDropdown.vue'
import AgentCreateDialog from './AgentCreateDialog.vue'
import { catalogLabel } from '@/utils/catalog'

const router = useRouter()
const { t } = useI18n()
const store = useAgentsStore()
const authStore = useAuthStore()

const showCreateDialog = ref(false)

function handleBack() {
  router.push('/')
}
const editingAgent = ref(null)
const showDetailDialog = ref(false)
const detailAgent = ref(null)

watch(showCreateDialog, (val) => {
  if (!val) editingAgent.value = null
})

watch(showDetailDialog, (val) => {
  if (!val) detailAgent.value = null
})

watch(() => store.userAgents, (items) => {
  if (!detailAgent.value) return
  const agentId = detailAgent.value.agent_id || detailAgent.value.id
  detailAgent.value = items.find(item => (item.agent_id || item.id) === agentId) || detailAgent.value
})

const filter = useAgentFilter({
  fetchFn: (params) => store.fetchUserAgents(params),
})

function canEdit(agent) {
  if (authStore.user?.is_admin) return true
  if (agent.is_system) return false
  return agent.created_by === authStore.user?.id
}

function canDrag(agent) {
  // admin 可拖所有 agent，普通用户仅可拖自建 agent
  if (authStore.user?.is_admin) return true
  return canEdit(agent)
}

async function handlePriorityChange({ agentId, priority }) {
  const result = await store.updateBatchPriority([{ agent_id: agentId, priority }])
  if (!result.success) {
    ElMessage.error(result.error)
    // 更新失败，刷新列表回滚本地状态
    filter.handleFilterChange()
  }
}

function onTabChange() {
  filter.handleFilterChange()
}

function handleCardClick(agent) {
  detailAgent.value = agent
  showDetailDialog.value = true
}

function handleEdit(agent) {
  editingAgent.value = agent
  showCreateDialog.value = true
}

async function handleDelete(agent) {
  try {
    await ElMessageBox.confirm(
      t('agentsPage.deletePrompt', { name: catalogLabel(agent) }),
      t('agentsPage.deleteTitle'),
      { confirmButtonText: t('agentsPage.confirm'), cancelButtonText: t('common.actions.cancel'), type: 'warning' }
    )
    const result = await store.deleteUserAgent(agent.agent_id)
    if (result.success) {
      ElMessage.success(t('agentsPage.deleteSuccess'))
      filter.handleFilterChange()
    } else {
      ElMessage.error(result.error)
    }
  } catch {
    // 取消
  }
}

function onAgentSaved() {
  showCreateDialog.value = false
  editingAgent.value = null
  filter.handleFilterChange()
}

onMounted(() => {
  store.fetchCategories()
  filter.handleFilterChange()
})
</script>

<style lang="scss" scoped>
.agents-page {
  min-height: 100vh;
  background: var(--color-background);
}

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
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
}

.header-left { display: flex; align-items: center; }

.back-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-in-out);
}
.back-btn:hover {
  background: var(--color-hover);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.page-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text);
  margin: 0;
}

.header-right { display: flex; align-items: center; }

/* 页面内容 */
.page-body {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.page-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 20px;
}

.category-tabs {
  margin-bottom: 16px;

  // 移动端 Tab 横向可滚动
  :deep(.el-tabs__nav-wrap) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  :deep(.el-tabs__nav-scroll) {
    white-space: nowrap;
  }
}

.filter-bar {
  margin-bottom: 16px;
}

@media (max-width: 767px) {
  .page-body { padding: 12px; }
  .header-center {
    position: static;
    transform: none;
  }
  .page-title {
    font-size: var(--font-size-base);
  }
}
</style>
