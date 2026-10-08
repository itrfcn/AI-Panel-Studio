// 讨论契约 — 对接后端 /api/topics
import { http, useMock, mockDelay, unwrapError } from './http'
import * as mock from '../mock/data'

// GET /api/topics — 首页讨论列表
export async function listTopics(params = {}) {
  if (useMock) {
    await mockDelay()
    const { page = 1, page_size = 20, status_filter } = params
    let items = mock.getTopics()
    if (status_filter) items = items.filter((t) => t.status === status_filter)
    const total = items.length
    const start = (page - 1) * page_size
    return { items: items.slice(start, start + page_size), total, page, page_size }
  }
  const { data } = await http.get('/api/topics', { params })
  return data
}

// POST /api/topics — 创建讨论（draft）
export async function createTopic({ title, expert_count = 4 }) {
  if (useMock) {
    await mockDelay(300)
    const id = Math.floor(Math.random() * 1000) + 100
    return {
      id,
      title,
      expert_count,
      status: 'draft',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      started_at: null,
      ended_at: null,
      summary: null,
      guests: [],
    }
  }
  const { data } = await http.post('/api/topics', { title, expert_count })
  return data
}

// GET /api/topics/:id — 讨论详情（含阵容）
export async function getTopic(id) {
  if (useMock) {
    await mockDelay()
    const t = mock.getTopic(id)
    if (!t) throw new Error('讨论不存在')
    return t
  }
  const { data } = await http.get(`/api/topics/${id}`)
  return data
}

// PATCH /api/topics/:id — 更新状态/总结
export async function updateTopic(id, { status, summary }) {
  if (useMock) {
    await mockDelay(200)
    return { id, status, summary, updated_at: new Date().toISOString() }
  }
  const { data } = await http.patch(`/api/topics/${id}`, { status, summary })
  return data
}

// POST /api/topics/:id/start — 触发讨论 → ongoing
export async function startDiscussion(id) {
  if (useMock) {
    await mockDelay(300)
    return { id, status: 'ongoing', started_at: new Date().toISOString() }
  }
  try {
    const { data } = await http.post(`/api/topics/${id}/start`)
    return data
  } catch (err) {
    throw new Error(unwrapError(err))
  }
}
