<template>
  <div class="leader-question-dialog">
    <el-dialog
      v-model="visible"
      :title="t('leader.questions.title')"
      :width="isMobile ? '95%' : '640px'"
      :top="isMobile ? '5vh' : '15vh'"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      @close="handleCancel"
      class="leader-dialog"
    >
      <div class="questions-container">
        <el-alert
          type="info"
          :closable="false"
          show-icon
        >
          <template #title>
            {{ t('leader.questions.instruction') }}
          </template>
        </el-alert>

        <div class="questions-list">
          <div
            v-for="(q, index) in questions"
            :key="index"
            class="question-item"
          >
            <div class="question-number">{{ t('leader.questions.number', { number: index + 1 }) }}</div>
            <div class="question-text">{{ getQuestionText(q) }}</div>

            <!-- 预设选项 + 自定义输入 -->
            <div class="options-group">
              <!-- 多选模式 -->
              <el-checkbox-group
                v-if="isMultiSelect(q)"
                v-model="answers[index].selectedList"
                class="options-checkbox"
              >
                <div
                  v-for="(opt, oi) in getQuestionOptions(q)"
                  :key="oi"
                  class="option-row"
                >
                  <el-checkbox :value="opt">{{ opt }}</el-checkbox>
                </div>
              </el-checkbox-group>

              <!-- 单选模式 -->
              <el-radio-group
                v-else
                v-model="answers[index].selected"
                class="options-radio"
              >
                <div
                  v-for="(opt, oi) in getQuestionOptions(q)"
                  :key="oi"
                  class="option-row"
                >
                  <el-radio :value="opt">{{ opt }}</el-radio>
                </div>
                <div class="option-row">
                  <el-radio value="__custom__">{{ t('leader.questions.customAnswer') }}</el-radio>
                </div>
              </el-radio-group>

              <!-- 自定义输入框（单选模式） -->
              <el-input
                v-if="!isMultiSelect(q) && answers[index].selected === '__custom__'"
                v-model="answers[index].custom"
                type="textarea"
                :rows="2"
                :placeholder="t('leader.questions.answerPlaceholder')"
                class="custom-input"
              />
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="handleCancel">{{ t('common.actions.cancel') }}</el-button>
          <el-button
            type="primary"
            @click="handleSubmit"
            :disabled="!allAnswered"
          >
            {{ t('leader.questions.submit') }}
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { useLeaderStore } from '@/stores/leader'
import { ElMessage } from 'element-plus'

const leaderStore = useLeaderStore()
const { leaderState, currentQuestions } = storeToRefs(leaderStore)
const { t, locale } = useI18n()

const props = defineProps({
  answerEndpoint: {
    type: String,
    default: '/api/leader/answer-questions'
  },
  includeAuthorization: {
    type: Boolean,
    default: true
  },
  reconcileOnDone: {
    type: Boolean,
    default: true
  }
})

const visible = ref(false)
const questions = ref([])   // 结构化问题数组 [{question, options}]
const answers = ref([])     // [{selected: '', custom: '', selectedList: []}, ...]
const isMobile = ref(false)

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
}

function getQuestionText(q) {
  if (typeof q === 'object' && q !== null) return q.question || String(q)
  return String(q)
}

function getQuestionOptions(q) {
  if (typeof q === 'object' && q !== null && Array.isArray(q.options)) {
    return q.options
  }
  return []
}

function isMultiSelect(q) {
  if (typeof q === 'object' && q !== null) {
    if (q.selection_type === 'multiple') return true
    if (q.selection_type === 'single') return false
  }
  const text = getQuestionText(q)
  return /可多选|（多选）|\[多选\]|multiple choice|select all that apply|select one or more/i.test(text)
}

function multiSelectSeparator(q) {
  if (typeof q === 'object' && q !== null && q.content_locale) {
    return q.content_locale === 'en-US' ? ', ' : '、'
  }
  return locale.value === 'en-US' ? ', ' : '、'
}

function initAnswers(questionList) {
  return questionList.map(q => {
    const options = getQuestionOptions(q)
    const multi = isMultiSelect(q)
    return {
      selected: multi || options.length === 0 ? '__custom__' : '',
      custom: '',
      selectedList: multi ? [] : []  // 多选时用数组存储
    }
  })
}

