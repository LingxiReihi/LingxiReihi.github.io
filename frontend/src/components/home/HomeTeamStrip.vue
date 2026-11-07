<script setup lang="ts">
import type { TeamMember } from '@/api/types'

defineProps<{ members: TeamMember[]; layout?: 'grid' | 'rail' }>()

// 跳关于页对应卡片：About 用 [data-author="昵称"] 定位，锚点参数就是昵称
const cardLink = (m: TeamMember) => ({ path: '/about', query: { a: m.nickname } })
</script>

<template>
  <div v-if="layout === 'rail'" class="flex snap-x gap-3 overflow-x-auto pb-3">
    <div v-for="m in members" :key="m.nickname" data-reveal class="w-44 shrink-0 snap-start">
      <RouterLink
        :to="cardLink(m)"
        class="group relative block border border-line bg-surface/40 p-4 transition-colors hover:border-brand/60"
      >
        <span class="pointer-events-none absolute left-0 top-0 h-2 w-2 border-l border-t border-brand opacity-50 transition-opacity group-hover:opacity-100" aria-hidden="true" />
        <img v-if="m.avatar" :src="m.avatar" :alt="m.nickname" loading="lazy"
             class="h-14 w-14 border border-line object-cover" />
        <div v-else class="grid h-14 w-14 place-items-center border border-line bg-elevated text-xl">🙂</div>
        <p class="mt-3 truncate text-sm font-medium transition-colors group-hover:text-brand">{{ m.nickname }}</p>
        <p class="mt-1 line-clamp-2 text-[11px] leading-relaxed text-ink-3">{{ m.signature || '这位管理员还没写签名' }}</p>
      </RouterLink>
    </div>
  </div>
  <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
    <div v-for="m in members" :key="m.nickname" data-reveal>
      <RouterLink
        :to="cardLink(m)"
        class="group relative flex h-full items-center gap-3 border border-line bg-surface/40 p-3.5 transition-colors hover:border-brand/60"
      >
        <span class="pointer-events-none absolute left-0 top-0 h-2 w-2 border-l border-t border-brand opacity-50 transition-opacity group-hover:opacity-100" aria-hidden="true" />
        <img v-if="m.avatar" :src="m.avatar" :alt="m.nickname" loading="lazy"
             class="h-11 w-11 shrink-0 border border-line object-cover" />
        <div v-else class="grid h-11 w-11 shrink-0 place-items-center border border-line bg-elevated">🙂</div>
        <div class="min-w-0">
          <p class="truncate text-sm font-medium transition-colors group-hover:text-brand">{{ m.nickname }}</p>
          <p class="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-ink-3">{{ m.signature || '这位管理员还没写签名' }}</p>
        </div>
      </RouterLink>
    </div>
  </div>
</template>
