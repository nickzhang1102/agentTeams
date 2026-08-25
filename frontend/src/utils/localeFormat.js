export function formatLocaleDateTime(value, locale, options = {}) {
  if (!value) return ''
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)

  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    ...options,
  }).format(date)
}

export function formatLocaleNumber(value, locale, options = {}) {
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value ?? '')
  return new Intl.NumberFormat(locale, options).format(number)
}
