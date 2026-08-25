import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import dayjs from 'dayjs'

const { patch, showError } = vi.hoisted(() => ({
  patch: vi.fn(() => Promise.resolve({ data: { locale: 'en-US' } })),
  showError: vi.fn(),
}))

vi.mock('@/utils/api', () => ({
  default: { patch },
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: showError },
}))

import { elementLocale, i18n } from '@/locales'
import { messages } from '@/locales/messages'
import { useLocaleStore } from '@/stores/locale'

function messageKeys(value, prefix = '') {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return child && typeof child === 'object' && !Array.isArray(child)
      ? messageKeys(child, path)
      : [path]
  })
}

function messageEntries(value, prefix = '') {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return child && typeof child === 'object' && !Array.isArray(child)
      ? messageEntries(child, path)
      : [[path, child]]
  })
}

function messageValue(catalog, key) {
  return key.split('.').reduce((value, segment) => value?.[segment], catalog)
}

function placeholders(value) {
  return [...value.matchAll(/\{([^{}]+)\}/g)].map((match) => match[1]).sort()
}

const sourceFiles = import.meta.glob('../../**/*.{js,vue}', {
  eager: true,
  query: '?raw',
  import: 'default',
})

describe('locale store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    window.history.replaceState({}, '', '/')
    document.documentElement.lang = ''
    Object.defineProperty(navigator, 'languages', {
      configurable: true,
      value: ['zh-CN'],
    })
    patch.mockClear()
    showError.mockClear()
  })

  it('uses the Chinese browser locale when no preference is stored', async () => {
    const store = useLocaleStore()

    await store.initializeLocale()

    expect(store.locale).toBe('zh-CN')
    expect(document.documentElement.lang).toBe('zh-CN')
  })

  it('keeps message keys symmetric across supported locales', () => {
    expect(messageKeys(messages['en-US']).sort()).toEqual(messageKeys(messages['zh-CN']).sort())
  })

  it('keeps every translated value nonempty', () => {
    for (const locale of Object.keys(messages)) {
      for (const [key, value] of messageEntries(messages[locale])) {
        expect(value, `${locale}:${key}`).toBeTypeOf('string')
        expect(value.trim(), `${locale}:${key}`).not.toBe('')
      }
    }
  })

  it('keeps interpolation placeholders aligned across locales', () => {
    for (const key of messageKeys(messages['zh-CN'])) {
      expect(
        placeholders(messageValue(messages['en-US'], key)),
        key,
      ).toEqual(placeholders(messageValue(messages['zh-CN'], key)))
    }
  })

  it('resolves every literal translation key used by source files', () => {
    const referencedKeys = new Set()
    const translationCall = /\b(?:t|i18n\.global\.t)\(\s*['"]([^'"]+)['"]/g

    for (const [filename, source] of Object.entries(sourceFiles)) {
      if (filename.includes('/locales/') || filename.includes('/__tests__/')) continue
      for (const match of source.matchAll(translationCall)) referencedKeys.add(match[1])
    }

    const missingKeys = [...referencedKeys]
      .filter((key) => messageValue(messages['zh-CN'], key) === undefined)
      .sort()

    expect(missingKeys).toEqual([])
  })

  it('uses the stored anonymous locale during initialization', async () => {
    localStorage.setItem('preferred_locale', 'en-US')
    const store = useLocaleStore()

    await store.initializeLocale()

    expect(store.locale).toBe('en-US')
    expect(document.documentElement.lang).toBe('en-US')
    expect(i18n.global.locale.value).toBe('en-US')
    expect(elementLocale.value.name).toBe('en')
    expect(dayjs.locale()).toBe('en')
  })

  it('uses the embed client locale before stored AgentTeams preferences', async () => {
    localStorage.setItem('preferred_locale', 'en-US')
    window.history.replaceState({}, '', '/embed/conversation/token?locale=zh-CN')
    const store = useLocaleStore()

    await store.initializeLocale()

    expect(store.locale).toBe('zh-CN')
    expect(document.documentElement.lang).toBe('zh-CN')
  })

  it('persists an explicit selection that matches the resolved locale', async () => {
    Object.defineProperty(navigator, 'languages', {
      configurable: true,
      value: ['en-US'],
    })
    const store = useLocaleStore()
    await store.initializeLocale()

    await store.setLocale('en-US')

    expect(localStorage.getItem('preferred_locale')).toBe('en-US')
  })

  it('persists the last explicit locale for an authenticated user', async () => {
    const store = useLocaleStore()
    await store.initializeLocale()
    store.syncAuthenticatedUser({ id: 1, preferred_locale: 'zh-CN' })

    await store.setLocale('en-US')
    await store.setLocale('zh-CN')

    await vi.waitFor(() => expect(patch).toHaveBeenCalledTimes(2))
    expect(patch.mock.calls.map((call) => call[1].locale)).toEqual(['en-US', 'zh-CN'])
    expect(store.locale).toBe('zh-CN')
    expect(localStorage.getItem('preferred_locale')).toBe('zh-CN')
    expect(JSON.parse(localStorage.getItem('user')).preferred_locale).toBe('zh-CN')
  })

  it('lets the authenticated user preference override anonymous storage', async () => {
    localStorage.setItem('preferred_locale', 'zh-CN')
    const store = useLocaleStore()
    await store.initializeLocale()

    store.syncAuthenticatedUser({ id: 1, preferred_locale: 'en-US' })

    expect(store.locale).toBe('en-US')
    expect(localStorage.getItem('preferred_locale')).toBe('en-US')
  })

  it('rejects unsupported explicit locales without changing state', async () => {
    localStorage.setItem('preferred_locale', 'zh-CN')
    const store = useLocaleStore()
    await store.initializeLocale()

    await expect(store.setLocale('fr-FR')).rejects.toThrow('UNSUPPORTED_LOCALE')
    expect(store.locale).toBe('zh-CN')
  })

  it('keeps the local locale when remote persistence fails', async () => {
    patch.mockRejectedValueOnce(new Error('offline'))
    const store = useLocaleStore()
    await store.initializeLocale()
    store.syncAuthenticatedUser({ id: 1, preferred_locale: 'zh-CN' })

    await store.setLocale('en-US')

    await vi.waitFor(() => expect(showError).toHaveBeenCalledOnce())
    expect(store.locale).toBe('en-US')
    expect(localStorage.getItem('preferred_locale')).toBe('en-US')
  })
})
