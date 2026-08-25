import { ref } from 'vue'
import { defineStore } from 'pinia'
import { isSupportedLocale } from '@/locales'
import api from '@/utils/api'

export const MAX_TRANSLATION_SOURCES = 20
export const TRANSLATION_POLL_INTERVAL_MS = 2000
export const TRANSLATION_POLL_WINDOW_MS = 3 * 60 * 1000

export const TRANSLATION_SOURCE_TYPES = [
  'message',
  'leader_agent_result',
  'leader_final_report',
]

export const TRANSLATION_VIEW_STATES = [
  'original',
  'pending',
  'ready',
  'failed',
  'unavailable',
]

export function isContentSourceRef(source) {
  return Boolean(
    source
    && TRANSLATION_SOURCE_TYPES.includes(source.type)
    && Number.isInteger(source.id)
    && source.id > 0
  )
}

export function contentSourceKey(source, targetLocale) {
  if (!isContentSourceRef(source) || !isSupportedLocale(targetLocale)) {
    return null
  }
  return `${source.type}:${source.id}:${targetLocale}`
}

export function applyTranslationOverlay(sourceType, source, payload) {
  if (!source || typeof source !== 'object' || !payload || typeof payload !== 'object') {
    return source
  }

  if (sourceType === 'message') {
    return typeof payload.text === 'string'
      ? { ...source, content: payload.text }
      : source
  }

  if (sourceType === 'leader_agent_result') {
    return copyPayloadFields(source, payload, ['content', 'summary', 'structured_report'])
  }

  if (sourceType === 'leader_final_report') {
    const translated = copyPayloadFields(source, payload, ['report', 'structured_report'])
    if (Object.prototype.hasOwnProperty.call(payload, 'executive_summary')) {
      translated.executive_summary = payload.executive_summary
      translated.summary = payload.executive_summary
    }
    return translated
  }

  return source
}

function copyPayloadFields(source, payload, fields) {
  const result = { ...source }
  fields.forEach(field => {
    if (Object.prototype.hasOwnProperty.call(payload, field)) {
      result[field] = payload[field]
    }
  })
  return result
}

