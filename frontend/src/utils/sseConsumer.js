/**
 * SSE 流消费者工具
 *
 * 封装 fetch + ReadableStream 的 SSE 解析逻辑，
 * 统一处理 buffer 拼接、行分割、JSON 解析、401 检测。
 */

/**
 * 消费 SSE 流式响应
 *
 * @param {Response} response - fetch 返回的 Response 对象（未调用 .json()）
 * @param {function} onMessage - 收到 SSE 事件时的回调 (data: object) => void
 * @param {object} [options] - 可选配置
 * @param {AbortSignal} [options.signal] - 用于取消读取的 AbortSignal
 * @param {number} [options.heartbeatTimeout] - 心跳超时（ms），0 表示不检查
 * @param {function} [options.onHeartbeat] - 收到心跳时的回调
 * @param {function} [options.on401] - 收到 401 时的回调
 * @returns {Promise<void>}
 */
export async function consumeSSEStream(response, onMessage, options = {}) {
  const {
    signal = null,
    heartbeatTimeout = 0,
    onHeartbeat = null,
    on401 = null,
  } = options

  // 检查 HTTP 状态
  if (!response.ok) {
    if (response.status === 401 && on401) {
      on401()
      return
    }
    const errorText = await response.text().catch(() => '')
    throw new Error(`HTTP error ${response.status}: ${errorText}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let lastDataTime = Date.now()
  let cancelled = false
  let timedOut = false

  const handleAbort = () => {
    cancelled = true
    void reader.cancel()
  }
  if (signal?.aborted) {
    handleAbort()
  } else {
    signal?.addEventListener('abort', handleAbort, { once: true })
  }

  // 心跳超时检查定时器
  let heartbeatTimer = null
  if (heartbeatTimeout > 0) {
    heartbeatTimer = setInterval(() => {
      if (!cancelled && Date.now() - lastDataTime > heartbeatTimeout) {
        console.error('[SSE] Heartbeat timeout')
        timedOut = true
        cancelled = true
        void reader.cancel()
      }
    }, heartbeatTimeout / 2)
  }

  try {
    while (!cancelled) {
      // signal 取消检查
      if (signal?.aborted) {
        reader.cancel()
        break
      }

      let readResult
      try {
        readResult = await reader.read()
      } catch (readError) {
        // reader.cancel() 触发的异常（心跳超时或外部取消）
        if (timedOut) throw new Error('连接超时（无心跳响应），请重试')
        if (signal?.aborted) break
        throw readError
      }
      const { done, value } = readResult
      if (done) {
        if (timedOut) throw new Error('连接超时（无心跳响应），请重试')
        break
      }
      if (signal?.aborted) break

      lastDataTime = Date.now()
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6))
            if (data.type === 'heartbeat') {
              onHeartbeat?.()
              continue
            }
            onMessage(data)
          } catch (e) {
            console.error('[SSE] Parse error:', e, line)
          }
        }
      }
    }

    // 处理缓冲区剩余数据
    if (buffer.trim().startsWith('data: ')) {
      try {
        const data = JSON.parse(buffer.trim().substring(6))
        onMessage(data)
      } catch (e) {
        console.error('[SSE] Parse remaining error:', e)
      }
    }
  } finally {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
    }
    signal?.removeEventListener('abort', handleAbort)
  }
}
