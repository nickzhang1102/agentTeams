import { ref, onMounted } from 'vue'

// 全局状态（跨组件共享）
const theme = ref('auto') // 'light' | 'dark' | 'auto'
const isDark = ref(false)

// 系统偏好监听提升到模块级：MediaQueryList 与 change 监听只注册一次，
// 避免 ThemeToggle/admin Sidebar 反复挂载时累积监听器（useResponsive 同款模式）
const systemDark = window.matchMedia('(prefers-color-scheme: dark)')

function applyTheme() {
  const shouldBeDark = theme.value === 'auto'
    ? systemDark.matches
    : theme.value === 'dark'

  document.documentElement.setAttribute('data-theme', shouldBeDark ? 'dark' : 'light')
  isDark.value = shouldBeDark
}

// 监听系统偏好变化（仅在 auto 模式下生效）
systemDark.addEventListener('change', () => {
  if (theme.value === 'auto') {
    applyTheme()
  }
})

export function useTheme() {
  // 初始化（仅在首次调用时执行）
  onMounted(() => {
    // 从 localStorage 读取主题偏好
    const saved = localStorage.getItem('theme')
    if (saved && ['light', 'dark', 'auto'].includes(saved)) {
      theme.value = saved
    }

    // 应用主题
    applyTheme()
  })

  return {
    theme,
    isDark,
    toggleTheme: (newTheme) => {
      theme.value = newTheme
      localStorage.setItem('theme', newTheme)
      applyTheme()
    }
  }
}
