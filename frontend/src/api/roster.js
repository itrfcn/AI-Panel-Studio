// 阵容契约 — 对接后端 /api/topics/:id/roster
import { http, useMock, mockDelay, unwrapError } from './http'
import * as mock from '../mock/data'

// POST /api/topics/:id/roster/generate — LLM 生成阵容
export async function generateRoster(topicId, { expert_count } = {}) {
  if (useMock) {
    await mockDelay(800) // 模拟 LLM 生成耗时
    return mock.getRoster(topicId)
  }
  try {
    const { data } = await http.post(
      `/api/topics/${topicId}/roster/generate`,
      {
        topic_id: topicId,
        expert_count,
      },
      // LLM 生成阵容耗时较长（实测 30-60s），叠加上游过载重试最坏可达 ~3 分钟
      { timeout: 200000 },
    )
    return data
  } catch (err) {
    throw new Error(unwrapError(err))
  }
}

// GET /api/topics/:id/roster — 获取阵容
export async function getRoster(topicId) {
  if (useMock) {
    await mockDelay()
    return mock.getRoster(topicId)
  }
  const { data } = await http.get(`/api/topics/${topicId}/roster`)
  return data
}

// POST /api/topics/:id/roster/confirm — 确认阵容 → setup
export async function confirmRoster(topicId) {
  if (useMock) {
    await mockDelay(300)
    return { ...mock.getRoster(topicId), is_confirmed: true }
  }
  try {
    const { data } = await http.post(`/api/topics/${topicId}/roster/confirm`)
    return data
  } catch (err) {
    throw new Error(unwrapError(err))
  }
}
