<script setup>
// 正在进行的讨论列表组件
// PRD §4.1：展示当前所有正在进行的讨论列表
import { computed } from 'vue'

const props = defineProps({
  topics: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'new'])

const statusMeta = {
  draft: { label: '草稿', cls: 'bg-gray-600 text-gray-200' },
  setup: { label: '准备中', cls: 'bg-yellow-600 text-yellow-100' },
  ongoing: { label: '进行中', cls: 'bg-green-600 text-green-100 animate-pulse' },
  summarizing: { label: '收尾中', cls: 'bg-blue-600 text-blue-100' },
  archived: { label: '已归档', cls: 'bg-gray-500 text-gray-100' },
}

const sorted = computed(() =>
  [...props.topics].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1)),
)
</script>

<template>
  <section class="h-full flex flex-col">
    <div class="shrink-0 flex items-center justify-between px-4 py-3 border-b border-studio-border">
      <h2 class="text-lg font-semibold">讨论列表</h2>
      <button
        class="text-sm px-3 py-1.5 rounded bg-studio-accent hover:opacity-90 text-white"
        @click="emit('new')"
      >
        + 发起新讨论
      </button>
    </div>

    <div class="grow min-h-0 overflow-y-auto lg:flex-1 p-4 space-y-3">
      <p v-if="loading" class="text-gray-400 text-sm">加载中…</p>
      <p v-else-if="!sorted.length" class="text-gray-500 text-sm">暂无讨论，点击右上角发起新讨论。</p>

      <article
        v-for="t in sorted"
        :key="t.id"
        class="cursor-pointer rounded-lg border border-studio-border bg-studio-panel p-4 hover:border-studio-accent transition"
        @click="emit('select', t)"
      >
        <div class="flex items-start justify-between gap-3">
          <h3 class="text-base font-medium leading-snug line-clamp-2">{{ t.title }}</h3>
          <span
            class="shrink-0 text-xs px-2 py-0.5 rounded"
            :class="statusMeta[t.status]?.cls"
          >
            {{ statusMeta[t.status]?.label || t.status }}
          </span>
        </div>
        <div class="mt-3 flex items-center gap-4 text-xs text-gray-400">
          <span>👥 {{ t.expert_count }} 位专家</span>
          <span v-if="t.has_summary">📄 已有总结</span>
          <span>🕒 {{ new Date(t.updated_at).toLocaleString('zh-CN') }}</span>
        </div>
      </article>
    </div>
  </section>
</template>
