import { describe, expect, it, vi, afterEach } from 'vitest'
import { copyToClipboard } from './clipboard'

// happy-dom 未实现 document.execCommand，先定义为可配置属性再 spy
function stubExecCommand(returnValue) {
  Object.defineProperty(document, 'execCommand', {
    value: vi.fn(() => returnValue),
    configurable: true,
    writable: true
  })
  return document.execCommand
}

describe('copyToClipboard', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('uses the modern Clipboard API in a secure context', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })

    await expect(copyToClipboard('secret')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('secret')
  })

  it('falls back to execCommand when the Clipboard API is unavailable', async () => {
    vi.stubGlobal('navigator', {})
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true })

    const execCommand = stubExecCommand(true)
    const appendSpy = vi.spyOn(document.body, 'appendChild')

    await expect(copyToClipboard('fallback-text')).resolves.toBe(true)
    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(appendSpy).toHaveBeenCalledTimes(1)
    // 临时 textarea 被清理
    expect(document.body.querySelectorAll('textarea')).toHaveLength(0)
  })

  it('falls back to execCommand when the Clipboard API rejects', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('NotAllowedError'))
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })

    const execCommand = stubExecCommand(true)
    await expect(copyToClipboard('retry-text')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('retry-text')
    expect(execCommand).toHaveBeenCalledWith('copy')
  })

  it('reports failure when execCommand returns false', async () => {
    vi.stubGlobal('navigator', {})
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true })

    stubExecCommand(false)
    await expect(copyToClipboard('nope')).resolves.toBe(false)
    expect(document.body.querySelectorAll('textarea')).toHaveLength(0)
  })
})
