<script setup>
// 现场 Transcript — 显示发言人姓名与职业/Title，颜色与专家一致
// PRD §4.3：不显示"举手"等内部事件
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
})

const scroller = ref(null)

const speechTypeLabel = {
  opening: '开场',
  followup: '追问',
  rebute: '反驳',
  supplement: '补充',
  grab: '抢答',
  summary: '收尾',
}

// 新消息到达或流式内容增长时自动滚动到底部
watch(
  () => [props.messages.length, props.messages[props.messages.length - 1]?.content?.length || 0],
  async () => {
    await nextTick()
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  },
)
</script>

<template>
  <section class="h-full flex flex-col">
    <div class="shrink-0 px-4 py-3 border-b border-studio-border flex items-center justify-between">
      <h2 class="text-lg font-semibold">现场 Transcript</h2>
      <span class="text-xs text-gray-400">{{ messages.length }} 条发言</span>
    </div>

    <div ref="scroller" class="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
      <div
        v-for="m in messages"
        :key="m.id || m.turn_index"
        class="flex gap-3"
      >
        <div
          class="w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold shrink-0"
          :style="{ background: m.guest_color }"
        >
          {{ (m.guest_name || '?').slice(0, 1) }}
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline gap-2 flex-wrap">
            <span class="font-medium" :style="{ color: m.guest_color }">{{ m.guest_name }}</span>
            <span class="text-xs text-gray-500">{{ m.guest_title || '' }}</span>
            <span
              v-if="m.speech_type"
              class="text-[10px] px-1.5 py-0.5 rounded bg-studio-border text-gray-300"
            >{{ speechTypeLabel[m.speech_type] || m.speech_type }}</span>
          </div>
          <p class="mt-1 text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">{{ m.content }}</p>
        </div>
      </div>

      <p v-if="!messages.length" class="text-gray-500 text-sm text-center py-8">
        等待讨论开始…
      </p>
    </div>
  </section>
</template>
