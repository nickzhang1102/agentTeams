<template>
  <el-config-provider :locale="elementLocale">
    <div id="app">
      <ThemeToggle v-if="!isEmbedRoute && !isAdminRoute" class="global-theme-toggle" />
      <router-view />
    </div>
  </el-config-provider>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElConfigProvider } from 'element-plus'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { elementLocale } from '@/locales'

const route = useRoute()
const isEmbedRoute = computed(() => route.path.startsWith('/embed/'))
const isAdminRoute = computed(() => route.path.startsWith('/admin'))
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
}

#app {
  width: 100%;
  height: 100vh;
  position: relative;
}

/* 全局主题切换按钮 - 固定在右上角 */
.global-theme-toggle {
  position: fixed;
  bottom: 20px;
  right: 16px;
  z-index: 9999;
}

/* 移动端保持与桌面一致，避免遮挡 header 用户菜单。 */
@media (max-width: 640px) {
  .global-theme-toggle {
    bottom: 20px;
    right: 16px;
  }
}
</style>
