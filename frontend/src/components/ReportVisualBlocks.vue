<template>
  <section v-if="normalizedBlocks.length" class="report-visual-blocks">
    <article
      v-for="block in normalizedBlocks"
      :key="block.block_id || `${block.type}-${block.title}`"
      class="visual-block"
    >
      <header class="visual-block-header">
        <h3>{{ block.title || blockTypeLabel(block.type) }}</h3>
        <div v-if="block.evidence_refs.length" class="evidence-ref-group">
          <span class="evidence-ref-count">{{ t('leader.report.evidenceCount', { count: block.evidence_refs.length }) }}</span>
          <button
            v-for="evidenceId in block.evidence_refs"
            :key="evidenceId"
            type="button"
            class="evidence-ref-chip"
            @click="emit('evidence-click', evidenceId)"
          >
            {{ evidenceId }}
          </button>
        </div>
      </header>

      <div v-if="block.type === 'risk_matrix'" class="visual-table-wrap">
        <table class="visual-table risk-matrix">
          <thead>
            <tr>
              <th>{{ t('leader.visual.risk') }}</th>
              <th>{{ t('leader.visual.likelihood') }}</th>
              <th>{{ t('leader.visual.impact') }}</th>
              <th>{{ t('leader.visual.mitigation') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(risk, index) in riskRows(block)" :key="`${block.block_id}-risk-${index}`">
              <td>{{ risk.risk || risk.name || t('leader.visual.unnamedRisk') }}</td>
              <td><span class="level-pill">{{ risk.likelihood || risk.probability || '-' }}</span></td>
              <td><span class="level-pill impact">{{ risk.impact || '-' }}</span></td>
              <td>{{ risk.mitigation || risk.action || risk.response || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!riskRows(block).length" class="empty-block">{{ t('leader.visual.noRisks') }}</p>
      </div>

      <div v-else-if="block.type === 'decision_matrix'" class="visual-table-wrap">
        <table class="visual-table decision-matrix">
          <thead>
            <tr>
              <th>{{ t('leader.visual.option') }}</th>
              <th>{{ t('leader.visual.pros') }}</th>
              <th>{{ t('leader.visual.cons') }}</th>
              <th>{{ t('leader.visual.score') }}</th>
              <th>{{ t('leader.visual.recommendation') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(option, index) in optionRows(block)" :key="`${block.block_id}-option-${index}`">
              <td>{{ option.option || option.name || t('leader.visual.unnamedOption') }}</td>
              <td>{{ listText(option.pros) }}</td>
              <td>{{ listText(option.cons) }}</td>
              <td>{{ option.score ?? '-' }}</td>
              <td>{{ option.recommendation || option.note || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!optionRows(block).length" class="empty-block">{{ t('leader.visual.noOptions') }}</p>
      </div>

      <pre v-else class="unknown-block">{{ JSON.stringify(block.data || {}, null, 2) }}</pre>
    </article>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const emit = defineEmits(['evidence-click'])

const props = defineProps({
  blocks: {
    type: Array,
    default: () => []
  }
})

const SUPPORTED_TYPES = new Set(['risk_matrix', 'decision_matrix'])

const normalizedBlocks = computed(() => {
  return (props.blocks || [])
    .filter(block => block && typeof block === 'object')
    .map(block => {
      if (!SUPPORTED_TYPES.has(block.type)) {
        console.warn('[ReportVisualBlocks] unknown block type:', block.type)
      }
      return {
        ...block,
        data: block.data && typeof block.data === 'object' ? block.data : {},
        evidence_refs: Array.isArray(block.evidence_refs) ? block.evidence_refs : []
      }
    })
})

function riskRows(block) {
  const risks = block.data?.risks || block.data?.items || []
  return Array.isArray(risks) ? risks.filter(item => item && typeof item === 'object') : []
}

function optionRows(block) {
  const options = block.data?.options || block.data?.items || []
  return Array.isArray(options) ? options.filter(item => item && typeof item === 'object') : []
}

function listText(value) {
  if (Array.isArray(value)) {
    return value.filter(Boolean).join(t('leader.visual.listSeparator')) || '-'
  }
  return value || '-'
}

function blockTypeLabel(type) {
  if (type === 'risk_matrix') return t('leader.visual.riskMatrix')
  if (type === 'decision_matrix') return t('leader.visual.decisionMatrix')
  return type || t('leader.visual.block')
}
</script>

<style scoped>
.report-visual-blocks {
  display: grid;
  gap: 12px;
  margin: 14px 0;
}

.visual-block {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  overflow: hidden;
}

.visual-block-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-lighter);
}

.visual-block-header h3 {
  margin: 0;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.evidence-ref-count {
  flex: 0 0 auto;
  font-size: 12px;
  color: var(--el-color-primary);
}

.evidence-ref-group {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}

.evidence-ref-chip {
  border: 1px dashed var(--el-color-primary-light-3);
  border-radius: 999px;
  background: transparent;
  color: var(--el-color-primary);
  cursor: pointer;
  font-size: 11px;
  padding: 2px 8px;
}

.visual-table-wrap {
  overflow-x: auto;
}

.visual-table {
  width: 100%;
  min-width: 640px;
  border-collapse: collapse;
  font-size: 13px;
}

.visual-table th,
.visual-table td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  text-align: left;
  vertical-align: top;
}

.visual-table th {
  color: var(--el-text-color-secondary);
  font-weight: 600;
  background: var(--el-fill-color-light);
}

.level-pill {
  display: inline-block;
  min-width: 52px;
  padding: 2px 7px;
  border-radius: 999px;
  text-align: center;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
}

.level-pill.impact {
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.empty-block {
  margin: 0;
  padding: 12px;
  color: var(--el-text-color-secondary);
}

.unknown-block {
  margin: 0;
  padding: 12px;
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
}

@media (max-width: 768px) {
  .visual-block-header {
    flex-direction: column;
  }
}
</style>
