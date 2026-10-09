// 流式契约 — 对接后端 /api/topics/:id/stream (SSE)
// SSE 在前端用 EventSource；mock 模式下回放样例发言以模拟"实时"效果
import { useMock } from './http'
import * as mock from '../mock/data'

function buildSseUrl(topicId) {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  return `${base}/api/topics/${topicId}/stream`
}

// 监听讨论流（SSE）
// 回调：onTranscript / onState / onInsight / onSystem / onEnd / onError
export function subscribeStream(topicId, handlers = {}) {
  if (useMock) {
    return mockReplayStream(topicId, handlers)
  }
  const es = new EventSource(buildSseUrl(topicId))

  es.addEventListener('transcript', (e) => {
    try { handlers.onTranscript?.(JSON.parse(e.data)) } catch {}
  })
  es.addEventListener('state', (e) => {
    try { handlers.onState?.(JSON.parse(e.data)) } catch {}
  })
  es.addEventListener('insight', (e) => {
    try { handlers.onInsight?.(JSON.parse(e.data)) } catch {}
  })
  es.addEventListener('system', (e) => {
    try { handlers.onSystem?.(JSON.parse(e.data)) } catch {}
  })
  es.addEventListener('heartbeat', () => {})
  es.addEventListener('end', () => handlers.onEnd?.())
  es.onerror = (err) => handlers.onError?.(err)

  return () => es.close()
}

// mock：把样例 transcript 逐条以时间间隔推送，模拟实时流
function mockReplayStream(topicId, handlers) {
  const transcripts = mock.getTranscripts(topicId)
  const insights = mock.getInsights(topicId)
  let stopped = false
  let timer = null

  handlers.onSystem?.({ message: 'mock stream started' })

  let i = 0
  const pushNext = () => {
    if (stopped) return
    if (i >= transcripts.length) {
      // 流结束后推送 insight
      insights.forEach((ins) => {
        handlers.onInsight?.({
          topic_id: Number(topicId),
          insight_id: ins.id,
          action: 'create',
          type: ins.type,
          summary: ins.summary,
          strength: ins.strength,
          version: ins.version,
          is_final: true,
        })
      })
      handlers.onEnd?.()
      return
    }
    const t = transcripts[i]
    handlers.onTranscript?.({
      topic_id: Number(topicId),
      transcript_id: t.id,
      guest_id: t.guest_id,
      guest_name: t.guest_name,
      guest_color: t.guest_color,
      turn_index: t.turn_index,
      speech_type: t.speech_type,
      status: 'done',
      content: t.content,
    })
    i++
    timer = setTimeout(pushNext, 1200)
  }
  timer = setTimeout(pushNext, 500)

  return () => {
    stopped = true
    if (timer) clearTimeout(timer)
  }
}

// POST /api/topics/:id/stream/cancel — 强制中断讨论
export async function cancelDiscussion(topicId) {
  if (useMock) {
    const { mockDelay } = await import('./http')
    await mockDelay()
    return { topic_id: Number(topicId), cancelled: true, status: 'cancelled' }
  }
  const { http } = await import('./http')
  const { data } = await http.post(`/api/topics/${topicId}/stream/cancel`)
  return data
}

// GET /api/topics/:id/stream/replay — 回放 archived 讨论
export async function replayDiscussion(topicId) {
  if (useMock) {
    const { http, mockDelay } = await import('./http')
    await mockDelay()
    return {
      topic_id: Number(topicId),
      transcripts: mock.getTranscripts(topicId),
      insights: mock.getInsights(topicId),
    }
  }
  const { http } = await import('./http')
  const { data } = await http.get(`/api/topics/${topicId}/stream/replay`)
  return data
}
