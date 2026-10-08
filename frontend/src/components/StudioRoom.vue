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
})

const moderator = computed(() => (props.topic.guests || []).find((g) => g.role === 'moderator'))
const experts = computed(() => (props.topic.guests || []).filter((g) => g.role === 'expert'))

const emit = defineEmits(['open-thoughts'])

function stateOf(guestId) {
  return props.guestStates[guestId] || { state: 'idle' }
}
</script>

<template>
  <div class="h-full flex flex-col lg:flex-row gap-3 p-3">
    <!-- 左：嘉宾小窗区（主持人 + 专家网格）独立滚动 -->
    <aside class="lg:w-72 shrink-0 lg:shrink flex flex-col gap-3 lg:max-h-full lg:overflow-y-auto">
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
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2 gap-3">
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

    <!-- 中：现场 Transcript 独立滚动 -->
    <div class="flex-1 min-w-0 min-h-[300px] lg:min-h-0 rounded-lg border border-studio-border bg-studio-panel overflow-hidden">
      <Transcript :messages="messages" />
    </div>

    <!-- 右：共识与分歧区 独立滚动 -->
    <aside class="lg:w-80 shrink-0 lg:shrink min-h-[300px] lg:min-h-0 rounded-lg border border-studio-border bg-studio-panel overflow-hidden">
      <InsightPanel :insights="insights" :loading="insightsLoading" />
    </aside>
  </div>
</template>
