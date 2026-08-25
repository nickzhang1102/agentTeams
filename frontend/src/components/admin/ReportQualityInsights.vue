<template>
  <section class="report-quality-insights">
    <div class="section-header">
      <h3>{{ t('admin.qualityInsights.title') }}</h3>
      <el-segmented
        v-model="selectedPeriod"
        :options="periodOptions"
        size="small"
        @change="handlePeriodChange"
      />
    </div>

    <el-skeleton v-if="adminStore.reportQualityInsightsLoading" animated :rows="4" />

    <el-empty
      v-else-if="adminStore.reportQualityInsightsError"
      :description="adminStore.reportQualityInsightsError"
    >
      <el-button size="small" type="primary" @click="loadInsights">{{ t('admin.actions.retry') }}</el-button>
    </el-empty>

    <el-empty
      v-else-if="!hasRatings"
      :description="t('admin.qualityInsights.noRatings')"
    />

    <template v-else>
      <div class="quality-summary">
        <div class="quality-metric">
          <span class="metric-label">{{ t('admin.qualityInsights.totalRatings') }}</span>
          <strong>{{ summary.total_ratings }}</strong>
        </div>
        <div class="quality-metric">
          <span class="metric-label">{{ t('admin.qualityInsights.positiveRate') }}</span>
          <strong class="positive">{{ summary.positive_rate }}%</strong>
        </div>
        <div class="quality-metric">
          <span class="metric-label">{{ t('admin.qualityInsights.negativeRate') }}</span>
          <strong class="negative">{{ summary.negative_rate }}%</strong>
        </div>
        <div class="quality-metric">
          <span class="metric-label">{{ t('admin.qualityInsights.period') }}</span>
          <strong>{{ t('admin.qualityInsights.days', { count: insights.period_days }) }}</strong>
        </div>
      </div>

      <div class="insight-grid">
        <div class="insight-panel">
          <h4>{{ t('admin.qualityInsights.problemClusters') }}</h4>
          <div v-if="clusters.length" class="cluster-list">
            <div
              v-for="cluster in clusters"
              :key="cluster.key"
              class="cluster-row"
            >
              <div class="cluster-main">
                <span>{{ cluster.label }}</span>
                <small>{{ t('admin.qualityInsights.clusterCount', { count: cluster.count, share: cluster.share }) }}</small>
              </div>
              <el-progress
                :percentage="cluster.share"
                :stroke-width="8"
                :show-text="false"
              />
              <p v-if="cluster.examples?.length" class="cluster-example">
                {{ cluster.examples[0] }}
              </p>
            </div>
          </div>
          <el-empty v-else :description="t('admin.qualityInsights.noNegativeComments')" :image-size="72" />
        </div>

        <div class="insight-panel">
          <h4>{{ t('admin.qualityInsights.targetBreakdown') }}</h4>
          <el-table :data="targetBreakdown" size="small" border>
            <el-table-column :label="t('admin.qualityInsights.target')" min-width="110">
              <template #default="{ row }">
                {{ targetTypeLabel(row.target_type) }}
              </template>
            </el-table-column>
            <el-table-column prop="total" :label="t('admin.qualityInsights.ratings')" width="72" align="center" />
            <el-table-column :label="t('admin.qualityInsights.positiveRate')" width="84" align="center">
              <template #default="{ row }">{{ row.positive_rate }}%</template>
            </el-table-column>
            <el-table-column :label="t('admin.qualityInsights.negativeRate')" width="84" align="center">
              <template #default="{ row }">{{ row.negative_rate }}%</template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <div class="negative-comments">
        <h4>{{ t('admin.qualityInsights.recentNegativeComments') }}</h4>
        <div v-if="recentComments.length" class="comment-list">
          <div
            v-for="comment in recentComments"
            :key="comment.id"
            class="comment-row"
          >
            <el-tag size="small" type="danger">
              {{ targetTypeLabel(comment.target_type) }} #{{ comment.target_id }}
            </el-tag>
            <span class="comment-text">{{ comment.comment }}</span>
            <time>{{ formatTime(comment.created_at) }}</time>
          </div>
        </div>
        <el-empty v-else :description="t('admin.qualityInsights.noNegativeComments')" :image-size="72" />
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAdminStore } from '@/stores/admin'
import { formatLocaleDateTime } from '@/utils/localeFormat'

const adminStore = useAdminStore()
const { t, locale } = useI18n()
const selectedPeriod = ref('30d')
const periodOptions = computed(() => [
  { label: t('admin.qualityInsights.periods.sevenDays'), value: '7d' },
  { label: t('admin.qualityInsights.periods.thirtyDays'), value: '30d' },
  { label: t('admin.qualityInsights.periods.ninetyDays'), value: '90d' }
])

const insights = computed(() => adminStore.reportQualityInsights || {})
const summary = computed(() => insights.value.summary || {
  total_ratings: 0,
  positive_count: 0,
  negative_count: 0,
  positive_rate: 0,
  negative_rate: 0
})
const clusters = computed(() => insights.value.problem_clusters || [])
const targetBreakdown = computed(() => insights.value.target_breakdown || [])
const recentComments = computed(() => insights.value.recent_negative_comments || [])
const hasRatings = computed(() => summary.value.total_ratings > 0)

function targetTypeLabel(type) {
  const key = type === 'final_report' ? 'final_report' : 'agent_result'
  return t(`admin.qualityInsights.targetTypes.${key}`)
}

function formatTime(value) {
  return formatLocaleDateTime(value, locale.value, {
    year: undefined,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function loadInsights() {
  return adminStore.fetchReportQualityInsights(selectedPeriod.value)
}

function handlePeriodChange() {
  loadInsights()
}

onMounted(() => {
  loadInsights()
})
</script>

<style lang="scss" scoped>
.report-quality-insights {
  background: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  padding: 20px;
  margin-top: 8px;
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;

  h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin: 0;
  }
}

.quality-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.quality-metric {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  min-width: 0;

  .metric-label {
    display: block;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-bottom: 6px;
  }

  strong {
    font-size: 22px;
    line-height: 1.2;
    color: var(--el-text-color-primary);
  }

  .positive {
    color: var(--el-color-success);
  }

  .negative {
    color: var(--el-color-danger);
  }
}

.insight-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 16px;
}

.insight-panel,
.negative-comments {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px;

  h4 {
    font-size: 14px;
    font-weight: 600;
    margin: 0 0 12px;
    color: var(--el-text-color-primary);
  }
}

.negative-comments {
  margin-top: 16px;
}

.cluster-list,
.comment-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cluster-main {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;

  span {
    font-size: 14px;
    color: var(--el-text-color-primary);
  }

  small {
    color: var(--el-text-color-secondary);
  }
}

.cluster-example {
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
  margin: 6px 0 0;
}

.comment-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  font-size: 13px;

  .comment-text {
    color: var(--el-text-color-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  time {
    color: var(--el-text-color-secondary);
    white-space: nowrap;
  }
}

@media (max-width: 900px) {
  .quality-summary,
  .insight-grid {
    grid-template-columns: 1fr;
  }

  .section-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .comment-row {
    grid-template-columns: 1fr;
    align-items: flex-start;

    .comment-text {
      white-space: normal;
    }
  }
}
</style>
