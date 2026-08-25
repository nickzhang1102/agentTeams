<template>
  <el-dropdown @command="handleCommand" trigger="click" placement="bottom-end">
    <el-button
      :icon="currentIcon"
      :aria-label="t('common.theme.selector')"
      :title="t('common.theme.selector')"
      circle
      size="default"
      class="theme-toggle-btn"
    />
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          command="light"
          :class="{ 'is-active': theme === 'light' }"
        >
          <el-icon><Sunny /></el-icon>
          <span style="margin-left: 8px;">{{ t('common.theme.light') }}</span>
        </el-dropdown-item>
        <el-dropdown-item
          command="dark"
          :class="{ 'is-active': theme === 'dark' }"
        >
          <el-icon><Moon /></el-icon>
          <span style="margin-left: 8px;">{{ t('common.theme.dark') }}</span>
        </el-dropdown-item>
        <el-dropdown-item
          command="auto"
          :class="{ 'is-active': theme === 'auto' }"
        >
          <el-icon><Monitor /></el-icon>
          <span style="margin-left: 8px;">{{ t('common.theme.auto') }}</span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import { computed } from 'vue'
import { Sunny, Moon, Monitor } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'

const { theme, isDark, toggleTheme } = useTheme()
const { t } = useI18n()

const currentIcon = computed(() => {
  if (theme.value === 'light') return Sunny
  if (theme.value === 'dark') return Moon
  return isDark.value ? Moon : Sunny
})

function handleCommand(command) {
  toggleTheme(command)
}
</script>

<style scoped>
.theme-toggle-btn {
  background: var(--el-bg-color);
  border-color: var(--el-border-color);
  color: var(--el-text-color-primary);
  box-shadow: var(--el-box-shadow-light);
}

.theme-toggle-btn:hover {
  background: var(--el-fill-color);
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.is-active {
  color: var(--el-color-primary);
  background-color: var(--el-fill-color-light);
}
</style>
