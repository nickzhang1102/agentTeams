<template>
  <el-dialog
    :model-value="modelValue"
    :width="isDesktop ? '420px' : '92%'"
    align-center
    @update:model-value="close"
  >
    <template #header>
      <span class="sponsor-title">{{ t('common.sponsor.title') }} 💜</span>
    </template>

    <!-- 档位选择视图 -->
    <template v-if="view === 'tiers'">
      <p class="sponsor-desc">{{ t('common.sponsor.desc') }}</p>
      <div class="tier-grid">
        <div
          v-for="tier in TIERS"
          :key="tier.amount"
          class="tier-card"
          @click="view = tier.amount"
        >
          <span class="tier-amount">¥{{ tier.amount }}</span>
          <span class="tier-label">{{ tier.emoji }} {{ t(`common.sponsor.tiers.t${tier.amount}`) }}</span>
        </div>
      </div>
      <p class="sponsor-star-tip">
        {{ t('common.sponsor.starTip') }}
        <a :href="REPO_URL" target="_blank" rel="noopener">Star ⭐</a>
      </p>
      <p class="sponsor-alt">
        <a href="javascript:;" @click="view = 'alipay'">{{ t('common.sponsor.alipayEntry') }}</a>
      </p>
    </template>

    <!-- 微信专属金额码视图 -->
    <template v-else-if="view === 'alipay'">
      <p class="sponsor-desc">{{ t('common.sponsor.alipayDesc') }}</p>
      <div class="qr-wrap">
        <img :src="alipayQr" :alt="t('common.sponsor.alipayAlt')">
      </div>
      <el-button class="sponsor-back" size="small" plain @click="view = 'tiers'">
        ← {{ t('common.sponsor.back') }}
      </el-button>
    </template>

    <!-- 支付宝通用码视图 -->
    <template v-else>
      <p class="sponsor-desc">{{ t('common.sponsor.wechatDesc', { amount: view }) }}</p>
      <div class="qr-wrap">
        <img :src="tierQr(view)" :alt="t('common.sponsor.wechatAltAmount', { amount: view })">
        <span class="qr-tier-tag">{{ tierEmoji(view) }} {{ t(`common.sponsor.tiers.t${view}`) }}</span>
      </div>
      <p class="sponsor-hint">{{ t('common.sponsor.amountHint') }}</p>
      <el-button class="sponsor-back" size="small" plain @click="view = 'tiers'">
        ← {{ t('common.sponsor.back') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResponsive } from '@/composables/useResponsive'
import { REPO_URL } from '@/utils/constants'
import wechatQr5 from '@/assets/sponsor/wechat5.png'
import wechatQr10 from '@/assets/sponsor/wechat10.png'
import wechatQr20 from '@/assets/sponsor/wechat20.png'
import wechatQr50 from '@/assets/sponsor/wechat50.png'
import wechatQr99 from '@/assets/sponsor/wechat99.png'
import alipayQr from '@/assets/sponsor/alipay.jpg'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()
const { isDesktop } = useResponsive()

// 赞助档位（能量补给风格，每档绑定专属金额收款码，与 OncoPath 同款）
const TIERS = [
  { amount: 5, emoji: '🌶️', qr: wechatQr5 },
  { amount: 10, emoji: '🍱', qr: wechatQr10 },
  { amount: 20, emoji: '☕', qr: wechatQr20 },
  { amount: 50, emoji: '🍢', qr: wechatQr50 },
  { amount: 99, emoji: '🍲', qr: wechatQr99 },
]

// 当前视图：'tiers' = 档位选择，'alipay' = 支付宝通用码，数字 = 对应档位微信码
const view = ref('tiers')

const tierQr = (amount) => TIERS.find((tier) => tier.amount === amount)?.qr
const tierEmoji = (amount) => TIERS.find((tier) => tier.amount === amount)?.emoji

// 每次打开弹窗回到档位选择视图
watch(() => props.modelValue, (show) => {
  if (show) view.value = 'tiers'
})

function close(value) {
  emit('update:modelValue', value)
}
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

.tier-grid {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.tier-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 104px;
  padding: 12px 8px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s;
}

.tier-card:hover {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 6%, transparent);
  transform: translateY(-2px);
}

.tier-amount {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-primary);
}

.tier-label {
  font-size: 12px;
  color: var(--color-text-muted, #64748b);
}

.qr-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.qr-wrap img {
  width: 200px;
  height: 200px;
  object-fit: contain;
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.qr-tier-tag {
  font-size: 13px;
  color: var(--color-text);
}

.sponsor-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--color-text-muted, #64748b);
  text-align: center;
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

.sponsor-alt {
  margin: 8px 0 0;
  font-size: 12px;
  text-align: center;
}

.sponsor-alt a {
  color: var(--color-text-muted, #64748b);
  text-decoration: none;
}

.sponsor-alt a:hover {
  color: var(--color-primary);
}

.sponsor-back {
  display: block;
  margin: 14px auto 0;
}
</style>
