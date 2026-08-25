<template>
  <div class="community-filter">
    <el-popover placement="bottom-start" :width="320" trigger="click">
      <template #reference>
        <el-button size="small">
          <el-icon><Filter /></el-icon>
          {{ t('knowledge.graph.communityFilter') }}
          <span v-if="selected.size > 0" class="filter-badge">{{ selected.size }}</span>
        </el-button>
      </template>

      <div class="filter-panel">
        <div class="filter-header">
          <el-button size="small" text @click="selectAll">{{ t('knowledge.actions.selectAll') }}</el-button>
          <el-button size="small" text @click="clearAll">{{ t('knowledge.actions.clear') }}</el-button>
        </div>
        <el-scrollbar max-height="300px">
          <div
            v-for="c in communities"
            :key="c.id"
            class="filter-item"
            @click="toggle(c.id)"
          >
            <el-checkbox
              :model-value="selected.has(c.id)"
              @click.stop
              @change="toggle(c.id)"
            />
            <span class="community-dot" :style="{ background: colorOf(c.id) }" />
            <span class="community-label">{{ t('knowledge.graph.community', { id: c.id }) }}</span>
            <span class="community-count">{{ c.count }}</span>
          </div>
        </el-scrollbar>
      </div>
    </el-popover>
  </div>
</template>

<script setup>
import { Filter } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const COLORS = [
  '#4f46e5', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#6366f1',
  '#06b6d4', '#84cc16', '#e11d48', '#a855f7', '#22d3ee',
  '#eab308', '#64748b', '#78716c'
]

const props = defineProps({
  communities: { type: Array, default: () => [] },
  selected: { type: Set, default: () => new Set() }
})

const emit = defineEmits(['change'])

function colorOf(id) {
  return COLORS[id % COLORS.length]
}

function toggle(id) {
  const next = new Set(props.selected)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  emit('change', next)
}

function selectAll() {
  emit('change', new Set(props.communities.map(c => c.id)))
}

function clearAll() {
  emit('change', new Set())
}
</script>

<style scoped>
.community-filter {
  display: inline-flex;
}

.filter-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  margin-left: 4px;
  font-size: 11px;
  color: #fff;
  background: #409eff;
  border-radius: 9px;
}

.filter-panel {
  max-height: 360px;
}

.filter-header {
  display: flex;
  justify-content: flex-end;
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s;
}

.filter-item:hover {
  background: #f5f7fa;
}

.community-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.community-label {
  flex: 1;
  font-size: 13px;
  color: #303133;
}

.community-count {
  font-size: 12px;
  color: #909399;
  font-variant-numeric: tabular-nums;
}
</style>
