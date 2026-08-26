// 响应式断点：与 ChatLayout 的移动端判定口径一致（< 768 为移动端）
import { ref, onMounted, onUnmounted } from 'vue'

const MD_BREAKPOINT = 768

// 单例状态，跨组件共享；立即初始化避免首帧闪烁
const media = window.matchMedia(`(min-width: ${MD_BREAKPOINT}px)`)
const isDesktop = ref(media.matches)

function handleChange(e) {
  isDesktop.value = e.matches
}

export function useResponsive() {
  onMounted(() => media.addEventListener('change', handleChange))
  onUnmounted(() => media.removeEventListener('change', handleChange))
  return { isDesktop }
}
