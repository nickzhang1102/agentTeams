<template>
  <footer class="app-footer">
    <!-- 桌面端完整状态栏 -->
    <template v-if="isDesktop">
      <span class="footer-brand">Agent Teams<strong v-if="version"> v{{ version }}</strong></span>
      <span class="footer-divider">|</span>
      <a class="footer-link" :href="REPO_URL" target="_blank" rel="noopener">GitHub</a>
      <span class="footer-divider">|</span>
      <button class="footer-sponsor" @click="showSponsor = true">💜 {{ t('common.footer.sponsor') }}</button>
      <span class="footer-divider">|</span>
      <span class="footer-meta">© 2026 AGPL-3.0</span>
      <span class="footer-divider">|</span>
      <span class="footer-meta">Made with ❤️ by nickzhang1102</span>
    </template>

    <!-- 移动端细条 -->
    <template v-else>
      <span class="footer-meta">Agent Teams<template v-if="version"> v{{ version }}</template></span>
      <span class="footer-dot">·</span>
      <button class="footer-sponsor" @click="showSponsor = true">💜 {{ t('common.footer.sponsor') }}</button>
    </template>

    <SponsorDialog v-model="showSponsor" />
  </footer>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResponsive } from '@/composables/useResponsive'
import { useAppVersion } from '@/composables/useAppVersion'
import { REPO_URL } from '@/utils/constants'
import SponsorDialog from '@/components/SponsorDialog.vue'

const { t } = useI18n()
const { isDesktop } = useResponsive()
const { version, fetchVersion } = useAppVersion()

const showSponsor = ref(false)

onMounted(() => {
  fetchVersion()
})
</script>

<style scoped>
.app-footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  /* 低于 Element Plus 弹层(2000+)与浮动按钮(9999)，避免遮挡弹窗与主题切换 */
  z-index: 900;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: var(--footer-height);
  padding: 4px 12px;
  background: var(--color-card);
  border-top: 1px solid var(--color-border);
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
}

.footer-brand {
  color: var(--color-text);
  font-weight: 600;
}

.footer-brand strong {
  color: var(--color-text-muted, #94a3b8);
  font-weight: 500;
}

.footer-divider {
  color: var(--color-border);
}

.footer-dot {
  color: var(--color-text-muted, #94a3b8);
}

.footer-link {
  color: var(--color-text);
  text-decoration: none;
}

.footer-link:hover {
  color: var(--color-primary);
}

.footer-sponsor {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 25%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-primary) 8%, transparent);
  color: var(--color-primary);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.footer-sponsor:hover,
.footer-sponsor:active {
  background: color-mix(in srgb, var(--color-primary) 18%, transparent);
}

.footer-meta {
  white-space: nowrap;
}

/* 移动端细条收紧间距 */
@media (max-width: 767px) {
  .app-footer {
    gap: 6px;
  }
}
</style>
