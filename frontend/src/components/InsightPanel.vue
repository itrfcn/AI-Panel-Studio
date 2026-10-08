<script setup>
// 共识与分歧展示区 — chain-of-thought 区
// PRD §4.3 & §6：实时更新对应区域，不等到讨论结束
import { computed } from 'vue'
import InsightCard from './InsightCard.vue'

const props = defineProps({
  insights: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const consensus = computed(() => props.insights.filter((i) => i.type === 'consensus'))
const divergence = computed(() => props.insights.filter((i) => i.type === 'divergence'))
</script>

<template>
  <section class="h-full flex flex-col">
    <div class="shrink-0 px-4 py-3 border-b border-studio-border">
      <h2 class="text-lg font-semibold">共识与分歧</h2>
      <p class="text-xs text-gray-400 mt-0.5">chain-of-thought · 实时生成</p>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
      <p v-if="loading && !insights.length" class="text-gray-400 text-sm">抽取中…</p>

      <!-- 共识区 -->
      <div>
        <h3 class="text-xs uppercase tracking-wider text-green-300 mb-2 flex items-center gap-2">
          <span class="w-1.5 h-1.5 rounded-full bg-green-400"></span>
          共识（{{ consensus.length }}）
        </h3>
        <div class="space-y-2">
          <InsightCard v-for="i in consensus" :key="i.id" :insight="i" />
          <p v-if="!consensus.length" class="text-xs text-gray-600">暂无共识</p>
        </div>
      </div>

      <!-- 分歧区 -->
      <div>
        <h3 class="text-xs uppercase tracking-wider text-orange-300 mb-2 flex items-center gap-2">
          <span class="w-1.5 h-1.5 rounded-full bg-orange-400"></span>
          分歧（{{ divergence.length }}）
        </h3>
        <div class="space-y-2">
          <InsightCard v-for="i in divergence" :key="i.id" :insight="i" />
          <p v-if="!divergence.length" class="text-xs text-gray-600">暂无分歧</p>
        </div>
      </div>

      <p
        v-if="!insights.length && !loading"
        class="text-gray-500 text-sm text-center py-6"
      >
        讨论进行中将实时生成共识与分歧…
      </p>
    </div>
  </section>
</template>
