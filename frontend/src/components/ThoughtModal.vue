<script setup>
// 思考过程弹窗 — 单独查看某位嘉宾的公开思考时间线
// 数据：EventPoint(hand_raise).payload.thought + 该轮实际发言
import { ref, watch } from 'vue'
import { getGuestThoughts } from '../api/topics'

const props = defineProps({
  topicId: { type: [String, Number], required: true },
  guest: { type: Object, default: null },
  // SSE 实时思考（打开弹窗期间仍在进行的那一轮）
  liveThought: { type: String, default: '' },
  liveState: { type: String, default: 'idle' },
})
const emit = defineEmits(['close'])

const timeline = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  if (!props.guest) return
  loading.value = true
  error.value = ''
  try {
    const data = await getGuestThoughts(props.topicId, props.guest.id)
    timeline.value = data.timeline || []
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// 打开时加载；打开期间该嘉宾新一轮举手时自动重载
watch(() => props.guest?.id, load, { immediate: true })
watch(() => props.liveState, (s, old) => {
  if (props.guest && s === 'hand_raised' && s !== old) load()
})

const typeLabel = {
  grab: '抢答', supplement: '补充', rebute: '反驳',
  followup: '追问', opening: '开场', summary: '总结',
}
const priorityLabel = { grab: '抢答意图', supplement: '补充意图', rebute: '反驳意图' }
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <!-- 遮罩 -->
    <div class="absolute inset-0 bg-black/60" @click="emit('close')"></div>

    <!-- 弹窗主体 -->
    <div class="relative w-full max-w-lg max-h-[85dvh] flex flex-col rounded-xl border border-studio-border bg-studio-panel shadow-2xl">
      <!-- 头部：嘉宾信息 -->
      <div class="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-studio-border">
        <div
          class="w-10 h-10 rounded-full flex items-center justify-center font-semibold text-sm shrink-0"
          :style="{ background: guest?.color, color: '#fff' }"
        >
          {{ guest?.name?.slice(0, 1) }}
        </div>
        <div class="min-w-0 flex-1">
          <div class="font-medium">{{ guest?.name }} 的思考过程</div>
          <p class="text-xs text-gray-400 truncate">{{ guest?.title }}</p>
        </div>
        <button class="text-gray-400 hover:text-white text-lg leading-none px-2" @click="emit('close')">✕</button>
      </div>
      <p v-if="guest?.stance" class="shrink-0 px-4 py-2 text-xs text-gray-400 border-b border-studio-border">
        立场：{{ guest.stance }}
      </p>

      <!-- 进行中的思考（实时） -->
      <div
        v-if="liveThought && liveState !== 'idle'"
        class="shrink-0 mx-4 mt-3 text-xs rounded px-2 py-1.5 text-green-200/90 bg-green-900/20 border border-green-800/40"
      >
        <span class="text-green-400">● 进行中</span> 💭 {{ liveThought }}
      </div>

      <!-- 时间线 -->
      <div class="flex-1 min-h-0 overflow-y-auto px-4 py-3 space-y-3">
        <div v-if="loading" class="text-sm text-gray-400 text-center py-6">加载中…</div>
        <div v-else-if="error" class="text-sm text-red-400 text-center py-6">{{ error }}</div>
        <div v-else-if="!timeline.length" class="text-sm text-gray-500 text-center py-6">
          该嘉宾还没有举手记录
        </div>
        <div
          v-for="(item, i) in timeline"
          :key="i"
          class="rounded-lg border border-studio-border bg-black/20 px-3 py-2"
        >
          <div class="flex items-center gap-2 text-xs">
            <span class="text-gray-500">第 {{ (item.turn_index ?? 0) + 1 }} 次发言机会</span>
            <span v-if="priorityLabel[item.priority]" class="px-1.5 py-0.5 rounded bg-blue-900/40 text-blue-200">
              {{ priorityLabel[item.priority] }}
            </span>
            <span
              v-if="item.speech_type"
              class="px-1.5 py-0.5 rounded"
              :class="item.spoke ? 'bg-green-900/40 text-green-200' : 'bg-gray-700/40 text-gray-400'"
            >
              {{ item.spoke ? typeLabel[item.speech_type] || item.speech_type : '未获发言' }}
            </span>
          </div>
          <p class="mt-1.5 text-xs text-blue-200/90">💭 {{ item.thought || '（无思考摘要）' }}</p>
          <p v-if="item.speech" class="mt-1.5 text-sm text-gray-200 leading-relaxed">{{ item.speech }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
