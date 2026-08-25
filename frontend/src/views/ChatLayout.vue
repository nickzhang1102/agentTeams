<template>
  <div class="chat-layout">
    <!-- 桌面端：侧边栏始终挂载，通过宽度控制显隐 -->
    <ConversationSidebar
      v-if="!isMobile"
      :expanded="sidebarExpanded"
      :is-mobile="false"
      @collapse="sidebarExpanded = false"
      @expand="sidebarExpanded = true"
    />

    <!-- 移动端：侧边栏作为覆盖层 -->
    <ConversationSidebar
      v-if="isMobile"
      :expanded="mobileSidebarOpen"
      :is-mobile="true"
      @collapse="mobileSidebarOpen = false"
    />

    <!-- 右侧主内容区 -->
    <div class="main-area">
      <!-- 移动端汉堡菜单 -->
      <button
        v-if="isMobile"
        class="hamburger-btn"
        :aria-label="t('conversation.navigation.expandSidebar')"
        :title="t('conversation.navigation.expandSidebar')"
        @click="mobileSidebarOpen = true"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="3" y1="6" x2="21" y2="6"/>
          <line x1="3" y1="12" x2="21" y2="12"/>
          <line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>

      <!-- 桌面端：侧边栏折叠时显示展开按钮 -->
      <button
        v-if="!isMobile && !sidebarExpanded"
        class="sidebar-expand-fab"
        @click="sidebarExpanded = true"
        :title="t('conversation.navigation.expandSidebar')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="3" y1="6" x2="21" y2="6"/>
          <line x1="3" y1="12" x2="21" y2="12"/>
          <line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>

      <!-- 子路由出口 -->
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import ConversationSidebar from '@/components/ConversationSidebar.vue'

const { t } = useI18n()

const sidebarExpanded = ref(true)
const mobileSidebarOpen = ref(false)
const isMobile = ref(false)

function checkMobile() {
  isMobile.value = window.innerWidth < 768
  // 切换到桌面端时关闭移动端侧边栏
  if (!isMobile.value) mobileSidebarOpen.value = false
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>

<style scoped lang="scss">
.chat-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--color-background, #f8f9fa);
}

.main-area {
  flex: 1;
  min-width: 0;
  height: 100vh;
  position: relative;
  overflow: hidden;
}

/* 移动端汉堡菜单 */
.hamburger-btn {
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: var(--color-card);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 10px;
  color: #303133;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.15s ease;

  &:hover {
    border-color: var(--color-primary, #2563eb);
    color: var(--color-primary, #2563eb);
  }
}

/* 桌面端侧边栏折叠后的浮动按钮 */
.sidebar-expand-fab {
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--color-card);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 8px;
  color: #303133;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
  transition: all 0.15s ease;

  &:hover {
    border-color: var(--color-primary, #2563eb);
    color: var(--color-primary, #2563eb);
    box-shadow: 0 2px 10px rgba(37, 99, 235, 0.15);
  }
}
</style>
