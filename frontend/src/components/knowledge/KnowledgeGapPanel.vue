<template>
  <div class="gap-panel">
    <div class="panel-header">
      <h3 class="panel-title">{{ t('knowledge.gap.title') }}</h3>
      <el-button :icon="Close" text @click="$emit('close')" />
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="panel-loading">
      <el-skeleton :rows="4" animated />
    </div>

    <!-- 无数据 -->
    <div v-else-if="!data" class="panel-empty">
      <el-empty :description="t('knowledge.gap.empty')" :image-size="60" />
    </div>

    <!-- 分析结果 -->
    <div v-else class="panel-body">
      <!-- 摘要卡片 -->
      <div class="gap-summary">
        <el-row :gutter="10">
          <el-col :span="8">
            <div class="stat-card stat-warning">
              <div class="stat-value">{{ data.summary.weak_node_count }}</div>
              <div class="stat-label">{{ t('knowledge.gap.weakNodes') }}</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="stat-card stat-danger">
              <div class="stat-value">{{ data.summary.isolated_node_count }}</div>
              <div class="stat-label">{{ t('knowledge.gap.isolatedNodes') }}</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="stat-card stat-info">
              <div class="stat-value">{{ data.summary.missing_bridge_count }}</div>
              <div class="stat-label">{{ t('knowledge.gap.missingBridges') }}</div>
            </div>
          </el-col>
        </el-row>
        <div class="coverage-bar">
          <span class="coverage-label">{{ t('knowledge.gap.coverage') }}</span>
          <el-progress
            :percentage="data.summary.coverage_score"
            :color="coverageColor"
            :stroke-width="10"
          />
        </div>
      </div>

      <!-- Tab 面板 -->
      <el-tabs v-model="activeTab" class="gap-tabs">
        <el-tab-pane :label="t('knowledge.gap.weakNodes')" name="weak">
          <el-scrollbar>
            <div
              v-for="node in data.weak_nodes"
              :key="node.id"
              class="gap-item"
              :class="{ 'is-weak': node.degree <= 1 }"
              @click="$emit('highlight-weak', node.id)"
            >
              <span class="item-degree" :class="degreeClass(node.degree)">
                {{ node.degree }}
              </span>
              <span class="item-label">{{ node.label }}</span>
              <el-tag size="small" type="info">C{{ node.community }}</el-tag>
            </div>
            <div v-if="data.weak_nodes.length === 0" class="empty-hint">
              {{ t('knowledge.gap.noWeakNodes') }}
            </div>
          </el-scrollbar>
        </el-tab-pane>

        <el-tab-pane :label="t('knowledge.gap.missingBridges')" name="bridges">
          <el-scrollbar>
            <div
              v-for="bridge in data.missing_bridges"
              :key="`${bridge.community_a}-${bridge.community_b}`"
              class="gap-item bridge-item"
              @click="$emit('highlight-bridge', bridge.community_a, bridge.community_b)"
            >
              <el-icon color="#ef4444"><Connection /></el-icon>
              <span class="bridge-pair">
                C{{ bridge.community_a }}
                <span class="bridge-label">{{ bridge.community_a_label }}</span>
                ↔
                C{{ bridge.community_b }}
                <span class="bridge-label">{{ bridge.community_b_label }}</span>
              </span>
            </div>
            <div v-if="data.missing_bridges.length === 0" class="empty-hint">
              {{ t('knowledge.gap.graphConnected') }}
            </div>
          </el-scrollbar>
        </el-tab-pane>

        <el-tab-pane :label="t('knowledge.gap.suggestions')" name="suggestions">
          <el-scrollbar>
            <div
              v-for="(suggestion, idx) in sortedSuggestions"
              :key="idx"
              class="gap-item suggestion-item"
            >
              <el-tag
                size="small"
                :type="priorityType(suggestion.priority)"
              >
                {{ priorityLabel(suggestion.priority) }}
              </el-tag>
              <span class="suggestion-desc">{{ suggestion.description }}</span>
            </div>
            <div v-if="data.suggestions.length === 0" class="empty-hint">
              {{ t('knowledge.gap.noSuggestions') }}
            </div>
          </el-scrollbar>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Close, Connection } from '@element-plus/icons-vue'

