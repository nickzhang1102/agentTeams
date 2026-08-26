<template>
  <el-dialog
    :model-value="modelValue"
    :width="isDesktop ? '420px' : '92%'"
    align-center
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <template #header>
      <span class="sponsor-title">{{ t('common.sponsor.title') }} 💜</span>
    </template>

    <p class="sponsor-desc">{{ t('common.sponsor.desc') }}</p>
    <div class="qr-grid">
      <div class="qr-item">
        <img :src="wechatQr" :alt="t('common.sponsor.wechatAlt')">
        <span>{{ t('common.sponsor.wechat') }}</span>
      </div>
      <div class="qr-item">
        <img :src="alipayQr" :alt="t('common.sponsor.alipayAlt')">
        <span>{{ t('common.sponsor.alipay') }}</span>
      </div>
    </div>
    <p class="sponsor-star-tip">
      {{ t('common.sponsor.starTip') }}
      <a :href="REPO_URL" target="_blank" rel="noopener">Star ⭐</a>
    </p>
  </el-dialog>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { useResponsive } from '@/composables/useResponsive'
import { REPO_URL } from '@/utils/constants'
import wechatQr from '@/assets/sponsor/wechat.jpg'
import alipayQr from '@/assets/sponsor/alipay.jpg'

defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['update:modelValue'])

const { t } = useI18n()
const { isDesktop } = useResponsive()
</script>

<style scoped>
.sponsor-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
}

.sponsor-desc {
  margin: 0 0 14px;
  font-size: 14px;
  color: var(--color-text);
  text-align: center;
}

.qr-grid {
  display: flex;
  justify-content: center;
  gap: 20px;
}

.qr-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.qr-item img {
  width: 150px;
  height: 150px;
  object-fit: contain;
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.qr-item span {
  font-size: 13px;
  color: var(--color-text-muted, #64748b);
}

.sponsor-star-tip {
  margin: 16px 0 0;
  font-size: 13px;
  color: var(--color-text-muted, #64748b);
  text-align: center;
}

.sponsor-star-tip a {
  color: var(--color-primary);
  text-decoration: none;
  font-weight: 500;
}
</style>
