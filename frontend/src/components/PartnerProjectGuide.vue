<template>
  <Teleport to="body">
    <Transition name="guide-fade">
      <div v-if="visible" class="partner-guide-mask" @click.self="handleClose">
        <div class="partner-guide-card">
          <!-- 步骤指示器 -->
          <div class="guide-steps">
            <span
              v-for="(step, i) in stepCount"
              :key="i"
              :class="['step-dot', { active: currentStep === i }]"
            />
            <button class="guide-skip" type="button" @click="handleClose">
              {{ t('home.partnerGuide.skip') }}
            </button>
          </div>

          <!-- 步骤一：介绍 Agent Teams 项目 -->
          <div v-if="currentStep === 0" class="guide-step-body">
            <div class="hero-icon">⚕</div>
            <h2 class="guide-title">{{ t('home.partnerGuide.step1Title') }}</h2>
            <p class="guide-desc">{{ t('home.partnerGuide.step1Desc') }}</p>
            <div class="feature-row">
              <div class="feature-chip">✚ {{ t('home.partnerGuide.featureData') }}</div>
              <div class="feature-chip">✎ {{ t('home.partnerGuide.featurePrompt') }}</div>
              <div class="feature-chip">⟲ {{ t('home.partnerGuide.featureEmbed') }}</div>
            </div>
          </div>

          <!-- 步骤二：集成后协作效果示意 -->
          <div v-else class="guide-step-body">
            <h2 class="guide-title">{{ t('home.partnerGuide.step2Title') }}</h2>
            <p class="guide-desc">{{ t('home.partnerGuide.step2Desc') }}</p>

            <div class="demo-stage" aria-hidden="true">
              <!-- Agent Teams 整理的会诊材料 -->
              <div class="material-row">
                <span v-for="m in materials" :key="m" class="material-chip">{{ m }}</span>
              </div>
              <div class="flow-line down" />
              <!-- AgentTeams 专科专家并行分析 -->
              <div class="expert-row">
                <div
                  v-for="(label, i) in expertLabels"
                  :key="label"
                  class="expert-node"
                  :style="{ animationDelay: `${i * 0.5}s` }"
                >
                  <div class="expert-avatar"><span class="expert-icon">⚕</span></div>
                  <span class="expert-label">{{ label }}</span>
                </div>
              </div>
              <div class="flow-line down up" />
              <!-- 综合会诊报告回传嵌入 -->
              <div class="report-card">{{ t('home.partnerGuide.reportChip') }}</div>
            </div>

            <el-button
              type="primary"
              size="large"
              class="guide-cta"
              @click="openPartnerRepo"
            >{{ t('home.partnerGuide.cta') }} ↗</el-button>
          </div>

          <!-- 底部操作 -->
          <div class="guide-actions">
            <el-button v-if="currentStep > 0" plain @click="currentStep--">
              {{ t('home.partnerGuide.prev') }}
            </el-button>
            <span class="action-spacer" />
            <el-button type="primary" round @click="nextStep">
              {{ currentStep < stepCount - 1 ? t('home.partnerGuide.next') : t('home.partnerGuide.done') }}
            </el-button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script>
// 首次引导已读标记；宿主页面据此判断是否自动弹出
export const PARTNER_GUIDE_SEEN_KEY = 'agent-teams.partner-guide-seen'
</script>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const PARTNER_REPO_URL = 'https://github.com/nickzhang1102/oncopath'

