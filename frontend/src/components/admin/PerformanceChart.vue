<template>
  <div class="performance-chart">
    <div v-if="data.length === 0" class="chart-empty">{{ t('admin.common.noData') }}</div>
    <template v-else>
      <div class="chart-y-axis">
        <span>{{ formatNumber(maxVal) }}</span>
        <span>{{ formatNumber(Math.round(maxVal / 2)) }}</span>
        <span>0</span>
      </div>
      <div class="chart-body">
        <div class="chart-grid">
          <div class="grid-line"></div>
          <div class="grid-line"></div>
          <div class="grid-line"></div>
        </div>
        <div class="chart-bars">
          <div v-for="item in data" :key="item.date" class="chart-bar-wrapper">
            <el-tooltip :content="tooltipText(item)" placement="top">
              <div class="chart-bar" :style="{ height: barHeight(item.tokens) + '%' }"></div>
            </el-tooltip>
            <span class="chart-label">{{ formatDate(item.date) }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatLocaleNumber } from '@/utils/localeFormat'

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  maxValue: {
    type: Number,
    default: 0
  }
})

const { t, locale } = useI18n()

const maxVal = computed(() => {
  if (props.maxValue > 0) return props.maxValue
  if (props.data.length === 0) return 1
  return Math.max(...props.data.map(d => d.tokens || 0), 1)
})

function barHeight(value) {
  if (maxVal.value === 0) return 0
  return Math.max((value / maxVal.value) * 100, 1)
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const parts = dateStr.split('-')
  if (parts.length >= 3) return `${parts[1]}/${parts[2]}`
  return dateStr
}

function formatNumber(num) {
  return formatLocaleNumber(num, locale.value, {
    notation: Number(num) >= 1000 ? 'compact' : 'standard',
    maximumFractionDigits: 1
  })
}

function tooltipText(item) {
  return t('admin.performanceChart.tooltip', {
    date: formatDate(item.date),
    tokens: formatLocaleNumber(item.tokens || 0, locale.value),
    cost: formatLocaleNumber(item.cost || 0, locale.value, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })
  })
}
</script>

<style lang="scss" scoped>
.performance-chart {
  display: flex;
  min-height: 220px;
  padding: 16px 0;
}

.chart-empty {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.chart-y-axis {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding-right: 8px;
  min-width: 48px;
  text-align: right;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  height: 180px;
}

.chart-body {
  flex: 1;
  position: relative;
  height: 180px;
}

.chart-grid {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  pointer-events: none;

  .grid-line {
    border-top: 1px dashed #e4e7ed;

    &:first-child {
      border-top: none;
    }
  }
}

.chart-bars {
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 100%;
  padding: 0 4px;
  overflow-x: auto;
}

.chart-bar-wrapper {
  flex: 1;
  min-width: 24px;
  max-width: 60px;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
}

.chart-bar {
  width: 100%;
  max-width: 36px;
  background: linear-gradient(180deg, #409eff, #79bbff);
  border-radius: 3px 3px 0 0;
  transition: height 0.3s ease;
  cursor: pointer;
  min-height: 2px;

  &:hover {
    background: linear-gradient(180deg, #337ecc, #66b1ff);
  }
}

.chart-label {
  font-size: 10px;
  color: var(--el-text-color-secondary);
  margin-top: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 48px;
}
</style>