const props = defineProps({
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false }
})

defineEmits(['close', 'highlight-weak', 'highlight-bridge'])
const { t } = useI18n()

const activeTab = ref('weak')

const coverageColor = computed(() => {
  const score = props.data?.summary?.coverage_score ?? 0
  if (score >= 80) return '#10b981'
  if (score >= 60) return '#f59e0b'
  return '#ef4444'
})

const priorityOrder = { high: 0, medium: 1, low: 2 }

const sortedSuggestions = computed(() => {
  if (!props.data?.suggestions) return []
  return [...props.data.suggestions].sort(
    (a, b) => (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9)
  )
})

function degreeClass(degree) {
  if (degree === 0) return 'degree-zero'
  if (degree === 1) return 'degree-one'
  return 'degree-two'
}

function priorityType(priority) {
  if (priority === 'high') return 'danger'
  if (priority === 'medium') return 'warning'
  return 'info'
}

function priorityLabel(priority) {
  return t(`knowledge.gap.priority.${priority}`, priority)
}
</script>

<style scoped>
.gap-panel {
  position: absolute;
  top: 0;
  left: 0;
  width: 320px;
  height: 100%;
  background: var(--color-bg-card, #fff);
  border-right: 1px solid var(--color-border, #e4e7ed);
  box-shadow: 4px 0 12px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  z-index: 20;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #e4e7ed);
}

.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text, #303133);
}

.panel-loading,
.panel-empty {
  padding: 24px 16px;
}

.panel-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 摘要卡片 */
.gap-summary {
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #e4e7ed);
}

.stat-card {
  text-align: center;
  padding: 8px 0;
  border-radius: 6px;
  background: var(--color-bg-page, #f5f7fa);
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  line-height: 1.2;
}

.stat-label {
  font-size: 11px;
  color: var(--color-text-secondary, #909399);
  margin-top: 2px;
}

.stat-warning .stat-value { color: #f59e0b; }
.stat-danger .stat-value { color: #ef4444; }
.stat-info .stat-value { color: #0ea5e9; }

.coverage-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}

.coverage-label {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  flex-shrink: 0;
  width: 40px;
}

/* Tabs */
.gap-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.gap-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 16px;
  flex-shrink: 0;
}

.gap-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.gap-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.gap-tabs :deep(.el-scrollbar) {
  height: 100%;
}

/* 列表项 */
.gap-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid #f5f5f5;
}

.gap-item:hover {
  background: var(--color-bg-page, #f5f7fa);
}

.item-degree {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
}

.degree-zero { background: #ef4444; }
.degree-one { background: #f59e0b; }
.degree-two { background: #0ea5e9; }

.item-label {
  flex: 1;
  font-size: 13px;
  color: var(--color-text, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 桥接项 */
.bridge-item {
  flex-wrap: wrap;
}

.bridge-pair {
  font-size: 13px;
  color: var(--color-text, #303133);
}

.bridge-label {
  font-size: 11px;
  color: var(--color-text-secondary, #909399);
  margin-left: 2px;
}

/* 建议项 */
.suggestion-item {
  align-items: flex-start;
  gap: 8px;
}

.suggestion-desc {
  flex: 1;
  font-size: 13px;
  color: var(--color-text, #303133);
  line-height: 1.5;
}

.empty-hint {
  text-align: center;
  padding: 16px;
  font-size: 13px;
  color: var(--color-text-secondary, #909399);
}

/* 侧边栏滑入动画 */
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(-100%);
}

@media (max-width: 768px) {
  .gap-panel {
    width: 100%;
    height: 50%;
    top: 0;
    left: 0;
    border-right: none;
    border-bottom: 1px solid var(--color-border, #e4e7ed);
  }
}
</style>
