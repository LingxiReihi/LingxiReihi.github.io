<script setup lang="ts">
import type { HotOut } from '@/api/types'
import { computed } from 'vue'

import { contentLink, TYPE_LABEL } from '@/utils/link'

const props = defineProps<{ items: HotOut[] }>()
// 热度条按最高分归一；score 由后端算（浏览×1 + 点赞×8 + 评论×12），前端不抄权重
const max = computed(() => Math.max(1, ...props.items.map((i) => i.score)))
</script>

<template>
  <ol class="mt-1">
    <li v-for="(h, i) in items" :key="`${h.type}-${h.id}`" data-reveal>
      <RouterLink
        :to="contentLink(h)"
        class="group grid grid-cols-[34px_1fr] items-center gap-4 border-b border-line/60 py-3 transition-colors hover:bg-elevated/30 md:grid-cols-[34px_1fr_120px_150px]"
      >
        <span class="font-mono text-[10px] text-brand/70">{{ String(i + 1).padStart(2, '0') }}</span>
        <div class="min-w-0">
          <p class="truncate text-sm font-medium transition-colors group-hover:text-brand md:text-[15px]">{{ h.title }}</p>
          <p class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">
            <span class="border border-line px-1.5 py-0.5">{{ TYPE_LABEL[h.type] }}</span>
            <span>PV {{ h.view_count }}</span>
            <span>♥ {{ h.likes }}</span>
            <span>CMT {{ h.comment_count }}</span>
          </p>
        </div>
        <span class="hidden font-mono text-[10px] tracking-[0.08em] text-ink-3 md:block">SCORE {{ h.score }}</span>
        <!-- 热度条：一根 2px 的仪表条 -->
        <div class="hidden h-0.5 w-full bg-elevated md:block">
          <div class="h-full bg-brand/70 transition-[width]" :style="{ width: `${Math.round((h.score / max) * 100)}%` }" />
        </div>
      </RouterLink>
    </li>
  </ol>
</template>
