<script setup>
// 顶层布局：固定占满视口，路由视图在自身容器内滚动
</script>

<template>
  <div class="h-screen w-screen flex flex-col bg-studio-bg">
    <header
      class="shrink-0 border-b border-studio-border px-6 py-3 flex items-center justify-between"
    >
      <div class="flex items-center gap-3">
        <span class="text-xl font-semibold tracking-wide">AI Panel Studio</span>
        <span class="text-xs text-gray-400">AI 圆桌演播厅</span>
      </div>
      <nav class="flex gap-4 text-sm">
        <RouterLink to="/" class="hover:text-white text-gray-300">首页</RouterLink>
        <RouterLink to="/setup" class="hover:text-white text-gray-300">发起新讨论</RouterLink>
      </nav>
    </header>
    <main class="flex-1 min-h-0 overflow-hidden">
      <RouterView />
    </main>
  </div>
</template>
