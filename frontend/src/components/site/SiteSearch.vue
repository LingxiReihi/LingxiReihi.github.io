<script setup lang="ts">
import type { ContentOut } from '@/api/types'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { searchApi } from '@/api'

const router = useRouter()
const q = ref('')
const items = ref<ContentOut[]>([])
const open = ref(false)
const loading = ref(false)
const searched = ref(false)
let timer: number | undefined
let reqSeq = 0

const TYPE_LABEL: Record<string, string> = { article: '博客', model: '模型', chat: '杂谈' }

function itemTo(x: ContentOut) {
  return x.type === 'chat' ? `/chats/${x.id}` : `/${x.type === 'model' ? 'models' : 'blog'}/${x.slug}`
}

function onInput() {
  window.clearTimeout(timer)
  const kw = q.value.trim()
  if (kw.length < 2) { items.value = []; searched.value = false; open.value = !!kw; return }
  timer = window.setTimeout(run, 300)
}

async function run() {
  const kw = q.value.trim()
  if (kw.length < 2) return
  const seq = ++reqSeq
  loading.value = true
  open.value = true
  try {
    const d = await searchApi.run(kw)
    if (seq !== reqSeq) return   // 丢弃过期响应
    items.value = d.items.slice(0, 8)
    searched.value = true
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

function go(x: ContentOut) {
  open.value = false
  router.push(itemTo(x))
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
  if (e.key === 'Enter') { window.clearTimeout(timer); run() }
}

function onOutside(e: MouseEvent) {
  if (!(e.target as HTMLElement).closest('.site-search')) open.value = false
}
onMounted(() => document.addEventListener('click', onOutside))
onBeforeUnmount(() => {
  document.removeEventListener('click', onOutside)
  window.clearTimeout(timer)
})
</script>

<template>
  <div class="site-search relative">
    <input
      v-model="q" type="search" placeholder="搜索内容…" maxlength="60"
      class="h-8 w-36 border border-line bg-elevated/40 px-3 font-mono text-[11px] tracking-[0.06em] outline-none transition-all placeholder:text-ink-3 focus:w-52 focus:border-brand [&::-webkit-search-cancel-button]:hidden"
      aria-label="搜索内容" @input="onInput" @keydown="onKey" @focus="q.trim().length >= 2 && (open = true)"
    >
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      leave-active-class="transition duration-100 ease-in"
      leave-to-class="opacity-0 -translate-y-1"
    >
      <div
        v-if="open"
        class="absolute right-0 top-full z-50 mt-2 w-80 max-w-[86vw] overflow-hidden border border-line bg-surface shadow-2xl"
      >
        <p v-if="loading" class="px-4 py-3 text-sm text-ink-3">搜索中…</p>
        <template v-else-if="items.length">
          <button
            v-for="x in items" :key="`${x.type}-${x.id}`"
            class="block w-full border-b border-line/60 px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-elevated"
            @click="go(x)"
          >
            <p class="flex items-center gap-2 text-sm font-medium">
              <span class="shrink-0 border border-line px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-3">{{ TYPE_LABEL[x.type] ?? x.type }}</span>
              <span class="truncate">{{ x.title }}</span>
            </p>
            <p v-if="x.summary" class="mt-1 truncate pl-1 text-xs text-ink-3">{{ x.summary }}</p>
          </button>
        </template>
        <p v-else-if="searched" class="px-4 py-3 text-sm text-ink-3">没有找到相关内容</p>
        <p v-else class="px-4 py-3 text-sm text-ink-3">输入 2 个字符以上开始搜索</p>
      </div>
    </Transition>
  </div>
</template>
