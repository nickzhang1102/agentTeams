<template>
  <span v-if="editedAt" class="edit-indicator" @click="toggleHistory">
    <span class="edited-label">{{ t('leader.report.edited') }}</span>
    <span v-if="showHistory && editHistory.length" class="edit-history">
      <span class="history-title">{{ t('leader.report.editHistory') }}</span>
      <span
        v-for="(entry, i) in editHistory"
        :key="i"
        class="history-item"
      >{{ entry }}</span>
    </span>
  </span>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  editedAt: { type: [String, Date], default: null },
  content: { type: [Object, String], default: null }
})

const showHistory = ref(false)
const { t } = useI18n()

// 从 content 中提取 edit_history 数组
const editHistory = computed(() => {
  if (!props.content) return []
  if (typeof props.content === 'object' && Array.isArray(props.content.edit_history)) {
    return props.content.edit_history
  }
  return []
})

function toggleHistory() {
  if (editHistory.value.length) {
    showHistory.value = !showHistory.value
  }
}
</script>

<style scoped>
.edit-indicator {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  flex-wrap: wrap;
}

.edited-label {
  font-size: 12px;
  color: var(--el-text-color-placeholder, #c0c4cc);
  cursor: default;
  white-space: nowrap;
}

.edit-indicator:has(.history-item) .edited-label {
  cursor: pointer;
}

.edit-indicator:has(.history-item) .edited-label:hover {
  color: var(--el-text-color-secondary, #909399);
}

.edit-history {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  margin-top: 4px;
  padding: 6px 8px;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 4px;
  font-size: 12px;
}

.history-title {
  color: var(--el-text-color-secondary, #909399);
  font-weight: 500;
}

.history-item {
  color: var(--el-text-color-regular, #606266);
  padding: 2px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter, #e4e7ed);
  word-break: break-word;
}

.history-item:last-child {
  border-bottom: none;
}
</style>
