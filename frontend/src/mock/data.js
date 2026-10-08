// mock 数据：对齐 backend/scripts/init_db.py 的 5 个样例话题
// 字段契约对齐 backend/app/schemas/*.py

export const topics = [
  {
    id: 1,
    title: 'AGI 是否会在 10 年内取代大部分知识工作者？',
    expert_count: 4,
    status: 'ongoing',
    expert_role_count: 4,
    has_summary: false,
    updated_at: '2026-10-08T08:12:00Z',
  },
  {
    id: 2,
    title: '远程办公 vs 回归办公室：后疫情时代的工作范式之争',
    expert_count: 4,
    status: 'archived',
    expert_role_count: 4,
    has_summary: true,
    updated_at: '2026-10-07T15:30:00Z',
  },
  {
    id: 3,
    title: '电动车的"全面替代燃油车"是否被高估？',
    expert_count: 4,
    status: 'setup',
    expert_role_count: 4,
    has_summary: false,
    updated_at: '2026-10-08T09:01:00Z',
  },
  {
    id: 4,
    title: '大学教育在 AI 时代是否还值得？',
    expert_count: 4,
    status: 'ongoing',
    expert_role_count: 4,
    has_summary: false,
    updated_at: '2026-10-08T09:05:00Z',
  },
  {
    id: 5,
    title: '元宇宙是否只是一场资本泡沫？',
    expert_count: 4,
    status: 'archived',
    expert_role_count: 4,
    has_summary: true,
    updated_at: '2026-10-06T11:20:00Z',
  },
]

// 嘉宾档案（对齐 init_db.py）
const guestsByTopic = {
  1: [
    { id: 1, role: 'moderator', name: '林清远', title: '资深科技评论员', stance: '中立主持人', color: '#2A6F97', sort_order: 0 },
    { id: 2, role: 'expert', name: '陈思齐', title: 'AI 实验室首席研究员', stance: '乐观派', color: '#E63946', sort_order: 1 },
    { id: 3, role: 'expert', name: '王敏行', title: '劳动经济学教授', stance: '谨慎派', color: '#F4A261', sort_order: 2 },
    { id: 4, role: 'expert', name: 'Daniel Carter', title: '硅谷连续创业者', stance: '激进派', color: '#264653', sort_order: 3 },
    { id: 5, role: 'expert', name: '周雅琴', title: '认知科学教授', stance: '悲观派', color: '#6A4C93', sort_order: 4 },
  ],
  2: [
    { id: 6, role: 'moderator', name: '苏明', title: '组织行为学顾问', stance: '中立主持人', color: '#457B9D', sort_order: 0 },
    { id: 7, role: 'expert', name: '张力行', title: 'HR SaaS 创始人', stance: '远程派', color: '#E76F51', sort_order: 1 },
    { id: 8, role: 'expert', name: 'Lisa Chen', title: '金融科技公司 COO', stance: '混合派', color: '#2A9D8F', sort_order: 2 },
    { id: 9, role: 'expert', name: '黄志远', title: '传统制造业 CEO', stance: '回归派', color: '#E9C46A', sort_order: 3 },
    { id: 10, role: 'expert', name: 'Marcus Wright', title: '远程协作工具 PM', stance: '远程派', color: '#6D597A', sort_order: 4 },
  ],
  4: [
    { id: 16, role: 'moderator', name: '宋怀瑾', title: '教育社会学教授', stance: '中立主持人', color: '#1D3557', sort_order: 0 },
    { id: 17, role: 'expert', name: '顾长青', title: '计算机系主任', stance: '改革派', color: '#E63946', sort_order: 1 },
    { id: 18, role: 'expert', name: '苏菲·拉弗勒', title: '终身学习平台创始人', stance: '替代派', color: '#F4A261', sort_order: 2 },
    { id: 19, role: 'expert', name: '罗伯特·海恩', title: '文学院教授', stance: '传统派', color: '#6A4C93', sort_order: 3 },
    { id: 20, role: 'expert', name: '林芷若', title: '职业教育研究学者', stance: '融合派', color: '#2A9D8F', sort_order: 4 },
  ],
  5: [
    { id: 21, role: 'moderator', name: '伊藤健', title: '科技投资评论员', stance: '中立主持人', color: '#4A4E69', sort_order: 0 },
    { id: 22, role: 'expert', name: '张若虚', title: 'XR 设备创业公司 CEO', stance: '长期派', color: '#9A8C98', sort_order: 1 },
    { id: 23, role: 'expert', name: '安娜·诺维科娃', title: '风险投资合伙人', stance: '泡沫派', color: '#C9ADA7', sort_order: 2 },
    { id: 24, role: 'expert', name: '程慕白', title: '图形渲染技术专家', stance: '技术派', color: '#22223B', sort_order: 3 },
    { id: 25, role: 'expert', name: '大卫·克拉克', title: '消费电子资深记者', stance: '怀疑派', color: '#F2E9E4', sort_order: 4 },
  ],
}

