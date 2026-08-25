<template>
  <el-dialog
    v-model="visible"
    class="template-picker-dialog"
    :title="t('common.templatePicker.title')"
    :width="isMobile ? '100%' : '720px'"
    :fullscreen="isMobile"
    :close-on-click-modal="true"
    @close="reset"
  >
    <div v-loading="loading" class="picker-body" :class="{ 'is-fullscreen': isMobile }">
      <div v-if="templates.length" class="template-list">
        <div
          v-for="tpl in templates"
          :key="tpl.id"
          class="tpl-card"
          @click="handleSelect(tpl)"
        >
          <div class="tpl-card-header">
            <span class="tpl-card-name">{{ catalogLabel(tpl) }}</span>
            <el-tag v-if="tpl.is_system" size="small" type="info">{{ t('common.templatePicker.system') }}</el-tag>
            <el-tag v-else size="small" type="success">{{ t('common.templatePicker.custom') }}</el-tag>
            <el-tag v-if="tpl.skip_assessment" size="small" type="warning">{{ t('common.templatePicker.fastMode') }}</el-tag>
          </div>
          <p class="tpl-card-desc">{{ tpl.description || t('common.templatePicker.noDescription') }}</p>
          <div class="tpl-card-meta">
            <span v-if="displayAgents(tpl).length">{{ displayAgents(tpl).map(catalogLabel).join(t('common.lists.separator')) }}</span>
            <span v-else-if="tpl.pack_id">{{ t('common.templatePicker.pack', { id: tpl.pack_id }) }}</span>
            <span>{{ t('common.templatePicker.usageCount', { count: tpl.usage_count }) }}</span>
          </div>
        </div>
      </div>
      <el-empty v-else-if="!loading" :description="t('common.templatePicker.empty')" />
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/api'
import { useLocaleStore } from '@/stores/locale'
import { catalogLabel } from '@/utils/catalog'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'select'])
const { t } = useI18n()
const localeStore = useLocaleStore()

const isMobile = ref(window.innerWidth <= 640)
const onResize = () => { isMobile.value = window.innerWidth <= 640 }
window.addEventListener('resize', onResize)
onUnmounted(() => window.removeEventListener('resize', onResize))

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const templates = ref([])
const loading = ref(false)
let latestRequestId = 0

watch(visible, async (val) => {
  if (val) await fetchTemplates()
})

watch(() => localeStore.locale, () => {
  if (visible.value) fetchTemplates()
})

async function fetchTemplates() {
  const requestId = ++latestRequestId
  const requestLocale = localeStore.locale
  loading.value = true
  try {
    const res = await api.get('/api/workflow-templates', {
      params: { per_page: 50, locale: requestLocale },
    })
    if (requestId !== latestRequestId) return
    templates.value = res.data.items || []
  } catch {
    if (requestId === latestRequestId) templates.value = []
  } finally {
    if (requestId === latestRequestId) loading.value = false
  }
}

function handleSelect(tpl) {
  emit('select', tpl)
  visible.value = false
}

function displayAgents(tpl) {
  return tpl.resolved_agents?.length ? tpl.resolved_agents : (tpl.agents || [])
}

function reset() {
  templates.value = []
}
</script>

<style lang="scss" scoped>
.picker-body {
  min-height: 120px;
  max-height: 60vh;
  overflow-y: auto;
}

.template-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  min-width: 0;
}

.tpl-card {
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
  overflow: hidden;

  &:hover {
    border-color: var(--el-color-primary);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  }
}

.tpl-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.tpl-card-name {
  font-size: 14px;
  font-weight: 600;
}

.tpl-card-desc {
  font-size: 12px;
  color: var(--el-text-color-regular);
  margin: 0 0 6px;
  line-height: 1.4;
}

.tpl-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  font-size: 11px;
  color: var(--el-text-color-secondary);

  span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }
}

@media (max-width: 640px) {
  .picker-body.is-fullscreen {
    max-height: none;
    height: auto;
    overflow: visible;
  }

  .template-list {
    grid-template-columns: 1fr;
  }

  .tpl-card-meta {
    flex-direction: column;
    gap: 4px;
  }

  /* el-dialog fullscreen 内部滚动统一 */
  :deep(.el-dialog) {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  :deep(.el-dialog__header) {
    flex-shrink: 0;
  }

  :deep(.el-dialog__body) {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 16px;
  }
}
</style>
