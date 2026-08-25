<template>
  <div class="admin-performance">
    <div class="page-header">
      <h2>{{ t('admin.nav.performance') }}</h2>
      <p class="page-desc">{{ t('admin.performance.description') }}</p>
    </div>

    <!-- 时间段选择 -->
    <div class="period-selector">
      <el-radio-group v-model="period" @change="handlePeriodChange">
        <el-radio-button value="day">{{ t('admin.performance.periods.day') }}</el-radio-button>
        <el-radio-button value="week">{{ t('admin.performance.periods.week') }}</el-radio-button>
        <el-radio-button value="month">{{ t('admin.performance.periods.month') }}</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <StatsCard :icon="Coin" :label="t('admin.performance.totalTokens')" :value="overview?.token_usage?.total || 0" color="#409eff" />
      <StatsCard :icon="TrendCharts" :label="t('admin.performance.dailyAverage')" :value="overview?.token_usage?.daily_avg || 0" color="#67c23a" />
      <StatsCard :icon="Money" :label="t('admin.performance.totalCost')" :value="formatCurrency(overview?.cost?.total)" color="#e6a23c" />
      <StatsCard :icon="WarningFilled" :label="t('admin.performance.errorRate')" :value="formatPercent(overview?.errors?.rate)" color="#f56c6c" />
    </div>

    <!-- Token 趋势图 -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span>{{ t('admin.performance.tokenTrend') }}</span>
          <span class="card-header-sub">{{ t('admin.performance.dailyAverageTokens', { count: formatNumber(overview?.token_usage?.daily_avg || 0) }) }}</span>
        </div>
      </template>
      <PerformanceChart :data="adminStore.tokenTrend" />
    </el-card>

    <!-- Agent 执行排名 -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span>{{ t('admin.performance.agentRanking') }}</span>
          <span class="card-header-sub">{{ t('admin.performance.totalCalls', { count: formatNumber(overview?.agent_execution?.total_calls || 0) }) }}</span>
        </div>
      </template>
      <el-table :data="adminStore.agentPerformance" stripe style="width: 100%" v-loading="loading">
        <el-table-column prop="agent_id" label="Agent ID" min-width="120" />
        <el-table-column prop="name" :label="t('admin.common.name')" min-width="120" />
        <el-table-column prop="total_calls" :label="t('admin.performance.calls')" width="100" align="center" />
        <el-table-column :label="t('admin.performance.successRate')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.success_rate >= 90 ? 'success' : row.success_rate >= 70 ? 'warning' : 'danger'" size="small">
              {{ row.success_rate }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="avg_time" :label="t('admin.performance.averageDuration')" width="110" align="center">
          <template #default="{ row }">
            {{ row.avg_time }}s
          </template>
        </el-table-column>
        <el-table-column prop="total_tokens" :label="t('admin.performance.tokenUsage')" width="120" align="right" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Coin, TrendCharts, Money, WarningFilled } from '@element-plus/icons-vue'
import { useAdminStore } from '@/stores/admin'
import StatsCard from '@/components/admin/StatsCard.vue'
import PerformanceChart from '@/components/admin/PerformanceChart.vue'
import { formatLocaleNumber } from '@/utils/localeFormat'

const adminStore = useAdminStore()
const { t, locale } = useI18n()

const period = ref('week')
const loading = ref(false)

const overview = ref(null)

function formatNumber(value) {
  return formatLocaleNumber(value || 0, locale.value)
}

function formatCurrency(value) {
  return formatLocaleNumber(value || 0, locale.value, { style: 'currency', currency: 'USD' })
}

function formatPercent(value) {
  return `${formatLocaleNumber(value || 0, locale.value)}%`
}

async function loadData() {
  loading.value = true
  try {
    const [overviewResult] = await Promise.allSettled([
      adminStore.fetchPerformanceOverview(period.value)
    ])
    if (overviewResult.status === 'fulfilled' && overviewResult.value) {
      overview.value = overviewResult.value
    }
    // 根据周期获取趋势数据
    const granularity = period.value === 'day' ? 'hour' : 'day'
    await adminStore.fetchTokenTrend({ granularity })
    // 获取 Agent 性能
    await adminStore.fetchAgentPerformance()
  } finally {
    loading.value = false
  }
}

function handlePeriodChange() {
  loadData()
}

onMounted(() => {
  loadData()
})
</script>

<style lang="scss" scoped>
.admin-performance {
  max-width: 1200px;
}

.page-header {
  margin-bottom: 20px;

  h2 {
    margin: 0 0 8px;
    font-size: 20px;
    color: var(--el-text-color-primary);
  }

  .page-desc {
    margin: 0;
    color: var(--el-text-color-secondary);
    font-size: 14px;
  }
}

.period-selector {
  margin-bottom: 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.section-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: 15px;

  .card-header-sub {
    font-weight: 400;
    font-size: 13px;
    color: var(--el-text-color-secondary);
  }
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
}
</style>