const props = defineProps({
  show: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:show'])

const { t } = useI18n()

const currentStep = ref(0)
const stepCount = 2

const visible = computed({
  get: () => props.show,
  set: (value) => emit('update:show', value),
})

// 示意内容：会诊材料与专科专家，与 OncoPath × Agent Teams 真实集成业务一致
const materials = computed(() => [
  t('home.partnerGuide.materialLab'),
  t('home.partnerGuide.materialExam'),
  t('home.partnerGuide.materialPathology'),
])

const expertLabels = computed(() => [
  t('home.partnerGuide.expertOncology'),
  t('home.partnerGuide.expertImaging'),
  t('home.partnerGuide.expertPathology'),
])

watch(() => props.show, (show) => {
  if (show) currentStep.value = 0
})

function nextStep() {
  if (currentStep.value < stepCount - 1) {
    currentStep.value++
    return
  }
  handleClose()
}

function handleClose() {
  try {
    localStorage.setItem(PARTNER_GUIDE_SEEN_KEY, '1')
  } catch {
    // localStorage 不可用时静默跳过：仅影响下次不再自动弹出
  }
  visible.value = false
}

function openPartnerRepo() {
  window.open(PARTNER_REPO_URL, '_blank', 'noopener,noreferrer')
}
</script>

<style scoped>
.partner-guide-mask {
  position: fixed;
  inset: 0;
  z-index: 2100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-md);
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.partner-guide-card {
  width: min(92vw, 480px);
  max-height: 86vh;
  overflow-y: auto;
  padding: var(--spacing-lg);
  border-radius: var(--radius-xl);
  background: var(--color-card);
  border: 1px solid var(--color-border);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.25);
  animation: cardFloatIn 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}

@keyframes cardFloatIn {
  from {
    opacity: 0;
    transform: translateY(36px) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.guide-fade-enter-active,
.guide-fade-leave-active {
  transition: opacity 0.3s ease;
}

.guide-fade-enter-from,
.guide-fade-leave-to {
  opacity: 0;
}

/* 步骤指示器 */
.guide-steps {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: var(--spacing-md);
}

.step-dot {
  width: 20px;
  height: 4px;
  border-radius: 2px;
  background: var(--color-border);
  transition: background 0.3s ease, width 0.3s ease;
}

.step-dot.active {
  width: 32px;
  background: var(--color-primary);
}

.guide-skip {
  margin-left: auto;
  padding: 4px 8px;
  border: 0;
  background: transparent;
  color: var(--color-text-secondary, #64748b);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.guide-step-body {
  animation: stepFadeIn 0.35s ease;
}

@keyframes stepFadeIn {
  from {
    opacity: 0;
    transform: translateX(12px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.hero-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  margin: 0 auto var(--spacing-sm);
  border-radius: 18px;
  font-size: 30px;
  color: var(--color-primary);
  background: rgba(37, 99, 235, 0.1);
  animation: heroGlow 2.4s ease-in-out infinite;
}

@keyframes heroGlow {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.1);
  }
  50% {
    box-shadow: 0 0 24px 4px rgba(37, 99, 235, 0.12);
  }
}

.guide-title {
  margin: 0 0 var(--spacing-sm);
  text-align: center;
  font-family: var(--font-heading);
  font-size: var(--font-size-h4);
  font-weight: 700;
  color: var(--color-text);
}

.guide-desc {
  margin: 0 0 var(--spacing-sm);
  text-align: center;
  font-size: var(--font-size-sm);
  line-height: var(--line-height-normal);
  color: var(--color-text-secondary, #475569);
}

.feature-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-sm);
}

.feature-chip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 9px 4px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  white-space: nowrap;
  color: var(--color-primary);
  background: rgba(37, 99, 235, 0.06);
  border: 1px solid rgba(37, 99, 235, 0.15);
}

/* ===== CSS 动画示意舞台 ===== */
.demo-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  margin-bottom: var(--spacing-sm);
  border-radius: var(--radius-lg);
  background: var(--color-background);
  border: 1px solid var(--color-border);
}

.material-row {
  display: flex;
  gap: var(--spacing-sm);
}

.material-chip {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  background: rgba(37, 99, 235, 0.06);
  border: 1px solid rgba(37, 99, 235, 0.15);
  animation: materialFloat 2.4s ease-in-out infinite;
}

@keyframes materialFloat {
  0%,
  100% {
    transform: translateY(0);
    opacity: 0.75;
  }
  50% {
    transform: translateY(-3px);
    opacity: 1;
  }
}

.flow-line {
  width: 2px;
  height: 18px;
  border-radius: 1px;
  background: linear-gradient(to bottom, var(--color-primary), var(--color-success));
  transform-origin: top;
  animation: lineGrow 2.4s ease-in-out infinite;
}

.flow-line.up {
  height: 14px;
  transform-origin: bottom;
  background: linear-gradient(to top, var(--color-success), var(--color-primary));
}

@keyframes lineGrow {
  0%,
  100% {
    transform: scaleY(0.2);
    opacity: 0.3;
  }
  45% {
    transform: scaleY(1);
    opacity: 1;
  }
}

.expert-row {
  display: flex;
  gap: var(--spacing-lg);
}

.expert-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  animation: expertPulse 2.4s ease-in-out infinite;
}

@keyframes expertPulse {
  0%,
  100% {
    opacity: 0.45;
    transform: scale(0.96);
  }
  30% {
    opacity: 1;
    transform: scale(1.04);
  }
}

.expert-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: #fff;
  background: var(--color-primary);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
}

.expert-icon {
  font-size: 16px;
}

.expert-label {
  max-width: 72px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary, #64748b);
}

.report-card {
  padding: 6px 14px;
  border-radius: 999px;
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-success);
  background: var(--color-success-bg);
  border: 1px solid var(--color-success);
  animation: reportBounce 2.4s ease-in-out infinite;
}

@keyframes reportBounce {
  0%,
  100% {
    transform: translateY(0);
  }
  55% {
    transform: translateY(-3px);
  }
}

.guide-cta {
  width: 100%;
}

/* 底部操作区 */
.guide-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
}

.action-spacer {
  flex: 1;
}

@media (max-width: 380px) {
  .expert-row {
    gap: var(--spacing-md);
  }

  .feature-row {
    grid-template-columns: 1fr;
  }

  .feature-chip {
    justify-content: flex-start;
  }
}
</style>
