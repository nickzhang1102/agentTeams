import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import dayjs from 'dayjs'
import 'dayjs/locale/en.js'
import 'dayjs/locale/zh-cn.js'
import en from 'element-plus/es/locale/lang/en'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { messages } from './messages.js'

export const DEFAULT_LOCALE = 'zh-CN'
export const SUPPORTED_LOCALES = ['zh-CN', 'en-US']
export const LOCALE_OPTIONS = [
  { value: 'zh-CN', label: '中文' },
  { value: 'en-US', label: 'English' },
]

const elementLocales = {
  'zh-CN': zhCn,
  'en-US': en,
}

const dayjsLocales = {
  'zh-CN': 'zh-cn',
  'en-US': 'en',
}

export const activeLocale = ref(DEFAULT_LOCALE)
export const elementLocale = ref(elementLocales[DEFAULT_LOCALE])

export const i18n = createI18n({
  legacy: false,
  locale: DEFAULT_LOCALE,
  fallbackLocale: DEFAULT_LOCALE,
  messages,
})

export function isSupportedLocale(locale) {
  return SUPPORTED_LOCALES.includes(locale)
}

export function normalizeBrowserLocale(locale) {
  if (!locale) return null

  const language = locale.trim().toLowerCase()
  if (language === 'zh' || language.startsWith('zh-')) return 'zh-CN'
  if (language === 'en' || language.startsWith('en-')) return 'en-US'
  return null
}

export function getCurrentLocale() {
  return activeLocale.value
}

export function applyLocale(locale) {
  activeLocale.value = locale
  i18n.global.locale.value = locale
  elementLocale.value = elementLocales[locale]
  dayjs.locale(dayjsLocales[locale])

  if (typeof document !== 'undefined') {
    document.documentElement.lang = locale
  }
}
