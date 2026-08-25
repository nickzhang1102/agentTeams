<template>
  <transition name="fade">
    <div
      v-show="isVisible"
      class="scroll-to-top-btn"
      :class="{ 'is-absolute': positionMode === 'absolute' }"
      :aria-label="t('leader.actions.scrollToTop')"
      :title="t('leader.actions.scrollToTop')"
      @click="scrollToTop"
    >
      <el-icon><ArrowUp /></el-icon>
    </div>
  </transition>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowUp } from '@element-plus/icons-vue'

const { t } = useI18n()

const props = defineProps({
  targetRef: {
    type: Object,
    default: null
  },
  containerRef: {
    type: Object,
    default: null
  },
  positionMode: {
    type: String,
    default: 'fixed', // 'fixed' 或 'absolute'
    validator: (value) => ['fixed', 'absolute'].includes(value)
  }
})

const isVisible = ref(false)

// 检查是否需要显示按钮
function checkVisibility() {
  if (!props.targetRef || !props.containerRef) {
    isVisible.value = false
    return
  }

  const containerRect = props.containerRef.getBoundingClientRect()
  const targetRect = props.targetRef.getBoundingClientRect()

  // 使用容器的滚动高度来判断内容是否足够长
  const contentHeight = props.containerRef.scrollHeight
  const viewportHeight = props.containerRef.clientHeight
  
  // 内容高度超过视口高度 + 100px 才有必要显示按钮
  const isLongContent = contentHeight > viewportHeight + 100
  
  // 检查目标锚点是否已经滚动离开顶部
  // targetRect.top < containerRect.top - 10 表示目标已经滚到容器顶部以上
  // 此时用户已经向下滚动了，需要显示按钮
  const hasScrolled = targetRect.top < containerRect.top - 10
  
  // 只有内容够长且已经滚动时才显示
  isVisible.value = isLongContent && hasScrolled
}

// 监听滚动事件
let scrollHandler = null
let mutationObserver = null
let resizeObserver = null
let checkTimeout = null

// 设置滚动监听
function setupScrollListener() {
  if (!props.containerRef || scrollHandler) return

  scrollHandler = () => checkVisibility()
  props.containerRef.addEventListener('scroll', scrollHandler)
}

// 清理滚动监听
function cleanupScrollListener(container = props.containerRef) {
  if (container && scrollHandler) {
    container.removeEventListener('scroll', scrollHandler)
    scrollHandler = null
  }
}

// 设置 MutationObserver 监听 DOM 变化（用于折叠面板展开/收起）
function setupMutationObserver() {
  const observeTarget = props.containerRef || props.targetRef
  if (!observeTarget || mutationObserver) return

  mutationObserver = new MutationObserver((mutations) => {
    // DOM 变化时延迟重新检查（等待动画完成）
    clearTimeout(checkTimeout)
    checkTimeout = setTimeout(() => {
      checkVisibility()
    }, 350) // el-collapse 动画大约 300ms
  })

  mutationObserver.observe(observeTarget, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['style', 'class']
  })
}

// 清理 MutationObserver
function cleanupMutationObserver() {
  if (mutationObserver) {
    mutationObserver.disconnect()
    mutationObserver = null
  }
  if (checkTimeout) {
    clearTimeout(checkTimeout)
    checkTimeout = null
  }
}

// 设置 ResizeObserver 监听元素大小变化
function setupResizeObserver() {
  const observeTarget = props.containerRef || props.targetRef
  if (!observeTarget || resizeObserver) return

  resizeObserver = new ResizeObserver((entries) => {
    // 大小变化时重新检查可见性
    clearTimeout(checkTimeout)
    checkTimeout = setTimeout(() => {
      checkVisibility()
    }, 100)
  })

  resizeObserver.observe(observeTarget)
}

// 清理 ResizeObserver
function cleanupResizeObserver() {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
}

// 监听 props 变化，处理动态 ref
watch(() => [props.targetRef, props.containerRef], ([newTarget, newContainer], [oldTarget, oldContainer] = []) => {
  cleanupScrollListener(oldContainer)
  cleanupMutationObserver()
  cleanupResizeObserver()

  if (newTarget && newContainer) {
    nextTick(() => {
      checkVisibility()
      setupScrollListener()
      setupMutationObserver()
      setupResizeObserver()
      // 延迟再次检查，确保 DOM 完全渲染
      setTimeout(() => {
        checkVisibility()
      }, 400)
    })
  } else {
    isVisible.value = false
  }
}, { immediate: true })

onMounted(() => {
  // 监听窗口大小变化
  window.addEventListener('resize', checkVisibility)
})

onUnmounted(() => {
  cleanupScrollListener()
  cleanupMutationObserver()
  cleanupResizeObserver()
  window.removeEventListener('resize', checkVisibility)
})

function scrollToTop() {
  if (props.targetRef) {
    props.targetRef.scrollIntoView({ behavior: 'smooth', block: 'start' })
    // 滚动完成后隐藏按钮
    setTimeout(() => {
      isVisible.value = false
    }, 500)
  }
}
</script>

<style scoped>
.scroll-to-top-btn {
  position: fixed;
  right: 20px;
  bottom: 80px;
  width: 44px;
  height: 44px;
  background: var(--color-primary);
  border: none;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
  z-index: 1000;
  transition: all 0.2s ease;
}

.scroll-to-top-btn:hover {
  background: var(--color-secondary);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
}

.scroll-to-top-btn:active {
  transform: translateY(0) scale(0.95);
  box-shadow: 0 2px 6px rgba(37, 99, 235, 0.2);
}

.scroll-to-top-btn .el-icon {
  font-size: 22px;
  color: white;
}

/* 绝对定位模式（用于 AgentStatusPanel 等嵌套滚动容器） */
.scroll-to-top-btn.is-absolute {
  position: fixed;
  right: 20px;
  bottom: 80px;
  z-index: 1000;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
