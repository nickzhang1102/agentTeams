import { ref } from 'vue'
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import api from '@/utils/api'
import {
  DEFAULT_LOCALE,
  LOCALE_OPTIONS,
  applyLocale,
  i18n,
  isSupportedLocale,
  normalizeBrowserLocale,
} from '@/locales'
import { resolveEmbedPrefix } from '@/utils/embedBase'

const LOCALE_STORAGE_KEY = 'preferred_locale'

function readStoredLocale() {
  const value = localStorage.getItem(LOCALE_STORAGE_KEY)
  return isSupportedLocale(value) ? value : null
}

function readCachedUser() {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null')
  } catch {
    return null
  }
}

function readCachedUserLocale() {
  const user = readCachedUser()
  return isSupportedLocale(user?.preferred_locale) ? user.preferred_locale : null
}

function readBrowserLocale() {
  const languages = navigator.languages?.length ? navigator.languages : [navigator.language]
  return languages.map(normalizeBrowserLocale).find(Boolean) || null
}

function readEmbedLocale() {
  if (typeof window === 'undefined') return null
  // 嵌入路径可能带宿主挂载前缀（如 OncoPath 同站反代的 /agentteams）；
  // 前缀随宿主部署而定，按 /embed/ 路径段识别，不写死具体前缀。
  if (resolveEmbedPrefix(window.location.pathname) === null) return null
  const value = new URLSearchParams(window.location.search).get('locale')
  return isSupportedLocale(value) ? value : null
}

export const useLocaleStore = defineStore('locale', () => {
  const locale = ref(DEFAULT_LOCALE)
  const initialized = ref(false)
  const switching = ref(false)
  let authenticatedUser = null
  let saveQueue = Promise.resolve()
  let latestSaveId = 0

  function apply(localeValue) {
    locale.value = localeValue
    applyLocale(localeValue)
  }

  async function initializeLocale() {
    if (initialized.value) return

    authenticatedUser = readCachedUser()
    const initialLocale = readEmbedLocale()
      || readCachedUserLocale()
      || readStoredLocale()
      || readBrowserLocale()
      || DEFAULT_LOCALE

    apply(initialLocale)
    initialized.value = true
  }

  async function setLocale(localeValue) {
    if (!isSupportedLocale(localeValue)) {
      throw new Error('UNSUPPORTED_LOCALE')
    }

    if (locale.value !== localeValue) {
      apply(localeValue)
    }
    localStorage.setItem(LOCALE_STORAGE_KEY, localeValue)

    if (authenticatedUser) {
      authenticatedUser.preferred_locale = localeValue
      localStorage.setItem('user', JSON.stringify(authenticatedUser))
      persistPreferredLocale(localeValue)
    }
  }

  function syncAuthenticatedUser(user) {
    authenticatedUser = user || null
    latestSaveId += 1

    if (isSupportedLocale(user?.preferred_locale)) {
      apply(user.preferred_locale)
      localStorage.setItem(LOCALE_STORAGE_KEY, user.preferred_locale)
    }
  }

  function clearAuthenticatedUser() {
    authenticatedUser = null
    latestSaveId += 1
  }

  function persistPreferredLocale(localeValue) {
    const saveId = ++latestSaveId
    switching.value = true

    saveQueue = saveQueue
      .catch(() => undefined)
      .then(() => api.patch(
        '/api/auth/me/locale',
        { locale: localeValue },
        { suppressGlobalError: true },
      ))
      .catch(() => {
        if (saveId === latestSaveId) {
          ElMessage.error(i18n.global.t('locale.saveFailed'))
        }
      })
      .finally(() => {
        if (saveId === latestSaveId) {
          switching.value = false
        }
      })
  }

  return {
    locale,
    options: LOCALE_OPTIONS,
    initialized,
    switching,
    initializeLocale,
    setLocale,
    syncAuthenticatedUser,
    clearAuthenticatedUser,
  }
})