// 已归档话题的现场发言（话题 2 与 5）
const transcriptsByTopic = {
  2: [
    { id: 1, turn_index: 1, guest_id: 6, guest_name: '苏明', guest_color: '#457B9D', speech_type: 'opening', content: '欢迎来到这场关于工作范式的圆桌。我们要回答一个问题：后疫情时代，远程、混合还是回归，哪种才是真正的答案？' },
    { id: 2, turn_index: 2, guest_id: 7, guest_name: '张力行', guest_color: '#E76F51', speech_type: 'grab', content: '我先抛观点：async-first 是未来。我们的员工 productivity 在远程后提升了 23%，人才池也扩张到全国。' },
    { id: 3, turn_index: 3, guest_id: 9, guest_name: '黄志远', guest_color: '#E9C46A', speech_type: 'rebute', content: '你的 23% 来自哪？我猜是知识工作者。但文化沉淀、新人融入、创新偶然性，这些不能用季度 KPI 衡量。' },
    { id: 4, turn_index: 4, guest_id: 8, guest_name: 'Lisa Chen', guest_color: '#2A9D8F', speech_type: 'supplement', content: '我同意双方各对一半。我们实践 3+2 混合：周二周四周现场，其余远程。关键不是地点，而是会议密度与异步文档质量。' },
    { id: 5, turn_index: 5, guest_id: 10, guest_name: 'Marcus Wright', guest_color: '#6D597A', speech_type: 'grab', content: '工具已经足够支撑 async。问题不在工具，而在管理者的信任传递能力——这是黄总真正担心的。' },
    { id: 6, turn_index: 6, guest_id: 6, guest_name: '苏明', guest_color: '#457B9D', speech_type: 'summary', content: '我们形成了共识：混合模式是当前最优解。但分歧仍在——管理者能否在缺乏物理在场时维持信任。这是下一场讨论的议题。' },
  ],
  5: [
    { id: 7, turn_index: 1, guest_id: 21, guest_name: '伊藤健', guest_color: '#4A4E69', speech_type: 'opening', content: '元宇宙这个词在过去 3 年从天堂到地狱。今天我们要拆解：哪些是真趋势，哪些是泡沫。' },
    { id: 8, turn_index: 2, guest_id: 22, guest_name: '张若虚', guest_color: '#9A8C98', speech_type: 'grab', content: '硬件正在逼近拐点。当头显低于 100g、续航 8 小时，消费市场会启动。' },
    { id: 9, turn_index: 3, guest_id: 23, guest_name: '安娜·诺维科娃', guest_color: '#C9ADA7', speech_type: 'rebute', content: '硬件拐点不等于商业拐点。问题是没有 killer app——估值却已经透支了 10 年。' },
    { id: 10, turn_index: 4, guest_id: 24, guest_name: '程慕白', guest_color: '#22223B', speech_type: 'supplement', content: '我同意安娜的财务判断，但从技术底层看，实时渲染与神经渲染的突破是真实的，不应被资本炒作掩盖。' },
    { id: 11, turn_index: 5, guest_id: 25, guest_name: '大卫·克拉克', guest_color: '#F2E9E4', speech_type: 'grab', content: '我跑 CES 15 年，看到的永远是 demo。用户最终买的是「解决问题」，不是「沉浸感」本身。' },
    { id: 12, turn_index: 6, guest_id: 21, guest_name: '伊藤健', guest_color: '#4A4E69', speech_type: 'summary', content: '我们的结论：泡沫阶段已过，但技术基建仍在生长。这是一场「泡沫化的真实趋势」。' },
  ],
}

const insightsByTopic = {
  2: [
    { id: 1, type: 'consensus', summary: '混合办公是当前最优解，3+2 是常见配置', strength: 'strong', version: 1, is_final: true, created_at: '2026-10-07T15:25:00Z', updated_at: '2026-10-07T15:30:00Z' },
    { id: 2, type: 'divergence', summary: '管理者在场与信任传递是否可解耦', strength: 'medium', version: 1, is_final: true, created_at: '2026-10-07T15:25:00Z', updated_at: '2026-10-07T15:30:00Z' },
  ],
  5: [
    { id: 3, type: 'consensus', summary: 'XR 与图形渲染是有价值的技术底座', strength: 'medium', version: 1, is_final: true, created_at: '2026-10-06T11:15:00Z', updated_at: '2026-10-06T11:20:00Z' },
    { id: 4, type: 'divergence', summary: '消费级 killer app 是否存在', strength: 'strong', version: 1, is_final: true, created_at: '2026-10-06T11:15:00Z', updated_at: '2026-10-06T11:20:00Z' },
  ],
}

const summaryByTopic = {
  2: '本场讨论未能形成单一答案。远程派以 productivity 数据与人才池扩张为据，回归派强调文化沉淀与创新偶然性。最终共识：混合模式为当前最优解，但需以「会议密度」与「异步文档质量」为 KPI 进行校验。分歧在于管理者是否能在缺乏物理在场时维持信任传递。',
  5: '讨论揭示了「元宇宙」概念的多义性。共识：XR 硬件与图形渲染是有价值的技术底座。分歧：消费级 use case 是否存在，以及当前估值是否透支了 10 年预期。最终判断：资本炒作阶段已过，但技术基建仍在生长——这是一场「泡沫化的真实趋势」。',
}

export function getTopics() {
  return topics
}

export function getTopic(id) {
  const t = topics.find((x) => x.id === Number(id))
  if (!t) return null
  return { ...t, guests: guestsByTopic[t.id] || [], summary: summaryByTopic[t.id] || null }
}

export function getRoster(topicId) {
  const t = topics.find((x) => x.id === Number(topicId))
  return {
    topic_id: Number(topicId),
    guests: guestsByTopic[Number(topicId)] || [],
    is_confirmed: !!t && t.status !== 'draft' && t.status !== 'setup',
  }
}

export function getTranscripts(topicId) {
  return transcriptsByTopic[Number(topicId)] || []
}

export function getInsights(topicId) {
  return insightsByTopic[Number(topicId)] || []
}
