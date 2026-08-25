<template>
  <div class="admin-header">
    <div class="header-left">
      <!-- 折叠/展开按钮 -->
      <el-icon
        class="collapse-btn"
        :size="20"
        :title="t('admin.shell.toggleSidebar')"
        :aria-label="t('admin.shell.toggleSidebar')"
        @click="$emit('toggle-sidebar')"
      >
        <Fold v-if="!collapsed" />
        <Expand v-else />
      </el-icon>

      <!-- 面包屑导航 -->
      <el-breadcrumb separator="/" class="header-breadcrumb">
        <el-breadcrumb-item :to="{ path: '/admin' }">{{ t('admin.shell.title') }}</el-breadcrumb-item>
        <el-breadcrumb-item v-if="currentPageName">{{ currentPageName }}</el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <div class="header-right">
      <LanguageSelector />
      <ThemeToggle />

      <!-- 用户下拉菜单 -->
      <el-dropdown trigger="click" @command="handleCommand">
        <span class="user-dropdown">
          <el-icon><UserFilled /></el-icon>
          <span class="username">{{ username }}</span>
          <el-icon class="arrow-icon"><ArrowDown /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="home">
              <el-icon><HomeFilled /></el-icon>
              {{ t('admin.shell.backToSite') }}
            </el-dropdown-item>
            <el-dropdown-item command="logout" divided>
              <el-icon><SwitchButton /></el-icon>
              {{ t('admin.shell.logout') }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import LanguageSelector from '@/components/LanguageSelector.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import {
  Fold,
  Expand,
  UserFilled,
  ArrowDown,
  HomeFilled,
  SwitchButton
} from '@element-plus/icons-vue'

defineProps({
  collapsed: {
    type: Boolean,
    default: false
  }
})

defineEmits(['toggle-sidebar'])

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

// 当前用户名
const username = computed(() => authStore.user?.username || t('admin.shell.administrator'))

// 页面名称映射
const pageNameMap = {
  '/admin/dashboard': 'dashboard',
  '/admin/performance': 'performance',
  '/admin/leader-sessions': 'leaderSessions',
  '/admin/featured': 'featured',
  '/admin/tools': 'tools',
  '/admin/openharness': 'openharness',
  '/admin/agentteams-integration': 'agentteamsIntegration',
  '/admin/llm-models': 'llmModels',
  '/admin/settings': 'settings'
}

// 当前页面名称（用于面包屑）
const currentPageName = computed(() => {
  const pageKey = pageNameMap[route.path]
  return pageKey ? t(`admin.nav.${pageKey}`) : ''
})

// 下拉菜单命令处理
function handleCommand(command) {
  if (command === 'home') {
    router.push('/')
  } else if (command === 'logout') {
    authStore.logout()
    router.push('/login')
  }
}
</script>

<style lang="scss" scoped>
.admin-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
  position: sticky;
  top: 0;
  z-index: 1000;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.collapse-btn {
  cursor: pointer;
  color: var(--el-text-color-regular);
  transition: color 0.2s;

  &:hover {
    color: var(--el-color-primary);
  }
}

.header-breadcrumb {
  line-height: 56px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-dropdown {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: var(--el-text-color-regular);
  font-size: 14px;

  &:hover {
    color: var(--el-color-primary);
  }
}

.username {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 640px) {
  .admin-header {
    padding: 0 12px;
  }

  .header-left {
    gap: 8px;
    min-width: 0;
  }

  .header-breadcrumb {
    display: none;
  }

  .header-right {
    gap: 8px;
  }

  .username,
  .arrow-icon {
    display: none;
  }
}

.arrow-icon {
  font-size: 12px;
}
</style>
