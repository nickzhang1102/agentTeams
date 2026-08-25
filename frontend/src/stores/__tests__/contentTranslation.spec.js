import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import {
  contentSourceKey,
  applyTranslationOverlay,
  isContentSourceRef,
  useContentTranslationStore,
} from '../contentTranslation'

vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import api from '@/utils/api'

const source = { type: 'leader_final_report', id: 42 }

describe('content translation view store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('validates source refs and builds locale-specific keys', () => {
    expect(isContentSourceRef(source)).toBe(true)
    expect(isContentSourceRef({ type: 'message', id: 0 })).toBe(false)
    expect(isContentSourceRef({ type: 'unknown', id: 1 })).toBe(false)
    expect(contentSourceKey(source, 'en-US')).toBe('leader_final_report:42:en-US')
    expect(contentSourceKey(source, 'fr-FR')).toBeNull()
  })

  it('overlays only declared translatable report fields', () => {
    const original = {
      id: 42,
      content: 'Original',
      summary: { title: 'Original summary' },
      structured_report: { title: 'Original structure' },
      evidence_map: [{ evidence_id: 'ev-1', excerpt: 'Do not translate' }],
      raw_tool_results: { 'ev-1': 'Raw output' },
    }
    const translated = applyTranslationOverlay('leader_agent_result', original, {
      content: 'Translated',
      summary: { title: 'Translated summary' },
      structured_report: { title: 'Translated structure' },
      evidence_map: [{ evidence_id: 'changed' }],
      raw_tool_results: { changed: true },
    })

    expect(translated).toMatchObject({
      content: 'Translated',
      summary: { title: 'Translated summary' },
      structured_report: { title: 'Translated structure' },
    })
    expect(translated.evidence_map).toBe(original.evidence_map)
    expect(translated.raw_tool_results).toBe(original.raw_tool_results)
  })

  it('publishes ready payload only for the active locale and epoch', () => {
    const store = useContentTranslationStore()
    const requestEpoch = store.beginView('en-US')

    expect(store.ensureEntry(source, 'en-US', requestEpoch).state).toBe('original')
    expect(store.setEntryState(source, 'en-US', 'ready', {
      payload: { report: 'Translated report' },
    }, requestEpoch)).toBe(true)
    expect(store.getPayload(source, 'en-US')).toEqual({ report: 'Translated report' })

    store.beginView('zh-CN')
    expect(store.getPayload(source, 'en-US')).toBeNull()
  })

  it('rejects writes from a stale locale epoch', () => {
    const store = useContentTranslationStore()
    const oldEpoch = store.beginView('en-US')
    store.beginView('zh-CN')

    expect(store.setEntryState(source, 'en-US', 'ready', {
      payload: { report: 'Late result' },
    }, oldEpoch)).toBe(false)
    expect(store.getEntry(source, 'en-US')).toBeNull()
  })

  it('reactivates a ready payload when returning to the same locale', () => {
    const store = useContentTranslationStore()
    const firstEpoch = store.beginView('en-US')
    store.setEntryState(source, 'en-US', 'ready', {
      payload: { report: 'Cached translation' },
    }, firstEpoch)

    store.beginView('zh-CN')
    const nextEnglishEpoch = store.beginView('en-US')
    const entry = store.ensureEntry(source, 'en-US', nextEnglishEpoch)

    expect(entry.state).toBe('ready')
    expect(store.getPayload(source, 'en-US')).toEqual({ report: 'Cached translation' })
  })

  it('invalidates the active view and can clear all entries', () => {
    const store = useContentTranslationStore()
    const requestEpoch = store.beginView('en-US')
    store.setEntryState(source, 'en-US', 'failed', {
      errorCode: 'TRANSLATION_FAILED',
    }, requestEpoch)

    store.invalidateView({ clearEntries: true })

    expect(store.activeLocale).toBeNull()
    expect(store.entries).toEqual({})
  })

  it('batches owner resolve requests at twenty unique sources', async () => {
    api.post.mockImplementation((_url, body) => Promise.resolve({
      data: {
        items: body.sources.map(item => ({
          source: item,
          status: 'ready',
          target_locale: body.target_locale,
          payload: { text: `translation-${item.id}` },
        })),
      },
    }))
    const store = useContentTranslationStore()
    const requestEpoch = store.beginView('en-US')
    const sources = Array.from({ length: 21 }, (_, index) => ({
      type: 'message',
      id: index + 1,
    }))

    await store.resolveOwner([...sources, sources[0]], 'en-US', requestEpoch)

    expect(api.post).toHaveBeenCalledTimes(2)
    expect(api.post.mock.calls[0][1].sources).toHaveLength(20)
    expect(api.post.mock.calls[1][1].sources).toHaveLength(1)
    expect(store.getPayload(sources[20], 'en-US')).toEqual({ text: 'translation-21' })
  })

  it('uses share lookup only and marks cache misses unavailable', async () => {
    localStorage.setItem('token', 'existing-owner-token')
    api.post.mockResolvedValue({
      data: {
        items: [{
          source,
          status: 'ready',
          target_locale: 'en-US',
          payload: { report: 'Shared translation' },
        }],
        missing_sources: [{ type: 'message', id: 7 }],
      },
    })
    const store = useContentTranslationStore()
    const requestEpoch = store.beginView('en-US')
    const missingSource = { type: 'message', id: 7 }

    await store.lookupShare(
      [source, missingSource],
      'en-US',
      'share/token',
      requestEpoch,
    )

    expect(api.post).toHaveBeenCalledWith(
      '/api/content-translations/share/share%2Ftoken/lookup',
      {
        target_locale: 'en-US',
        sources: [source, missingSource],
      },
      { suppressGlobalError: true },
    )
    expect(api.post.mock.calls.some(([url]) => url === '/api/content-translations/resolve')).toBe(false)
    expect(api.get).not.toHaveBeenCalled()
    expect(store.getPayload(source, 'en-US')).toEqual({ report: 'Shared translation' })
    expect(store.getEntry(missingSource, 'en-US')).toMatchObject({ state: 'unavailable' })
    expect(store.pendingPollCount).toBe(0)
  })

  it('does not poll or expose non-ready share lookup items', async () => {
    api.post.mockResolvedValue({
      data: {
        items: [{
          source,
          translation_id: 601,
          status: 'pending',
          target_locale: 'en-US',
        }],
        missing_sources: [],
      },
    })
    const store = useContentTranslationStore()
    const requestEpoch = store.beginView('en-US')

    await store.lookupShare([source], 'en-US', 'public-token', requestEpoch)

    expect(store.getEntry(source, 'en-US')).toMatchObject({ state: 'unavailable' })
    expect(store.pendingPollCount).toBe(0)
    expect(api.get).not.toHaveBeenCalled()
  })

  it('polls each pending translation id once and publishes ready payload', async () => {
    vi.useFakeTimers()
    api.post.mockResolvedValue({
      data: {
        items: [{
          source,
          translation_id: 501,
          status: 'pending',
          target_locale: 'en-US',
        }],
      },
    })
    api.get.mockResolvedValue({
      data: {
        translation_id: 501,
        status: 'ready',
        target_locale: 'en-US',
        payload: { report: 'Ready report' },
      },
    })
    const store = useContentTranslationStore()
    const requestEpoch = store.beginView('en-US')

    await store.resolveOwner([source, source], 'en-US', requestEpoch)
    expect(store.pendingPollCount).toBe(1)

    await vi.advanceTimersByTimeAsync(2000)

    expect(api.get).toHaveBeenCalledTimes(1)
    expect(store.pendingPollCount).toBe(0)
    expect(store.getPayload(source, 'en-US')).toEqual({ report: 'Ready report' })
  })

  it('stops pending polling when a new locale epoch begins', async () => {
    vi.useFakeTimers()
    api.post.mockResolvedValue({
      data: {
        items: [{
          source,
          translation_id: 502,
          status: 'pending',
          target_locale: 'en-US',
        }],
      },
    })
    const store = useContentTranslationStore()
    const requestEpoch = store.beginView('en-US')

    await store.resolveOwner([source], 'en-US', requestEpoch)
    store.beginView('zh-CN')
    await vi.advanceTimersByTimeAsync(4000)

    expect(store.pendingPollCount).toBe(0)
    expect(api.get).not.toHaveBeenCalled()
  })

  it('pauses polling while the document is hidden', async () => {
    vi.useFakeTimers()
    let visibilityState = 'hidden'
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibilityState)
    api.post.mockResolvedValue({
      data: {
        items: [{
          source,
          translation_id: 503,
          status: 'pending',
          target_locale: 'en-US',
        }],
      },
    })
    api.get.mockResolvedValue({
      data: {
        translation_id: 503,
        status: 'ready',
        payload: { report: 'Visible result' },
      },
    })
    const store = useContentTranslationStore()
    const requestEpoch = store.beginView('en-US')
    await store.resolveOwner([source], 'en-US', requestEpoch)

    await vi.advanceTimersByTimeAsync(2000)
    expect(api.get).not.toHaveBeenCalled()

    visibilityState = 'visible'
    await vi.advanceTimersByTimeAsync(2000)
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(store.getPayload(source, 'en-US')).toEqual({ report: 'Visible result' })
  })

  it('falls back after three minutes of active pending polls', async () => {
    vi.useFakeTimers()
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    api.post.mockResolvedValue({
      data: {
        items: [{
          source,
          translation_id: 504,
          status: 'pending',
          target_locale: 'en-US',
        }],
      },
    })
    api.get.mockResolvedValue({ data: { status: 'pending' } })
    const store = useContentTranslationStore()
    const requestEpoch = store.beginView('en-US')
    await store.resolveOwner([source], 'en-US', requestEpoch)

    await vi.advanceTimersByTimeAsync(180000)

    expect(store.pendingPollCount).toBe(0)
    expect(store.getEntry(source, 'en-US')).toMatchObject({
      state: 'failed',
      errorCode: 'POLL_TIMEOUT',
    })
  })
})
