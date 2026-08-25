<template>
  <div
    v-if="reportText"
    class="final-report"
    :ref="(el) => setReportRef(el)"
    data-message-id="final-report"
  >
    <div class="report-header">
      <el-icon><Document /></el-icon>
      <span>{{ t('leader.report.title') }}</span>
    </div>
    <ContentTranslationStatus :state="translationState" />
    <div class="report-content">
      <section v-if="reportSummary" class="report-summary">
        <div class="summary-header">
          <h3 v-html="renderInlineMd(reportSummary.title || t('leader.report.summary'))"></h3>
          <el-button
            v-if="hasEvidence"
            size="small"
            text
            type="primary"
            @click="evidenceDrawerVisible = true"
          >
            {{ t('leader.report.evidenceCount', { count: reportEvidence.length }) }}
          </el-button>
        </div>
        <p
          v-if="reportSummary.executive_summary"
          class="summary-lead"
          v-html="renderInlineMd(reportSummary.executive_summary)"
        ></p>
        <div class="summary-grid">
          <div v-if="listHasItems(reportSummary.key_findings)" class="summary-section">
            <strong>{{ t('leader.report.keyFindings') }}</strong>
            <ul>
              <li v-for="item in reportSummary.key_findings" :key="item" v-html="renderInlineMd(item)"></li>
            </ul>
          </div>
          <div v-if="listHasItems(reportSummary.recommendations)" class="summary-section">
            <strong>{{ t('leader.report.recommendations') }}</strong>
            <ul>
              <li v-for="item in reportSummary.recommendations" :key="item" v-html="renderInlineMd(item)"></li>
            </ul>
          </div>
          <div v-if="listHasItems(reportSummary.risks)" class="summary-section">
            <strong>{{ t('leader.report.risks') }}</strong>
            <ul>
              <li v-for="item in reportSummary.risks" :key="item" v-html="renderInlineMd(item)"></li>
            </ul>
          </div>
          <div v-if="listHasItems(reportSummary.next_steps)" class="summary-section">
            <strong>{{ t('leader.report.nextSteps') }}</strong>
            <ul>
              <li v-for="item in reportSummary.next_steps" :key="item" v-html="renderInlineMd(item)"></li>
            </ul>
          </div>
        </div>
      </section>
      <ReportVisualBlocks :blocks="reportVisualBlocks" @evidence-click="handleEvidenceClick" />
      <el-collapse v-if="reportSummary" v-model="activeDetail" class="report-detail-collapse">
        <el-collapse-item :title="t('leader.report.fullReport')" name="full-report">
          <MarkdownRenderer
            :content="reportText"
            :evidence-map="reportEvidence"
            :evidence-label="t('leader.evidence.inlineReference')"
            @evidence-click="handleEvidenceClick"
          />
        </el-collapse-item>
      </el-collapse>
      <MarkdownRenderer
        v-else
        :content="reportText"
        :evidence-map="reportEvidence"
        :evidence-label="t('leader.evidence.inlineReference')"
        @evidence-click="handleEvidenceClick"
      />
    </div>

    <ReportEvidenceDrawer
      v-model="evidenceDrawerVisible"
      :evidence-map="reportEvidence"
      :session-id="effectiveSessionId"
      :highlight-id="highlightEvidenceId"
      :title="t('leader.report.evidenceTitle')"
      :detail-enabled="evidenceDetailEnabled"
    />

    <!-- 操作工具条 -->
    <ChatActionBar
      :message="{ id: 'final-report', content: reportText, user_content: '评审模式最终报告' }"
      :conversation-id="conversationId || 'leader-session'"
    />

  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLeaderStore } from '@/stores/leader'
import { applyTranslationOverlay, useContentTranslationStore } from '@/stores/contentTranslation'
import { Document } from '@element-plus/icons-vue'
import ChatActionBar from './ChatActionBar.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ReportEvidenceDrawer from './ReportEvidenceDrawer.vue'
import ReportVisualBlocks from './ReportVisualBlocks.vue'
import ContentTranslationStatus from './ContentTranslationStatus.vue'
import { renderInlineMd } from '@/utils/markdown'

