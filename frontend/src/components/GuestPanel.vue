<script setup>
// 嘉宾独立小窗 — 单个主持人/专家的状态显示
// PRD §4.3：实时显示 Agent 运行状态（待机/准备/发言中）与思考摘要
import { computed } from 'vue'

const props = defineProps({
  guest: { type: Object, required: true },
  state: { type: String, default: 'idle' }, // idle / preparing / speaking
  thought: { type: String, default: '' },
})

const stateMeta = {
  idle: { label: '待机', dot: 'bg-gray-400', ring: 'ring-gray-600', icon: '' },
  hand_raised: { label: '举手', dot: 'bg-blue-400 animate-pulse', ring: 'ring-blue-500/60', icon: '✋' },
  preparing: { label: '准备中', dot: 'bg-yellow-400 animate-pulse', ring: 'ring-yellow-500/60', icon: '' },
  speaking: { label: '发言中', dot: 'bg-green-400 animate-pulse', ring: 'ring-green-400/80', icon: '🎤' },
}

const meta = computed(() => stateMeta[props.state] || stateMeta.idle)
const isModerator = computed(() => props.guest.role === 'moderator')
</script>

<template>
  <div
    class="rounded-lg border bg-studio-panel p-3 transition"
    :class="[
      isModerator ? 'border-studio-accent' : 'border-studio-border',
      state === 'speaking' || state === 'hand_raised' ? `ring-2 ${meta.ring}` : '',
    ]"
    :style="{ boxShadow: state === 'speaking' ? `0 0 0 1px ${guest.color}` : undefined }"
  >
    <div class="flex items-center gap-3">
      <div
        class="w-10 h-10 rounded-full flex items-center justify-center font-semibold text-sm shrink-0"
        :style="{ background: guest.color, color: '#fff' }"
      >
        {{ guest.name.slice(0, 1) }}
      </div>
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <span class="font-medium truncate">{{ guest.name }}</span>
          <span
            v-if="isModerator"
            class="text-[10px] px-1.5 py-0.5 rounded bg-studio-accent/30 text-blue-200"
          >主持人</span>
        </div>
        <p class="text-xs text-gray-400 truncate">{{ guest.title }}</p>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <span v-if="meta.icon" class="text-sm">{{ meta.icon }}</span>
        <span class="w-2 h-2 rounded-full" :class="meta.dot"></span>
        <span class="text-xs text-gray-300">{{ meta.label }}</span>
      </div>
    </div>

    <p
      v-if="guest.stance"
      class="mt-2 text-xs text-gray-400 truncate"
    >立场：{{ guest.stance }}</p>

    <div
      v-if="(state === 'preparing' || state === 'hand_raised') && thought"
      class="mt-2 text-xs rounded px-2 py-1 line-clamp-2"
      :class="state === 'hand_raised' ? 'text-blue-200/80 bg-blue-900/20' : 'text-yellow-200/80 bg-yellow-900/20'"
    >
      💭 {{ thought }}
    </div>
  </div>
</template>
