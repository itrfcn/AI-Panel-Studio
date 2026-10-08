<script setup>
// 演播厅视图 — 编排 StudioRoom + SSE 订阅
// PRD §4.3 演播厅模式 + §6 实时共识/分歧
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import StudioRoom from '../components/StudioRoom.vue'
import { getTopic, startDiscussion } from '../api/topics'
import { subscribeStream, replayDiscussion } from '../api/stream'
import { listInsights } from '../api/insights'

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()

const topic = ref(null)
const messages = ref([])
const insights = ref([])
const guestStates = reactive({}) // { [guestId]: { state, thought } }
const insightsLoading = ref(false)
const error = ref('')
const streamEnded = ref(false)
let unsubscribe = null

function resetGuestStates(state = 'idle') {
  if (!topic.value?.guests) return
  for (const g of topic.value.guests) {
    guestStates[g.id] = { state, thought: '' }
  }
}

function setSpeaking(guestId) {
  // 当前发言者 speaking，其余 expert idle（主持人保留原状态）
  for (const g of topic.value?.guests || []) {
    if (g.id === guestId) {
      guestStates[g.id] = { state: 'speaking', thought: '' }
    } else if (g.role === 'expert') {
      guestStates[g.id] = { state: 'idle', thought: '' }
    }
  }
}

async function loadArchived() {
  // archived：回放完整 transcript + insights
  const replay = await replayDiscussion(props.id)
  messages.value = replay.transcripts || []
  insights.value = replay.insights || (await listInsights(props.id))
}

function startStream() {
  unsubscribe = subscribeStream(props.id, {
    onTranscript: (t) => {
      messages.value.push(t)
      setSpeaking(t.guest_id)
    },
    onInsight: (ins) => {
      // create / update / finalize
      const idx = insights.value.findIndex((i) => i.id === ins.insight_id)
      const item = {
        id: ins.insight_id,
        type: ins.type,
        summary: ins.summary,
        strength: ins.strength,
        version: ins.version,
        is_final: ins.is_final,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      if (idx >= 0) insights.value[idx] = item
      else insights.value.push(item)
    },
    onSystem: (s) => console.log('[stream]', s),
    onEnd: () => {
      streamEnded.value = true
      resetGuestStates('idle')
    },
    onError: (e) => {
      console.error('[stream error]', e)
      error.value = '实时流连接失败'
    },
  })
}

async function load() {
  error.value = ''
  try {
    topic.value = await getTopic(props.id)
    resetGuestStates('idle')

    if (topic.value.status === 'archived') {
      await loadArchived()
    } else if (topic.value.status === 'ongoing') {
      // 已在进行中：拉取已有 insights，再订阅增量
      insightsLoading.value = true
      try {
        insights.value = await listInsights(props.id)
      } finally {
        insightsLoading.value = false
      }
      startStream()
    } else if (topic.value.status === 'setup') {
      // 候选阵容待启动：前端触发 start 后再订阅
      const started = await startDiscussion(props.id)
      topic.value.status = started.status
      topic.value.started_at = started.started_at
      startStream()
    } else {
      error.value = `讨论状态 ${topic.value.status} 不可加入演播厅`
    }
  } catch (e) {
    error.value = e.message || '加载失败'
  }
}

onMounted(load)
onBeforeUnmount(() => {
  if (unsubscribe) unsubscribe()
})
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- 话题标题栏 -->
    <div class="shrink-0 px-4 py-3 border-b border-studio-border flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h1 v-if="topic" class="text-lg font-semibold truncate">{{ topic.title }}</h1>
        <h1 v-else class="text-lg text-gray-400">加载中…</h1>
      </div>
      <div class="flex items-center gap-3 shrink-0">
        <span
          v-if="topic"
          class="text-xs px-2 py-0.5 rounded"
          :class="{
            'bg-green-600 text-green-100': topic.status === 'ongoing',
            'bg-gray-500 text-gray-100': topic.status === 'archived',
            'bg-yellow-600 text-yellow-100': topic.status === 'summarizing',
          }"
        >
          {{ { ongoing: '进行中', archived: '已归档', summarizing: '收尾中', setup: '待启动' }[topic?.status] || topic?.status }}
        </span>
        <button class="text-xs text-gray-400 hover:text-white" @click="router.push('/')">← 返回列表</button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="shrink-0 px-4 py-2 bg-red-900/30 text-red-300 text-sm">
      {{ error }}
    </div>

    <!-- 演播厅主体（各区域独立滚动） -->
    <div v-if="topic" class="flex-1 min-h-0">
      <StudioRoom
        :topic="topic"
        :messages="messages"
        :insights="insights"
        :guest-states="guestStates"
        :insights-loading="insightsLoading"
      />
    </div>
  </div>
</template>
