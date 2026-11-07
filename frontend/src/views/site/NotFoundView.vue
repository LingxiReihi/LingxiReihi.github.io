<script setup lang="ts">
import { useSeo } from '@/composables/useSeo'
useSeo({ title: '404 页面不存在', path: '/404' })
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-4 px-4 py-32 text-center">
    <p class="text-6xl font-bold text-brand/60">404</p>
    <h1 class="text-xl font-medium">页面不存在或已被移动</h1>
    <p class="text-sm text-ink-3">你访问的链接可能已失效</p>
    <div class="mt-2 flex gap-3">
      <RouterLink to="/" class="rounded-lg bg-brand px-5 py-2 text-sm font-medium text-black hover:opacity-90">回首页</RouterLink>
      <RouterLink to="/blog" class="rounded-lg border border-line px-5 py-2 text-sm hover:bg-elevated">去博客</RouterLink>
    </div>
  </div>
</template>