export const useContentTranslationStore = defineStore('contentTranslation', () => {
  const entries = ref({})
  const activeLocale = ref(null)
  const epoch = ref(0)
  const pendingPollCount = ref(0)
  const pendingPollers = new Map()

  function beginView(targetLocale) {
    if (!isSupportedLocale(targetLocale)) {
      throw new Error('UNSUPPORTED_LOCALE')
    }
    stopAllPollers()
    activeLocale.value = targetLocale
    epoch.value += 1
    return epoch.value
  }

  function ensureEntry(source, targetLocale = activeLocale.value, requestEpoch = epoch.value) {
    const key = contentSourceKey(source, targetLocale)
    if (!key || !isCurrentView(targetLocale, requestEpoch)) {
      return null
    }

    const existing = entries.value[key]
    const next = existing?.state === 'ready'
      ? { ...existing, epoch: requestEpoch }
      : {
          source: { type: source.type, id: source.id },
          targetLocale,
          state: 'original',
          epoch: requestEpoch,
        }
    entries.value = { ...entries.value, [key]: next }
    return next
  }

  function setEntryState(
    source,
    targetLocale,
    state,
    details = {},
    requestEpoch = epoch.value,
  ) {
    const key = contentSourceKey(source, targetLocale)
    if (
      !key
      || !TRANSLATION_VIEW_STATES.includes(state)
      || !isCurrentView(targetLocale, requestEpoch)
    ) {
      return false
    }

    entries.value = {
      ...entries.value,
      [key]: {
        source: { type: source.type, id: source.id },
        targetLocale,
        state,
        ...details,
        epoch: requestEpoch,
      },
    }
    return true
  }

  function getEntry(source, targetLocale = activeLocale.value) {
    const key = contentSourceKey(source, targetLocale)
    return key ? entries.value[key] || null : null
  }

  function getPayload(source, targetLocale = activeLocale.value) {
    const entry = getEntry(source, targetLocale)
    if (
      entry?.state !== 'ready'
      || entry.epoch !== epoch.value
      || entry.targetLocale !== activeLocale.value
    ) {
      return null
    }
    return entry.payload || null
  }

  async function resolveOwner(sources, targetLocale, requestEpoch = epoch.value) {
    if (!isCurrentView(targetLocale, requestEpoch)) {
      return
    }

    const unresolved = uniqueSources(sources).filter(source => {
      const entry = ensureEntry(source, targetLocale, requestEpoch)
      return entry?.state !== 'ready'
    })

    for (let index = 0; index < unresolved.length; index += MAX_TRANSLATION_SOURCES) {
      if (!isCurrentView(targetLocale, requestEpoch)) {
        return
      }
      const batch = unresolved.slice(index, index + MAX_TRANSLATION_SOURCES)
      try {
        const response = await api.post('/api/content-translations/resolve', {
          target_locale: targetLocale,
          sources: batch,
        }, { suppressGlobalError: true })
        applyResolveItems(response.data?.items || [], targetLocale, requestEpoch)
      } catch (error) {
        const errorCode = extractTranslationErrorCode(error)
        batch.forEach(source => {
          setEntryState(source, targetLocale, 'failed', { errorCode }, requestEpoch)
        })
      }
    }
  }

  async function lookupShare(
    sources,
    targetLocale,
    shareToken,
    requestEpoch = epoch.value,
  ) {
    if (!isCurrentView(targetLocale, requestEpoch)) {
      return
    }

    const unresolved = uniqueSources(sources).filter(source => {
      const entry = ensureEntry(source, targetLocale, requestEpoch)
      return entry?.state !== 'ready'
    })

    for (let index = 0; index < unresolved.length; index += MAX_TRANSLATION_SOURCES) {
      if (!isCurrentView(targetLocale, requestEpoch)) {
        return
      }
      const batch = unresolved.slice(index, index + MAX_TRANSLATION_SOURCES)
      try {
        const response = await api.post(
          `/api/content-translations/share/${encodeURIComponent(shareToken)}/lookup`,
          {
            target_locale: targetLocale,
            sources: batch,
          },
          { suppressGlobalError: true },
        )
        applyShareLookup(response.data, batch, targetLocale, requestEpoch)
      } catch (error) {
        const errorCode = extractTranslationErrorCode(error)
        batch.forEach(source => {
          setEntryState(source, targetLocale, 'unavailable', { errorCode }, requestEpoch)
        })
      }
    }
  }

  function applyShareLookup(data, requestedSources, targetLocale, requestEpoch) {
    const readyKeys = new Set()
    ;(data?.items || []).forEach(item => {
      const source = item?.source
      if (item?.status !== 'ready' || !isContentSourceRef(source)) {
        return
      }
      if (setEntryState(source, targetLocale, 'ready', responseDetails(item), requestEpoch)) {
        readyKeys.add(`${source.type}:${source.id}`)
      }
    })

    requestedSources.forEach(source => {
      if (!readyKeys.has(`${source.type}:${source.id}`)) {
        setEntryState(source, targetLocale, 'unavailable', {}, requestEpoch)
      }
    })
  }

  function applyResolveItems(items, targetLocale, requestEpoch) {
    items.forEach(item => {
      const source = item?.source
      if (!isContentSourceRef(source)) {
        return
      }
      const details = responseDetails(item)
      if (item.status === 'ready') {
        setEntryState(source, targetLocale, 'ready', details, requestEpoch)
      } else if (item.status === 'pending' && Number.isInteger(item.translation_id)) {
        if (setEntryState(source, targetLocale, 'pending', details, requestEpoch)) {
          startPolling(source, targetLocale, item.translation_id, requestEpoch)
        }
      } else {
        setEntryState(source, targetLocale, 'failed', details, requestEpoch)
      }
    })
  }

  function startPolling(source, targetLocale, translationId, requestEpoch) {
    if (pendingPollers.has(translationId)) {
      return
    }

    const poller = {
      source,
      targetLocale,
      translationId,
      requestEpoch,
      activeElapsed: 0,
      timer: null,
    }
    pendingPollers.set(translationId, poller)
    pendingPollCount.value = pendingPollers.size
    schedulePoll(poller)
  }

  function schedulePoll(poller) {
    poller.timer = setTimeout(() => pollTranslation(poller), TRANSLATION_POLL_INTERVAL_MS)
  }

  async function pollTranslation(poller) {
    if (!pendingPollers.has(poller.translationId)) {
      return
    }
    if (!isCurrentView(poller.targetLocale, poller.requestEpoch)) {
      stopPoller(poller.translationId)
      return
    }
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
      schedulePoll(poller)
      return
    }

    poller.activeElapsed += TRANSLATION_POLL_INTERVAL_MS
    if (poller.activeElapsed >= TRANSLATION_POLL_WINDOW_MS) {
      setEntryState(poller.source, poller.targetLocale, 'failed', {
        errorCode: 'POLL_TIMEOUT',
      }, poller.requestEpoch)
      stopPoller(poller.translationId)
      return
    }

    try {
      const response = await api.get(`/api/content-translations/${poller.translationId}`, {
        suppressGlobalError: true,
      })
      const item = response.data || {}
      if (item.status === 'ready') {
        setEntryState(
          poller.source,
          poller.targetLocale,
          'ready',
          responseDetails(item),
          poller.requestEpoch,
        )
        stopPoller(poller.translationId)
        return
      }
      if (item.status === 'failed') {
        setEntryState(
          poller.source,
          poller.targetLocale,
          'failed',
          responseDetails(item),
          poller.requestEpoch,
        )
        stopPoller(poller.translationId)
        return
      }
    } catch (error) {
      const status = error.response?.status
      if (status === 403 || status === 404 || status === 409) {
        setEntryState(poller.source, poller.targetLocale, 'failed', {
          errorCode: extractTranslationErrorCode(error),
        }, poller.requestEpoch)
        stopPoller(poller.translationId)
        return
      }
    }
    schedulePoll(poller)
  }

  function stopPoller(translationId) {
    const poller = pendingPollers.get(translationId)
    if (poller?.timer) {
      clearTimeout(poller.timer)
    }
    pendingPollers.delete(translationId)
    pendingPollCount.value = pendingPollers.size
  }

  function stopAllPollers() {
    Array.from(pendingPollers.keys()).forEach(stopPoller)
  }

  function invalidateView({ clearEntries = false } = {}) {
    stopAllPollers()
    epoch.value += 1
    activeLocale.value = null
    if (clearEntries) {
      entries.value = {}
    }
  }

  function isCurrentView(targetLocale, requestEpoch) {
    return targetLocale === activeLocale.value && requestEpoch === epoch.value
  }

  function uniqueSources(sources) {
    const seen = new Set()
    return (sources || []).filter(source => {
      const key = isContentSourceRef(source) ? `${source.type}:${source.id}` : null
      if (!key || seen.has(key)) {
        return false
      }
      seen.add(key)
      return true
    })
  }

  function responseDetails(item) {
    return {
      translationId: item.translation_id ?? item.translationId,
      sourceHash: item.source_hash,
      sourceLocale: item.source_locale,
      payload: item.payload || null,
      errorCode: item.error_code || null,
    }
  }

  function extractTranslationErrorCode(error) {
    return error.response?.data?.detail?.code
      || error.response?.data?.code
      || 'TRANSLATION_REQUEST_FAILED'
  }

  return {
    entries,
    activeLocale,
    epoch,
    pendingPollCount,
    beginView,
    ensureEntry,
    setEntryState,
    getEntry,
    getPayload,
    resolveOwner,
    lookupShare,
    invalidateView,
    stopAllPollers,
  }
})
