<template>
  <el-drawer
    :model-value="modelValue"
    :title="title || t('leader.evidence.defaultTitle')"
    direction="rtl"
    size="min(92vw, 420px)"
    class="report-evidence-drawer"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="normalizedEvidence.length" class="evidence-list">
      <article
        v-for="item in normalizedEvidence"
        :key="item.evidence_id || item.title"
        :data-ev-id="item.evidence_id"
        class="evidence-item"
      >
        <div class="evidence-item-header">
          <strong>{{ item.title || item.evidence_id || t('leader.evidence.item') }}</strong>
          <div class="evidence-item-actions">
            <el-tag v-if="item.source_type" size="small" effect="plain">
              {{ item.source_type }}
            </el-tag>
            <el-tooltip
              v-if="safeUrl(item.url)"
              :content="t('leader.evidence.openSource')"
              placement="top"
            >
              <el-button
                text
                circle
                :icon="Link"
                :aria-label="t('leader.evidence.openSource')"
                @click="openSource(item.url)"
              />
            </el-tooltip>
          </div>
        </div>

        <div class="evidence-badges">
          <el-tag size="small" :type="completenessTagType(item.completeness)" effect="light">
            {{ completenessLabel(item.completeness) }}
          </el-tag>
          <span v-if="locatorLabel(item.locator)" class="evidence-locator">
            {{ locatorLabel(item.locator) }}
          </span>
        </div>

        <p
          v-if="item.excerpt && !detailFallbackText(item)"
          class="evidence-excerpt"
        >
          {{ item.excerpt }}
        </p>
        <dl class="evidence-meta">
          <div v-if="item.evidence_id">
            <dt>ID</dt>
            <dd>{{ item.evidence_id }}</dd>
          </div>
          <div v-if="item.agent_id">
            <dt>Agent</dt>
            <dd>{{ item.agent_id }}</dd>
          </div>
          <div v-if="item.subtask_id">
            <dt>{{ t('leader.evidence.subtask') }}</dt>
            <dd>{{ item.subtask_id }}</dd>
          </div>
        </dl>

        <el-button
          v-if="detailEnabled && item.evidence_id"
          class="evidence-detail-toggle"
          text
          :icon="expandedId === item.evidence_id ? ArrowUp : ArrowDown"
          @click="toggleDetail(item)"
        >
          {{ expandedId === item.evidence_id
            ? t('leader.evidence.hidePassage')
            : t('leader.evidence.viewPassage') }}
        </el-button>

        <div
          v-if="expandedId === item.evidence_id"
          class="evidence-detail"
          aria-live="polite"
        >
          <div v-if="detailState(item).status === 'loading'" class="evidence-detail-loading">
            <el-skeleton :rows="3" animated />
          </div>

          <template v-else-if="detailState(item).status === 'success'">
            <div
              v-if="detailState(item).data.completeness === 'snippet'"
              class="evidence-detail-notice"
            >
              {{ t('leader.evidence.snippetNotice') }}
            </div>
            <div
              v-else-if="detailState(item).data.completeness === 'legacy'"
              class="evidence-detail-notice"
            >
              {{ t('leader.evidence.legacyNotice') }}
            </div>
            <p class="evidence-passage">{{ detailState(item).data.passage }}</p>
          </template>

          <div v-else class="evidence-detail-error">
            <span>{{ detailErrorLabel(detailState(item).status) }}</span>
            <el-button
              v-if="detailState(item).status === 'error'"
              text
              :icon="RefreshRight"
              @click="loadDetail(item, { force: true })"
            >
              {{ t('leader.evidence.retry') }}
            </el-button>
          </div>

          <!-- 详情不可用时，回退展示已有摘要内容，避免“查看证据”完全无意义 -->
          <div
            v-if="detailFallbackText(item)"
            class="evidence-detail-fallback"
            aria-live="polite"
          >
            <div class="evidence-detail-notice">
              {{ t('leader.evidence.fallbackNotice') }}
            </div>
            <p class="evidence-passage">{{ detailFallbackText(item) }}</p>
          </div>
        </div>
      </article>
    </div>
    <el-empty v-else :description="t('leader.evidence.empty')" />
  </el-drawer>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, Link, RefreshRight } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/api'

const { t } = useI18n()

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  evidenceMap: {
    type: [Array, Object],
    default: () => []
  },
  sessionId: {
    type: [Number, String],
    default: ''
  },
  title: {
    type: String,
    default: ''
  },
  highlightId: {
    type: String,
    default: ''
  },
  detailEnabled: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:modelValue'])
const expandedId = ref('')
const detailCache = reactive({})
const pendingRequests = new Map()
let highlightTimer = null

const normalizedEvidence = computed(() => {
  if (Array.isArray(props.evidenceMap)) {
    return props.evidenceMap.filter(Boolean)
  }
  if (props.evidenceMap && typeof props.evidenceMap === 'object') {
    return Object.values(props.evidenceMap).filter(Boolean)
  }
  return []
})

function cacheKey(evidenceId) {
  return `${props.sessionId || 'no-session'}:${evidenceId}`
}

function detailState(item) {
  return detailCache[cacheKey(item.evidence_id)] || { status: 'idle', data: null }
}

async function toggleDetail(item) {
  if (!props.detailEnabled) return
  if (expandedId.value === item.evidence_id) {
    expandedId.value = ''
    return
  }
  expandedId.value = item.evidence_id
  await loadDetail(item)
}

