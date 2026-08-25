import { isSupportedLocale } from '@/locales'

export function collectLeaderTranslationSources({
  messages = [],
  agentResults = [],
  finalReport = null,
  targetLocale,
}) {
  if (!isSupportedLocale(targetLocale)) {
    return []
  }

  const sources = []
  messages.forEach(message => {
    const rawContent = message?.rawContent ?? message?.content
    const messageType = message?.type || message?.message_type
    if (
      isEligibleSource(message, targetLocale)
      && messageType !== 'answer'
      && hasMessageText(rawContent)
    ) {
      sources.push({ type: 'message', id: message.id })
    }
  })

  agentResults.forEach(result => {
    if (isEligibleSource(result, targetLocale) && hasVisibleText({
      content: result.content,
      summary: result.summary,
      structured_report: result.structured_report,
    })) {
      sources.push({ type: 'leader_agent_result', id: result.id })
    }
  })

  if (
    isEligibleSource(finalReport, targetLocale)
    && hasVisibleText({
      report: finalReport.report,
      executive_summary: finalReport.executive_summary || finalReport.summary,
      structured_report: finalReport.structured_report,
    })
  ) {
    sources.push({ type: 'leader_final_report', id: finalReport.id })
  }

  const seen = new Set()
  return sources.filter(source => {
    const key = `${source.type}:${source.id}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function isEligibleSource(source, targetLocale) {
  return Boolean(
    source
    && Number.isInteger(source.id)
    && source.id > 0
    && isSupportedLocale(source.content_locale)
    && source.content_locale !== targetLocale
  )
}

function hasMessageText(content) {
  return (typeof content === 'string' && content.trim().length > 0)
    || (typeof content?.text === 'string' && content.text.trim().length > 0)
}

function hasVisibleText(value) {
  if (typeof value === 'string') {
    return value.trim().length > 0
  }
  if (Array.isArray(value)) {
    return value.some(hasVisibleText)
  }
  if (value && typeof value === 'object') {
    return Object.values(value).some(hasVisibleText)
  }
  return false
}
