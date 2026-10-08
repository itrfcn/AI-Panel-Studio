<script setup>
// 单条共识/分歧卡片
import { computed } from 'vue'

const props = defineProps({
  insight: { type: Object, required: true },
})

const isConsensus = computed(() => props.insight.type === 'consensus')

const strengthLabel = { weak: '弱', medium: '中', strong: '强' }

const tagCls = computed(() =>
  isConsensus.value
    ? 'bg-green-600/30 text-green-200 border-green-500/40'
    : 'bg-orange-600/30 text-orange-200 border-orange-500/40',
)
</script>

<template>
  <div
    class="rounded-lg border bg-studio-panel p-3 transition hover:border-studio-accent"
    :class="isConsensus ? 'border-green-700/40' : 'border-orange-700/40'"
  >
    <div class="flex items-center gap-2 mb-1.5">
      <span
        class="text-[10px] px-1.5 py-0.5 rounded border"
        :class="tagCls"
      >
        {{ isConsensus ? '共识' : '分歧' }}
      </span>
      <span class="text-[10px] text-gray-500">强度：{{ strengthLabel[insight.strength] || insight.strength }}</span>
      <span v-if="insight.is_final" class="text-[10px] text-blue-300">最终版</span>
      <span class="ml-auto text-[10px] text-gray-600">v{{ insight.version }}</span>
    </div>
    <p class="text-sm text-gray-100 leading-snug">{{ insight.summary }}</p>
  </div>
</template>
