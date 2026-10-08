<script setup>
// 首页 — 讨论列表 + 发起新讨论
// PRD §4.1：展示当前所有正在进行的讨论列表
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import TopicList from '../components/TopicList.vue'
import { listTopics } from '../api/topics'

const router = useRouter()
const topics = ref([])
const loading = ref(false)
const loadError = ref('')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await listTopics()
    topics.value = res.items || []
  } catch (e) {
    loadError.value = e?.response?.data?.detail || e?.message || '加载讨论列表失败'
  } finally {
    loading.value = false
  }
}

function onSelect(t) {
  router.push(`/studio/${t.id}`)
}

onMounted(load)
</script>

<template>
  <div class="h-full flex flex-col lg:flex-row overflow-y-auto lg:overflow-hidden">
    <!-- 左侧：讨论列表 — 移动端自然高度随页滚动，桌面端独立滚动 -->
    <div class="w-full lg:w-96 shrink-0 border-b lg:border-b-0 lg:border-r border-studio-border lg:h-full">
      <TopicList :topics="topics" :loading="loading" @select="onSelect" @new="router.push('/setup')" />
    </div>

    <!-- 右侧：欢迎/说明区 — 移动端自然高度随页滚动，桌面端独立滚动并垂直居中 -->
    <div class="flex-1 min-w-0 lg:overflow-y-auto p-4 sm:p-8 lg:flex lg:flex-col">
      <div class="max-w-3xl w-full mx-auto lg:my-auto">
        <!-- 后端连接失败提示 -->
        <div
          v-if="loadError"
          class="mb-6 rounded-lg border border-red-700 bg-red-900/30 p-4 text-sm text-red-200"
        >
          <p class="font-medium mb-1">无法加载讨论列表</p>
          <p class="text-red-300/80 text-xs mb-2">{{ loadError }}</p>
          <p class="text-xs text-red-300/60">
            请确认后端已启动（uvicorn app.main:app --port 8000）且 .env 中 LLM_API_KEY 已配置。
          </p>
          <button
            class="mt-2 text-xs px-2 py-1 rounded bg-red-700 hover:bg-red-600 text-white"
            @click="load"
          >重试</button>
        </div>
        <h1 class="text-2xl sm:text-3xl lg:text-4xl font-semibold mb-3">AI 圆桌演播厅</h1>
        <p class="text-gray-400 leading-relaxed">
          召集一支虚拟智库，围绕任意议题展开深度碰撞。主持人负责开场、追问与收尾，
          专家自主"举手"抢答与反驳，过程中实时生成共识与分歧。
        </p>

        <div class="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-4 lg:gap-5">
          <div class="rounded-lg border border-studio-border bg-studio-panel p-4">
            <div class="text-sm text-blue-300 mb-1">多 Agent 协作</div>
            <p class="text-xs text-gray-400">主持人与 N 位专家分阶段分上下文对话，避免幻觉</p>
          </div>
          <div class="rounded-lg border border-studio-border bg-studio-panel p-4">
            <div class="text-sm text-green-300 mb-1">过程可见</div>
            <p class="text-xs text-gray-400">chain-of-thought 实时生成，不等到结束才出现</p>
          </div>
          <div class="rounded-lg border border-studio-border bg-studio-panel p-4">
            <div class="text-sm text-orange-300 mb-1">沉浸感</div>
            <p class="text-xs text-gray-400">嘉宾小窗状态切换 + 流式发言，像在看一场直播</p>
          </div>
          <div class="rounded-lg border border-studio-border bg-studio-panel p-4">
            <div class="text-sm text-purple-300 mb-1">可回放</div>
            <p class="text-xs text-gray-400">archived 讨论可完整回放发言与共识分歧</p>
          </div>
        </div>

        <p class="mt-8 text-sm text-gray-500">
          从讨论列表选择一场加入观察，或点击「发起新讨论」开始。
        </p>
      </div>
    </div>
  </div>
</template>
