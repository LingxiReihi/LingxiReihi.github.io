<script setup lang="ts">
import type { ContentOut } from '@/api/types'
import { formatDate } from '@/utils/format'

defineProps<{ item: ContentOut; to: string }>()
</script>

<template>
  <RouterLink
    :to="to"
    class="group relative block overflow-hidden border border-line bg-surface/60 transition-colors hover:border-brand/60 hover:bg-elevated/40"
  >
    <!-- 四角刻度线：HUD 卡片标识 -->
    <span class="pointer-events-none absolute left-0 top-0 z-10 h-2 w-2 border-l border-t border-brand opacity-50 transition-opacity group-hover:opacity-100" aria-hidden="true" />
    <span class="pointer-events-none absolute bottom-0 right-0 z-10 h-2 w-2 border-b border-r border-brand opacity-50 transition-opacity group-hover:opacity-100" aria-hidden="true" />

    <div v-if="item.cover" class="border-b border-line">
      <img :src="item.cover" :alt="item.title" loading="lazy" class="w-full" />
    </div>
    <div class="p-4 md:p-5">
      <h3 class="text-sm font-semibold leading-snug md:text-[15px] group-hover:text-brand">{{ item.title }}</h3>
      <p v-if="item.summary" class="mt-2 line-clamp-1 text-xs text-ink-2 md:line-clamp-2 md:text-[13px]">{{ item.summary }}</p>
      <div class="mt-3 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">
        <span>{{ formatDate(item.published_at) }}</span>
        <span v-for="t in item.tags.slice(0, 3)" :key="t.id" class="border border-line px-1.5 py-0.5">{{ t.name }}</span>
        <span v-if="item.extra.reading_time" class="ml-auto">≈{{ item.extra.reading_time }} MIN</span>
      </div>
    </div>
  </RouterLink>
</template>