const props = defineProps({
  conversationId: {
    type: [Number, String],
    default: ''
  },
  sessionId: {
    type: [Number, String],
    default: ''
  },
  evidenceDetailEnabled: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['report-scroll-target'])

const leaderStore = useLeaderStore()
const translationStore = useContentTranslationStore()
const { t, locale } = useI18n()
const reportRef = ref(null)
const activeDetail = ref([])
const evidenceDrawerVisible = ref(false)
const highlightEvidenceId = ref('')

const effectiveSessionId = computed(() => (
  props.sessionId || sourceFinalReport.value?.leader_session_id || ''
))

const sourceFinalReport = computed(() => {
  // 根据 sessionId 获取对应会话的最终报告
  if (props.sessionId) {
    const sessionIdNum = Number(props.sessionId)

    // 安全检查：确保转换成功
    if (!isNaN(sessionIdNum)) {
      const session = leaderStore.sessions.find(s => s.id === sessionIdNum)
      if (session && session.final_report) {
        return session.final_report
      }
    }
  }

  // 降级：使用全局 finalReport（实时执行场景）
  return leaderStore.finalReport
})

const finalReportSource = computed(() => {
  const report = sourceFinalReport.value
  return Number.isInteger(report?.id) && report.id > 0
    ? { type: 'leader_final_report', id: report.id }
    : null
})

const translationEntry = computed(() => finalReportSource.value
  ? translationStore.getEntry(finalReportSource.value, locale.value)
  : null)

const translationState = computed(() => translationEntry.value?.state || 'original')

const finalReport = computed(() => applyTranslationOverlay(
  'leader_final_report',
  sourceFinalReport.value,
  translationEntry.value?.state === 'ready' ? translationEntry.value.payload : null,
))

const reportText = computed(() => {
  const report = finalReport.value
  if (typeof report === 'string') {
    return report
  } else if (report && typeof report === 'object') {
    return report.report || report.content || report.final_report || ''
  }
  return ''
})

const reportSummary = computed(() => {
  const report = finalReport.value
  if (!report || typeof report !== 'object') {
    return null
  }
  return normalizeReportSummary(report.summary) ||
    normalizeReportSummary(report.executive_summary) ||
    normalizeReportSummary(report.structured_report)
})

const reportEvidence = computed(() => {
  const report = finalReport.value
  if (!report || typeof report !== 'object') {
    return []
  }
  const evidence = report.evidence_map || report.structured_report?.evidence_map || []
  return Array.isArray(evidence) ? evidence : Object.values(evidence || {})
})

const reportVisualBlocks = computed(() => {
  const report = finalReport.value
  if (!report || typeof report !== 'object') {
    return []
  }
  const blocks = report.visual_blocks || report.structured_report?.visual_blocks || []
  return Array.isArray(blocks) ? blocks : []
})

const hasEvidence = computed(() => reportEvidence.value.length > 0)

function handleEvidenceClick(evidenceId) {
  highlightEvidenceId.value = evidenceId
  evidenceDrawerVisible.value = true
}

function listHasItems(value) {
  return Array.isArray(value) && value.length > 0
}

function normalizeReportSummary(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  const summary = {
    title: typeof value.title === 'string' ? value.title : '',
    executive_summary: typeof value.executive_summary === 'string'
      ? value.executive_summary
      : (typeof value.one_sentence === 'string' ? value.one_sentence : ''),
    key_findings: normalizeSummaryList(value.key_findings),
    recommendations: normalizeSummaryList(value.recommendations),
    risks: normalizeSummaryList(value.risks),
    next_steps: normalizeSummaryList(value.next_steps)
  }

  if (
    summary.title ||
    summary.executive_summary ||
    summary.key_findings.length ||
    summary.recommendations.length ||
    summary.risks.length ||
    summary.next_steps.length
  ) {
    return summary
  }
  return null
}

function normalizeSummaryList(value) {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .map(item => String(item ?? '').trim())
    .filter(Boolean)
}

function setReportRef(el) {
  if (el) {
    reportRef.value = el
  }
}

// 向父组件传递滚动目标（只在 ref 变化时 emit 一次）
watch(reportRef, (newRef) => {
  if (newRef) {
    emit('report-scroll-target', newRef)
  }
}, { immediate: true })
</script>

<style scoped>
.final-report {
  background: var(--color-card);
  border: 1px solid #409eff;
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
}

.report-header {
  display: flex;
  align-items: center;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--el-color-primary);
  padding-bottom: 10px;
  border-bottom: 1px solid #e4e7ed;
}

.report-header .el-icon {
  margin-right: 8px;
  font-size: 18px;
}

.report-content {
  line-height: 1.8;
  word-wrap: break-word;
  font-size: 14px;
}

.report-summary {
  padding: 12px;
  margin-bottom: 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-fill-color-light);
}

.report-summary h3 {
  margin: 0 0 8px;
  font-size: 15px;
  color: var(--el-text-color-primary);
}

.summary-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.summary-header h3 {
  margin: 0;
}

.summary-lead {
  margin: 0 0 10px;
  color: var(--el-text-color-primary);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.summary-section strong {
  display: block;
  margin-bottom: 4px;
  color: var(--el-text-color-primary);
}

.summary-section ul {
  margin: 0;
  padding-left: 18px;
}

.report-detail-collapse {
  margin-top: 12px;
}

.report-detail-collapse :deep(.el-collapse-item__header) {
  padding: 0 10px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}

.report-detail-collapse :deep(.el-collapse-item__header.is-active) {
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}

.report-detail-collapse :deep(.el-collapse-item__wrap) {
  border: 1px solid var(--el-border-color-light);
  border-top: none;
  border-radius: 0 0 6px 6px;
}

.report-detail-collapse :deep(.el-collapse-item__content) {
  padding: 12px;
}

.report-content :deep(h2) {
  margin: 16px 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.report-content :deep(h3) {
  margin: 14px 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.report-content :deep(p) {
  margin: 8px 0;
}

.report-content :deep(ul),
.report-content :deep(ol) {
  padding-left: 24px;
  margin: 8px 0;
}

.report-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}

.report-content :deep(th),
.report-content :deep(td) {
  border: 1px solid #ddd;
  padding: 8px;
  text-align: left;
}

.report-content :deep(th) {
  background-color: #f5f7fa;
  font-weight: 600;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .final-report {
    padding: 6px;
    margin: 4px 0;
  }

  .report-header {
    font-size: 14px;
    margin-bottom: 8px;
    padding-bottom: 6px;
  }

  .report-content {
    font-size: 13px;
  }

  .summary-header {
    flex-direction: column;
    align-items: stretch;
  }

  .report-content :deep(h2) {
    font-size: 16px;
  }

  .report-content :deep(h3) {
    font-size: 14px;
  }
}
</style>
