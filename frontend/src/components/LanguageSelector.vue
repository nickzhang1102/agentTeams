<template>
  <div class="language-selector">
    <button
      ref="triggerRef"
      class="lang-trigger"
      :class="{ active: dropdownOpen }"
      :aria-label="t('locale.selector')"
      :aria-expanded="dropdownOpen"
      aria-haspopup="listbox"
      type="button"
      @click.stop="toggleDropdown"
    >
      <svg class="lang-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <path d="M2 12h20" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
      <span class="lang-label">{{ currentOption?.label }}</span>
      <svg
        class="lang-chevron"
        :class="{ open: dropdownOpen }"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>

    <Teleport to="body">
      <transition name="lang-dropdown">
        <ul
          v-if="dropdownOpen"
          class="lang-dropdown"
          role="listbox"
          :aria-label="t('locale.selector')"
          :style="dropdownStyle"
        >
          <li
            v-for="option in localeStore.options"
            :key="option.value"
            class="lang-option"
            :class="{ selected: option.value === localeStore.locale }"
            role="option"
            :aria-selected="option.value === localeStore.locale"
            @click="select(option.value)"
          >
            <span class="lang-option-label">{{ option.label }}</span>
            <svg
              v-if="option.value === localeStore.locale"
              class="lang-check"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="3"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </li>
        </ul>
      </transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocaleStore } from '@/stores/locale'

const localeStore = useLocaleStore()
const { t } = useI18n()

const triggerRef = ref(null)
const dropdownOpen = ref(false)
const dropdownStyle = ref({})

const currentOption = computed(() =>
  localeStore.options.find((o) => o.value === localeStore.locale),
)

function toggleDropdown() {
  dropdownOpen.value = !dropdownOpen.value
  if (dropdownOpen.value && triggerRef.value) {
    const rect = triggerRef.value.getBoundingClientRect()
    dropdownStyle.value = {
      position: 'fixed',
      top: `${rect.bottom + 8}px`,
      left: `${rect.left}px`,
      minWidth: `${rect.width}px`,
    }
  }
}

function closeDropdown() {
  dropdownOpen.value = false
}

function select(value) {
  localeStore.setLocale(value)
  closeDropdown()
}

function handleClickOutside(e) {
  if (!e.target.closest('.language-selector')) {
    closeDropdown()
  }
}

document.addEventListener('click', handleClickOutside)
onBeforeUnmount(() => document.removeEventListener('click', handleClickOutside))
</script>

<style scoped>
.language-selector {
  position: relative;
  display: inline-flex;
}

/* ===== 触发器：与主页 .tool-button 同源设计语言 ===== */
.lang-trigger {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 12px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-in-out),
    border-color var(--duration-fast) var(--ease-in-out),
    color var(--duration-fast) var(--ease-in-out),
    transform var(--duration-fast) var(--ease-in-out);
}

.lang-trigger:hover {
  background: var(--color-hover);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.lang-trigger:active {
  transform: scale(0.97);
}

.lang-trigger.active {
  background: var(--color-hover);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

/* 聚焦环 — 继承设计系统无障碍规范 */
.lang-trigger:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.lang-icon {
  flex-shrink: 0;
  opacity: 0.85;
}

.lang-label {
  white-space: nowrap;
  letter-spacing: 0.01em;
}

.lang-chevron {
  flex-shrink: 0;
  opacity: 0.55;
  transition:
    transform var(--duration-fast) var(--ease-in-out),
    opacity var(--duration-fast) var(--ease-in-out);
}

.lang-chevron.open {
  transform: rotate(180deg);
  opacity: 1;
}

/* ===== 下拉面板：玻璃拟态 + 主页卡片阴影体系 ===== */
.lang-dropdown {
  list-style: none;
  margin: 0;
  min-width: 148px;
  padding: 6px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  z-index: 9999;
  /* 玻璃拟态叠加：在支持 backdrop-filter 的浏览器上生效 */
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.lang-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 12px;
  background: transparent;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
  text-align: left;
  transition:
    background var(--duration-fast) var(--ease-in-out),
    color var(--duration-fast) var(--ease-in-out),
    transform var(--duration-fast) var(--ease-in-out);
}

.lang-option:hover {
  background: var(--color-hover);
  color: var(--color-primary);
}

.lang-option:active {
  transform: scale(0.98);
}

.lang-option.selected {
  background: var(--color-primary);
  color: #ffffff;
}

.lang-option.selected:hover {
  background: var(--color-secondary);
}

.lang-option-label {
  flex: 1;
  white-space: nowrap;
}

.lang-check {
  flex-shrink: 0;
  color: #ffffff;
}

/* ===== 下拉动画：与主页 .dropdown 同源 ===== */
.lang-dropdown-enter-active {
  transition:
    opacity 0.18s var(--ease-out),
    transform 0.18s var(--ease-out);
}

.lang-dropdown-leave-active {
  transition:
    opacity 0.12s var(--ease-in),
    transform 0.12s var(--ease-in);
}

.lang-dropdown-enter-from,
.lang-dropdown-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

/* ===== 减少动画模式 ===== */
@media (prefers-reduced-motion: reduce) {
  .lang-trigger,
  .lang-option,
  .lang-chevron,
  .lang-dropdown-enter-active,
  .lang-dropdown-leave-active {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}

/* ===== 移动端适配（与主页工具栏 640px 断点一致） ===== */
@media (max-width: 640px) {
  .lang-label {
    display: none;
  }

  .lang-trigger {
    padding: 0 8px;
  }

  .lang-chevron {
    display: none;
  }
}
</style>
