<template>
  <div class="register-container">
    <!-- Animated Background -->
    <div class="background-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
      <div class="circle circle-3"></div>
    </div>

    <!-- Register Card -->
    <el-card class="register-card glass-container animate-fade-in">
      <template #header>
        <div class="card-header">
          <div class="logo-icon animate-float">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z" fill="url(#gradient)"/>
              <defs>
                <linearGradient id="gradient" x1="2" y1="2" x2="22" y2="22">
                  <stop offset="0%" stop-color="#DB2777"/>
                  <stop offset="100%" stop-color="#CA8A04"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h2 class="title text-gradient">{{ t('auth.register.title') }}</h2>
          <p class="subtitle">{{ t('auth.register.subtitle') }}</p>
        </div>
      </template>

      <el-form
        ref="registerFormRef"
        :model="registerForm"
        :rules="rules"
        label-width="0"
        class="register-form"
      >
        <el-form-item prop="username">
          <el-input
            v-model="registerForm.username"
            :placeholder="t('auth.fields.username')"
            size="large"
            prefix-icon="User"
            clearable
          />
        </el-form-item>

        <el-form-item prop="email">
          <el-input
            v-model="registerForm.email"
            type="email"
            :placeholder="t('auth.fields.email')"
            size="large"
            prefix-icon="Message"
            clearable
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="registerForm.password"
            type="password"
            :placeholder="t('auth.fields.password')"
            size="large"
            prefix-icon="Lock"
            show-password
          />
        </el-form-item>

        <el-form-item prop="confirmPassword">
          <el-input
            v-model="registerForm.confirmPassword"
            type="password"
            :placeholder="t('auth.fields.confirmPassword')"
            size="large"
            prefix-icon="Lock"
            show-password
            @keyup.enter="handleRegister"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            @click="handleRegister"
            class="register-button"
          >
            <span v-if="!loading">{{ t('auth.register.submit') }}</span>
            <span v-else>{{ t('auth.register.submitting') }}</span>
          </el-button>
        </el-form-item>

        <div class="footer-link">
          {{ t('auth.register.hasAccount') }}
          <router-link to="/login" class="login-link">{{ t('auth.register.loginNow') }}</router-link>
        </div>
      </el-form>
    </el-card>

    <!-- Footer -->
    <div class="register-footer">
      <p>© 2026 Agent Teams. Powered by znick</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

const registerFormRef = ref(null)
const loading = ref(false)

const registerForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const validatePass = (rule, value, callback) => {
  if (value === '') {
    callback(new Error(t('auth.validation.passwordRequired')))
  } else if (value.length < 8) {
    callback(new Error(t('auth.validation.passwordLength')))
  } else {
    if (registerForm.confirmPassword !== '') {
      registerFormRef.value.validateField('confirmPassword')
    }
    callback()
  }
}

const validatePass2 = (rule, value, callback) => {
  if (value === '') {
    callback(new Error(t('auth.validation.confirmPasswordRequired')))
  } else if (value !== registerForm.password) {
    callback(new Error(t('auth.validation.passwordsMismatch')))
  } else {
    callback()
  }
}

const rules = computed(() => ({
  username: [
    { required: true, message: t('auth.validation.usernameRequired'), trigger: 'blur' },
    { min: 3, max: 50, message: t('auth.validation.usernameLength'), trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: t('auth.validation.emailInvalid'), trigger: 'blur' }
  ],
  password: [
    { required: true, validator: validatePass, trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, validator: validatePass2, trigger: 'blur' }
  ]
}))

const handleRegister = async () => {
  if (!registerFormRef.value) return

  await registerFormRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    const result = await authStore.register(
      registerForm.username,
      registerForm.password,
      registerForm.email || null
    )
    loading.value = false

    if (result.success) {
      ElMessage.success(t('auth.register.success'))
      router.push('/login')
    } else {
      ElMessage.error(t(`auth.errors.${result.code || 'REQUEST_FAILED'}`))
    }
  })
}
</script>

