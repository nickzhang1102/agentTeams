<template>
  <div class="admin-dashboard">
    <h2 class="page-title">{{ t('admin.nav.dashboard') }}</h2>

    <!-- 加载骨架屏 -->
    <template v-if="loading">
      <div class="stats-grid">
        <el-skeleton v-for="i in 4" :key="i" animated>
          <template #template>
            <div class="skeleton-card">
              <el-skeleton-item variant="circle" style="width: 48px; height: 48px;" />
              <div style="flex: 1; margin-left: 16px;">
                <el-skeleton-item variant="h1" style="width: 60%;" />
                <el-skeleton-item variant="text" style="width: 40%; margin-top: 8px;" />
              </div>
            </div>
          </template>
        </el-skeleton>
      </div>
    </template>

    <!-- 错误状态 -->
    <template v-else-if="error">
      <el-empty :description="t('admin.dashboard.loadFailed')">
        <el-button type="primary" @click="loadData">{{ t('admin.actions.retry') }}</el-button>
      </el-empty>
    </template>

    <!-- 正常内容 -->
    <template v-else>
      <!-- 统计卡片 -->
      <div class="stats-grid">
        <StatsCard :icon="User" :label="t('admin.dashboard.stats.totalUsers')" :value="statsData.users.total" color="#409eff" />
        <StatsCard :icon="ChatDotRound" :label="t('admin.dashboard.stats.conversationsToday')" :value="statsData.conversations.today" color="#67c23a" />
        <StatsCard :icon="Message" :label="t('admin.dashboard.stats.messagesToday')" :value="statsData.messages.today" color="#e6a23c" />
        <StatsCard :icon="Cpu" :label="t('admin.dashboard.stats.activeAgents')" :value="statsData.agents.active" color="#f56c6c" />
      </div>

      <!-- 补充统计行 -->
      <div class="stats-grid stats-grid-secondary">
        <StatsCard :icon="UserFilled" :label="t('admin.dashboard.stats.activeToday')" :value="statsData.users.active_today" color="#9b59b6" />
        <StatsCard :icon="ChatLineSquare" :label="t('admin.dashboard.stats.totalConversations')" :value="statsData.conversations.total" color="#3498db" />
        <StatsCard :icon="ChatLineRound" :label="t('admin.dashboard.stats.totalMessages')" :value="statsData.messages.total" color="#1abc9c" />
        <StatsCard :icon="Cpu" :label="t('admin.dashboard.stats.agentSuccessRate')" :value="formatPercent(statsData.agents.success_rate)" color="#e67e22" />
      </div>

      <ReportQualityInsights />

      <!-- 会话管理 -->
      <div class="conversation-section">
        <div class="section-header">
          <h3>{{ t('admin.dashboard.conversations') }}</h3>
          <div class="filter-bar">
            <el-select
              v-model="adminStore.conversationFilters.user_id"
              :placeholder="t('admin.dashboard.allUsers')"
              clearable
              size="small"
              style="width: 140px"
              @change="handleFilterChange"
            >
              <el-option
                v-for="u in adminStore.users"
                :key="u.id"
                :label="u.username"
                :value="u.id"
              />
            </el-select>
            <el-select
              v-model="adminStore.conversationFilters.category"
              :placeholder="t('admin.dashboard.allCategories')"
              clearable
              size="small"
              style="width: 120px"
              @change="handleFilterChange"
            >
              <el-option v-for="option in categoryOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-select
              v-model="adminStore.conversationFilters.status"
              :placeholder="t('admin.dashboard.allStatuses')"
              clearable
              size="small"
              style="width: 120px"
              @change="handleFilterChange"
            >
              <el-option v-for="option in statusOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
          </div>
        </div>

        <el-table
          :data="adminStore.conversations"
          stripe
          size="small"
          v-loading="adminStore.loading"
          style="width: 100%"
        >
          <el-table-column prop="id" label="ID" width="70" align="center" />
          <el-table-column prop="title" :label="t('admin.dashboard.title')" min-width="200" show-overflow-tooltip />
          <el-table-column prop="username" :label="t('admin.dashboard.user')" width="100" />
          <el-table-column :label="t('admin.dashboard.category')" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="categoryType(row.category)">{{ categoryLabel(row.category) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.dashboard.status')" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.dashboard.review')" width="60" align="center">
            <template #default="{ row }">
              <el-icon v-if="row.is_review_mode" color="#409eff"><Check /></el-icon>
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.common.updatedAt')" width="160">
            <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column :label="t('admin.common.operations')" width="80" align="center" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openConversation(row)">{{ t('admin.actions.view') }}</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrap" v-if="adminStore.conversationPagination.total > 0">
          <el-pagination
            small
            layout="total, prev, pager, next"
            :total="adminStore.conversationPagination.total"
            :page-size="adminStore.conversationPagination.per_page"
            :current-page="adminStore.conversationPagination.page"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { User, ChatDotRound, Message, Cpu, UserFilled, ChatLineSquare, ChatLineRound, Check } from '@element-plus/icons-vue'
import { useAdminStore } from '@/stores/admin'
import StatsCard from '@/components/admin/StatsCard.vue'
import ReportQualityInsights from '@/components/admin/ReportQualityInsights.vue'
import { formatLocaleDateTime, formatLocaleNumber } from '@/utils/localeFormat'

const adminStore = useAdminStore()
const router = useRouter()
const { t, locale } = useI18n()

const loading = ref(true)
const error = ref(false)

const statsData = ref({
  users: { total: 0, active_today: 0 },
  conversations: { total: 0, today: 0 },
  messages: { total: 0, today: 0 },
  agents: { total: 0, active: 0, success_rate: 0 }
})

// 分类映射
const CATEGORY_KEYS = ['technology', 'business', 'medical', 'investment', 'science', 'writing', 'legal', 'education', 'lifestyle', 'other']
const CATEGORY_TYPE = {
  technology: '', business: 'success', medical: 'danger', investment: 'warning',
  science: 'info', writing: '', legal: 'warning', education: 'success',
  lifestyle: 'info', other: 'info'
}

const STATUS_KEYS = ['new', 'analyzing', 'error', 'completed']
const STATUS_TYPE = { new: 'info', analyzing: 'warning', error: 'danger', completed: 'success' }

const categoryOptions = computed(() => CATEGORY_KEYS.map(value => ({ value, label: categoryLabel(value) })))
const statusOptions = computed(() => STATUS_KEYS.map(value => ({ value, label: statusLabel(value) })))

function categoryLabel(c) { return c ? t(`admin.dashboard.categories.${c}`, c) : t('admin.dashboard.categories.other') }
function categoryType(c) { return CATEGORY_TYPE[c] || 'info' }
function statusLabel(s) { return s ? t(`admin.dashboard.statuses.${s}`, s) : t('admin.dashboard.statuses.new') }
function statusType(s) { return STATUS_TYPE[s] || 'info' }
function formatTime(value) { return formatLocaleDateTime(value, locale.value) }
function formatPercent(value) { return `${formatLocaleNumber(value || 0, locale.value)}%` }

function handleFilterChange() {
  adminStore.fetchConversations(1)
}

function handlePageChange(page) {
  adminStore.fetchConversations(page)
}

function openConversation(row) {
  const token = row.share_token || row.id
  const url = router.resolve({ path: `/conversation/${token}` }).href
  window.open(url, '_blank')
}

async function loadData() {
  loading.value = true
  error.value = false

  try {
    const [statsResult] = await Promise.allSettled([
      adminStore.fetchDashboardStats(),
      adminStore.fetchUsers(),
      adminStore.fetchConversations(1)
    ])

    if (statsResult.status === 'fulfilled' && adminStore.dashboardStats) {
      statsData.value = adminStore.dashboardStats
    }

    if (statsResult.status === 'rejected') {
      error.value = true
    }
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style lang="scss" scoped>
.admin-dashboard {
  max-width: 1200px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 0 0 20px 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.stats-grid-secondary {
  .stats-card {
    padding: 16px 20px;

    .stats-value {
      font-size: 20px;
    }

    .stats-icon {
      width: 40px;
      height: 40px;

      :deep(.el-icon) {
        font-size: 22px;
      }
    }
  }
}

.skeleton-card {
  display: flex;
  align-items: center;
  padding: 20px;
  background: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.conversation-section {
  background: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  padding: 20px;
  margin-top: 8px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;

  h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin: 0;
  }
}

.filter-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .page-title {
    font-size: 18px;
  }

  .section-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
