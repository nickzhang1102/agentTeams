<template>
  <div class="stats-card" :style="{ borderLeftColor: color }">
    <div class="stats-icon" :style="{ color: color }">
      <el-icon :size="28"><component :is="icon" /></el-icon>
    </div>
    <div class="stats-info">
      <div class="stats-value">{{ displayValue }}</div>
      <div class="stats-label">{{ label }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatLocaleNumber } from '@/utils/localeFormat'

const props = defineProps({
  icon: {
    type: [Object, String],
    required: true
  },
  label: {
    type: String,
    required: true
  },
  value: {
    type: [Number, String],
    required: true
  },
  color: {
    type: String,
    default: '#409eff'
  }
})

const { locale } = useI18n()
const displayValue = computed(() => (
  typeof props.value === 'number' ? formatLocaleNumber(props.value, locale.value) : props.value
))
</script>

<style lang="scss" scoped>
.stats-card {
  display: flex;
  align-items: center;
  gap: 16px;
  background: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  padding: 20px;
  border-left: 4px solid;
  transition: box-shadow 0.3s;

  &:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  }
}

.stats-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.04);
}

.stats-info {
  flex: 1;
  min-width: 0;
}

.stats-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.2;
}

.stats-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
