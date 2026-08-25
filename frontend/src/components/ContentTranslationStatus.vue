<template>
  <div v-if="label" class="translation-status" :class="`is-${state}`" role="status">
    <el-icon v-if="state === 'pending'" class="is-loading"><Loading /></el-icon>
    <span>{{ label }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loading } from '@element-plus/icons-vue'

const props = defineProps({
  state: {
    type: String,
    default: 'original',
  },
})

const { t } = useI18n()
const label = computed(() => {
  if (props.state === 'pending') return t('leader.translation.pending')
  if (props.state === 'failed') return t('leader.translation.failed')
  if (props.state === 'unavailable') return t('leader.translation.unavailable')
  return ''
})
</script>

<style scoped>
.translation-status {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  margin: 6px 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 18px;
}

.translation-status.is-failed,
.translation-status.is-unavailable {
  color: var(--el-color-warning-dark-2);
}
</style>
