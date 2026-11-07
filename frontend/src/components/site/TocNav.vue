<script setup lang="ts">
import type { TocItem } from '@/composables/useMd'
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { setAnchorHash } from '@/utils/link'

const props = defineProps<{ items: TocItem[] }>()
const active = ref('')
let obs: IntersectionObserver | null = null

onMounted(() => {
  obs = new IntersectionObserver(
    (entries) => {
      for (const e of entries) if (e.isIntersecting) active.value = e.target.id
    },
    { rootMargin: '-80px 0px -70% 0px' },
  )
  document.querySelectorAll('.prose h2[id], .prose h3[id]').forEach((h) => obs!.observe(h))
})
onBeforeUnmount(() => obs?.disconnect())

function jump(id: string) {
  const item = props.items.find((t) => t.id === id)
  if (item) setAnchorHash(item.id)
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  active.value = id
}
</script>

<template>
  <nav aria-label="文章目录" class="text-sm">
    <p class="mb-3 font-semibold text-ink-2">目录</p>
    <ul class="space-y-1 border-l border-line">
      <li v-for="t in items" :key="t.id">
        <button
          class="-ml-px block w-full border-l-2 py-1 pl-3 text-left truncate transition-colors"
          :class="[
            t.level === 3 ? 'pl-6' : '',
            active === t.id ? 'border-brand text-brand' : 'border-transparent text-ink-3 hover:text-ink-2',
          ]"
          :title="t.text"
          @click="jump(t.id)"
        >{{ t.text }}</button>
      </li>
    </ul>
  </nav>
</template>