function openWithQuestions(qs) {
  questions.value = qs
  answers.value = initAnswers(qs)
  visible.value = true
}

function ensurePendingQuestionVisible() {
  const qs = currentQuestions.value
  if (leaderState.value !== 'questioning' || !qs || qs.length === 0) {
    return
  }

  const currentQsText = questions.value.map(q => q.question || q).join('|')
  const newQsText = qs.map(q => q.question || q).join('|')
  if (currentQsText !== newQsText) {
    openWithQuestions(qs)
    return
  }

  // Browser tab/window resume can hide Element Plus overlays. Reopen the
  // existing round without rebuilding answers entered by the user.
  visible.value = true
}

function handlePageResume() {
  if (!document.hidden) {
    ensurePendingQuestionVisible()
  }
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  window.addEventListener('focus', handlePageResume)
  window.addEventListener('pageshow', handlePageResume)
  document.addEventListener('visibilitychange', handlePageResume)

  // 页面加载时恢复（如果已处于 questioning 状态）
  ensurePendingQuestionVisible()
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
  window.removeEventListener('focus', handlePageResume)
  window.removeEventListener('pageshow', handlePageResume)
  document.removeEventListener('visibilitychange', handlePageResume)
})

// 首次 SSE 追问到达时立即打开；页面恢复监听只负责浏览器挂起后的兜底。
watch([leaderState, currentQuestions], ([state, qs]) => {
  if (state === 'questioning' && qs && qs.length > 0) {
    ensurePendingQuestionVisible()
  } else if (state !== 'questioning') {
    visible.value = false
  }
}, { immediate: true, deep: true, flush: 'post' })

const allAnswered = computed(() => {
  return answers.value.every((a, idx) => {
    const multi = isMultiSelect(questions.value[idx])
    if (multi) {
      return a.selectedList && a.selectedList.length > 0
    }
    if (a.selected === '__custom__') return a.custom && a.custom.trim()
    return !!a.selected
  })
})

async function handleSubmit() {
  const abortCtrl = new AbortController()
  try {
    const answerTexts = answers.value.map((a, idx) => {
      const multi = isMultiSelect(questions.value[idx])
      if (multi) {
        return a.selectedList.join(multiSelectSeparator(questions.value[idx]))
      }
      if (a.selected === '__custom__') return a.custom.trim()
      return a.selected
    })
    await leaderStore.submitAnswers(answerTexts, {
      abortController: abortCtrl,
      endpoint: props.answerEndpoint,
      includeAuthorization: props.includeAuthorization,
      reconcileOnDone: props.reconcileOnDone
    })

    // 新一轮追问已弹出时，不关闭 dialog（handleSubmit 在 submitAnswers 后才执行）
    if (leaderStore.leaderState === 'questioning') {
      ElMessage.info(t('leader.questions.continueAnswering'))
      return
    }

    ElMessage.success(t('leader.questions.submitted'))
    visible.value = false
  } catch (error) {
    // AbortError 是正常中断（新一轮追问），不显示错误
    if (error.name === 'AbortError') {
      return
    }
    console.error('提交答案失败:', error)
    ElMessage.error(t('leader.questions.submitFailed'))
  } finally {
    // 清理：若流仍在运行，中断之
    if (!abortCtrl.signal.aborted) {
      abortCtrl.abort()
    }
  }
}

function handleCancel() {
  visible.value = false
  questions.value = []
  answers.value = []
}
</script>

<style scoped>
.questions-container {
  padding: 12px 0;
}

.questions-list {
  margin-top: 16px;
  max-height: 55vh;
  overflow-y: auto;
}

.question-item {
  margin-bottom: 20px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  border-left: 3px solid #409eff;
}

.question-number {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-primary);
  margin-bottom: 6px;
}

.question-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
  line-height: 1.6;
}

.options-group {
  margin-top: 8px;
}

.options-radio,
.options-checkbox {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.option-row {
  padding: 4px 0;
}

.custom-input {
  margin-top: 10px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

@media (max-width: 768px) {
  .leader-dialog :deep(.el-dialog) {
    margin: 0 auto !important;
  }
  .leader-dialog :deep(.el-dialog__body) {
    padding: 12px;
    max-height: 65vh;
    overflow-y: auto;
  }
  .question-item {
    padding: 12px;
    margin-bottom: 14px;
  }
  .question-text {
    font-size: 13px;
  }
}
</style>
