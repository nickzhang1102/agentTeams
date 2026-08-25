import { describe, expect, it } from 'vitest'
import zhCN from '@/locales/zh-CN/admin.js'
import enUS from '@/locales/en-US/admin.js'
import { formatLocaleDateTime, formatLocaleNumber } from '@/utils/localeFormat.js'

function leafKeys(value, prefix = '') {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return child && typeof child === 'object' ? leafKeys(child, path) : [path]
  })
}

describe('admin locale resources', () => {
  it('keeps zh-CN and en-US resource shapes symmetric', () => {
    expect(leafKeys(enUS)).toEqual(leafKeys(zhCN))
  })

  it('formats dates and numbers with the selected locale', () => {
    const value = new Date('2026-08-02T08:05:00Z')

    expect(formatLocaleDateTime(value, 'en-US')).not.toBe(formatLocaleDateTime(value, 'zh-CN'))
    expect(formatLocaleNumber(1234567.89, 'en-US')).toBe('1,234,567.89')
  })
})
