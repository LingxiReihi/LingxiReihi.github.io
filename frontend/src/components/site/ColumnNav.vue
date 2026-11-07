<script setup lang="ts">
/** 列表页左侧栏目目录栏：层级树（最多三级，「全部」+ 栏目逐级展开），图标统一用线性 folder。
 *  展开父栏目显示其直属文章 + 子栏目；点栏目名筛选主列表（含子孙内容），URL ?column= 同步。
 *  行尾数字是 total（自身 + 全部子孙），与点进去的列表条数同口径；本级直属数只有后台栏目页在用。
 *  移动端折叠为「栏目 ▾」开关，lg 起常驻侧栏。modelValue 为选中栏目 slug（null=全部）。 */
import { chatsApi, columnsApi, modelsApi, postsApi } from '@/api'
import type { ColumnOut, ContentOut, ContentType } from '@/api/types'
import { computed, onMounted, ref } from 'vue'

import LineIcon from '@/components/common/LineIcon.vue'

const props = defineProps<{ type: ContentType, modelValue: string | null }>()
const emit = defineEmits<{ 'update:modelValue': [string | null] }>()

const cols = ref<ColumnOut[]>([])
const loading = ref(true)
const mobileOpen = ref(false)
const expanded = ref<Set<string>>(new Set())
const articles = ref<Record<string, ContentOut[]>>({})
const fetching = ref<Set<string>>(new Set())

const kidsMap = computed(() => {
  const m = new Map<number | null, ColumnOut[]>()
  for (const c of cols.value) {
    const k = c.parent_id ?? null
    if (!m.has(k)) m.set(k, [])
    m.get(k)!.push(c)
  }
  return m
})

/** DFS 扁平化为带 depth 的行；子行仅在其父展开时出现 */
const rows = computed(() => {
  const out: { c: ColumnOut, depth: number }[] = []
  const walk = (list: ColumnOut[], depth: number) => {
    for (const c of list) {
      out.push({ c, depth })
      if (expanded.value.has(c.slug)) walk(kidsMap.value.get(c.id) ?? [], depth + 1)
    }
  }
  walk(kidsMap.value.get(null) ?? [], 0)
  return out
})

function hasKids(c: ColumnOut) {
  return (kidsMap.value.get(c.id) ?? []).length > 0
}

function pathOf(a: ContentOut) {
  return props.type === 'article' ? `/blog/${a.slug}`
    : props.type === 'model' ? `/models/${a.slug}` : `/chats/${a.id}`
}

async function load() {
  loading.value = true
  try {
    const d = await columnsApi.list(props.type)
    cols.value = d.items
  } catch { /* 目录栏非关键 */ } finally {
    loading.value = false
  }
}
onMounted(load)

async function toggle(c: ColumnOut) {
  const next = new Set(expanded.value)
  if (next.has(c.slug)) { next.delete(c.slug); expanded.value = next; return }
  next.add(c.slug); expanded.value = next
  if (articles.value[c.slug]) return
  fetching.value = new Set([...fetching.value, c.slug])
  try {
    if (props.type === 'chat') {
      const d = await chatsApi.list({ column: c.slug, column_direct: true, limit: 50 })
      articles.value = { ...articles.value, [c.slug]: d.items }
    } else {
      const api = props.type === 'article' ? postsApi.list : modelsApi.list
      const d = await api({ column: c.slug, column_direct: true, page_size: 50 })
      articles.value = { ...articles.value, [c.slug]: d.items }
    }
  } catch {
    articles.value = { ...articles.value, [c.slug]: [] }
  } finally {
    const f = new Set(fetching.value); f.delete(c.slug); fetching.value = f
  }
}

function select(slug: string | null) {
  emit('update:modelValue', slug)
  mobileOpen.value = false
}
</script>

<template>
  <!-- 左栏固定：内容在 main 里滚动时它不动（lg 以上）。
       栏目多到超过一屏时内部自己滚，避免底部被视口切掉。 -->
  <nav
    v-if="loading || cols.length"
    aria-label="栏目目录"
    class="self-start lg:sticky lg:top-4 lg:max-h-[calc(100svh-7rem)] lg:overflow-y-auto lg:overscroll-contain"
  >
    <!-- 移动端开关 -->
    <button
      class="flex w-full items-center justify-between border border-line bg-surface px-3 py-2 font-mono text-[11px] uppercase tracking-[0.12em] lg:hidden"
      :aria-expanded="mobileOpen"
      @click="mobileOpen = !mobileOpen"
    >
      <span class="inline-flex items-center gap-1.5">
        <LineIcon name="folder" :size="14" />
        <span>栏目{{ modelValue ? ` · ${cols.find(c => c.slug === modelValue)?.name ?? ''}` : '' }}</span>
      </span>
      <span class="text-ink-3">{{ mobileOpen ? '▴' : '▾' }}</span>
    </button>

    <div :class="mobileOpen ? 'mt-2' : 'hidden lg:block'">
      <p class="mb-2 hidden font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3 lg:block">// 栏目</p>
      <button
        class="flex w-full items-center gap-1.5 border border-transparent px-2 py-1.5 text-left text-[13px] transition-colors hover:border-line hover:text-ink"
        :class="!modelValue ? 'border-brand bg-brand text-[#04110f] font-medium' : 'text-ink-2'"
        @click="select(null)"
      >
        <LineIcon name="folder" :size="14" class="mr-1.5 inline align-[-2px]" />全部
      </button>

      <div v-if="loading" class="mt-1 px-2 text-xs text-ink-3">加载中…</div>
      <template v-for="{ c, depth } in rows" :key="c.slug">
        <div class="mt-0.5 flex items-center gap-0.5" :style="{ paddingLeft: `${depth * 14}px` }">
          <button
            class="h-6 w-6 shrink-0 text-xs text-ink-3 transition-transform hover:text-brand"
            :style="{ transform: expanded.has(c.slug) ? 'rotate(90deg)' : '' }"
            :aria-label="expanded.has(c.slug) ? '收起' : '展开' + c.name"
            @click="toggle(c)"
          >▸</button>
          <button
            class="flex min-w-0 flex-1 items-center justify-between gap-2 border border-transparent px-1.5 py-1 text-left text-[13px] transition-colors hover:border-line hover:text-ink"
            :class="modelValue === c.slug ? 'border-brand bg-brand text-[#04110f] font-medium' : 'text-ink-2'"
            @click="select(modelValue === c.slug ? null : c.slug)"
          >
            <span class="flex min-w-0 items-center gap-1.5">
              <LineIcon name="folder" :size="14" class="shrink-0 opacity-70" />
              <span class="truncate">{{ c.name }}</span>
            </span>
            <span class="shrink-0 font-mono text-[10px] tabular-nums text-ink-3">{{ c.total ?? c.count ?? 0 }}</span>
          </button>
        </div>
        <ul v-if="expanded.has(c.slug)" class="my-1 space-y-0.5" :style="{ paddingLeft: `${depth * 14 + 26}px` }">
          <li v-if="fetching.has(c.slug)" class="py-1 text-xs text-ink-3">加载中…</li>
          <template v-else>
            <li v-for="a in articles[c.slug]" :key="a.id">
              <RouterLink
                :to="pathOf(a)"
                class="block truncate px-1.5 py-1 text-xs text-ink-2 transition-colors hover:text-brand"
                :title="a.title"
              >{{ a.title }}</RouterLink>
            </li>
            <li v-if="!articles[c.slug]?.length && !hasKids(c)" class="py-1 text-xs text-ink-3">暂无内容</li>
          </template>
        </ul>
      </template>
    </div>
  </nav>
</template>
