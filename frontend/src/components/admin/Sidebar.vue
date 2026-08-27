<template>
  <div class="admin-sidebar" :class="{ 'is-collapsed': collapsed }">
    <!-- Logo 区域 -->
    <div class="sidebar-logo">
      <el-icon :size="24"><Monitor /></el-icon>
      <span v-show="!collapsed" class="logo-text">{{ t('admin.shell.title') }}</span>
    </div>

    <!-- 导航菜单 -->
    <div class="sidebar-body">
      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed"
        :collapse-transition="false"
        router
        :background-color="sidebarBg"
        :text-color="sidebarText"
        :active-text-color="sidebarActiveText"
      >
        <el-menu-item index="/admin/dashboard">
          <el-icon><Monitor /></el-icon>
          <template #title>{{ t('admin.nav.dashboard') }}</template>
        </el-menu-item>

        <el-menu-item index="/admin/performance">
          <el-icon><TrendCharts /></el-icon>
          <template #title>{{ t('admin.nav.performance') }}</template>
        </el-menu-item>

        <el-menu-item index="/admin/leader-sessions">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>{{ t('admin.nav.leaderSessions') }}</template>
        </el-menu-item>

        <el-menu-item index="/admin/featured">
          <el-icon><Star /></el-icon>
          <template #title>{{ t('admin.nav.featured') }}</template>
        </el-menu-item>

        <el-menu-item index="/admin/tools">
          <el-icon><SetUp /></el-icon>
          <template #title>{{ t('admin.nav.tools') }}</template>
        </el-menu-item>

        <el-menu-item index="/admin/openharness">
          <el-icon><Connection /></el-icon>
          <template #title>{{ t('admin.nav.openharness') }}</template>
        </el-menu-item>

        <el-menu-item index="/admin/agentteams-integration">
          <el-icon><Link /></el-icon>
          <template #title>{{ t('admin.nav.agentteamsIntegration') }}</template>
        </el-menu-item>

      </el-menu>
    </div>

    <!-- 底部：返回主站按钮（对齐 OncoPath 管理后台侧边栏「返回前台」） -->
    <div class="sidebar-footer">
      <router-link to="/" class="back-to-site" :title="t('admin.shell.backToSite')">
        <el-icon><Back /></el-icon>
        <span v-show="!collapsed">{{ t('admin.shell.backToSite') }}</span>
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Monitor, TrendCharts, SetUp, Connection, DataAnalysis, Star, Link, Back } from '@element-plus/icons-vue'
import { useTheme } from '@/composables/useTheme'

defineProps({
  collapsed: {
    type: Boolean,
    default: false
  }
})

const route = useRoute()
const { t } = useI18n()

// 根据当前路由路径高亮对应菜单项
const activeMenu = computed(() => {
  return route.path
})

// 侧边栏颜色（响应暗色模式）
const { isDark } = useTheme()

const sidebarBg = computed(() => isDark.value ? '#1E293B' : '#FFFFFF')
const sidebarText = computed(() => isDark.value ? '#94A3B8' : '#303133')
const sidebarActiveText = computed(() => isDark.value ? '#6BB3FF' : '#409eff')
</script>

<style lang="scss" scoped>
.admin-sidebar {
  width: 220px;
  /* 预留全局底部状态栏高度，避免内容被遮挡 */
  height: calc(100vh - var(--footer-height));
  background-color: var(--el-bg-color-overlay);
  transition: width 0.3s;
  overflow: hidden;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 1001;
  display: flex;
  flex-direction: column;

  &.is-collapsed {
    width: 64px;
  }
}

.sidebar-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.sidebar-footer {
  border-top: 1px solid var(--el-border-color-light);
  padding: 4px 0;
}

.back-to-site {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 50px;
  padding: 0 20px;
  color: var(--el-text-color-regular);
  font-size: 14px;
  text-decoration: none;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.2s, color 0.2s;

  &:hover {
    background-color: var(--el-fill-color-dark);
    color: var(--el-color-primary);
  }
}

/* 折叠态：图标居中 */
.is-collapsed .back-to-site {
  justify-content: center;
  gap: 0;
  padding: 0;
}

.sidebar-logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--el-text-color-primary);
  font-size: 18px;
  font-weight: 600;
  background-color: var(--el-fill-color-dark);
  overflow: hidden;
  white-space: nowrap;
}

.logo-text {
  transition: opacity 0.3s;
}

// Element Plus 菜单样式覆盖
:deep(.el-menu) {
  border-right: none;
}

:deep(.el-menu-item) {
  &:hover {
    background-color: var(--el-fill-color-dark) !important;
  }

  &.is-active {
    background-color: var(--el-fill-color-darker) !important;
  }
}

@media (max-width: 768px) {
  .admin-sidebar {
    width: 220px;
    transform: translateX(0);
    transition: transform 0.3s;

    &.is-collapsed {
      width: 220px;
      transform: translateX(-100%);
    }
  }
}
</style>
