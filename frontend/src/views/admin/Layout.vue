<template>
  <div class="admin-layout">
    <!-- 侧边栏 -->
    <Sidebar :collapsed="sidebarCollapsed" />

    <!-- 移动端遮罩层 -->
    <div
      v-if="isMobile && !sidebarCollapsed"
      class="sidebar-overlay"
      @click="sidebarCollapsed = true"
    />

    <!-- 主内容区 -->
    <div class="admin-main" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
      <Header
        :collapsed="sidebarCollapsed"
        @toggle-sidebar="handleToggleSidebar"
      />
      <div class="admin-content">
        <!-- 权限校验中 -->
        <div v-if="checking" class="admin-loading">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          <p>{{ t('admin.shell.checkingPermission') }}</p>
        </div>

        <!-- 无权限 -->
        <div v-else-if="!adminStore.isAdmin" class="admin-denied">
          <el-icon :size="48" color="#f56c6c"><CircleCloseFilled /></el-icon>
          <h2>{{ t('admin.shell.accessDenied') }}</h2>
          <p>{{ t('admin.shell.noPermission') }}</p>
          <el-button type="primary" @click="router.push('/')">{{ t('admin.shell.backHome') }}</el-button>
        </div>

        <!-- 管理员内容 -->
        <router-view v-else />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Loading, CircleCloseFilled } from '@element-plus/icons-vue'
import { useAdminStore } from '@/stores/admin'
import Sidebar from '@/components/admin/Sidebar.vue'
import Header from '@/components/admin/Header.vue'

const router = useRouter()
const { t } = useI18n()
const adminStore = useAdminStore()

const sidebarCollapsed = ref(false)
const checking = ref(true)
const isMobile = ref(false)

// 检测移动端
function checkMobile() {
  isMobile.value = window.innerWidth < 768
  if (isMobile.value) {
    sidebarCollapsed.value = true
  }
}

// 切换侧边栏
function handleToggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

// 权限检查
onMounted(async () => {
  checkMobile()
  window.addEventListener('resize', checkMobile)

  const isAdmin = await adminStore.checkAdminStatus()
  if (!isAdmin) {
    ElMessage.error(t('admin.shell.noAdminPermission'))
    router.push('/')
  }
  checking.value = false
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>

<style lang="scss" scoped>
.admin-layout {
  display: flex;
  /* 预留全局底部状态栏高度，避免内容被遮挡 */
  min-height: calc(100vh - var(--footer-height));
}

.sidebar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  z-index: 1000;
}

.admin-main {
  flex: 1;
  min-width: 0;
  margin-left: 220px;
  transition: margin-left 0.3s;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - var(--footer-height));

  &.sidebar-collapsed {
    margin-left: 64px;
  }
}

.admin-content {
  flex: 1;
  min-width: 0;
  padding: 20px;
  background-color: var(--el-bg-color-page);
}

.admin-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  gap: 16px;
  color: var(--el-text-color-secondary);

  p {
    font-size: 14px;
  }
}

.admin-denied {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  gap: 12px;

  h2 {
    color: var(--el-color-danger);
    margin: 0;
  }

  p {
    color: var(--el-text-color-secondary);
    margin: 0;
  }
}

// 移动端适配
@media (max-width: 768px) {
  .admin-main {
    margin-left: 0 !important;
  }

  .admin-content {
    padding: 12px;
  }
}
</style>
