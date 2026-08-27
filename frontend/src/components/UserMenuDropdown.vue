<template>
  <div class="user-menu-dropdown">
    <div v-if="authStore.isAuthenticated" class="user-menu">
      <el-dropdown @command="handleCommand">
        <span class="user-info">
          <el-avatar :size="32" :src="authStore.user?.avatar">
            {{ authStore.user?.username?.charAt(0).toUpperCase() }}
          </el-avatar>
          <span class="username">{{ authStore.user?.username }}</span>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="agents">
              <el-icon><User /></el-icon>
              {{ t('auth.menu.agents') }}
            </el-dropdown-item>
            <el-dropdown-item command="templates">
              <el-icon><Operation /></el-icon>
              {{ t('auth.menu.templates') }}
            </el-dropdown-item>
            <el-dropdown-item command="knowledge">
              <el-icon><FolderOpened /></el-icon>
              {{ t('auth.menu.knowledge') }}
            </el-dropdown-item>
            <el-dropdown-item command="projectSettings">
              <el-icon><Setting /></el-icon>
              {{ t('auth.menu.projectSettings') }}
            </el-dropdown-item>
            <el-dropdown-item command="settings">
              <el-icon><Lock /></el-icon>
              {{ t('auth.menu.settings') }}
            </el-dropdown-item>
            <!-- 管理后台入口（仅管理员可见，对齐 OncoPath 系统管理入口） -->
            <el-dropdown-item v-if="authStore.user?.is_admin" divided command="admin">
              <el-icon><Management /></el-icon>
              {{ t('auth.menu.admin') }}
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              <el-icon><SwitchButton /></el-icon>
              {{ t('auth.menu.logout') }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    <div v-else class="auth-buttons">
      <el-button @click="router.push('/login')" text>{{ t('auth.menu.login') }}</el-button>
      <el-button @click="router.push('/register')" type="primary">{{ t('auth.menu.register') }}</el-button>
    </div>

    <!-- 修改密码弹窗 -->
    <el-dialog
      v-model="showPasswordDialog"
      :title="t('auth.password.title')"
      class="password-dialog"
      width="min(420px, calc(100vw - 32px))"
      append-to-body
      :close-on-click-modal="false"
    >
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-width="130px"
        @submit.prevent="handleSubmitPassword"
      >
        <el-form-item :label="t('auth.password.old')" prop="oldPassword">
          <el-input
            v-model="passwordForm.oldPassword"
            type="password"
            :placeholder="t('auth.password.oldPlaceholder')"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-form-item :label="t('auth.password.new')" prop="newPassword">
          <el-input
            v-model="passwordForm.newPassword"
            type="password"
            :placeholder="t('auth.password.newPlaceholder')"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item :label="t('auth.password.confirm')" prop="confirmPassword">
          <el-input
            v-model="passwordForm.confirmPassword"
            type="password"
            :placeholder="t('auth.password.confirmPlaceholder')"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPasswordDialog = false">{{ t('common.actions.cancel') }}</el-button>
        <el-button
          type="primary"
          :loading="passwordLoading"
          @click="handleSubmitPassword"
        >
          {{ t('auth.password.submit') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { User, Operation, FolderOpened, Lock, SwitchButton, Setting, Management } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  authStore: { type: Object, required: true }
})

const router = useRouter()
const { t } = useI18n()

// 修改密码弹窗
const showPasswordDialog = ref(false)
const passwordLoading = ref(false)
const passwordFormRef = ref(null)
const passwordForm = ref({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const validateConfirmPassword = (rule, value, callback) => {
  if (value !== passwordForm.value.newPassword) {
    callback(new Error(t('auth.validation.passwordsMismatch')))
  } else {
    callback()
  }
}

const passwordRules = computed(() => ({
  oldPassword: [
    { required: true, message: t('auth.password.oldRequired'), trigger: 'blur' }
  ],
  newPassword: [
    { required: true, message: t('auth.password.newRequired'), trigger: 'blur' },
    { min: 8, message: t('auth.validation.passwordLength'), trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: t('auth.password.confirmRequired'), trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
}))

async function handleSubmitPassword() {
  if (!passwordFormRef.value) return
  try {
    await passwordFormRef.value.validate()
  } catch { return }

  passwordLoading.value = true
  try {
    const result = await props.authStore.changePassword(
      passwordForm.value.oldPassword,
      passwordForm.value.newPassword
    )
    if (result.success) {
      ElMessage.success(t('auth.password.success'))
      showPasswordDialog.value = false
      passwordForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
    } else {
      ElMessage.error(t(`auth.errors.${result.code || 'REQUEST_FAILED'}`))
    }
  } catch {
    ElMessage.error(t('auth.password.retry'))
  } finally {
    passwordLoading.value = false
  }
}

const NAV_ROUTES = {
  agents: '/agents',
  templates: '/templates',
  knowledge: '/knowledge',
  projectSettings: '/project/settings',
  admin: '/admin'
}

function handleCommand(command) {
  if (command === 'settings') {
    showPasswordDialog.value = true
  } else if (command === 'logout') {
    props.authStore.logout()
    router.push('/')
  } else if (NAV_ROUTES[command]) {
    router.push(NAV_ROUTES[command])
  }
}
</script>

<style scoped>
.user-menu-dropdown {
  display: flex;
  align-items: center;
}

.user-menu { cursor: pointer; }

.user-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-md);
  transition: background var(--duration-fast) var(--ease-in-out);
}
.user-info:hover { background: var(--color-hover); }

.username {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text);
}

@media (max-width: 640px) {
  .username { display: none; }
}

.auth-buttons {
  display: flex;
  gap: var(--spacing-sm);
}
</style>