async function loadDetail(item, { force = false } = {}) {
  if (!props.detailEnabled) return null
  const evidenceId = String(item?.evidence_id || '').trim()
  const key = cacheKey(evidenceId)
  if (!evidenceId || !props.sessionId) {
    detailCache[key] = { status: 'unresolvable', data: null }
    return null
  }
  const current = detailCache[key]
  if (!force && current?.status === 'success') {
    return current.data
  }
  if (!force && pendingRequests.has(key)) {
    return pendingRequests.get(key)
  }

  detailCache[key] = { status: 'loading', data: null }
  const request = api.get(
    `/api/leader/sessions/${encodeURIComponent(props.sessionId)}/evidence/${encodeURIComponent(evidenceId)}`,
    { suppressGlobalError: true }
  ).then((response) => {
    detailCache[key] = { status: 'success', data: response.data }
    return response.data
  }).catch((error) => {
    const status = error?.response?.status
    const mappedStatus = {
      401: 'forbidden',
      403: 'forbidden',
      404: 'notFound',
      410: 'unavailable',
      422: 'unresolvable'
    }[status] || 'error'
    detailCache[key] = { status: mappedStatus, data: null }
    return null
  }).finally(() => {
    pendingRequests.delete(key)
  })

  pendingRequests.set(key, request)
  return request
}

function safeUrl(value) {
  const url = String(value || '').trim()
  if (!/^https?:\/\//i.test(url)) return ''
  try {
    const parsed = new URL(url)
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : ''
  } catch {
    return ''
  }
}

function openSource(value) {
  const url = safeUrl(value)
  if (url) {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}

function completenessLabel(value) {
  const key = ['passage', 'snippet', 'legacy', 'unavailable'].includes(value)
    ? value
    : 'legacy'
  return t(`leader.evidence.completeness.${key}`)
}

function completenessTagType(value) {
  return {
    passage: 'success',
    snippet: 'warning',
    legacy: 'info',
    unavailable: 'danger'
  }[value] || 'info'
}

function locatorLabel(locator) {
  if (!locator || typeof locator !== 'object') return ''
  const parts = []
  if (locator.page != null) parts.push(t('leader.evidence.page', { page: locator.page }))
  if (locator.source_file) parts.push(String(locator.source_file))
  else if (locator.document_id) parts.push(String(locator.document_id))
  return parts.join(' / ')
}

function detailErrorLabel(status) {
  const key = ['forbidden', 'notFound', 'unavailable', 'unresolvable'].includes(status)
    ? status
    : 'loadFailed'
  return t(`leader.evidence.errors.${key}`)
}

function detailFallbackText(item) {
  if (expandedId.value !== item?.evidence_id) return ''
  const status = detailState(item).status
  const failedStates = ['error', 'forbidden', 'notFound', 'unavailable', 'unresolvable']
  if (!failedStates.includes(status)) return ''
  return String(item?.excerpt || '').trim()
}

function focusHighlightedEvidence(id) {
  nextTick(() => {
    const target = Array.from(document.querySelectorAll('[data-ev-id]'))
      .find(element => element.dataset.evId === id)
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    target.classList.add('evidence-item--highlighted')
    if (highlightTimer) clearTimeout(highlightTimer)
    highlightTimer = setTimeout(() => {
      target.classList.remove('evidence-item--highlighted')
    }, 2000)
  })
}

watch(
  () => [props.highlightId, props.modelValue],
  ([id, open]) => {
    if (!id || !open) return
    focusHighlightedEvidence(id)
    const item = normalizedEvidence.value.find(candidate => candidate.evidence_id === id)
    if (item && props.detailEnabled) {
      expandedId.value = id
      loadDetail(item)
    }
  },
  { immediate: true }
)

watch(() => props.sessionId, () => {
  expandedId.value = ''
})

watch(() => props.detailEnabled, (enabled) => {
  if (!enabled) expandedId.value = ''
})

onBeforeUnmount(() => {
  if (highlightTimer) clearTimeout(highlightTimer)
})

defineExpose({
  detailCache,
  detailState,
  expandedId,
  loadDetail,
  openSource,
  safeUrl,
  toggleDetail
})
</script>

<style scoped>
.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  min-width: 0;
}

.evidence-item {
  width: 100%;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-light);
  transition: box-shadow 0.3s ease;
  box-sizing: border-box;
}

.evidence-item--highlighted {
  box-shadow: 0 0 0 2px var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.evidence-item-header,
.evidence-item-actions,
.evidence-badges {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.evidence-item-header {
  justify-content: space-between;
}

.evidence-item-actions {
  flex: 0 0 auto;
  align-items: center;
}

.evidence-item-header strong {
  min-width: 0;
  color: var(--el-text-color-primary);
  overflow-wrap: anywhere;
}

.evidence-badges {
  align-items: center;
  flex-wrap: wrap;
  margin-top: 8px;
}

.evidence-locator {
  min-width: 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.evidence-excerpt {
  margin: 10px 0;
  color: var(--el-text-color-regular);
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.evidence-meta {
  display: grid;
  gap: 6px;
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.evidence-meta div {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 8px;
}

.evidence-meta dt {
  font-weight: 600;
}

.evidence-meta dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
}

.evidence-detail-toggle {
  margin-top: 8px;
  padding-left: 0;
}

.evidence-detail {
  width: 100%;
  min-width: 0;
  margin-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 10px;
  box-sizing: border-box;
}

.evidence-detail-loading {
  min-height: 96px;
}

.evidence-detail-notice,
.evidence-detail-error {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.evidence-detail-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 40px;
}

.evidence-detail-fallback {
  margin-top: 8px;
  border-top: 1px dashed var(--el-border-color-light);
  padding-top: 8px;
}

.evidence-passage {
  max-height: 320px;
  margin: 8px 0 0;
  overflow: auto;
  color: var(--el-text-color-primary);
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 768px) {
  .evidence-passage {
    max-height: 42vh;
  }
}
</style>