<style scoped>
.register-container {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 50%, #DBEAFE 100%);
  overflow: hidden;
  padding: 2rem;
}

/* Animated Background Decoration */
.background-decoration {
  position: absolute;
  width: 100%;
  height: 100%;
  overflow: hidden;
  z-index: 0;
}

.circle {
  position: absolute;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.1) 0%, rgba(59, 130, 246, 0.1) 100%);
  filter: blur(40px);
}

.circle-1 {
  width: 400px;
  height: 400px;
  top: -100px;
  right: -100px;
  animation: float 6s ease-in-out infinite;
}

.circle-2 {
  width: 300px;
  height: 300px;
  bottom: -50px;
  left: -50px;
  animation: float 8s ease-in-out infinite reverse;
}

.circle-3 {
  width: 250px;
  height: 250px;
  top: 50%;
  right: 10%;
  animation: float 7s ease-in-out infinite;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0);
  }
  50% {
    transform: translate(-30px, -30px);
  }
}

/* Register Card */
.register-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 440px;
  padding: 0;
  overflow: visible;
}

.card-header {
  text-align: center;
  padding: var(--space-2);
}

.logo-icon {
  margin-bottom: var(--space-4);
}

.title {
  margin: 0 0 var(--space-2) 0;
  font-size: var(--text-3xl);
  font-weight: 700;
  letter-spacing: -0.025em;
}

.subtitle {
  margin: 0;
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  font-weight: 400;
}

/* Form */
.register-form {
  margin-top: var(--space-6);
}

.register-form :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.3);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  transition: all var(--transition-base) var(--ease-in-out);
}

.register-form :deep(.el-input__wrapper:hover) {
  background: rgba(255, 255, 255, 0.8);
  border-color: rgba(37, 99, 235, 0.3);
}

.register-form :deep(.el-input__wrapper:focus-within) {
  background: rgba(255, 255, 255, 0.9);
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1), 0 4px 12px rgba(0, 0, 0, 0.1);
}

.register-button {
  width: 100%;
  height: 48px;
  font-size: var(--text-lg, 1.125rem);
  font-weight: 600;
  border-radius: var(--radius-lg, 0.75rem);
  background: linear-gradient(135deg, var(--color-primary, #4F9CF9) 0%, var(--color-primary-light, #6BB3FF) 100%);
  border: none;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
  transition: all var(--transition-base, 200ms) var(--ease-in-out, cubic-bezier(0.4, 0, 0.2, 1));
  color: #FFFFFF !important;
}

.register-button span {
  color: #FFFFFF !important;
}

.register-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4);
}

.register-button:active {
  transform: translateY(0);
}

/* Footer Link */
.footer-link {
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin-top: var(--space-6);
}

.login-link {
  color: var(--color-primary);
  text-decoration: none;
  font-weight: 600;
  transition: all var(--transition-base);
  padding: 0 0.25rem;
  border-radius: var(--radius-sm);
}

.login-link:hover {
  color: var(--color-primary-dark);
  background: rgba(219, 39, 119, 0.1);
}

/* Register Footer */
.register-footer {
  position: relative;
  z-index: 1;
  margin-top: var(--space-8);
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

/* Responsive */
@media (max-width: 768px) {
  .register-container {
    padding: var(--space-4);
  }

  .register-card {
    max-width: 100%;
  }

  .circle-1,
  .circle-2,
  .circle-3 {
    display: none;
  }
}

/* Accessibility - Reduced Motion */
@media (prefers-reduced-motion: reduce) {
  .circle-1,
  .circle-2,
  .circle-3,
  .logo-icon {
    animation: none;
  }

  .register-button:hover,
  .register-card:hover {
    transform: none;
  }
}

/* Dark Mode */
[data-theme="dark"] .register-container {
  background: linear-gradient(135deg, #0F172A 0%, #1E293B 50%, #334155 100%);
}

[data-theme="dark"] .circle {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(96, 165, 250, 0.15) 100%);
}
</style>
