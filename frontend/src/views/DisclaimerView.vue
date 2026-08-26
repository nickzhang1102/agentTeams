<template>
  <div class="disclaimer-page">
    <div class="disclaimer-container">
      <div class="disclaimer-header">
        <h1>{{ t('common.disclaimerTitle') }}</h1>
        <router-link to="/login" class="back-link">{{ t('common.backToLogin') }}</router-link>
      </div>
      <el-card shadow="never" class="disclaimer-card">
        <MarkdownRenderer :content="mdContent" />
      </el-card>
    </div>
  </div>
</template>

<script setup>
// 免责声明以 ?raw 单源引入仓库根的 DISCLAIMER.md，避免内容双份漂移
import disclaimerMd from '@repo/DISCLAIMER.md?raw'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const mdContent = disclaimerMd
</script>

<style scoped>
.disclaimer-page {
  min-height: 100vh;
  padding: var(--spacing-lg, 24px);
  background: var(--color-background, #f8fafc);
}

.disclaimer-container {
  max-width: 860px;
  margin: 0 auto;
}

.disclaimer-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--spacing-md, 16px);
  margin-bottom: var(--spacing-md, 16px);
}

.disclaimer-header h1 {
  margin: 0;
  font-size: var(--font-size-h3, 22px);
  color: var(--color-text, #0f172a);
}

.back-link {
  font-size: var(--font-size-sm, 13px);
  color: var(--color-primary, #2563eb);
  text-decoration: none;
  white-space: nowrap;
}

.back-link:hover {
  text-decoration: underline;
}

.disclaimer-card {
  border-radius: var(--radius-lg, 12px);
}
</style>
