import axios from 'axios'

// 是否启用 mock（VITE_USE_MOCK=true 时使用本地数据，不调后端）
export const useMock = (import.meta.env.VITE_USE_MOCK ?? 'true') === 'true'

// 后端 Base URL（空字符串走 vite 代理 /api）
const baseURL = import.meta.env.VITE_API_BASE_URL || ''

export const http = axios.create({
  baseURL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// mock 模式下统一延迟，模拟网络
export function mockDelay(ms = 200) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// 简易错误归一化
export function unwrapError(err) {
  return err?.response?.data?.detail || err?.message || '请求失败'
}
