<script setup>
// 嘉宾演播厅组件 — 编排 主持人 + 4 位嘉宾的独立小窗 + 现场 Transcript + 共识/分歧区
// PRD §4.3 演播厅模式 + §4.4 响应式布局（各区域独立滚动）
import { computed } from 'vue'
import GuestPanel from './GuestPanel.vue'
import Transcript from './Transcript.vue'
import InsightPanel from './InsightPanel.vue'

const props = defineProps({
  topic: { type: Object, required: true },
  messages: { type: Array, default: () => [] },
  insights: { type: Array, default: () => [] },
  // guestStates: { [guestId]: { state: 'idle'|'preparing'|'speaking', thought?: string } }
  guestStates: { type: Object, default: () => ({}) },
  insightsLoading: { type: Boolean, default: false },
  phase: { type: String, default: '' },
})

const moderator = computed(() => (props.topic.guests || []).find((g) => g.role === 'moderator'))
const experts = computed(() => (props.topic.guests || []).filter((g) => g.role === 'expert'))

const emit = defineEmits(['open-thoughts'])

function stateOf(guestId) {
  return props.guestStates[guestId] || { state: 'idle' }
}
</script>

<template>
  <div class="h-full flex flex-col lg:flex-row gap-3 p-3 overflow-y-auto lg:overflow-hidden">
    <!-- 左：嘉宾小窗区（主持人 + 专家单列）— 移动端自然高度随页滚动，桌面端独立滚动 -->
    <aside class="shrink-0 lg:w-72 lg:shrink flex flex-col gap-3 lg:max-h-full lg:overflow-y-auto">
      <div class="shrink-0 px-1 pb-1 text-xs uppercase tracking-wider text-gray-400">
        演播厅阵容
      </div>
      <GuestPanel
        v-if="moderator"
        :guest="moderator"
        :state="stateOf(moderator.id).state"
        :thought="stateOf(moderator.id).thought"
        @open="emit('open-thoughts', moderator.id)"
      />
      <div class="grid grid-cols-1 gap-3">
        <GuestPanel
          v-for="g in experts"
          :key="g.id"
          :guest="g"
          :state="stateOf(g.id).state"
          :thought="stateOf(g.id).thought"
          @open="emit('open-thoughts', g.id)"
        />
      </div>
    </aside>

    <!-- 中：现场 Transcript — 移动端固定视口高度内部滚动（流式体验），桌面端撑满独立滚动 -->
    <div class="shrink-0 lg:shrink h-[60vh] lg:h-auto lg:flex-1 min-w-0 rounded-lg border border-studio-border bg-studio-panel overflow-hidden">
      <Transcript :messages="messages" :phase="phase" />
    </div>

    <!-- 右：共识与分歧区 — 移动端自然高度随页滚动，桌面端撑满独立滚动 -->
    <aside class="shrink-0 lg:w-80 lg:shrink rounded-lg border border-studio-border bg-studio-panel overflow-hidden lg:overflow-visible">
      <InsightPanel :insights="insights" :loading="insightsLoading" />
    </aside>
  </div>
</template>
