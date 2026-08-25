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

import { useAgentsStore } from '@/stores/agents'
import { useKnowledgeStore } from '@/stores/knowledge'
import { useLocaleStore } from '@/stores/locale'
import { useWorkflowTemplateStore } from '@/stores/workflowTemplate'
import { catalogLabel } from '@/utils/catalog'

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

describe('localized catalog stores', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    get.mockReset()
  })

  it('resolves display labels with compatibility fallbacks', () => {
    expect(catalogLabel({ label: 'English', name: '中文', key: 'item' })).toBe('English')
    expect(catalogLabel({ name: '中文', key: 'item' })).toBe('中文')
    expect(catalogLabel({ key: 'item' })).toBe('item')
  })

  it('sends the UI locale and ignores stale Agent responses', async () => {
    const first = deferred()
    const second = deferred()
    get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const localeStore = useLocaleStore()
    const store = useAgentsStore()
    localeStore.locale = 'zh-CN'
    const chineseRequest = store.fetchAgents()
    localeStore.locale = 'en-US'
    const englishRequest = store.fetchAgents()

    second.resolve({ data: { agents: [{ agent_id: 'a', label: 'English' }] } })
    await englishRequest
    first.resolve({ data: { agents: [{ agent_id: 'a', label: '中文' }] } })
    await chineseRequest

    expect(get.mock.calls[0][1].params.locale).toBe('zh-CN')
    expect(get.mock.calls[1][1].params.locale).toBe('en-US')
    expect(store.agents[0].label).toBe('English')
  })

  it('refreshes loaded templates on locale change and keeps the latest response', async () => {
    const initial = deferred()
    const refresh = deferred()
    get.mockReturnValueOnce(initial.promise).mockReturnValueOnce(refresh.promise)

    const localeStore = useLocaleStore()
    const store = useWorkflowTemplateStore()
    localeStore.locale = 'zh-CN'
    const initialRequest = store.fetchTemplates({ page: 2 })
    initial.resolve({ data: { items: [{ id: 7, label: '中文' }], page: 2 } })
    await initialRequest

    localeStore.locale = 'en-US'
    await Promise.resolve()
    expect(get.mock.calls[1][1].params).toMatchObject({ page: 2, locale: 'en-US' })
    refresh.resolve({ data: { items: [{ id: 7, label: 'English' }], page: 2 } })
    await refresh.promise
    await Promise.resolve()

    expect(store.templates).toEqual([{ id: 7, label: 'English' }])
  })

  it('sends the UI locale and ignores stale knowledge category responses', async () => {
    const first = deferred()
    const second = deferred()
    get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const localeStore = useLocaleStore()
    const store = useKnowledgeStore()
    localeStore.locale = 'zh-CN'
    const chineseRequest = store.fetchCategories()
    localeStore.locale = 'en-US'
    const englishRequest = store.fetchCategories()

    second.resolve({ data: { categories: [{ key: 'regulation', label: 'Policies' }] } })
    await englishRequest
    first.resolve({ data: { categories: [{ key: 'regulation', label: '制度' }] } })
    await chineseRequest

    expect(get.mock.calls[0][1].params.locale).toBe('zh-CN')
    expect(get.mock.calls[1][1].params.locale).toBe('en-US')
    expect(store.categories).toEqual([{ key: 'regulation', label: 'Policies' }])
  })
})
