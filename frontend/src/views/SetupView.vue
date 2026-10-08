<script setup>
// 准备页 — 输入话题与专家人数，生成阵容，确认后进入演播厅
// PRD §4.2
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createTopic } from '../api/topics'
import { generateRoster, confirmRoster } from '../api/roster'

const router = useRouter()

const form = reactive({
  title: '',
  expert_count: 4,
})
const creating = ref(false)
const generating = ref(false)
const confirming = ref(false)
const roster = ref(null) // { guests, is_confirmed }
const topicId = ref(null) // 已创建的话题 id，重新生成阵容时复用
const error = ref('')

async function onGenerate() {
  error.value = ''
  if (!form.title.trim()) {
    error.value = '请输入话题'
    return
  }
  generating.value = true
  roster.value = null
  try {
    // 1. 首次创建讨论（draft）；重新生成阵容时复用同一 topic
    if (topicId.value === null) {
      const topic = await createTopic({
        title: form.title.trim(),
        expert_count: form.expert_count,
      })
      topicId.value = topic.id
    }
    // 2. 生成阵容（后端会先清旧候选再写新阵容）
    const r = await generateRoster(topicId.value, { expert_count: form.expert_count })
    roster.value = { ...r, _topicId: topicId.value }
  } catch (e) {
    error.value = e.message || '生成失败'
  } finally {
    generating.value = false
  }
}

// 话题标题被修改后，旧 topic 不再适用，下次生成时重建
watch(
  () => form.title,
  () => {
    topicId.value = null
    roster.value = null
  },
)

async function onConfirm() {
  if (!roster.value) return
  confirming.value = true
  error.value = ''
  try {
    await confirmRoster(roster.value._topicId)
    router.push(`/studio/${roster.value._topicId}`)
  } catch (e) {
    error.value = e.message || '确认失败'
  } finally {
    confirming.value = false
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-3xl mx-auto p-6 space-y-6">
      <div>
        <h1 class="text-2xl font-semibold mb-1">发起新讨论</h1>
        <p class="text-sm text-gray-400">输入话题与专家人数，系统将生成主持人与专家阵容</p>
      </div>

      <!-- 输入区 -->
      <section class="rounded-lg border border-studio-border bg-studio-panel p-5 space-y-4">
        <div>
          <label class="block text-sm text-gray-300 mb-1.5">讨论话题</label>
          <input
            v-model="form.title"
            type="text"
            placeholder="如：AGI 是否会在 10 年内取代大部分知识工作者？"
            class="w-full px-3 py-2 rounded bg-studio-bg border border-studio-border text-sm focus:border-studio-accent outline-none"
          />
        </div>
        <div>
          <label class="block text-sm text-gray-300 mb-1.5">专家人数</label>
          <div class="flex items-center gap-4">
            <input
              v-model.number="form.expert_count"
              type="range" min="2" max="6" step="1"
              class="flex-1"
            />
            <span class="w-10 text-center text-lg font-semibold">{{ form.expert_count }}</span>
          </div>
        </div>
        <button
          class="w-full py-2.5 rounded bg-studio-accent hover:opacity-90 text-white text-sm font-medium disabled:opacity-50"
          :disabled="generating"
          @click="onGenerate"
        >
          {{ generating ? '生成中…' : roster ? '重新生成阵容' : '生成阵容' }}
        </button>
        <p v-if="error" class="text-sm text-red-400">{{ error }}</p>
      </section>

      <!-- 阵容展示 -->
      <section v-if="roster" class="rounded-lg border border-studio-border bg-studio-panel p-5">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold">候选阵容</h2>
          <span class="text-xs text-gray-400">{{ roster.guests.length }} 位嘉宾</span>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div
            v-for="g in roster.guests"
            :key="g.id"
            class="rounded-lg border border-studio-border p-3"
            :style="{ borderLeft: `4px solid ${g.color}` }"
          >
            <div class="flex items-center gap-2">
              <span
                class="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold"
                :style="{ background: g.color, color: '#fff' }"
              >{{ g.name.slice(0, 1) }}</span>
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="font-medium text-sm">{{ g.name }}</span>
                  <span
                    v-if="g.role === 'moderator'"
                    class="text-[10px] px-1.5 py-0.5 rounded bg-studio-accent/30 text-blue-200"
                  >主持人</span>
                </div>
                <p class="text-xs text-gray-400 truncate">{{ g.title }}</p>
              </div>
            </div>
            <p v-if="g.stance" class="mt-2 text-xs text-gray-400">立场：{{ g.stance }}</p>
          </div>
        </div>

        <button
          class="mt-5 w-full py-2.5 rounded bg-green-600 hover:opacity-90 text-white text-sm font-medium disabled:opacity-50"
          :disabled="confirming"
          @click="onConfirm"
        >
          {{ confirming ? '确认中…' : '确认阵容，进入演播厅' }}
        </button>
      </section>
    </div>
  </div>
</template>
