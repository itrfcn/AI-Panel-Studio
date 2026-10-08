// 共识与分歧契约 — 对接后端 /api/topics/:id/insights
import { http, useMock, mockDelay } from './http'
import * as mock from '../mock/data'

// GET /api/topics/:id/insights — 列出共识/分歧
export async function listInsights(topicId, { type_filter, final_only } = {}) {
  if (useMock) {
    await mockDelay()
    let items = mock.getInsights(topicId)
    if (type_filter) items = items.filter((i) => i.type === type_filter)
    if (final_only) items = items.filter((i) => i.is_final)
    return items
  }
  const { data } = await http.get(`/api/topics/${topicId}/insights`, {
    params: { type_filter, final_only },
  })
  return data
}

// GET /api/topics/:id/insights/:insightId — 单条详情（含关联）
export async function getInsight(topicId, insightId) {
  if (useMock) {
    await mockDelay()
    const items = mock.getInsights(topicId)
    const found = items.find((i) => i.id === Number(insightId))
    if (!found) throw new Error('Insight 不存在')
    return { ...found, guest_ids: [], transcript_ids: [] }
  }
  const { data } = await http.get(`/api/topics/${topicId}/insights/${insightId}`)
  return data
}
