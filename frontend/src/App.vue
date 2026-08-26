<template>
  <el-config-provider :locale="elementLocale">
    <div id="app" :class="{ 'has-footer': !isEmbedRoute }">
      <ThemeToggle v-if="!isEmbedRoute && !isAdminRoute" class="global-theme-toggle" />
      <router-view />
      <!-- 全局底部状态栏（品牌版本/GitHub/赞助/协议/署名），嵌入模式不展示 -->
      <AppFooter v-if="!isEmbedRoute" />
    </div>
  </el-config-provider>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElConfigProvider } from 'element-plus'
import ThemeToggle from '@/components/ThemeToggle.vue'
import AppFooter from '@/components/AppFooter.vue'
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

/* 底部状态栏占位补偿：文档流页面预留高度并延续背景色，防止内容被遮挡 */
#app.has-footer {
  height: auto;
  min-height: 100vh;
  padding-bottom: var(--footer-height);
  background: var(--color-background);
}

/* 全局主题切换按钮 - 固定在右上角 */
.global-theme-toggle {
  position: fixed;
  bottom: calc(var(--footer-height) + 12px);
  right: 16px;
  z-index: 9999;
}

/* 移动端保持与桌面一致，避免遮挡 header 用户菜单。 */
@media (max-width: 640px) {
  .global-theme-toggle {
    bottom: calc(var(--footer-height) + 12px);
    right: 16px;
  }
}
</style>
