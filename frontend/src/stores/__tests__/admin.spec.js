import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/utils/api', () => ({
  default: {
    get,
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}))

import { useAdminStore } from '@/stores/admin'
import { useLocaleStore } from '@/stores/locale'
import { applyLocale } from '@/locales'

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

describe('localized Admin tool catalogs', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    applyLocale('zh-CN')
    get.mockReset()
  })

  it('refreshes only a tool catalog that has already been loaded', async () => {
    get
      .mockResolvedValueOnce({ data: { tools: [{ name: 'shell', description: '中文' }] } })
      .mockResolvedValueOnce({ data: { tools: [{ name: 'shell', description: 'English' }] } })

    const localeStore = useLocaleStore()
    const store = useAdminStore()
    localeStore.locale = 'zh-CN'
    await store.fetchToolList()

    localeStore.locale = 'en-US'
    await Promise.resolve()
    await Promise.resolve()

    expect(get).toHaveBeenNthCalledWith(1, '/api/admin/tools', { params: { locale: 'zh-CN' } })
    expect(get).toHaveBeenNthCalledWith(2, '/api/admin/tools', { params: { locale: 'en-US' } })
    expect(get).not.toHaveBeenCalledWith('/api/admin/openharness/tools', expect.anything())
    expect(store.toolList[0].description).toBe('English')
  })

  it('keeps the latest locale when tool catalog responses arrive out of order', async () => {
    const chinese = deferred()
    const english = deferred()
    get.mockReturnValueOnce(chinese.promise).mockReturnValueOnce(english.promise)

    const localeStore = useLocaleStore()
    const store = useAdminStore()
    localeStore.locale = 'zh-CN'
    const chineseRequest = store.fetchToolList()
    localeStore.locale = 'en-US'
    const englishRequest = store.fetchToolList()

    english.resolve({ data: { tools: [{ name: 'shell', description: 'English' }] } })
    await englishRequest
    chinese.resolve({ data: { tools: [{ name: 'shell', description: '中文' }] } })
    await chineseRequest

    expect(store.toolList).toEqual([{ name: 'shell', description: 'English' }])
  })

  it('uses independent race protection for the OpenHarness catalog', async () => {
    const chinese = deferred()
    const english = deferred()
    get.mockReturnValueOnce(chinese.promise).mockReturnValueOnce(english.promise)

    const localeStore = useLocaleStore()
    const store = useAdminStore()
    localeStore.locale = 'zh-CN'
    const chineseRequest = store.fetchOpenHarnessTools()
    localeStore.locale = 'en-US'
    const englishRequest = store.fetchOpenHarnessTools()

    english.resolve({ data: { tools: [{ name: 'shell', description: 'English OH' }] } })
    await englishRequest
    chinese.resolve({ data: { tools: [{ name: 'shell', description: '中文 OH' }] } })
    await chineseRequest

    expect(get.mock.calls[0][1].params.locale).toBe('zh-CN')
    expect(get.mock.calls[1][1].params.locale).toBe('en-US')
    expect(store.openharnessTools[0].description).toBe('English OH')
    expect(store.toolList).toEqual([])
  })

  it('localizes client-owned fallback errors', async () => {
    get.mockRejectedValueOnce(new Error('network unavailable'))
    applyLocale('en-US')

    const store = useAdminStore()
    await store.fetchConversations()

    expect(store.error).toBe('Could not load data')
  })

  it('preserves unknown backend diagnostics', async () => {
    get.mockRejectedValueOnce({ response: { data: { error: '上游诊断原文' } } })
    applyLocale('en-US')

    const store = useAdminStore()
    await store.fetchConversations()

    expect(store.error).toBe('上游诊断原文')
  })
})
