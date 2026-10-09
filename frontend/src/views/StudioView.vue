<script setup>
// 演播厅视图 — 编排 StudioRoom + SSE 订阅
// PRD §4.3 演播厅模式 + §6 实时共识/分歧
import { onBeforeUnmount, onMounted, reactive, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import StudioRoom from '../components/StudioRoom.vue'
import ThoughtModal from '../components/ThoughtModal.vue'
import { getTopic, startDiscussion } from '../api/topics'
import { subscribeStream, replayDiscussion, cancelDiscussion } from '../api/stream'
import { listInsights } from '../api/insights'

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()

const topic = ref(null)
// 消息按 transcript_id 聚合：真实 SSE 一条发言会先推若干 streaming delta，再推 done
const messages = ref([])
const insights = ref([])
const guestStates = reactive({}) // { [guestId]: { state, thought } }
const insightsLoading = ref(false)
const error = ref('')
const streamEnded = ref(false)
const thoughtGuestId = ref(null) // 思考过程弹窗当前查看的嘉宾
const currentPhase = ref('') // 后端 system 事件的 phase（expert_decide/extract 等）
const cancelling = ref(false)
const showCancelConfirm = ref(false)
let unsubscribe = null

const canCancel = computed(() =>
  ['ongoing', 'summarizing'].includes(topic.value?.status) && !streamEnded.value,
)

function askCancel() {
  if (!canCancel.value || cancelling.value) return
  showCancelConfirm.value = true
}

async function confirmCancel() {
  showCancelConfirm.value = false
  cancelling.value = true
  try {
    await cancelDiscussion(props.id)
    if (unsubscribe) unsubscribe()
    streamEnded.value = true
    await refreshFinalState()
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || '中断失败'
  } finally {
    cancelling.value = false
  }
}

const thoughtGuest = computed(
  () => topic.value?.guests?.find((g) => g.id === thoughtGuestId.value) || null,
)
const thoughtLive = computed(() => guestStates[thoughtGuestId.value] || { state: 'idle', thought: '' })

function resetGuestStates(state = 'idle') {
  if (!topic.value?.guests) return
  for (const g of topic.value.guests) {
    guestStates[g.id] = { state, thought: '' }
  }
}

function setGuestState(guestId, state, thought = '') {
  // 忠实反映后端 state 事件，不做额外推断
  if (guestStates[guestId]) {
    guestStates[guestId] = { state, thought }
  }
}

function guestMap() {
  const m = {}
  for (const g of topic.value?.guests || []) m[g.id] = g
  return m
}

async function loadArchived() {
  // archived：回放完整 transcript + insights（真实后端 /stream/replay）
  const replay = await replayDiscussion(props.id)
  const gmap = guestMap()
  messages.value = (replay.transcripts || []).map((t) => ({
    ...t,
    // replay payload 不含 guest_title，用阵容信息补齐
    guest_title: gmap[t.guest_id]?.title || '',
  }))
  if (replay.insights?.length) {
    insights.value = replay.insights
  } else {
    insights.value = await listInsights(props.id, { final_only: true })
  }
}

// 真实 SSE：transcript 事件按 transcript_id 聚合，避免流式 delta 产生碎片消息
function upsertTranscript(t) {
  const idx = messages.value.findIndex((m) => m.id === t.transcript_id)
  const base = {
    id: t.transcript_id,
    transcript_id: t.transcript_id,
    topic_id: t.topic_id,
    guest_id: t.guest_id,
    guest_name: t.guest_name,
    guest_color: t.guest_color,
    guest_title: guestMap()[t.guest_id]?.title || '',
    turn_index: t.turn_index,
    speech_type: t.speech_type,
    status: t.status,
    content: '',
  }
  if (idx < 0) {
    messages.value.push(base)
  }
  const target = messages.value[idx < 0 ? messages.value.length - 1 : idx]
  if (t.status === 'streaming') {
    target.status = 'streaming'
    target.content += t.delta || ''
  } else if (t.status === 'done') {
    target.status = 'done'
    // done 事件携带服务端最终完整文本，以它为准
    target.content = t.content || target.content
  } else if (t.status === 'aborted') {
    target.status = 'aborted'
  }
}

async function refreshFinalState() {
  // 流结束：以服务端最终状态为准（topic.status=archived + summary + 最终版 insight）
  try {
    topic.value = await getTopic(props.id)
    insights.value = await listInsights(props.id, { final_only: true })
    // 用 replay 补全可能丢失的 transcript 事件（SSE 传输不保证 100% 可达）
    const replay = await replayDiscussion(props.id)
    const gmap = guestMap()
    for (const t of replay.transcripts || []) {
      const idx = messages.value.findIndex((m) => m.id === t.id)
      if (idx < 0) {
        // SSE 期间丢失的发言，补入
        messages.value.push({
          ...t,
          guest_title: gmap[t.guest_id]?.title || '',
        })
      } else if (messages.value[idx].status !== 'done') {
        // 不完整的条目用服务端最终版本覆盖
        messages.value[idx].content = t.content
        messages.value[idx].status = t.status
      }
    }
    messages.value.sort((a, b) => a.turn_index - b.turn_index)
  } catch (e) {
    console.error('[refresh final state]', e)
  }
}

function startStream() {
  unsubscribe = subscribeStream(props.id, {
    onTranscript: (t) => {
      currentPhase.value = '' // 有人发言，清除等待提示
      upsertTranscript(t)
    },
    onState: (s) => {
      currentPhase.value = '' // 状态变化，清除等待提示
      // 后端推送的嘉宾状态：idle / hand_raised / preparing / speaking
      setGuestState(s.guest_id, s.state, s.thought || '')
    },
    onInsight: (ins) => {
      currentPhase.value = '' // 洞见到达，清除等待提示
      // 流结束后会用 final_only 列表整体覆盖，保证只展示最终版
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
      const idx = insights.value.findIndex((i) => i.id === ins.insight_id)
      if (idx >= 0) insights.value[idx] = item
      else insights.value.push(item)
    },
    onSystem: (s) => {
      console.log('[stream]', s)
      if (s.phase) currentPhase.value = s.phase
    },
    onEnd: () => {
      streamEnded.value = true
      resetGuestStates('idle')
      refreshFinalState()
    },
    onError: (e) => {
      // 服务端在 end 后正常关闭连接也会触发 error，此时不算失败
      if (streamEnded.value) return
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
    } else if (topic.value.status === 'ongoing' || topic.value.status === 'summarizing') {
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
            'bg-red-600 text-red-100': topic.status === 'cancelled',
          }"
        >
          {{ { ongoing: '进行中', archived: '已归档', summarizing: '收尾中', setup: '待启动', cancelled: '已中断' }[topic?.status] || topic?.status }}
        </span>
        <button
          v-if="canCancel"
          class="text-xs px-2.5 py-1 rounded bg-red-600/80 hover:bg-red-600 text-white disabled:opacity-50"
          :disabled="cancelling"
          @click="askCancel"
        >
          {{ cancelling ? '中断中…' : '⏹ 中断讨论' }}
        </button>
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
        :phase="currentPhase"
        @open-thoughts="(gid) => (thoughtGuestId = gid)"
      />
    </div>

    <!-- 思考过程弹窗 -->
    <ThoughtModal
      v-if="thoughtGuest"
      :topic-id="props.id"
      :guest="thoughtGuest"
      :live-thought="thoughtLive.thought"
      :live-state="thoughtLive.state"
      @close="thoughtGuestId = null"
    />

    <!-- 中断确认弹窗 -->
    <div v-if="showCancelConfirm" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/60" @click="showCancelConfirm = false"></div>
      <div class="relative w-full max-w-sm rounded-xl border border-studio-border bg-studio-panel shadow-2xl">
        <div class="px-5 py-4 border-b border-studio-border">
          <h3 class="text-base font-semibold">确认中断讨论？</h3>
        </div>
        <div class="px-5 py-4 text-sm text-gray-300 leading-relaxed">
          中断后讨论将立即停止，已有的发言和共识/分歧会保留，该话题状态变为「已中断」，可随时回看。
        </div>
        <div class="px-5 py-3 flex justify-end gap-2 border-t border-studio-border">
          <button
            class="px-4 py-1.5 rounded text-sm text-gray-300 hover:bg-studio-border disabled:opacity-50"
            :disabled="cancelling"
            @click="showCancelConfirm = false"
          >取消</button>
          <button
            class="px-4 py-1.5 rounded text-sm bg-red-600 hover:bg-red-500 text-white disabled:opacity-50"
            :disabled="cancelling"
            @click="confirmCancel"
          >{{ cancelling ? '中断中…' : '确认中断' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
